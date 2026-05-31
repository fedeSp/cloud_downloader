#!/usr/bin/env bash
# =============================================================================
#  Build script — Cloud Downloader para macOS
#  Descarga rclone, empaqueta la app con PyInstaller (.app) y genera un .dmg
#
#  Requisitos: Python 3.8+  (brew install python)
#              pip           (incluido con Python)
#  Opcional:   UPX           (brew install upx) — comprime el binario
#
#  Uso:
#    chmod +x build_mac.sh
#    ./build_mac.sh
# =============================================================================

set -euo pipefail

APP_NAME="CloudDownloader"
ARCH=$(uname -m)   # x86_64 o arm64

if [[ "$ARCH" == "arm64" ]]; then
    RCLONE_URL="https://downloads.rclone.org/rclone-current-osx-arm64.zip"
else
    RCLONE_URL="https://downloads.rclone.org/rclone-current-osx-amd64.zip"
fi

echo ""
echo "======================================"
echo "  Cloud Downloader — macOS Build"
echo "  Arquitectura: $ARCH"
echo "======================================"
echo ""

# ── 1. Verificar Python ───────────────────────────────────────────────────────
echo "[1/5] Verificando Python..."

if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python 3.8+ no encontrado."
    echo "Instalalo con: brew install python"
    exit 1
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)

if [[ "$PY_MAJOR" -lt 3 || ("$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 8) ]]; then
    echo "[ERROR] Se requiere Python 3.8+. Versión encontrada: $PY_VER"
    exit 1
fi
echo "    Python $PY_VER OK"

# Verificar tkinter (puede faltar en Python de Homebrew)
if ! python3 -c "import tkinter" 2>/dev/null; then
    echo ""
    echo "[ERROR] tkinter no disponible en Python $PY_VER."
    echo "En macOS con Homebrew: brew install python-tk@${PY_MAJOR}.${PY_MINOR}"
    echo "O instalá Python desde https://python.org (incluye tkinter)"
    exit 1
fi
echo "    tkinter OK"

# Instalar / actualizar PyInstaller
python3 -m pip install --upgrade --quiet pyinstaller
echo "    PyInstaller OK"

# ── 2. Descargar rclone ───────────────────────────────────────────────────────
echo ""
echo "[2/5] Preparando rclone..."

if [[ -f "rclone" ]]; then
    echo "    rclone ya existe, saltando descarga."
else
    echo "    Descargando rclone para macOS ($ARCH)..."
    curl -fsSL "$RCLONE_URL" -o rclone.zip
    unzip -q -j rclone.zip "*/rclone" -d .
    chmod +x rclone
    rm rclone.zip

    if [[ ! -f "rclone" ]]; then
        echo "[ERROR] No se pudo extraer el binario rclone."
        exit 1
    fi
    echo "    rclone OK"
fi

# ── 3. Build con PyInstaller ──────────────────────────────────────────────────
echo ""
echo "[3/5] Empaquetando con PyInstaller (.app)..."

python3 -m PyInstaller drive_downloader.spec --clean --noconfirm

APP_PATH="dist/${APP_NAME}.app"
if [[ ! -d "$APP_PATH" ]]; then
    echo "[ERROR] Build fallido: $APP_PATH no encontrado."
    exit 1
fi
echo "    $APP_PATH OK"

# Quitar atributos de cuarentena para que rclone pueda ejecutarse dentro del bundle
echo ""
echo "[4/5] Eliminando cuarentena del bundle (xattr)..."
xattr -rd com.apple.quarantine "$APP_PATH" 2>/dev/null || true
echo "    OK"

# ── 4. Crear .dmg ────────────────────────────────────────────────────────────
echo ""
echo "[5/5] Generando .dmg..."

DMG_TMP="dist/dmg_tmp"
DMG_OUT="dist/${APP_NAME}.dmg"

rm -rf "$DMG_TMP"
mkdir -p "$DMG_TMP"

cp -r "$APP_PATH" "$DMG_TMP/"
# Symlink a /Applications para que el usuario arrastre la app
ln -s /Applications "$DMG_TMP/Applications"

hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$DMG_TMP" \
    -ov -format UDZO \
    "$DMG_OUT"

rm -rf "$DMG_TMP"

DMG_SIZE=$(du -sh "$DMG_OUT" | cut -f1)
echo "    $DMG_OUT ($DMG_SIZE) OK"

# ── Resumen ───────────────────────────────────────────────────────────────────
echo ""
echo "=============================="
echo "  Build completado"
echo "=============================="
echo ""
echo "  App bundle : $APP_PATH"
echo "  Instalador : $DMG_OUT"
echo ""
echo "Para distribuir: abrí el .dmg y arrastrá la app a /Applications."
echo ""
echo "NOTA: Al ejecutar la app por primera vez se abrirá Terminal con"
echo "'rclone config' para autenticar Google Drive. Solo hace falta una vez."
echo ""
echo "Si macOS bloquea la app (no verificada): clic derecho → Abrir."
echo ""
