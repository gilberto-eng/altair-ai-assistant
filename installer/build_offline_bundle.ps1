$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$OfflineRoot = Join-Path $PSScriptRoot 'offline_bundle'
$WheelDir = Join-Path $OfflineRoot 'wheels'
$PythonDir = Join-Path $OfflineRoot 'python'

New-Item -ItemType Directory -Path $WheelDir -Force | Out-Null
New-Item -ItemType Directory -Path $PythonDir -Force | Out-Null

# Limpa bundle anterior para garantir que o pacote esteja consistente.
Get-ChildItem -Path $WheelDir -Force | Remove-Item -Recurse -Force

$BuildPython = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $BuildPython)) {
    $BuildPython = (Get-Command python -ErrorAction Stop).Source
}

Write-Output 'Baixando rodas da biblioteca local...'
& $BuildPython -m pip download -r (Join-Path $Root 'requirements.txt') --dest $WheelDir --only-binary=:all:
if ($LASTEXITCODE -ne 0) {
    throw 'Falha ao baixar as dependencias para a build offline.'
}

$PythonUrl = 'https://www.python.org/ftp/python/3.10.0/python-3.10.0-amd64.exe'
$PythonLocal = Join-Path $PythonDir 'python-3.10.0-amd64.exe'
if (-not (Test-Path $PythonLocal)) {
    Write-Output "Baixando Python 3.10.0 para o bundle offline: $PythonUrl"
    Invoke-WebRequest -Uri $PythonUrl -OutFile $PythonLocal
}

Write-Output 'Bundle offline pronto:'
Write-Output $OfflineRoot
