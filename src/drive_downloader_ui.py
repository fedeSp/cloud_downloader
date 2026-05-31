import sys
import os

# Asegura que src/ esté en el path cuando se ejecuta como .py o como .exe
_src_dir = os.path.dirname(os.path.abspath(__file__))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

from config import PROVIDERS, GDOCS_EXPORT
from rclone import provider_is_configured
from download import run_downloads
from updater import check_for_update, get_current_version
from ui.auth_dialog import show_auth_dialog
from ui.queue_panel import QueuePanel
from ui.update_dialog import show_update_dialog

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Cloud Downloader")
        self.geometry("920x780")
        self.minsize(720, 620)

        self._cancel_requested = False
        self._current_process  = None

        self._build_ui()
        self.after(2000, self._check_for_update)

    # ── UI Construction ───────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._build_input()
        self._build_queue()
        self._build_options()
        self._build_buttons()
        self._build_progress()
        self._build_log()

    def _build_header(self):
        header = ctk.CTkFrame(self, corner_radius=0, height=54)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="Cloud Downloader",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(side="left", padx=18)

        version = get_current_version()
        ctk.CTkLabel(
            header, text=f"v{version}",
            text_color=("gray50", "gray60"),
            font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=(0, 8))

        self._theme_btn = ctk.CTkButton(
            header, text="Oscuro", width=90, height=32,
            fg_color="transparent", hover_color=("gray80", "gray25"),
            command=self._toggle_theme,
        )
        self._theme_btn.pack(side="right", padx=10)

        ctk.CTkButton(
            header, text="Reconectar cuenta", width=150, height=32,
            fg_color="transparent", hover_color=("gray80", "gray25"),
            text_color=("gray40", "gray60"),
            command=self._reconnect_provider,
        ).pack(side="right", padx=4)

    def _build_input(self):
        frame = ctk.CTkFrame(self)
        frame.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(frame, text="Proveedor",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=(12, 8), pady=(10, 4), sticky="w")

        self._provider_var = tk.StringVar(value="drive")
        self._provider_var.trace_add("write", self._update_url_hint)

        for col, (key, prov) in enumerate(PROVIDERS.items()):
            ctk.CTkRadioButton(
                frame, text=prov["name"],
                variable=self._provider_var, value=key,
            ).grid(row=0, column=col + 1, padx=12, pady=(10, 4), sticky="w")

        ctk.CTkLabel(frame, text="URL / Ruta",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=1, column=0, padx=(12, 8), pady=(0, 10), sticky="w")

        self._url_entry = ctk.CTkEntry(
            frame,
            placeholder_text="https://drive.google.com/drive/folders/...",
            height=36,
        )
        self._url_entry.grid(row=1, column=1, columnspan=3, sticky="ew",
                             padx=(0, 8), pady=(0, 10))
        self._url_entry.bind("<Return>", lambda e: self._add_to_queue())

        ctk.CTkButton(frame, text="+ Agregar", width=100, height=36,
                      command=self._add_to_queue).grid(
            row=1, column=4, padx=(0, 12), pady=(0, 10))

        frame.columnconfigure(2, weight=1)

    def _build_queue(self):
        ctk.CTkLabel(self, text="Cola de descargas",
                     font=ctk.CTkFont(weight="bold"), anchor="w").pack(
            fill="x", padx=14, pady=(4, 2))

        self._queue = QueuePanel(self, height=160)
        self._queue.pack(fill="x", padx=12, pady=(0, 6))

    def _build_options(self):
        outer = ctk.CTkFrame(self, corner_radius=8)
        outer.pack(fill="x", padx=12, pady=(4, 2))

        opts_header = ctk.CTkFrame(outer, fg_color=("gray85", "gray20"), corner_radius=6)
        opts_header.pack(fill="x", padx=4, pady=(4, 4))

        ctk.CTkLabel(
            opts_header, text="Opciones de descarga",
            font=ctk.CTkFont(weight="bold"), anchor="w",
        ).pack(side="left", padx=12, pady=8)

        opts_body = ctk.CTkFrame(outer, fg_color="transparent")

        def toggle():
            if opts_body.winfo_ismapped():
                opts_body.pack_forget()
                toggle_btn.configure(text="▼")
            else:
                opts_body.pack(fill="x", padx=4, pady=(0, 8))
                toggle_btn.configure(text="▲")

        toggle_btn = ctk.CTkButton(
            opts_header, text="▼", width=38, height=28,
            fg_color="transparent", hover_color=("gray75", "gray30"),
            command=toggle,
        )
        toggle_btn.pack(side="right", padx=8, pady=4)

        opts_row = ctk.CTkFrame(opts_body, fg_color="transparent")
        opts_row.pack(fill="x", padx=8, pady=(8, 8))

        ctk.CTkLabel(opts_row, text="Filtrar extensiones:").pack(side="left", padx=(4, 6))
        self._ext_entry = ctk.CTkEntry(
            opts_row, placeholder_text="pdf, mp4, docx  (vacio = todos)",
            width=240, height=32)
        self._ext_entry.pack(side="left")

        ctk.CTkLabel(opts_row, text="Google Docs:").pack(side="left", padx=(24, 6))
        self._export_var = tk.StringVar(value=list(GDOCS_EXPORT.keys())[0])
        ctk.CTkOptionMenu(
            opts_row, variable=self._export_var,
            values=list(GDOCS_EXPORT.keys()), width=260,
        ).pack(side="left")

    def _build_buttons(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", padx=12, pady=6)

        self._download_btn = ctk.CTkButton(
            frame, text="Descargar todo",
            height=44, font=ctk.CTkFont(size=14, weight="bold"),
            command=self._start_download,
        )
        self._download_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self._cancel_btn = ctk.CTkButton(
            frame, text="Cancelar",
            height=44, state="disabled",
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray25"),
            command=self._cancel_download,
        )
        self._cancel_btn.pack(side="left", fill="x", expand=True, padx=(6, 0))

    def _build_progress(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="x", padx=12, pady=(4, 2))

        self._progress_bar = ctk.CTkProgressBar(frame)
        self._progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self._progress_bar.set(0)

        self._progress_label = ctk.CTkLabel(frame, text="0 / 0 archivos",
                                             width=130, anchor="e")
        self._progress_label.pack(side="right")

    def _build_log(self):
        ctk.CTkLabel(self, text="Log", font=ctk.CTkFont(weight="bold"),
                     anchor="w").pack(fill="x", padx=14, pady=(6, 2))

        self._log_box = ctk.CTkTextbox(self, state="disabled", wrap="word",
                                        font=ctk.CTkFont(size=12))
        self._log_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    # ── Helpers ───────────────────────────────────────────────────────

    def _log(self, msg):
        self.after(0, lambda m=msg: self._log_append(m))

    def _log_append(self, msg):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _update_progress(self, value, maximum):
        self._progress_bar.set(value / maximum if maximum > 0 else 0)
        self._progress_label.configure(text=f"{value} / {maximum} archivos")

    def _reset_ui(self):
        self._cancel_requested = False
        self.after(0, lambda: self._download_btn.configure(state="normal"))
        self.after(0, lambda: self._cancel_btn.configure(state="disabled"))

    def _toggle_theme(self):
        new = "light" if ctk.get_appearance_mode() == "Dark" else "dark"
        ctk.set_appearance_mode(new)
        self._theme_btn.configure(text="Claro" if new == "dark" else "Oscuro")

    def _update_url_hint(self, *_):
        hints = {
            "drive":    "https://drive.google.com/drive/folders/...",
            "onedrive": "Documents/Proyecto X",
            "dropbox":  "/Fotos/Vacaciones",
        }
        self._url_entry.configure(
            placeholder_text=hints.get(self._provider_var.get(), ""))

    # ── Actions ───────────────────────────────────────────────────────

    def _add_to_queue(self):
        url = self._url_entry.get().strip()
        if not url:
            messagebox.showerror("Error", "Ingresa una URL o ruta.")
            return
        folder = filedialog.askdirectory(title="Elegir carpeta de destino")
        if not folder:
            return
        self._queue.add(self._provider_var.get(), url, folder)
        self._url_entry.delete(0, "end")

    def _reconnect_provider(self):
        pkey = self._provider_var.get()
        name = PROVIDERS[pkey]["name"]
        if messagebox.askyesno(
            f"Reconectar {name}",
            f"Esto reemplazara la cuenta de {name} conectada.\nContinuar?",
        ):
            show_auth_dialog(self, pkey)

    def _start_download(self):
        items = self._queue.items
        if not items:
            messagebox.showerror("Error", "La cola esta vacia. Agrega al menos una URL.")
            return

        for item in items:
            if not item.get("dest", "").strip():
                messagebox.showerror(
                    "Error",
                    f"Falta el destino para:\n{item['url'][:60]}\n\n"
                    "Elige una carpeta en la cola.",
                )
                return

        for pkey in {item["provider"] for item in items}:
            if not provider_is_configured(pkey):
                name = PROVIDERS[pkey]["name"]
                if not messagebox.askyesno(
                    "Autenticacion requerida",
                    f"Necesitas conectar {name} primero.\nConectar ahora?",
                ):
                    return
                if not show_auth_dialog(self, pkey):
                    return

        ext_raw    = self._ext_entry.get().strip()
        extensions = [e.strip().lstrip(".").lower() for e in ext_raw.split(",") if e.strip()]
        export_fmt = GDOCS_EXPORT.get(self._export_var.get(), "")

        self._cancel_requested = False
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")
        self._log("Iniciando...")
        self._download_btn.configure(state="disabled")
        self._cancel_btn.configure(state="normal")

        run_downloads(
            queue_items=list(items),
            extensions=extensions,
            export_fmt=export_fmt,
            log_cb=lambda m: self.after(0, lambda msg=m: self._log_append(msg)),
            progress_cb=lambda v, t: self.after(0, lambda val=v, tot=t: self._update_progress(val, tot)),
            done_cb=lambda: self.after(0, self._reset_ui),
            get_cancel=lambda: self._cancel_requested,
            set_process=lambda p: setattr(self, "_current_process", p),
        )

    def _cancel_download(self):
        self._cancel_requested = True
        if self._current_process:
            self._current_process.terminate()
        self._log("Cancelando...")

    def _check_for_update(self):
        def on_available(new_version, url):
            self.after(0, lambda v=new_version, u=url: show_update_dialog(self, v, u))

        check_for_update(on_update_available=on_available)


if __name__ == "__main__":
    app = App()
    app.mainloop()

