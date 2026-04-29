param(
    [string]$OutputDir = "dist",
    [string]$BundleName = "sit-auto-target-toolkit.zip"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
$bundleItems = @("Toolkit")

foreach ($item in $bundleItems) {
    $path = Join-Path $root $item
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required path is missing: $path"
    }
}

$dist = Join-Path $root $OutputDir
New-Item -ItemType Directory -Path $dist -Force | Out-Null

$sourcePaths = $bundleItems | ForEach-Object { Join-Path $root $_ }

$bundlePath = Join-Path $dist $BundleName
try {
    Compress-Archive -Path $sourcePaths -DestinationPath $bundlePath -Force
} catch {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $fallbackName = [System.IO.Path]::GetFileNameWithoutExtension($BundleName) + "-$stamp.zip"
    $bundlePath = Join-Path $dist $fallbackName
    Compress-Archive -Path $sourcePaths -DestinationPath $bundlePath -Force
}

Write-Host "Target bundle created:"
Write-Host "  $bundlePath"
Write-Host ""
Write-Host "Copy this zip to the target server only if you need manual upload."
Write-Host "Normal run-suite execution can upload Toolkit, Toolkit/UserFiles, and Toolkit/Settings automatically."
