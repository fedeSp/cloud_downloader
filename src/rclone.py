import os
import re
import sys
import json
import subprocess

from config import PROVIDERS


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
    return remote in config and "token" in config[remote]


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
