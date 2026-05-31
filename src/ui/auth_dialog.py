import tkinter as tk
import customtkinter as ctk
import subprocess
import threading

from config import PROVIDERS
from rclone import RCLONE_PATH, _popen_kwargs, extract_token, write_remote_config


def show_auth_dialog(parent, provider_key):
    prov      = PROVIDERS[provider_key]
    auth_proc = [None]

    dialog = ctk.CTkToplevel(parent)
    dialog.title(f"Conectar {prov['name']}")
    dialog.geometry("500x310")
    dialog.resizable(False, False)
    dialog.grab_set()
    dialog.transient(parent)
    parent.update_idletasks()
    dx = parent.winfo_x() + (parent.winfo_width()  - 500) // 2
    dy = parent.winfo_y() + (parent.winfo_height() - 310) // 2
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
        status_var.set("Conectado correctamente!")
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
                    parent.after(0, lambda: on_error(
                        "No se recibio autorizacion. "
                        "Cancelaste en el navegador? Intenta de nuevo."
                    ))
                    return
                extra = {"drive_type": "personal"} if provider_key == "onedrive" else {}
                write_remote_config(prov["remote"], prov["rclone_type"], token, extra)
                parent.after(0, on_success)
            except subprocess.TimeoutExpired:
                if auth_proc[0]: auth_proc[0].kill()
                parent.after(0, lambda: on_error("Tiempo de espera agotado (5 min)."))
            except Exception as exc:
                parent.after(0, lambda e=exc: on_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    connect_btn.configure(command=on_connect)
    dialog.protocol("WM_DELETE_WINDOW", close_dialog)
    dialog.wait_window()
    return result["ok"]
