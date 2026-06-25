# İrtifa - tek komutla güncel .exe üretir.
#
# Akış: frontend build (Tailwind/Vite) -> PyInstaller onefile -> paketlenmiş smoke-test.
# Kullanım:
#   powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1 -Clean
#
# -Clean        : build/, dist/, Irtifa.spec silinir (sıfırdan build)
# -SkipFrontend : frontend build atlanır (dist güncel olduğundan eminsen)
param(
    [switch]$Clean,
    [switch]$SkipFrontend
)

# PyInstaller ve npm normal loglarini stderr'e yazar. PowerShell 5.1'de
# $ErrorActionPreference="Stop" iken bu satırlar ölümcül hata sayılır ve build
# daha ilk INFO satırında durur. Bu yüzden Continue + açık $LASTEXITCODE kontrolü.
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Assert-LastExit {
    param([string]$What)
    if ($LASTEXITCODE -ne 0) { throw "$What başarısız (exit $LASTEXITCODE)" }
}

# 1) Temizlik (isteğe bağlı)
if ($Clean) {
    Write-Host "== temizlik ==" -ForegroundColor Cyan
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue `
        (Join-Path $Root "build"), `
        (Join-Path $Root "dist"), `
        (Join-Path $Root "BalonManifesto.spec"), `
        (Join-Path $Root "Irtifa.spec")
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
    --name Irtifa `
    --icon "assets\irtifa.ico" `
    --add-data "data;data" `
    --add-data "frontend/dist;frontend/dist" `
    --add-data "app/templates;app/templates" `
    --collect-all anthropic `
    --collect-all webview `
    --collect-all pythonnet `
    --collect-all clr_loader `
    --collect-all proxy_tools `
    --collect-all bottle `
    --collect-all googleapiclient `
    --collect-all google_auth_httplib2 `
    --collect-all google.api_core `
    --collect-all google.cloud.vision `
    --collect-all argon2 `
    --collect-all reportlab `
    desktop_launcher.py
Assert-LastExit "PyInstaller"

$Exe = Join-Path $Root "dist\Irtifa.exe"
if (-not (Test-Path $Exe)) { throw "Exe oluşturulamadı: $Exe" }

# 4) Paketlenmiş exe smoke-test (bundle veri + frontend/dist + tüm importlar)
Write-Host "== smoke-test ==" -ForegroundColor Cyan
$Smoke = Start-Process -FilePath $Exe -ArgumentList "--smoke-test" -Wait -PassThru
if ($Smoke.ExitCode -ne 0) { throw "Smoke-test başarısız (exit $($Smoke.ExitCode))" }

Write-Host "OK -> $Exe" -ForegroundColor Green
