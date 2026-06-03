import os
import re
import sys
import json
import ssl
import subprocess
import urllib.request

from config import PROVIDERS

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = None


def get_rclone_path():
    exe = "rclone.exe" if sys.platform == "win32" else "rclone"
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, exe)
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), exe)
    if os.path.exists(local):
        return local
    return exe


def get_config_path():
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA", ""), "rclone", "rclone.conf")
    return os.path.expanduser("~/.config/rclone/rclone.conf")


def _parse_config():
    path = get_config_path()
    if not os.path.exists(path):
        return {}
    config, current = {}, None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                current = line[1:-1]
                config[current] = {}
            elif "=" in line and current:
                k, _, v = line.partition("=")
                config[current][k.strip()] = v.strip()
    return config


def provider_is_configured(provider_key):
    config = _parse_config()
    remote = PROVIDERS[provider_key]["remote"]
    if remote not in config:
        return False
    token_str = config[remote].get("token", "")
    if not token_str:
        return False
    try:
        token_data = json.loads(token_str)
        return bool(token_data.get("access_token"))
    except (json.JSONDecodeError, AttributeError):
        return False


def write_remote_config(remote_name, rclone_type, token_json, extra=None):
    config_path = get_config_path()
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    content = open(config_path, encoding="utf-8").read() if os.path.exists(config_path) else ""
    section = f"[{remote_name}]\ntype = {rclone_type}\ntoken = {token_json}\n"
    if extra:
        section += "".join(f"{k} = {v}\n" for k, v in extra.items())
    section += "\n"
    pattern = rf'\[{re.escape(remote_name)}\][^\[]*'
    if re.search(pattern, content, re.DOTALL):
        content = re.sub(pattern, section, content, flags=re.DOTALL)
    else:
        content += section
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(content)


def extract_token(output):
    m = re.search(r'--->\s*(\{.+?\})\s*<---', output, re.DOTALL)
    if m:
        return m.group(1).strip()
    for line in output.splitlines():
        line = line.strip()
        if '"access_token"' in line:
            try:
                json.loads(line)
                return line
            except json.JSONDecodeError:
                pass
    return None


def _popen_kwargs():
    if sys.platform != "win32":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}


def extract_drive_folder_id(url):
    m = re.search(r'/folders/([a-zA-Z0-9_-]+)', url)
    if m:
        return m.group(1)
    raise ValueError("URL invalida de Google Drive")


RCLONE_PATH = get_rclone_path()


# ── Dropbox shared-link API ───────────────────────────────────────────────────

def get_provider_access_token(provider_key):
    """Returns the OAuth access_token for a provider's configured remote, or None."""
    config = _parse_config()
    remote = PROVIDERS[provider_key]["remote"]
    token_str = config.get(remote, {}).get("token", "")
    if not token_str:
        return None
    try:
        return json.loads(token_str).get("access_token")
    except (json.JSONDecodeError, AttributeError):
        return None


def is_dropbox_shared_link(url: str) -> bool:
    """True if url looks like a Dropbox shared folder/file link."""
    return "dropbox.com/" in url and url.startswith(("http://", "https://"))


def _dbx_api(endpoint: str, payload: dict, token: str) -> dict:
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        endpoint, data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    kw = {"context": _SSL_CTX} if _SSL_CTX else {}
    with urllib.request.urlopen(req, **kw) as resp:
        return json.loads(resp.read())


def list_dropbox_shared_entries(shared_url: str, token: str) -> list:
    """Return all entries (files + folders) inside a Dropbox shared folder link.

    Each entry: {"Path": str, "Name": str, "IsDir": bool}
    """
    entries = []
    data = _dbx_api(
        "https://api.dropboxapi.com/2/files/list_folder",
        {"path": "", "shared_link": {"url": shared_url},
         "recursive": True, "include_deleted": False},
        token,
    )
    while True:
        for e in data.get("entries", []):
            entries.append({
                "Path":  e["path_lower"].lstrip("/"),
                "Name":  e["name"],
                "IsDir": e.get(".tag") == "folder",
            })
        if not data.get("has_more"):
            break
        data = _dbx_api(
            "https://api.dropboxapi.com/2/files/list_folder/continue",
            {"cursor": data["cursor"]}, token,
        )
    return entries


def download_dropbox_shared_file(shared_url: str, file_path: str, dest_dir: str, token: str):
    """Download one file from a Dropbox shared folder link into dest_dir."""
    arg = json.dumps({"url": shared_url, "path": "/" + file_path.lstrip("/")})
    req = urllib.request.Request(
        "https://content.dropboxapi.com/2/sharing/get_shared_link_file",
        headers={"Authorization": f"Bearer {token}", "Dropbox-API-Arg": arg},
    )
    out_path = os.path.join(dest_dir, file_path.replace("/", os.sep))
    os.makedirs(os.path.dirname(out_path) or dest_dir, exist_ok=True)
    kw = {"context": _SSL_CTX} if _SSL_CTX else {}
    with urllib.request.urlopen(req, **kw) as resp:
        with open(out_path, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
