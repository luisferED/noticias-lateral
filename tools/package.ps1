$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$outputDir = Join-Path $projectRoot 'dist'
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
$destination = Join-Path $outputDir ('el-deber-web-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.zip')
$entries = @(
    'server.py', 'config.py', 'index.html', 'assets',
    'requirements.txt', '.env.example',
    '.dockerignore', '.gitignore', 'Dockerfile', 'compose.yaml',
    'instalar.bat', 'iniciar.bat', 'README.md', 'README.txt',
    'tools/package.ps1', 'tests/test_service.py', 'tests/test_rotation.cjs'
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
