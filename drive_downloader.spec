# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — compatible con Windows y macOS (PyInstaller 5+/6+)
import sys
import os
from PyInstaller.utils.hooks import collect_data_files

ctk_datas = collect_data_files("customtkinter")

APP_NAME   = 'CloudDownloader'
ICON_WIN   = os.path.join(SPECPATH, 'assets', 'icon.ico')
ICON_MAC   = os.path.join(SPECPATH, 'assets', 'icon.icns')
rclone_bin = 'rclone.exe' if sys.platform == 'win32' else 'rclone'
rclone_src = os.path.join(SPECPATH, rclone_bin)

if not os.path.exists(rclone_src):
    raise FileNotFoundError(
        f"\n[ERROR] Binario de rclone no encontrado: {rclone_src}\n"
        "Ejecutá el script de build primero para descargarlo."
    )

a = Analysis(
    [os.path.join(SPECPATH, 'src', 'drive_downloader_ui.py')],
    pathex=[SPECPATH, os.path.join(SPECPATH, 'src')],
    binaries=[(rclone_src, '.')],   # rclone queda en sys._MEIPASS
    datas=ctk_datas + [('version.json', '.')],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

# ──────────────────────────────────────────
# macOS → onedir + .app bundle
# ──────────────────────────────────────────
if sys.platform == 'darwin':
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        argv_emulation=False,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name=APP_NAME,
    )
    app = BUNDLE(
        coll,
        name=f'{APP_NAME}.app',
        icon=ICON_MAC,
        bundle_identifier='com.clouddownloader.app',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'LSBackgroundOnly':        'False',
        },
    )

# ──────────────────────────────────────────
# Windows / Linux → single onefile .exe
# ──────────────────────────────────────────
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        icon=ICON_WIN,
    )
