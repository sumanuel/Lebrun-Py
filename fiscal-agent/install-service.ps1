param(
  [string]$ServiceName = "LebrunFiscalAgent",
  [string]$BaseUrl = "http://127.0.0.1:8000",
  [string]$Token = "",
  [string]$Caja = "",
  [string]$NssmPath = "",
  [switch]$Uninstall
)

# Requiere: ejecutar PowerShell como Administrador
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Error "Ejecute este script como Administrador."
  exit 1
}

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$AgentPy = Join-Path $Here "agent.py"
$VenvDir = Join-Path $Here ".venv"
$Py = Join-Path $VenvDir "Scripts\python.exe"
$Pip = Join-Path $VenvDir "Scripts\pip.exe"
$Req = Join-Path $Here "requirements.txt"

function Find-Nssm {
  if ($NssmPath -and (Test-Path $NssmPath)) { return $NssmPath }
  $local = Join-Path $Here "nssm.exe"
  if (Test-Path $local) { return $local }
  $cmd = Get-Command nssm -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return ""
}

$Nssm = Find-Nssm
if (-not $Nssm) {
  Write-Error "No se encontró nssm.exe. Opciones: (1) ponga nssm.exe en esta carpeta (fiscal-agent), (2) instale NSSM y agregue al PATH, o (3) pase -NssmPath C:\ruta\nssm.exe"
  exit 1
}

if ($Uninstall) {
  & $Nssm stop $ServiceName | Out-Null
  & $Nssm remove $ServiceName confirm | Out-Null
  Write-Host "Servicio removido: $ServiceName"
  exit 0
}

if (-not (Test-Path $AgentPy)) {
  Write-Error "No existe agent.py en $Here"
  exit 1
}

if (-not $Token) {
  Write-Error "Debe indicar -Token (mismo valor que LEBRUN_FISCAL_AGENT_TOKEN del servidor)."
  exit 1
}

# Crear venv si no existe
if (-not (Test-Path $Py)) {
  Write-Host "Creando virtualenv en $VenvDir"
  py -3 -m venv $VenvDir
}

Write-Host "Instalando dependencias"
& $Pip install -r $Req

$LogDir = Join-Path $Here "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stdout = Join-Path $LogDir "stdout.log"
$Stderr = Join-Path $LogDir "stderr.log"

# Instalar/actualizar servicio
Write-Host "Instalando servicio $ServiceName con NSSM"
& $Nssm install $ServiceName $Py $AgentPy | Out-Null

# Variables de entorno del servicio
& $Nssm set $ServiceName AppEnvironmentExtra "LEBRUN_SERVER_URL=$BaseUrl" | Out-Null
& $Nssm set $ServiceName AppEnvironmentExtra "LEBRUN_FISCAL_AGENT_TOKEN=$Token" | Out-Null
if ($Caja) {
  & $Nssm set $ServiceName AppEnvironmentExtra "LEBRUN_FISCAL_CAJA=$Caja" | Out-Null
}
& $Nssm set $ServiceName AppEnvironmentExtra "LEBRUN_FISCAL_POLL_SECONDS=2" | Out-Null

# Logs
& $Nssm set $ServiceName AppStdout $Stdout | Out-Null
& $Nssm set $ServiceName AppStderr $Stderr | Out-Null
& $Nssm set $ServiceName AppRotateFiles 1 | Out-Null
& $Nssm set $ServiceName AppRotateOnline 1 | Out-Null
& $Nssm set $ServiceName AppRotateBytes 10485760 | Out-Null
& $Nssm set $ServiceName AppRotateSeconds 86400 | Out-Null

# Directorio de trabajo
& $Nssm set $ServiceName AppDirectory $Here | Out-Null

# Arranque
& $Nssm set $ServiceName Start SERVICE_AUTO_START | Out-Null

Write-Host "Iniciando servicio"
& $Nssm start $ServiceName | Out-Null

Write-Host "OK. Servicio instalado y ejecutándose."
Write-Host "Stdout: $Stdout"
Write-Host "Stderr: $Stderr"
