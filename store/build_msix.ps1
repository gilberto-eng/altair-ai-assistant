param(
    [string]$IdentityName = 'GilbertoDellecrode.AltairAssistant',
    [string]$Publisher = 'CN=7456B696-B094-46AF-AE42-85C96DD53848',
    [string]$PublisherDisplayName = "Gilberto Delle'crode",
    [string]$DisplayName = 'Altair',
    [string]$SupportEmail = '',
    [string]$PrivacyPolicyUrl = '',
    [string]$Version = '1.0.0.0',
    [string]$OutputDir = (Join-Path $PSScriptRoot 'output'),
    [string]$WindowsSdkRoot = ''
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$buildPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
$manifestPath = Join-Path $PSScriptRoot 'Altair.appxmanifest'
$assetsDir = Join-Path $PSScriptRoot 'Assets'
$workDir = Join-Path $PSScriptRoot '.tmp'
$packageRoot = Join-Path $workDir 'package'
$distDir = Join-Path $repoRoot 'dist'
$appDir = Join-Path $distDir 'Altair'
$internalDir = Join-Path $appDir '_internal'

if (-not (Test-Path $buildPython -PathType Leaf)) {
    throw "Python do ambiente .venv nao encontrado: $buildPython. Crie o ambiente e instale requirements.txt e PyInstaller."
}
if (-not $SupportEmail -or $SupportEmail -notmatch '^[^\s@]+@[^\s@]+\.[^\s@]+$') {
    throw 'Informe um email de suporte valido com -SupportEmail. Ele sera usado para receber denuncias de conteudo de IA.'
}
if (-not $PrivacyPolicyUrl -or -not $PrivacyPolicyUrl.StartsWith('https://', [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Informe a URL HTTPS da politica de privacidade publicada com -PrivacyPolicyUrl.'
}
if (-not (Test-Path (Join-Path $repoRoot 'requirements.txt') -PathType Leaf)) {
    throw 'requirements.txt nao encontrado.'
}
if (Test-Path $workDir) { Remove-Item -LiteralPath $workDir -Recurse -Force }
if (Test-Path $appDir) { Remove-Item -LiteralPath $appDir -Recurse -Force }
New-Item -ItemType Directory -Path $workDir -Force | Out-Null

Write-Output 'Gerando o executavel Altair com as dependencias Python...'
$pyinstallerArgs = @(
    '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed',
    '--name', 'Altair', '--distpath', $distDir, '--workpath', (Join-Path $workDir 'pyinstaller'),
    '--specpath', $workDir, '--contents-directory', '_internal',
    '--icon', (Join-Path $repoRoot 'assets\altair_icon.ico'),
    '--paths', (Join-Path $repoRoot 'src'),
    '--paths', (Join-Path $repoRoot 'src\altair'),
    '--paths', (Join-Path $repoRoot 'src\altair\core'),
    '--paths', (Join-Path $repoRoot 'src\altair\app'),
    '--add-data', "$(Join-Path $repoRoot 'assets');assets",
    '--add-data', "$(Join-Path $repoRoot 'scripts\whatsapp\teste.js');scripts\whatsapp"
)
foreach ($module in @(
    'customtkinter', 'PyQt5', 'pygame', 'matplotlib', 'cadquery', 'pyvista',
    'pyvistaqt', 'vtk', 'sounddevice', 'selenium', 'undetected_chromedriver',
    'fastapi', 'uvicorn', 'pydantic', 'sympy', 'numpy'
)) {
    $pyinstallerArgs += @('--collect-all', $module)
}
$pyinstallerArgs += (Join-Path $repoRoot 'run_altair.py')
& $buildPython @pyinstallerArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou com codigo $LASTEXITCODE." }

if (-not (Test-Path (Join-Path $internalDir 'assets') -PathType Container)) {
    throw 'Os recursos do Altair nao foram incluidos no executavel.'
}
$supportConfig = @{ email = $SupportEmail; privacy_url = $PrivacyPolicyUrl } | ConvertTo-Json
[System.IO.File]::WriteAllText(
    (Join-Path $internalDir 'support.json'),
    $supportConfig,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Output 'Baixando Node.js LTS e instalando dependencias WhatsApp na build...'
$releases = Invoke-RestMethod -Uri 'https://nodejs.org/dist/index.json'
$release = $releases | Where-Object { $_.lts -and $_.files -contains 'win-x64-zip' } | Select-Object -First 1
if (-not $release) { throw 'Nao foi encontrada uma versao LTS do Node.js para Windows x64.' }
$nodeZip = Join-Path $workDir "node-$($release.version)-win-x64.zip"
Invoke-WebRequest -Uri "https://nodejs.org/dist/$($release.version)/node-$($release.version)-win-x64.zip" -OutFile $nodeZip
$nodeExtract = Join-Path $workDir 'node-extract'
Expand-Archive -LiteralPath $nodeZip -DestinationPath $nodeExtract -Force
$nodeSource = Join-Path $nodeExtract "node-$($release.version)-win-x64"
$nodeDest = Join-Path $internalDir 'tools\node'
New-Item -ItemType Directory -Path $nodeDest -Force | Out-Null
Copy-Item -Path (Join-Path $nodeSource '*') -Destination $nodeDest -Recurse -Force

$packageJson = Join-Path $internalDir 'package.json'
$packageLock = Join-Path $internalDir 'package-lock.json'
Copy-Item -LiteralPath (Join-Path $repoRoot 'package.json') -Destination $packageJson -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'package-lock.json') -Destination $packageLock -Force
$nodeExe = Join-Path $nodeDest 'node.exe'
$npmCli = Join-Path $nodeDest 'node_modules\npm\bin\npm-cli.js'
if (-not (Test-Path $npmCli -PathType Leaf)) { throw 'npm-cli.js nao foi encontrado na distribuicao Node.js.' }
$browserCache = Join-Path $internalDir 'browser'
$env:PUPPETEER_CACHE_DIR = $browserCache
$env:PATH = "$nodeDest;$env:PATH"
Push-Location $internalDir
try {
    & $nodeExe $npmCli 'ci' '--omit=dev' '--no-audit' '--no-fund'
    if ($LASTEXITCODE -ne 0) { throw "npm ci falhou com codigo $LASTEXITCODE." }
} finally {
    Pop-Location
    Remove-Item Env:PUPPETEER_CACHE_DIR -ErrorAction SilentlyContinue
}
if (-not (Test-Path (Join-Path $browserCache 'chrome') -PathType Container)) {
    throw 'O Chromium do Puppeteer nao foi baixado para dentro do pacote.'
}

Write-Output 'Coletando avisos de licenca das dependencias incluídas...'
$noticesScript = Join-Path $PSScriptRoot 'generate_third_party_notices.py'
& $buildPython $noticesScript `
    --node-root (Join-Path $internalDir 'node_modules') `
    --output (Join-Path $internalDir 'THIRD_PARTY_NOTICES.txt')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar os avisos de licenca.' }

Write-Output 'Montando pacote MSIX...'
New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null
Copy-Item -Path (Join-Path $appDir '*') -Destination $packageRoot -Recurse -Force
Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $packageRoot 'AppxManifest.xml') -Force
Copy-Item -LiteralPath $assetsDir -Destination $packageRoot -Recurse -Force

[xml]$manifest = Get-Content -Raw -Path (Join-Path $packageRoot 'AppxManifest.xml')
$ns = [System.Xml.XmlNamespaceManager]::new($manifest.NameTable)
$ns.AddNamespace('a', 'http://schemas.microsoft.com/appx/manifest/foundation/windows10')
$ns.AddNamespace('uap', 'http://schemas.microsoft.com/appx/manifest/uap/windows10')
$identity = $manifest.SelectSingleNode('/a:Package/a:Identity', $ns)
$identity.SetAttribute('Name', $IdentityName)
$identity.SetAttribute('Publisher', $Publisher)
$identity.SetAttribute('Version', $Version)
$properties = $manifest.SelectSingleNode('/a:Package/a:Properties', $ns)
$properties.SelectSingleNode('a:DisplayName', $ns).InnerText = $DisplayName
$properties.SelectSingleNode('a:PublisherDisplayName', $ns).InnerText = $PublisherDisplayName
$application = $manifest.SelectSingleNode('/a:Package/a:Applications/a:Application', $ns)
$application.SetAttribute('Executable', 'Altair.exe')
$visualElements = $manifest.SelectSingleNode('/a:Package/a:Applications/a:Application/uap:VisualElements', $ns)
$visualElements.SetAttribute('DisplayName', $DisplayName)
$manifest.Save((Join-Path $packageRoot 'AppxManifest.xml'))

$makeAppx = Get-Command makeappx.exe -ErrorAction SilentlyContinue
if (-not $makeAppx -and $WindowsSdkRoot) {
    $candidate = Join-Path $WindowsSdkRoot 'makeappx.exe'
    if (Test-Path $candidate) { $makeAppx = $candidate }
}
if (-not $makeAppx) {
    $sdkCandidates = @(
        'C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\makeappx.exe',
        'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\makeappx.exe',
        'C:\Program Files (x86)\Windows Kits\10\bin\x64\makeappx.exe'
    )
    foreach ($candidate in $sdkCandidates) {
        if (Test-Path $candidate) { $makeAppx = $candidate; break }
    }
}
if (-not $makeAppx) { throw 'makeappx.exe nao encontrado. Instale o Windows 10/11 SDK.' }

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$msixPath = Join-Path $OutputDir "$DisplayName.msix"
& $makeAppx Package /d $packageRoot /p $msixPath /o
if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar o pacote MSIX.' }

Write-Output "MSIX gerado em: $msixPath"
Write-Output 'A Microsoft assina o pacote apos a certificacao. Reserve o nome no Partner Center e use exatamente o IdentityName e Publisher da identidade reservada.'
