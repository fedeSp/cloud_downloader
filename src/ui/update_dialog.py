import webbrowser
import customtkinter as ctk

RELEASES_URL = "https://github.com/fedeSp/cloud_downloader/releases/latest"


def show_update_dialog(parent, new_version: str, download_url: str):
    """Muestra el aviso de actualización disponible y maneja la descarga."""
    from updater import download_and_apply

    dialog = ctk.CTkToplevel(parent)
    dialog.title("Actualización disponible")
    dialog.geometry("420x240")
    dialog.resizable(False, False)
    dialog.grab_set()
    dialog.transient(parent)
    parent.update_idletasks()
    dx = parent.winfo_x() + (parent.winfo_width()  - 420) // 2
    dy = parent.winfo_y() + (parent.winfo_height() - 240) // 2
    dialog.geometry(f"+{dx}+{dy}")

    ctk.CTkLabel(
        dialog,
        text="Nueva version disponible",
        font=ctk.CTkFont(size=17, weight="bold"),
    ).pack(pady=(24, 6))

    ctk.CTkLabel(
        dialog,
        text=f"Version {new_version} esta disponible.\n"
             "La app se va a reiniciar automaticamente al descargar.",
        justify="center",
    ).pack(pady=(0, 12))

    progress_bar = ctk.CTkProgressBar(dialog, width=360)
    progress_bar.pack(pady=(0, 6))
    progress_bar.set(0)

    status_lbl = ctk.CTkLabel(dialog, text="")
    status_lbl.pack()

    btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
    btn_frame.pack(pady=12)

    def on_update():
        update_btn.configure(state="disabled")
        skip_btn.configure(state="disabled")
        status_lbl.configure(text="Descargando...")

        def progress(downloaded, total):
            if total:
                parent.after(0, lambda d=downloaded, t=total: progress_bar.set(d / t))
                mb = downloaded / 1_048_576
                parent.after(0, lambda m=mb: status_lbl.configure(
                    text=f"Descargando... {m:.1f} MB"))

        def on_error(msg):
            parent.after(0, lambda: status_lbl.configure(
                text=f"No se pudo instalar automaticamente.", text_color=("red", "#ef5350")))
            parent.after(0, lambda: update_btn.configure(
                state="normal", text="Descargar desde web",
                command=lambda: webbrowser.open(RELEASES_URL)))
            parent.after(0, lambda: skip_btn.configure(state="normal"))

        download_and_apply(download_url, progress_cb=progress, error_cb=on_error)

    update_btn = ctk.CTkButton(
        btn_frame, text="Descargar e instalar",
        width=180, height=36, command=on_update,
    )
    update_btn.pack(side="left", padx=(0, 8))

    skip_btn = ctk.CTkButton(
        btn_frame, text="Ahora no",
        width=110, height=36,
        fg_color="transparent",
        hover_color=("gray80", "gray30"),
        command=dialog.destroy,
    )
    skip_btn.pack(side="left")
