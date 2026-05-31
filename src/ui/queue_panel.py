from tkinter import filedialog
import customtkinter as ctk

from config import PROVIDERS


class QueuePanel(ctk.CTkScrollableFrame):
    """Scrollable list of pending download items."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._items: list[dict] = []
        self._rows:  list       = []
        self.refresh()

    # ── Public API ────────────────────────────────────────────────────

    @property
    def items(self):
        return self._items

    def add(self, provider: str, url: str, dest: str):
        self._items.append({"provider": provider, "url": url, "dest": dest})
        self.refresh()

    def remove(self, idx: int):
        if 0 <= idx < len(self._items):
            self._items.pop(idx)
        self.refresh()

    def choose_dest(self, idx: int):
        folder = filedialog.askdirectory()
        if folder and 0 <= idx < len(self._items):
            self._items[idx]["dest"] = folder
            self.refresh()

    # ── Internal ──────────────────────────────────────────────────────

    def refresh(self):
        for widget in self._rows:
            widget.destroy()
        self._rows.clear()

        if not self._items:
            lbl = ctk.CTkLabel(
                self,
                text="Cola vacia. Agrega URLs con el boton + Agregar.",
                text_color=("gray50", "gray60"),
            )
            lbl.pack(pady=10)
            self._rows.append(lbl)
            return

        icons = {"drive": "Drive", "onedrive": "OneDrive", "dropbox": "Dropbox"}
        for i, item in enumerate(self._items):
            row = ctk.CTkFrame(self, corner_radius=6)
            row.pack(fill="x", padx=4, pady=2)
            self._rows.append(row)

            # — URL row —
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
                command=lambda ix=i: self.remove(ix),
            ).pack(side="right", padx=6, pady=(6, 2))

            # — Destination row —
            dest_row = ctk.CTkFrame(row, fg_color="transparent")
            dest_row.pack(fill="x", pady=(0, 4))

            dest_text  = item["dest"] if item["dest"] else "Sin destino"
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
                command=lambda ix=i: self.choose_dest(ix),
            ).pack(side="right", padx=6)
