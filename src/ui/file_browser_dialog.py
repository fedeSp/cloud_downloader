"""Lazy file-browser dialog for selective download.

Shows a tree view of the remote (loaded level by level via rclone lsjson)
with tri-state checkboxes (☐ / ☑ / ⊟).  Returns a list of selected paths
where files are plain strings and unexpanded-but-checked directories carry
a trailing "/" so the download layer can match all their contents.
"""

from __future__ import annotations

import json
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import customtkinter as ctk

from config import PROVIDERS
from rclone import RCLONE_PATH, _popen_kwargs, extract_drive_folder_id


# ── Checkbox label helpers ────────────────────────────────────────────────────

_CHECK = {True: "☑", False: "☐", None: "⊟"}
_DIR_ICON  = "📁"
_FILE_ICON = "📄"
_LOADING_TEXT = "  ⏳ Cargando..."


class FileBrowserDialog(ctk.CTkToplevel):
    """Modal tree-browser dialog.  Read `.result` after `wait_window()`."""

    def __init__(self, parent, item: dict, export_fmt: str = ""):
        super().__init__(parent)
        self.title("Explorar archivos")
        self.geometry("720x540")
        self.minsize(520, 380)
        self.transient(parent)
        self.grab_set()
        # Center on parent
        self.update_idletasks()
        px, py = parent.winfo_x(), parent.winfo_y()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        self.geometry(f"+{px + (pw - 720) // 2}+{py + (ph - 540) // 2}")

        self._item       = item
        self._export_fmt = export_fmt
        self.result: list[str] | None = None  # set on confirm; None = cancelled

        # Per-node state
        self._check_state: dict[str, bool | None] = {}  # True/False/None(partial)
        self._node_path:   dict[str, str]          = {}  # relative rclone path
        self._node_isdir:  dict[str, bool]         = {}  # is directory?

        self._build_remote_info()
        self._build_ui()
        self._load_children("", "")  # kick off root load

        self.protocol("WM_DELETE_WINDOW", self._cancel)

    # ── Remote path computation ───────────────────────────────────────────────

    def _build_remote_info(self):
        provider = self._item["provider"]
        url      = self._item["url"]
        remote   = PROVIDERS[provider]["remote"]

        if provider == "drive":
            folder_id          = extract_drive_folder_id(url)
            self._remote_root  = f"{remote}:/"
            self._extra_args   = ["--drive-root-folder-id", folder_id]
            if self._export_fmt:
                self._extra_args += ["--drive-export-formats", self._export_fmt]
        elif provider == "onedrive":
            self._remote_root  = f"{remote}:/{url.strip('/')}"
            self._extra_args   = []
        elif provider == "dropbox":
            path               = url.strip("/")
            self._remote_root  = f"{remote}:/{path}" if path else f"{remote}:/"
            self._extra_args   = []
        else:
            self._remote_root  = f"{remote}:/{url.strip('/')}"
            self._extra_args   = []

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar ───────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 2))

        ctk.CTkLabel(
            top, text="Seleccioná los archivos a descargar:",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(side="left")

        ctk.CTkButton(
            top, text="Seleccionar todo", width=145, height=30,
            font=ctk.CTkFont(size=13),
            command=self._select_all,
        ).pack(side="right", padx=(4, 0))

        ctk.CTkButton(
            top, text="Deseleccionar todo", width=155, height=30,
            font=ctk.CTkFont(size=13),
            fg_color="transparent", hover_color=("gray80", "gray30"),
            command=self._deselect_all,
        ).pack(side="right")

        # ── Status line ───────────────────────────────────────────────
        self._status_var = tk.StringVar(value="Cargando…")
        ctk.CTkLabel(
            self, textvariable=self._status_var,
            text_color=("gray40", "gray60"),
            font=ctk.CTkFont(size=12),
            anchor="w",
        ).pack(fill="x", padx=14, pady=(2, 0))

        # ── Tree ──────────────────────────────────────────────────────
        tree_frame = ctk.CTkFrame(self)
        tree_frame.pack(fill="both", expand=True, padx=12, pady=6)

        # Themed treeview
        dark = ctk.get_appearance_mode() == "Dark"
        bg  = "#2b2b2b" if dark else "#f0f0f0"
        fg  = "#dce4ee" if dark else "#1a1a1a"
        sel = "#2a5298" if dark else "#3a7bd5"

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Browser.Treeview",
            background=bg, foreground=fg,
            fieldbackground=bg,
            borderwidth=0, rowheight=30,
            font=("Segoe UI", 12) if tk.TkVersion >= 8.6 else ("TkDefaultFont", 12),
        )
        style.configure("Browser.Treeview.Heading", background=bg, foreground=fg)
        style.map(
            "Browser.Treeview",
            background=[("selected", sel)],
            foreground=[("selected", "#ffffff")],
        )

        self._tree = ttk.Treeview(
            tree_frame, selectmode="none",
            show="tree", style="Browser.Treeview",
        )
        vsb = ttk.Scrollbar(tree_frame, orient="vertical",   command=self._tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        self._tree.pack(fill="both", expand=True)

        self._tree.bind("<<TreeviewOpen>>", self._on_expand)
        self._tree.bind("<Button-1>",       self._on_click)

        # ── Bottom buttons ────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=(2, 12))

        ctk.CTkButton(
            btn_frame, text="Confirmar selección", height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._confirm,
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkButton(
            btn_frame, text="Cancelar", height=40,
            font=ctk.CTkFont(size=14),
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray25"),
            command=self._cancel,
        ).pack(side="left", fill="x", expand=True)

    # ── rclone lsjson (lazy, per-folder) ─────────────────────────────────────

    def _remote_for(self, rel_path: str) -> str:
        """Build the full rclone remote string for a relative path."""
        root = self._remote_root.rstrip("/")
        if rel_path:
            return f"{root}/{rel_path}"
        return self._remote_root

    def _load_children(self, parent_node: str, rel_path: str):
        """Async: run lsjson for rel_path, then call _populate on the main thread."""
        remote = self._remote_for(rel_path)
        cmd    = [RCLONE_PATH, "lsjson", remote] + self._extra_args

        def run():
            try:
                res = subprocess.run(
                    cmd, capture_output=True, text=True, **_popen_kwargs()
                )
                if res.returncode == 0:
                    entries = json.loads(res.stdout or "[]")
                else:
                    entries = []
            except Exception:
                entries = []
            self.after(0, lambda: self._populate(parent_node, rel_path, entries))

        threading.Thread(target=run, daemon=True).start()

    def _populate(self, parent_node: str, parent_rel: str, entries: list):
        # Remove loading placeholder if present
        for child in self._tree.get_children(parent_node):
            if self._tree.item(child, "text") == _LOADING_TEXT:
                self._tree.delete(child)

        if not entries and not parent_node:
            self._status_var.set("La carpeta está vacía.")
            return

        # Sort: folders first, then files, both alphabetically
        entries.sort(key=lambda e: (not e["IsDir"], e["Name"].lower()))

        for entry in entries:
            name    = entry["Name"]
            is_dir  = entry["IsDir"]
            rel     = f"{parent_rel}/{name}".lstrip("/") if parent_rel else name
            icon    = _DIR_ICON if is_dir else _FILE_ICON
            state   = self._check_state.get(parent_node, False)
            check   = _CHECK[True if state is True else False]
            label   = f"{check}  {icon} {name}"

            node_id = self._tree.insert(parent_node, "end", text=label, open=False)
            self._check_state[node_id] = True if state is True else False
            self._node_path[node_id]   = rel
            self._node_isdir[node_id]  = is_dir

            if is_dir:
                # Insert a placeholder so the expand arrow is shown
                self._tree.insert(node_id, "end", text=_LOADING_TEXT)

        if not parent_node:
            total = len(entries)
            dirs  = sum(1 for e in entries if e["IsDir"])
            files = total - dirs
            self._status_var.set(
                f"{dirs} carpeta(s), {files} archivo(s) en la raíz"
            )

    # ── Tree events ───────────────────────────────────────────────────────────

    def _on_expand(self, _event):
        node_id  = self._tree.focus()
        children = self._tree.get_children(node_id)
        if len(children) == 1 and self._tree.item(children[0], "text") == _LOADING_TEXT:
            self._tree.delete(children[0])
            rel = self._node_path.get(node_id, "")
            self._load_children(node_id, rel)

    def _on_click(self, event):
        # Ignore clicks on the expand/collapse indicator
        element = self._tree.identify_element(event.x, event.y)
        if "indicator" in element:
            return
        node_id = self._tree.identify_row(event.y)
        if not node_id or node_id not in self._check_state:
            return
        current   = self._check_state[node_id]
        new_state = not current if current is not None else True
        self._set_subtree(node_id, new_state)
        self._refresh_parents(node_id)

    # ── Checkbox state management ─────────────────────────────────────────────

    def _set_subtree(self, node_id: str, state: bool):
        """Recursively set check state for node and all loaded descendants."""
        if node_id not in self._check_state:
            return
        self._check_state[node_id] = state
        self._redraw_label(node_id)
        for child in self._tree.get_children(node_id):
            self._set_subtree(child, state)

    def _refresh_parents(self, node_id: str):
        """Walk up and update parent tri-state based on children."""
        parent = self._tree.parent(node_id)
        if not parent:
            return
        children_states = [
            self._check_state[c]
            for c in self._tree.get_children(parent)
            if c in self._check_state
        ]
        if not children_states:
            return
        if all(s is True for s in children_states):
            new = True
        elif all(s is False for s in children_states):
            new = False
        else:
            new = None  # partial
        self._check_state[parent] = new
        self._redraw_label(parent)
        self._refresh_parents(parent)

    def _redraw_label(self, node_id: str):
        state   = self._check_state.get(node_id, False)
        is_dir  = self._node_isdir.get(node_id, False)
        name    = self._node_path.get(node_id, "").rsplit("/", 1)[-1]
        icon    = _DIR_ICON if is_dir else _FILE_ICON
        self._tree.item(node_id, text=f"{_CHECK[state]}  {icon} {name}")

    # ── Select/deselect all ───────────────────────────────────────────────────

    def _select_all(self):
        for node_id in self._tree.get_children(""):
            self._set_subtree(node_id, True)

    def _deselect_all(self):
        for node_id in self._tree.get_children(""):
            self._set_subtree(node_id, False)

    # ── Collect selected paths ────────────────────────────────────────────────

    def _collect(self) -> list[str]:
        """Return selected paths.

        - Plain files:          their relative path  (e.g. "folder/file.txt")
        - Checked dirs that were never expanded: path ending with "/"
          (the downloader will match all files under that prefix)
        """
        result: list[str] = []
        self._collect_nodes(self._tree.get_children(""), result)
        return result

    def _collect_nodes(self, nodes, result: list[str]):
        for node_id in nodes:
            if node_id not in self._check_state:
                continue
            state  = self._check_state[node_id]
            is_dir = self._node_isdir.get(node_id, False)

            if not is_dir:
                if state is True:
                    result.append(self._node_path[node_id])
            else:
                children = self._tree.get_children(node_id)
                has_real = any(
                    self._tree.item(c, "text") != _LOADING_TEXT
                    for c in children
                )
                if state is True and not has_real:
                    # Entire directory selected but never expanded
                    result.append(self._node_path[node_id] + "/")
                else:
                    self._collect_nodes(children, result)

    # ── Dialog result ─────────────────────────────────────────────────────────

    def _confirm(self):
        selected = self._collect()
        if not selected:
            if not messagebox.askyesno(
                "Sin selección",
                "No seleccionaste ningún archivo.\n\n"
                "¿Querés continuar sin filtro (descargar todo)?",
                parent=self,
            ):
                return
            selected = None  # None = download everything
        self.result = selected
        self.grab_release()
        self.destroy()

    def _cancel(self):
        self.result = None
        self.grab_release()
        self.destroy()


# ── Public helper ─────────────────────────────────────────────────────────────

def show_file_browser(parent, item: dict, export_fmt: str = "") -> list[str] | None:
    """Open modal browser, return selected paths or None (cancelled/download-all)."""
    dlg = FileBrowserDialog(parent, item, export_fmt)
    parent.wait_window(dlg)
    return dlg.result
