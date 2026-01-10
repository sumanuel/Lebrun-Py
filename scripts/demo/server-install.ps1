param(
  [string]$ProjectRoot = "$(Resolve-Path (Join-Path $PSScriptRoot '..\..'))"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "ProjectRoot: $ProjectRoot"
Set-Location $ProjectRoot

$VenvDir = Join-Path $ProjectRoot ".venv"
$Py = Join-Path $VenvDir "Scripts\python.exe"
$Pip = Join-Path $VenvDir "Scripts\pip.exe"

if (-not (Test-Path $Py)) {
  Write-Host "Creando virtualenv en $VenvDir"
  py -3 -m venv $VenvDir
}

Write-Host "Instalando dependencias del servidor"
& $Pip install -r (Join-Path $ProjectRoot "requirements.txt")

Write-Host "OK: entorno listo"