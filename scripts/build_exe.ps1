# Balon Manifesto - tek komutla guncel .exe uretir.
#
# Akis: frontend build (Tailwind/Vite) -> PyInstaller onefile -> paketlenmis smoke-test.
# Kullanim:
#   powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1 -Clean
#
# -Clean        : build/, dist/, BalonManifesto.spec silinir (sifirdan build)
# -SkipFrontend : frontend build atlanir (dist guncel oldugundan eminsen)
param(
    [switch]$Clean,
    [switch]$SkipFrontend
)

# PyInstaller ve npm normal loglarini stderr'e yazar. PowerShell 5.1'de
# $ErrorActionPreference="Stop" iken bu satirlar olumcul hata sayilir ve build
# daha ilk INFO satirinda durur. Bu yuzden Continue + acik $LASTEXITCODE kontrolu.
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Assert-LastExit {
    param([string]$What)
    if ($LASTEXITCODE -ne 0) { throw "$What basarisiz (exit $LASTEXITCODE)" }
}

# 1) Temizlik (istege bagli)
if ($Clean) {
    Write-Host "== temizlik ==" -ForegroundColor Cyan
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue `
        (Join-Path $Root "build"), `
        (Join-Path $Root "dist"), `
        (Join-Path $Root "BalonManifesto.spec")
}

# 2) Frontend build (Tailwind/Vite) -> frontend/dist
#    .exe bu klasoru oldugu gibi paketler; bayat kalirsa eski arayuz gider.
if (-not $SkipFrontend) {
    Push-Location (Join-Path $Root "frontend")
    try {
        Write-Host "== npm install ==" -ForegroundColor Cyan
        npm install
        Assert-LastExit "npm install"

        Write-Host "== npm run build ==" -ForegroundColor Cyan
        npm run build
        Assert-LastExit "npm run build"
    } finally {
        Pop-Location
    }
} else {
    Write-Host "== frontend build atlandi (-SkipFrontend) ==" -ForegroundColor Yellow
}

# 3) Exe paketleme (PyInstaller, tek dosya, konsolsuz)
Write-Host "== PyInstaller ==" -ForegroundColor Cyan
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
Assert-LastExit "PyInstaller"

$Exe = Join-Path $Root "dist\BalonManifesto.exe"
if (-not (Test-Path $Exe)) { throw "Exe olusturulamadi: $Exe" }

# 4) Paketlenmis exe smoke-test (bundle veri + frontend/dist + tum importlar)
Write-Host "== smoke-test ==" -ForegroundColor Cyan
$Smoke = Start-Process -FilePath $Exe -ArgumentList "--smoke-test" -Wait -PassThru
if ($Smoke.ExitCode -ne 0) { throw "Smoke-test basarisiz (exit $($Smoke.ExitCode))" }

Write-Host "OK -> $Exe" -ForegroundColor Green
