$ErrorActionPreference = "Stop"
$APP_NAME   = "CloudDownloader"
$RCLONE_URL = "https://downloads.rclone.org/rclone-current-windows-amd64.zip"
$RCLONE_ZIP = "rclone-windows.zip"
$RCLONE_EXE = "rclone.exe"

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  Cloud Downloader - Windows Build"    -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check Python
Write-Host "[1/4] Verificando Python..." -ForegroundColor Yellow
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] Python no encontrado. Instalalo desde https://python.org" -ForegroundColor Red
    exit 1
}
$pyVer = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Host "    Python $pyVer OK" -ForegroundColor Green
python -m pip install --upgrade --quiet pyinstaller customtkinter
Write-Host "    PyInstaller OK" -ForegroundColor Green

# 2. Download rclone
Write-Host ""
Write-Host "[2/4] Preparando rclone..." -ForegroundColor Yellow
if (Test-Path $RCLONE_EXE) {
    Write-Host "    rclone.exe ya existe, saltando descarga." -ForegroundColor Green
} else {
    Write-Host "    Descargando rclone para Windows..."
    Invoke-WebRequest -Uri $RCLONE_URL -OutFile $RCLONE_ZIP -UseBasicParsing
    Write-Host "    Extrayendo rclone.exe..."
    Expand-Archive -Path $RCLONE_ZIP -DestinationPath "rclone_tmp" -Force
    Get-ChildItem -Path "rclone_tmp" -Filter "rclone.exe" -Recurse `
        | Select-Object -First 1 `
        | Copy-Item -Destination "."
    Remove-Item "rclone_tmp" -Recurse -Force
    Remove-Item $RCLONE_ZIP -Force
    if (-not (Test-Path $RCLONE_EXE)) {
        Write-Host "[ERROR] No se pudo extraer rclone.exe" -ForegroundColor Red
        exit 1
    }
    Write-Host "    rclone.exe OK" -ForegroundColor Green
}

# 3. Build with PyInstaller
Write-Host ""
Write-Host "[3/4] Empaquetando con PyInstaller..." -ForegroundColor Yellow
python -m PyInstaller drive_downloader.spec --clean --noconfirm

$exePath = "dist\$APP_NAME.exe"
if (-not (Test-Path $exePath)) {
    Write-Host "[ERROR] Build fallido: $exePath no encontrado." -ForegroundColor Red
    exit 1
}
$exeSize = [math]::Round((Get-Item $exePath).Length / 1MB, 1)
Write-Host "    $exePath ($exeSize MB) OK" -ForegroundColor Green

# 4. Inno Setup (optional)
Write-Host ""
Write-Host "[4/4] Buscando Inno Setup..." -ForegroundColor Yellow
$innoCompiler = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($innoCompiler) {
    Write-Host "    Encontrado: $innoCompiler"
    New-Item -ItemType Directory -Path "dist\installer" -Force | Out-Null
    & $innoCompiler "installer\installer.iss"
    $setupPath = "dist\installer\${APP_NAME}_Setup.exe"
    if (Test-Path $setupPath) {
        $sz = [math]::Round((Get-Item $setupPath).Length / 1MB, 1)
        Write-Host "    Installer: $setupPath ($sz MB)" -ForegroundColor Green
    }
} else {
    Write-Host "    Inno Setup no encontrado - se omite el instalador." -ForegroundColor DarkGray
    Write-Host "    Descargalo de: https://jrsoftware.org/isinfo.php" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "=============================" -ForegroundColor Cyan
Write-Host "  Build completado"             -ForegroundColor Cyan
Write-Host "=============================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Ejecutable: dist\$APP_NAME.exe"
if ($innoCompiler -and (Test-Path "dist\installer\${APP_NAME}_Setup.exe")) {
    Write-Host "  Installer:  dist\installer\${APP_NAME}_Setup.exe"
}
Write-Host ""
Write-Host "NOTA: Al abrir la app por primera vez se pedira conectar Google Drive."
Write-Host "Solo hay que hacerlo una vez."
Write-Host ""