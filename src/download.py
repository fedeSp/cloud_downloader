import json
import subprocess
import threading

from config import PROVIDERS
from rclone import (RCLONE_PATH, _popen_kwargs, extract_drive_folder_id,
                    get_provider_access_token, is_dropbox_shared_link,
                    list_dropbox_shared_entries, download_dropbox_shared_file)


def build_list_cmd(item, export_fmt):
    provider    = item["provider"]
    url         = item["url"]
    remote      = PROVIDERS[provider]["remote"]
    extra       = []

    if provider == "drive":
        folder_id   = extract_drive_folder_id(url)
        remote_path = f"{remote}:/"
        extra      += ["--drive-root-folder-id", folder_id]
        if export_fmt:
            extra += ["--drive-export-formats", export_fmt]
    elif provider == "onedrive":
        remote_path = f"{remote}:/{url.strip('/')}"
    elif provider == "dropbox":
        path        = url.strip("/")
        remote_path = f"{remote}:/{path}" if path else f"{remote}:/"
    else:
        remote_path = f"{remote}:/{url.strip('/')}"

    cmd = [RCLONE_PATH, "lsjson", remote_path, "--recursive"] + extra
    return remote_path, extra, cmd


def run_downloads(queue_items, extensions, export_fmt,
                  log_cb, progress_cb, done_cb, get_cancel, set_process):
    """Start listing + downloading in a background thread.

    Callbacks (all invoked from the worker thread — must be thread-safe):
      log_cb(msg)           — append a line to the log
      progress_cb(n, total) — update progress bar
      done_cb()             — called when finished or cancelled
      get_cancel() -> bool  — returns True if the user requested cancellation
      set_process(proc)     — stores the active subprocess for cancel support
    """

    def worker():
        # tasks: (item, remote_path|None, extra_args|None, file_info, shared_url|None)
        all_tasks = []
        for item in queue_items:
            try:
                provider = item["provider"]
                url      = item["url"]

                if provider == "dropbox" and is_dropbox_shared_link(url):
                    token = get_provider_access_token("dropbox")
                    if not token:
                        log_cb("Error: no hay cuenta Dropbox configurada.")
                        continue
                    log_cb(f"Listando: {url[:60]}…")
                    all_entries = list_dropbox_shared_entries(url, token)
                    files       = [e for e in all_entries if not e["IsDir"]]
                    shared_url  = url
                    remote_path = None
                    extra_args  = None
                else:
                    remote_path, extra_args, list_cmd = build_list_cmd(item, export_fmt)
                    result = subprocess.run(
                        list_cmd, capture_output=True, text=True, **_popen_kwargs()
                    )
                    if result.returncode != 0:
                        log_cb(f"Error listando {url}: {result.stderr.strip()}")
                        continue
                    files      = [f for f in json.loads(result.stdout) if not f.get("IsDir")]
                    shared_url = None

                if extensions:
                    files = [
                        f for f in files
                        if any(f["Path"].lower().endswith(f".{ext}") for ext in extensions)
                    ]
                # Filter by user-selected paths (from the file browser)
                selected = item.get("selected_files")  # None = all
                if selected is not None:
                    dir_prefixes = [s for s in selected if s.endswith("/")]
                    file_exact   = {s for s in selected if not s.endswith("/")}
                    files = [
                        f for f in files
                        if f["Path"] in file_exact
                        or any(f["Path"].startswith(p) for p in dir_prefixes)
                    ]
                for f in files:
                    all_tasks.append((item, remote_path, extra_args, f, shared_url))
                log_cb(f"Carpeta: {url[:55]}: {len(files)} archivo(s)")
            except Exception as exc:
                log_cb(f"Error en {item['url']}: {exc}")

        total = len(all_tasks)
        if total == 0:
            log_cb("No se encontraron archivos.")
            done_cb()
            return

        progress_cb(0, total)
        log_cb(f"Total: {total} archivo(s)")

        completed = 0
        for item, remote_path, extra_args, file_info, shared_url in all_tasks:
            if get_cancel():
                log_cb("Descarga cancelada.")
                break
            path = file_info["Path"]
            log_cb(f"Descargando: {path}")
            if shared_url:
                try:
                    token = get_provider_access_token("dropbox")
                    download_dropbox_shared_file(shared_url, path, item["dest"], token)
                    completed += 1
                    progress_cb(completed, total)
                    log_cb(f"OK: {path}")
                except Exception as exc:
                    log_cb(f"Error: {path} — {exc}")
            else:
                cmd = [
                    RCLONE_PATH, "copy", remote_path, item["dest"],
                    "--include", path,
                    "--create-empty-src-dirs",
                    "--transfers", "1",
                    "--ignore-existing",
                    "--log-level", "ERROR",
                ] + extra_args
                proc = subprocess.Popen(cmd, **_popen_kwargs())
                set_process(proc)
                proc.wait()
                if proc.returncode == 0:
                    completed += 1
                    progress_cb(completed, total)
                    log_cb(f"OK: {path}")
                else:
                    log_cb(f"Error: {path}")

        done_cb()

    threading.Thread(target=worker, daemon=True).start()
