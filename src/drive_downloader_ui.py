import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import subprocess
import threading
import os
import re
import sys
import json

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

# =========================
# PROVIDERS CONFIG
# =========================

PROVIDERS = {
    "drive":    {"name": "Google Drive", "rclone_type": "drive",    "remote": "drive"},
    #"onedrive": {"name": "OneDrive",     "rclone_type": "onedrive", "remote": "onedrive"},
    #"dropbox":  {"name": "Dropbox",      "rclone_type": "dropbox",  "remote": "dropbox"},
}

GDOCS_EXPORT = {
    "Docs->DOCX / Sheets->XLSX / Slides->PPTX": "docx,xlsx,pptx",
    "Todo como PDF":                             "pdf",
    "No exportar":                               "",
}

# =========================
# PLATFORM / RCLONE SETUP
# =========================

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

# =========================
# GLOBALS
# =========================

cancel_requested = False
current_process  = None
total_files      = 0
completed_files  = 0
queue_items      = []   # [{"provider": str, "url": str, "dest": str}]
_queue_rows      = []   # CTkFrame refs for queue rows

# =========================
# HELPERS
# =========================

def log(msg):
    app.after(0, lambda m=msg: _log_append(m))


def _log_append(msg):
    log_box.configure(state="normal")
    log_box.insert("end", msg + "\n")
    log_box.see("end")
    log_box.configure(state="disabled")


def _update_progress(value, maximum):
    progress_bar.set(value / maximum if maximum > 0 else 0)
    progress_label.configure(text=f"{value} / {maximum} archivos")


def reset_ui():
    global cancel_requested
    cancel_requested = False
    app.after(0, lambda: download_btn.configure(state="normal"))
    app.after(0, lambda: cancel_btn.configure(state="disabled"))


# =========================
# AUTH DIALOG
# =========================

def show_auth_dialog(provider_key):
    prov      = PROVIDERS[provider_key]
    auth_proc = [None]

    dialog = ctk.CTkToplevel(app)
    dialog.title(f"Conectar {prov['name']}")
    dialog.geometry("500x310")
    dialog.resizable(False, False)
    dialog.grab_set()
    dialog.transient(app)
    app.update_idletasks()
    dx = app.winfo_x() + (app.winfo_width()  - 500) // 2
    dy = app.winfo_y() + (app.winfo_height() - 310) // 2
    dialog.geometry(f"+{dx}+{dy}")

    ctk.CTkLabel(
        dialog, text=f"Conectar {prov['name']}",
        font=ctk.CTkFont(size=18, weight="bold"),
    ).pack(pady=(24, 8))

    ctk.CTkLabel(
        dialog,
        text=f"Hace clic en el boton para abrir tu navegador\n"
             f"y autorizar el acceso a {prov['name']}.",
        justify="center",
    ).pack()

    status_var = tk.StringVar()
    status_lbl = ctk.CTkLabel(dialog, textvariable=status_var,
                               wraplength=460, justify="center")
    status_lbl.pack(pady=8)

    spinner     = ctk.CTkProgressBar(dialog, mode="indeterminate", width=420)
    connect_btn = ctk.CTkButton(dialog, text=f"Conectar con {prov['name']}",
                                width=290, height=42)
    connect_btn.pack(pady=6)

    result = {"ok": False}

    def close_dialog():
        if auth_proc[0]:
            try: auth_proc[0].kill()
            except Exception: pass
        dialog.destroy()

    def on_success():
        result["ok"] = True
        spinner.stop(); spinner.pack_forget()
        status_var.set(f"Google Drive conectado correctamente!")
        status_lbl.configure(text_color=("green", "#4caf50"))
        connect_btn.configure(text="Continuar", state="normal", command=dialog.destroy)
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)

    def on_error(msg):
        spinner.stop(); spinner.pack_forget()
        status_var.set(f"Error: {msg}")
        status_lbl.configure(text_color=("red", "#ef5350"))
        connect_btn.configure(text="Reintentar", state="normal", command=on_connect)
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)

    def on_connect():
        connect_btn.configure(state="disabled", text="Abriendo navegador...")
        status_var.set(
            f"Se abrio tu navegador. Inicia sesion en {prov['name']}\n"
            "y autoriza el acceso. Esta ventana se actualiza sola."
        )
        status_lbl.configure(text_color=("gray50", "gray70"))
        spinner.pack(pady=(0, 6)); spinner.start()
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)

        def worker():
            try:
                proc = subprocess.Popen(
                    [RCLONE_PATH, "authorize", prov["rclone_type"]],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, **_popen_kwargs(),
                )
                auth_proc[0] = proc
                stdout, stderr = proc.communicate(timeout=300)
                token = extract_token(stdout + stderr)
                if not token:
                    app.after(0, lambda: on_error(
                        "No se recibio autorizacion. "
                        "Cancelaste en el navegador? Intenta de nuevo."
                    ))
                    return
                extra = {"drive_type": "personal"} if provider_key == "onedrive" else {}
                write_remote_config(prov["remote"], prov["rclone_type"], token, extra)
                app.after(0, on_success)
            except subprocess.TimeoutExpired:
                if auth_proc[0]: auth_proc[0].kill()
                app.after(0, lambda: on_error("Tiempo de espera agotado (5 min)."))
            except Exception as exc:
                app.after(0, lambda e=exc: on_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    connect_btn.configure(command=on_connect)
    dialog.protocol("WM_DELETE_WINDOW", close_dialog)
    dialog.wait_window()
    return result["ok"]


# =========================
# QUEUE UI
# =========================

def refresh_queue():
    for f in _queue_rows:
        f.destroy()
    _queue_rows.clear()

    if not queue_items:
        lbl = ctk.CTkLabel(
            queue_scroll,
            text="Cola vacia. Agrega URLs con el boton + Agregar.",
            text_color=("gray50", "gray60"),
        )
        lbl.pack(pady=10)
        _queue_rows.append(lbl)
        return

    icons = {"drive": "Drive", "onedrive": "OneDrive", "dropbox": "Dropbox"}
    for i, item in enumerate(queue_items):
        row = ctk.CTkFrame(queue_scroll, corner_radius=6)
        row.pack(fill="x", padx=4, pady=2)
        _queue_rows.append(row)

        # URL row
        url_row = ctk.CTkFrame(row, fg_color="transparent")
        url_row.pack(fill="x")

        ctk.CTkLabel(
            url_row, text=f"[{icons.get(item['provider'], '')}]",
            width=70, text_color=("gray40", "gray60"),
        ).pack(side="left", padx=(8, 2), pady=(6, 2))

        ctk.CTkLabel(
            url_row,
            text=item["url"][:76] + ("..." if len(item["url"]) > 76 else ""),
            anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=4)

        ctk.CTkButton(
            url_row, text="X", width=28, height=24,
            fg_color="transparent",
            hover_color=("gray80", "gray30"),
            text_color=("gray40", "gray70"),
            command=lambda ix=i: remove_from_queue(ix),
        ).pack(side="right", padx=6, pady=(6, 2))

        # Destination row
        dest_row = ctk.CTkFrame(row, fg_color="transparent")
        dest_row.pack(fill="x", pady=(0, 4))

        dest_text = item["dest"] if item["dest"] else "Sin destino"
        dest_color = ("gray30", "gray70") if item["dest"] else ("orange", "#e6a817")
        ctk.CTkLabel(
            dest_row,
            text=f"  →  {dest_text[:65] + ('...' if len(dest_text) > 65 else '')}",
            anchor="w",
            text_color=dest_color,
            font=ctk.CTkFont(size=11),
        ).pack(side="left", fill="x", expand=True, padx=(74, 4))

        ctk.CTkButton(
            dest_row, text="Elegir destino", width=110, height=24,
            fg_color="transparent",
            hover_color=("gray80", "gray30"),
            text_color=("gray50", "gray60"),
            font=ctk.CTkFont(size=11),
            command=lambda ix=i: choose_item_dest(ix),
        ).pack(side="right", padx=6)


def add_to_queue():
    url = url_entry.get().strip()
    if not url:
        messagebox.showerror("Error", "Ingresa una URL o ruta.")
        return
    folder = filedialog.askdirectory(title="Elegir carpeta de destino")
    if not folder:
        return
    queue_items.append({"provider": provider_var.get(), "url": url, "dest": folder})
    url_entry.delete(0, "end")
    refresh_queue()


def remove_from_queue(idx):
    if 0 <= idx < len(queue_items):
        queue_items.pop(idx)
    refresh_queue()


def choose_item_dest(idx):
    folder = filedialog.askdirectory()
    if folder and 0 <= idx < len(queue_items):
        queue_items[idx]["dest"] = folder
        refresh_queue()


# =========================
# DOWNLOAD
# =========================

def build_list_cmd(item, export_fmt):
    provider = item["provider"]
    url      = item["url"]
    remote   = PROVIDERS[provider]["remote"]
    extra    = []

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


def start_download():
    global total_files, completed_files, cancel_requested

    if not queue_items:
        messagebox.showerror("Error", "La cola esta vacia. Agrega al menos una URL.")
        return

    for item in queue_items:
        if not item.get("dest", "").strip():
            messagebox.showerror(
                "Error",
                f"Falta el destino para:\n{item['url'][:60]}\n\nElige una carpeta en la cola.",
            )
            return

    for pkey in {item["provider"] for item in queue_items}:
        if not provider_is_configured(pkey):
            name = PROVIDERS[pkey]["name"]
            if not messagebox.askyesno(
                "Autenticacion requerida",
                f"Necesitas conectar {name} primero.\nConectar ahora?",
            ):
                return
            if not show_auth_dialog(pkey):
                return

    ext_raw    = ext_entry.get().strip()
    extensions = [e.strip().lstrip(".").lower() for e in ext_raw.split(",") if e.strip()]
    export_fmt = GDOCS_EXPORT.get(export_var.get(), "")

    cancel_requested = False
    completed_files  = 0

    log_box.configure(state="normal")
    log_box.delete("1.0", "end")
    log_box.configure(state="disabled")
    log("Iniciando...")

    all_tasks = []
    for item in queue_items:
        try:
            remote_path, extra_args, list_cmd = build_list_cmd(item, export_fmt)
            result = subprocess.run(list_cmd, capture_output=True, text=True, **_popen_kwargs())
            if result.returncode != 0:
                log(f"Error listando {item['url']}: {result.stderr.strip()}")
                continue
            files = [f for f in json.loads(result.stdout) if not f.get("IsDir")]
            if extensions:
                files = [f for f in files if any(
                    f["Path"].lower().endswith(f".{ext}") for ext in extensions
                )]
            for f in files:
                all_tasks.append((item, remote_path, extra_args, f))
            log(f"Carpeta: {item['url'][:55]}: {len(files)} archivo(s)")
        except Exception as e:
            log(f"Error en {item['url']}: {e}")

    total_files = len(all_tasks)
    if total_files == 0:
        log("No se encontraron archivos.")
        return

    app.after(0, lambda: _update_progress(0, total_files))
    log(f"Total: {total_files} archivo(s)")
    download_btn.configure(state="disabled")
    cancel_btn.configure(state="normal")

    def worker():
        global current_process, completed_files
        for item, remote_path, extra_args, file_info in all_tasks:
            if cancel_requested:
                log("Descarga cancelada.")
                break
            path = file_info["Path"]
            log(f"Descargando: {path}")
            cmd = [
                RCLONE_PATH, "copy", remote_path, item["dest"],
                "--include", path,
                "--create-empty-src-dirs",
                "--transfers", "1",
                "--ignore-existing",
                "--log-level", "ERROR",
            ] + extra_args
            current_process = subprocess.Popen(cmd, **_popen_kwargs())
            current_process.wait()
            if current_process.returncode == 0:
                completed_files += 1
                cf, tf = completed_files, total_files
                app.after(0, lambda v=cf, m=tf: _update_progress(v, m))
                log(f"OK: {path}")
            else:
                log(f"Error: {path}")
        reset_ui()

    threading.Thread(target=worker, daemon=True).start()


def cancel_download():
    global cancel_requested, current_process
    cancel_requested = True
    if current_process:
        current_process.terminate()
    log("Cancelando...")


def choose_directory():
    folder = filedialog.askdirectory()
    if folder:
        dest_var.set(folder)


def reconnect_provider():
    pkey = provider_var.get()
    name = PROVIDERS[pkey]["name"]
    if messagebox.askyesno(
        f"Reconectar {name}",
        f"Esto reemplazara la cuenta de {name} conectada.\nContinuar?",
    ):
        show_auth_dialog(pkey)


def update_url_hint(*_):
    hints = {
        "drive":    "https://drive.google.com/drive/folders/...",
        "onedrive": "Documents/Proyecto X",
        "dropbox":  "/Fotos/Vacaciones",
    }
    url_entry.configure(placeholder_text=hints.get(provider_var.get(), ""))


def toggle_theme():
    new = "light" if ctk.get_appearance_mode() == "Dark" else "dark"
    ctk.set_appearance_mode(new)
    theme_btn.configure(text="Claro" if new == "dark" else "Oscuro")


# =========================
# UI BUILD
# =========================

app = ctk.CTk()
app.title("Cloud Downloader")
app.geometry("920x780")
app.minsize(720, 620)

# ──── Header ──── #
header = ctk.CTkFrame(app, corner_radius=0, height=54)
header.pack(fill="x")
header.pack_propagate(False)

ctk.CTkLabel(
    header, text="Cloud Downloader",
    font=ctk.CTkFont(size=20, weight="bold"),
).pack(side="left", padx=18)

theme_btn = ctk.CTkButton(
    header, text="Oscuro", width=90, height=32,
    fg_color="transparent", hover_color=("gray80", "gray25"),
    command=toggle_theme,
)
theme_btn.pack(side="right", padx=10)

ctk.CTkButton(
    header, text="Reconectar cuenta", width=150, height=32,
    fg_color="transparent", hover_color=("gray80", "gray25"),
    text_color=("gray40", "gray60"),
    command=reconnect_provider,
).pack(side="right", padx=4)

# ──── Provider + URL ──── #
input_frame = ctk.CTkFrame(app)
input_frame.pack(fill="x", padx=12, pady=(10, 4))

ctk.CTkLabel(input_frame, text="Proveedor",
             font=ctk.CTkFont(weight="bold")).grid(
    row=0, column=0, padx=(12, 8), pady=(10, 4), sticky="w")

provider_var = tk.StringVar(value="drive")
provider_var.trace_add("write", update_url_hint)

for col, (key, prov) in enumerate(PROVIDERS.items()):
    ctk.CTkRadioButton(
        input_frame, text=prov["name"],
        variable=provider_var, value=key,
    ).grid(row=0, column=col + 1, padx=12, pady=(10, 4), sticky="w")

ctk.CTkLabel(input_frame, text="URL / Ruta",
             font=ctk.CTkFont(weight="bold")).grid(
    row=1, column=0, padx=(12, 8), pady=(0, 10), sticky="w")

url_entry = ctk.CTkEntry(
    input_frame,
    placeholder_text="https://drive.google.com/drive/folders/...",
    height=36,
)
url_entry.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(0, 8), pady=(0, 10))
url_entry.bind("<Return>", lambda e: add_to_queue())

ctk.CTkButton(input_frame, text="+ Agregar", width=100, height=36,
              command=add_to_queue).grid(
    row=1, column=4, padx=(0, 12), pady=(0, 10))

input_frame.columnconfigure(2, weight=1)

# ──── Queue ──── #
ctk.CTkLabel(app, text="Cola de descargas",
             font=ctk.CTkFont(weight="bold"), anchor="w").pack(
    fill="x", padx=14, pady=(4, 2))

queue_scroll = ctk.CTkScrollableFrame(app, height=160)
queue_scroll.pack(fill="x", padx=12, pady=(0, 6))

# ──── Options ──── #
# ── Options Accordion ── #
opts_outer = ctk.CTkFrame(app, corner_radius=8)
opts_outer.pack(fill="x", padx=12, pady=(4, 2))

opts_header = ctk.CTkFrame(opts_outer, fg_color=("gray85", "gray20"), corner_radius=6)
opts_header.pack(fill="x", padx=4, pady=(4, 4))

ctk.CTkLabel(
    opts_header, text="Opciones de descarga",
    font=ctk.CTkFont(weight="bold"), anchor="w",
).pack(side="left", padx=12, pady=8)

opts_body = ctk.CTkFrame(opts_outer, fg_color="transparent")
# starts collapsed


def toggle_options():
    if opts_body.winfo_ismapped():
        opts_body.pack_forget()
        opts_toggle_btn.configure(text="▼")
    else:
        opts_body.pack(fill="x", padx=4, pady=(0, 8))
        opts_toggle_btn.configure(text="▲")


opts_toggle_btn = ctk.CTkButton(
    opts_header, text="▼", width=38, height=28,
    fg_color="transparent",
    hover_color=("gray75", "gray30"),
    command=toggle_options,
)
opts_toggle_btn.pack(side="right", padx=8, pady=4)

opts_row = ctk.CTkFrame(opts_body, fg_color="transparent")
opts_row.pack(fill="x", padx=8, pady=(8, 8))

ctk.CTkLabel(opts_row, text="Filtrar extensiones:").pack(side="left", padx=(4, 6))

ext_entry = ctk.CTkEntry(
    opts_row, placeholder_text="pdf, mp4, docx  (vacio = todos)",
    width=240, height=32)
ext_entry.pack(side="left")

ctk.CTkLabel(opts_row, text="Google Docs:").pack(side="left", padx=(24, 6))

export_var = tk.StringVar(value=list(GDOCS_EXPORT.keys())[0])
ctk.CTkOptionMenu(
    opts_row, variable=export_var,
    values=list(GDOCS_EXPORT.keys()), width=260,
).pack(side="left")

# ────── Destination ────── #


# ── Buttons ── #
btn_frame = ctk.CTkFrame(app, fg_color="transparent")
btn_frame.pack(fill="x", padx=12, pady=6)

download_btn = ctk.CTkButton(
    btn_frame, text="Descargar todo",
    height=44, font=ctk.CTkFont(size=14, weight="bold"),
    command=start_download,
)
download_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

cancel_btn = ctk.CTkButton(
    btn_frame, text="Cancelar",
    height=44, state="disabled",
    fg_color=("gray70", "gray30"),
    hover_color=("gray60", "gray25"),
    command=cancel_download,
)
cancel_btn.pack(side="left", fill="x", expand=True, padx=(6, 0))

# ── Progress ── #
prog_frame = ctk.CTkFrame(app, fg_color="transparent")
prog_frame.pack(fill="x", padx=12, pady=(4, 2))

progress_bar = ctk.CTkProgressBar(prog_frame)
progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 12))
progress_bar.set(0)

progress_label = ctk.CTkLabel(prog_frame, text="0 / 0 archivos", width=130, anchor="e")
progress_label.pack(side="right")

# ── Log ── #
ctk.CTkLabel(app, text="Log", font=ctk.CTkFont(weight="bold"), anchor="w").pack(
    fill="x", padx=14, pady=(6, 2))

log_box = ctk.CTkTextbox(app, state="disabled", wrap="word",
                          font=ctk.CTkFont(size=12))
log_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))

# Init
refresh_queue()
app.mainloop()

