$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$outputDir = Join-Path $projectRoot 'dist'
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
$destination = Join-Path $outputDir ('el-deber-deploy-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.zip')
$entries = @(
    'server.py', 'config.py', 'ndi_sender.py', 'index.html', 'assets',
    'requirements.txt', 'requirements-ndi.txt', '.env.example',
    'ndi_status.py', 'ndi_service.py', 'Dockerfile.ndi', 'Dockerfile.ndi.dockerignore',
    'DESPLIEGUE_NDI_LINUX.md',
    '.dockerignore', '.gitignore', 'Dockerfile', 'compose.yaml',
    'instalar.bat', 'iniciar.bat', 'iniciar_ndi.bat', 'README.md', 'README.txt',
    'tools', 'tests'
)
$sources = $entries | ForEach-Object { Join-Path $projectRoot $_ }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::Open($destination, 'Create')
try {
    foreach ($source in $sources) {
        $files = if (Test-Path -LiteralPath $source -PathType Container) {
            Get-ChildItem -LiteralPath $source -Recurse -File | Where-Object { $_.FullName -notmatch '[\\/]__pycache__[\\/]' }
        } else { Get-Item -LiteralPath $source }
        foreach ($file in $files) {
            $relative = $file.FullName.Substring($projectRoot.Length + 1).Replace('\', '/')
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $file.FullName, $relative) | Out-Null
        }
    }
} finally { $archive.Dispose() }
Get-Item -LiteralPath $destination | Select-Object FullName, Length
