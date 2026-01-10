param(
  [string]$ProjectRoot = "$(Resolve-Path (Join-Path $PSScriptRoot '..\..'))"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Set-Location $ProjectRoot

$VenvDir = Join-Path $ProjectRoot ".venv"
$Py = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $Py)) {
  Write-Error "No existe $Py. Ejecute primero .\scripts\demo\server-install.ps1"
  exit 1
}

$HostAddr = if ($env:LEBRUN_UVICORN_HOST) { $env:LEBRUN_UVICORN_HOST } else { "127.0.0.1" }
$Port = if ($env:LEBRUN_UVICORN_PORT) { $env:LEBRUN_UVICORN_PORT } else { "8000" }

Write-Host "Iniciando servidor en http://$HostAddr`:$Port"
Write-Host "(Lee .env automaticamente)"

& $Py -m uvicorn app.main:app --host $HostAddr --port $Port --reload