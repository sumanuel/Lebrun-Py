param(
  [string]$ServerUrl = "http://127.0.0.1:8000",
  [string]$Token = "change-me",
  [string]$Caja = "TEST",
  [string]$InvoiceId = "",
  [string]$Tipdoc = "FAV",
  [string]$DocNumero = "",
  [string]$JobsPath = "./data/fiscal_jobs.json",
  [switch]$OnlyEnqueue,
  [switch]$SkipClaim
)

$ErrorActionPreference = "Stop"

function Get-UtcIso {
  return (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
}

function Read-JsonFile([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    return @()
  }
  $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
  if ([string]::IsNullOrWhiteSpace($raw)) {
    return @()
  }
  $obj = $raw | ConvertFrom-Json
  if ($null -eq $obj) { return @() }
  if ($obj -is [System.Array]) { return $obj }
  return @($obj)
}

function Write-JsonFile([string]$Path, $Object) {
  $dir = Split-Path -Parent $Path
  if ($dir -and -not (Test-Path -LiteralPath $dir)) {
    New-Item -ItemType Directory -Path $dir | Out-Null
  }
  # Importante: Windows PowerShell 5.1 escribe UTF-8 con BOM por defecto,
  # y eso rompe json.loads() del backend. Guardamos UTF-8 SIN BOM.
  $json = ($Object | ConvertTo-Json -Depth 50)
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText((Resolve-Path -LiteralPath $Path), $json, $utf8NoBom)
}

function Enqueue-Job {
  param(
    [string]$JobsPath,
    [string]$Caja,
    [string]$InvoiceId,
    [string]$Tipdoc,
    [string]$DocNumero
  )

  $rows = Read-JsonFile -Path $JobsPath
  $id = [Guid]::NewGuid().ToString("N")

  $payload = @{
    requested_by = "stub"
    invoice_id   = $InvoiceId
    tipdoc       = ($Tipdoc.Trim().ToUpper())
    doc_numero   = $DocNumero
    table        = "admdoccli"
  }

  $job = [ordered]@{
    id         = $id
    created_at = (Get-UtcIso)
    status     = "pending"
    caja       = $Caja
    job_type   = "PRINT_DOC"
    payload    = $payload
    result     = $null
    error      = $null
  }

  $new = @($rows) + @($job)
  Write-JsonFile -Path $JobsPath -Object $new
  return $id
}

function Invoke-Next {
  param([string]$ServerUrl, [string]$Token, [string]$Caja)
  $headers = @{ "X-Agent-Token" = $Token }
  try {
    $resp = Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 -Headers $headers ("{0}/api/fiscal/next?caja={1}" -f $ServerUrl.TrimEnd('/'), [Uri]::EscapeDataString($Caja))
    if ($resp.StatusCode -eq 204) { return $null }
    return ($resp.Content | ConvertFrom-Json)
  } catch {
    throw "No se pudo llamar /api/fiscal/next: $($_.Exception.Message)"
  }
}

function Invoke-Complete {
  param(
    [string]$ServerUrl,
    [string]$Token,
    [string]$JobId,
    [hashtable]$Result
  )
  $headers = @{ "X-Agent-Token" = $Token }
  $url = "{0}/api/fiscal/{1}/complete?ok=true" -f $ServerUrl.TrimEnd('/'), $JobId
  $json = ($Result | ConvertTo-Json -Depth 20)
  try {
    return Invoke-RestMethod -Method Post -TimeoutSec 15 -Headers $headers -ContentType "application/json" -Body $json $url
  } catch {
    throw "No se pudo completar job: $($_.Exception.Message)"
  }
}

# --- Main ---
if ([string]::IsNullOrWhiteSpace($Tipdoc)) { $Tipdoc = "FAV" }
$Tipdoc = $Tipdoc.Trim().ToUpper()
if (@("FAV","DEV","NDE") -notcontains $Tipdoc) { $Tipdoc = "FAV" }

if (-not $InvoiceId) {
  Write-Host "Nota: InvoiceId vacío. Esto solo valida cola/API; el agente real requiere snapshot." -ForegroundColor Yellow
}

Write-Host "Encolando PRINT_DOC en $JobsPath ..." -ForegroundColor Cyan
$jobId = Enqueue-Job -JobsPath $JobsPath -Caja $Caja -InvoiceId $InvoiceId -Tipdoc $Tipdoc -DocNumero $DocNumero
Write-Host "Job encolado: $jobId (caja=$Caja tipdoc=$Tipdoc)" -ForegroundColor Green

if ($OnlyEnqueue) {
  exit 0
}

if ($SkipClaim) {
  Write-Host "Saltando claim/complete (SkipClaim)." -ForegroundColor Yellow
  exit 0
}

Write-Host "Reclamando job vía $ServerUrl/api/fiscal/next ..." -ForegroundColor Cyan
$job = Invoke-Next -ServerUrl $ServerUrl -Token $Token -Caja $Caja
if ($null -eq $job) {
  throw "El servidor devolvió 204 (no hay job). Verifica que está apuntando al mismo JobsPath y que caja coincide."
}

if ($job.id -ne $jobId) {
  Write-Host "Advertencia: se reclamó otro job (id=$($job.id)) en vez de $jobId. Igual continúo completando el reclamado." -ForegroundColor Yellow
}

# Result simulado (como si el agente imprimió y leyó S1)
$rand = Get-Random -Minimum 10000000 -Maximum 99999999
$result = @{
  printed = $true
  invoice_id = $InvoiceId
  tipdoc = $Tipdoc
  doc_numero = $DocNumero
  registered_machine_number = "STUBMACH"
  last_invoice_number = "$rand"
  last_credit_note_number = "$rand"
  last_debit_note_number = "$rand"
  daily_closure_counter = "0"
}

Write-Host "Completando job vía /complete (result simulado) ..." -ForegroundColor Cyan
$updated = Invoke-Complete -ServerUrl $ServerUrl -Token $Token -JobId $job.id -Result $result
Write-Host "Completado: id=$($updated.id) status=$($updated.status)" -ForegroundColor Green

# Mostrar lo que quedó grabado en el archivo (incluye db_update_ok/db_update_error si aplica)
$rows2 = Read-JsonFile -Path $JobsPath
$found = $rows2 | Where-Object { $_.id -eq $job.id } | Select-Object -First 1
if ($null -ne $found) {
  Write-Host "Resultado almacenado en cola:" -ForegroundColor Cyan
  $found.result | ConvertTo-Json -Depth 20
}
