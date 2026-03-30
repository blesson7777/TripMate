Param(
    [ValidateSet("all", "driver", "transporter")]
    [string]$Target = "all"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$keyProps = Join-Path $projectRoot "android\key.properties"
if (-not (Test-Path $keyProps)) {
    throw "Missing android/key.properties. Copy android/key.properties.example and set your Play upload keystore values first."
}

flutter pub get

if ($Target -in @("all", "driver")) {
    flutter build appbundle `
        --release `
        --flavor driverPlay `
        -t lib/main_driver.dart `
        --dart-define=APP_DISTRIBUTION_CHANNEL=play
}

if ($Target -in @("all", "transporter")) {
    flutter build appbundle `
        --release `
        --flavor transporterPlay `
        -t lib/main_transporter.dart `
        --dart-define=APP_DISTRIBUTION_CHANNEL=play
}

Write-Host ""
Write-Host "Play Store bundles are ready:"
Write-Host "  Driver      -> build\app\outputs\bundle\driverPlayRelease\app-driverPlay-release.aab"
Write-Host "  Transporter -> build\app\outputs\bundle\transporterPlayRelease\app-transporterPlay-release.aab"
