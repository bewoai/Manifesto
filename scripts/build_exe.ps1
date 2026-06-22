param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if ($Clean) {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue `
        (Join-Path $Root "build"), `
        (Join-Path $Root "dist"), `
        (Join-Path $Root "BalonManifesto.spec")
}

python -m PyInstaller `
    --noconfirm `
    --onefile `
    --windowed `
    --name BalonManifesto `
    --add-data "data;data" `
    --add-data "frontend/dist;frontend/dist" `
    --collect-all anthropic `
    --collect-all googleapiclient `
    --collect-all google_auth_httplib2 `
    --collect-all google.api_core `
    desktop_launcher.py

$Exe = Join-Path $Root "dist\BalonManifesto.exe"
if (!(Test-Path $Exe)) {
    throw "Exe was not created: $Exe"
}

$Smoke = Start-Process -FilePath $Exe -ArgumentList "--smoke-test" -Wait -PassThru
if ($Smoke.ExitCode -ne 0) {
    throw "Packaged smoke test failed with exit code $($Smoke.ExitCode)"
}

Write-Host "Built: $Exe"
