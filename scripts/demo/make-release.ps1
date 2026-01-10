param(
  [string]$Version = "v0.0.0-demo",
  [string]$OutDir = "$(Resolve-Path (Join-Path $PSScriptRoot '..\..'))"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$ReleaseDir = Join-Path $ProjectRoot "release"
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

$ZipPath = Join-Path $ReleaseDir ("Lebrun-Py_" + $Version + ".zip")
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }

# Copiamos todo el proyecto excepto carpetas pesadas / locales
$Temp = Join-Path $ReleaseDir ("_tmp_" + $Version)
if (Test-Path $Temp) { Remove-Item -Recurse -Force $Temp }
New-Item -ItemType Directory -Force -Path $Temp | Out-Null

$exclude = @(
  "\\.venv\\",
  "\\__pycache__\\",
  "\\data\\",
  "\\release\\",
  "\\.git\\",
  "\\.pytest_cache\\"
)

Write-Host "Copiando archivos a staging: $Temp"
Get-ChildItem -Path $ProjectRoot -Recurse -File | ForEach-Object {
  $full = $_.FullName
  $rel = $full.Substring($ProjectRoot.Path.Length).TrimStart('\\')

  foreach ($ex in $exclude) {
    if ($full -match $ex) { return }
  }

  # No enviar secretos
  if ($rel -ieq ".env") { return }

  $dest = Join-Path $Temp $rel
  $destDir = Split-Path -Parent $dest
  New-Item -ItemType Directory -Force -Path $destDir | Out-Null
  Copy-Item -Force $full $dest
}

Write-Host "Creando zip: $ZipPath"
Compress-Archive -Path (Join-Path $Temp "*") -DestinationPath $ZipPath -Force

Remove-Item -Recurse -Force $Temp

Write-Host "OK: $ZipPath"