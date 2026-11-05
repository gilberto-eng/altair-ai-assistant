$ErrorActionPreference = 'Stop'

Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location ..

# Build AltairInstaller.exe (standalone) via PyInstaller.
#
# Prereqs (na maquina que vai buildar):
#   1) Ambiente .venv criado na raiz do repositorio
#   2) PyInstaller instalado nesse ambiente
#   3) Executar este script a partir de uma copia completa do repositorio
#
# Output:
#   dist/AltairInstaller.exe

$BuildRoot = Join-Path $PSScriptRoot '.build'
$PayloadRoot = Join-Path $BuildRoot 'payload'
$PayloadZip = Join-Path $BuildRoot 'payload.zip'

if (Test-Path $BuildRoot) { Remove-Item -Recurse -Force $BuildRoot }
New-Item -ItemType Directory -Path $PayloadRoot -Force | Out-Null

foreach ($name in @('src', 'scripts', 'assets', 'data', 'json', 'tools')) {
  $source = Join-Path (Get-Location) $name
  if (Test-Path $source) {
    Copy-Item -Path $source -Destination $PayloadRoot -Recurse -Force
  }
}

foreach ($name in @(
    'run_altair.py',
    'run_macro.py',
    'requirements.txt',
    'package.json',
    'package-lock.json',
    'macro.json',
    'Modelfile',
    '.env.example'
)) {
  $source = Join-Path (Get-Location) $name
  if (Test-Path $source -PathType Leaf) {
    Copy-Item -Path $source -Destination $PayloadRoot -Force
  }
}

$OfflineBundle = Join-Path (Get-Location) 'installer/offline_bundle'
if (Test-Path $OfflineBundle) {
  Copy-Item -Path $OfflineBundle -Destination $PayloadRoot -Recurse -Force
}

Get-ChildItem -Path $PayloadRoot -Recurse -Force -Directory |
  Where-Object { $_.Name -in @('__pycache__', '.pytest_cache') } |
  Remove-Item -Recurse -Force
Get-ChildItem -Path $PayloadRoot -Recurse -Force -File |
  Where-Object { $_.Name -like '*.pyc' -or $_.Name -like '*.pyo' -or $_.Name -match '\.bak\d*$|^_write_(probe|test)\.txt$' } |
  Remove-Item -Force

if (-not (Test-Path (Join-Path $PayloadRoot 'src/altair/main.py'))) {
  throw 'Payload incompleto: src/altair/main.py nao encontrado.'
}

Write-Output 'Gerando payload limpo sem configs locais...'
Compress-Archive -Path (Join-Path $PayloadRoot '*') -DestinationPath $PayloadZip -Force

$PiperModel = Join-Path (Get-Location) 'assets/piper/voices/pt_BR-faber-medium.onnx'
$PiperExecutable = Join-Path (Get-Location) 'assets/piper/piper.exe'
if (-not (Test-Path $PiperModel) -or -not (Test-Path $PiperExecutable)) {
  Write-Warning 'Assets do Piper ausentes; a voz local nao funcionara ate serem incluidos ou configurado outro provedor de voz.'
}

Write-Output 'Buildando AltairInstaller.exe...'
$BuildPython = Join-Path (Get-Location) '.venv/Scripts/python.exe'
if (-not (Test-Path $BuildPython)) {
  $BuildPython = (Get-Command python -ErrorAction Stop).Source
}
& $BuildPython -m PyInstaller --noconfirm --clean `
  --name AltairInstaller `
  --onefile `
  --noconsole `
  --icon "$PSScriptRoot/../assets/altair_icon.ico" `
  --add-data "$PayloadZip;." `
  installer/altair_installer.py
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller falhou com codigo $LASTEXITCODE."
}

Write-Output 'OK: built dist/AltairInstaller.exe'
