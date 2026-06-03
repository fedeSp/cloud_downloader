"""
updater.py — Auto-update via GitHub Releases

Flujo:
  1. check_for_update() consulta la API de GitHub en background
  2. Si hay versión nueva, llama a on_update_available(new_version, download_url)
  3. download_and_apply() descarga el nuevo ejecutable y lanza el swap
     - Windows: script .bat que espera que el proceso actual cierre y luego reemplaza el .exe
     - macOS:   script .sh equivalente
"""

import os
import sys
import json
import ssl
import subprocess
import tempfile
import threading
import urllib.request
from urllib.error import URLError

try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = None

GITHUB_REPO   = "fedeSp/cloud_downloader"
API_URL       = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
REQUEST_TIMEOUT = 10  # segundos


# ── Version helpers ───────────────────────────────────────────────────────────

def _version_tuple(v: str):
    """'1.2.3' → (1, 2, 3)"""
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except ValueError:
        return (0,)


def get_current_version() -> str:
    """Lee version.json embebido en el .exe o del filesystem en dev."""
    base = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "version.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("version", "0.0.0")
    except (OSError, json.JSONDecodeError):
        return "0.0.0"


# ── GitHub API ────────────────────────────────────────────────────────────────

def _fetch_latest_release():
    """Devuelve (tag_name, download_url) o lanza una excepción."""
    req = urllib.request.Request(
        API_URL,
        headers={"User-Agent": "CloudDownloader-updater"},
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT,
                                context=_SSL_CONTEXT) as resp:
        data = json.loads(resp.read().decode())

    tag     = data.get("tag_name", "")
    assets  = data.get("assets", [])

    # Elegir el asset correcto según plataforma
    if sys.platform == "win32":
        wanted = "CloudDownloader.exe"
    else:
        wanted = "CloudDownloader.dmg"

    url = next(
        (a["browser_download_url"] for a in assets if a["name"] == wanted),
        None,
    )
    return tag, url


# ── Public API ────────────────────────────────────────────────────────────────

def check_for_update(on_update_available, on_error=None):
    """Comprueba en background si hay versión nueva.

    on_update_available(new_version: str, download_url: str) se llama desde
    el thread de background — usá app.after(0, ...) si necesitás tocar la UI.
    """
    def worker():
        try:
            tag, url = _fetch_latest_release()
            current  = get_current_version()
            if _version_tuple(tag) > _version_tuple(current) and url:
                on_update_available(tag.lstrip("v"), url)
        except URLError:
            pass  # sin internet — ignorar silenciosamente
        except Exception as exc:
            if on_error:
                on_error(str(exc))

    threading.Thread(target=worker, daemon=True).start()


def download_and_apply(download_url: str, progress_cb=None, error_cb=None):
    """Descarga el nuevo ejecutable y lanza el script de swap.

    progress_cb(downloaded_bytes, total_bytes) — puede ser None
    Después de iniciar el swap, termina el proceso actual.
    """
    def worker():
        try:
            # Directorio donde vive el ejecutable actual
            if getattr(sys, "frozen", False):
                current_exe = sys.executable
            else:
                # En dev no hacemos swap real
                if error_cb:
                    error_cb("Auto-update solo funciona en el ejecutable empaquetado.")
                return

            # Descargar a %TEMP% para que no aparezca junto al .exe actual
            suffix = ".exe" if sys.platform == "win32" else ".dmg"
            fd, new_exe = tempfile.mkstemp(suffix=suffix, prefix="CloudDownloader_new_")
            os.close(fd)

            # Descargar
            req = urllib.request.Request(
                download_url,
                headers={"User-Agent": "CloudDownloader-updater"},
            )
            with urllib.request.urlopen(req, timeout=120,
                                            context=_SSL_CONTEXT) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk = 65536
                with open(new_exe, "wb") as f:
                    while True:
                        buf = resp.read(chunk)
                        if not buf:
                            break
                        f.write(buf)
                        downloaded += len(buf)
                        if progress_cb:
                            progress_cb(downloaded, total)

            # Lanzar el script de swap y salir
            _launch_swap(current_exe, new_exe)

        except Exception as exc:
            if error_cb:
                error_cb(str(exc))

    threading.Thread(target=worker, daemon=True).start()


# ── Swap scripts ──────────────────────────────────────────────────────────────

def _launch_swap(current_exe: str, new_exe: str):
    """Crea un script que reemplaza current_exe con new_exe y relanza la app."""
    if sys.platform == "win32":
        _swap_windows(current_exe, new_exe)
    else:
        _swap_macos(current_exe, new_exe)
    os.kill(os.getpid(), 9)  # fuerza el cierre del proceso actual


def _swap_windows(current_exe: str, new_exe: str):
    pid    = os.getpid()
    fd, bat = tempfile.mkstemp(suffix=".bat", prefix="cd_update_")
    os.close(fd)

    script = f"""@echo off
setlocal
set RETRIES=0
:wait
tasklist /FI "PID eq {pid}" 2>NUL | find /I "{pid}" >NUL
if not errorlevel 1 (
    timeout /t 1 /nobreak >NUL
    goto wait
)
timeout /t 2 /nobreak >NUL
:retry
copy /Y "{new_exe}" "{current_exe}" >NUL 2>&1
if errorlevel 1 (
    set /a RETRIES+=1
    if %RETRIES% lss 10 (
        timeout /t 1 /nobreak >NUL
        goto retry
    )
    exit /b 1
)
del /F /Q "{new_exe}" >NUL 2>&1
start "" "{current_exe}"
del "%~f0"
"""
    with open(bat, "w") as f:
        f.write(script)

    subprocess.Popen(
        ["cmd.exe", "/c", bat],
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
        close_fds=True,
    )


def _swap_macos(current_exe: str, new_exe: str):
    pid    = os.getpid()
    fd, sh = tempfile.mkstemp(suffix=".sh", prefix="cd_update_")
    os.close(fd)

    script = f"""#!/bin/bash
while kill -0 {pid} 2>/dev/null; do sleep 1; done
mv -f "{new_exe}" "{current_exe}"
chmod +x "{current_exe}"
# Quitar cuarentena de Gatekeeper para que no requiera re-aprobacion
xattr -d com.apple.quarantine "{current_exe}" 2>/dev/null || true
open "{current_exe}"
rm -- "$0"
"""
    with open(sh, "w") as f:
        f.write(script)
    os.chmod(sh, 0o755)

    subprocess.Popen(
        ["/bin/bash", sh],
        close_fds=True,
        start_new_session=True,
    )
