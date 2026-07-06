from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class LogPanel(ttk.Frame):
    """Scrolling log with color-coded lines (info / status / error)."""

    def __init__(self, parent: tk.Misc, colors: dict[str, str], height: int = 9) -> None:
        super().__init__(parent, style="Panel.TFrame")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.text = tk.Text(
            self,
            height=height,
            bg=colors.get("log_bg", colors["bg"]),
            fg=colors["text"],
            insertbackground=colors["text"],
            relief=tk.FLAT,
            wrap=tk.WORD,
            font=("Consolas", 9),
        )
        self.text.grid(row=0, column=0, sticky="nsew")
        self.text.tag_configure("info", foreground=colors["muted"])
        self.text.tag_configure("status", foreground=colors["green"])
        self.text.tag_configure("error", foreground=colors["red"])
        self.text.configure(state=tk.DISABLED)

    def _append(self, message: str, tag: str) -> None:
        self.text.configure(state=tk.NORMAL)
        self.text.insert(tk.END, message + "\n", tag)
        self.text.see(tk.END)
        self.text.configure(state=tk.DISABLED)

    def info(self, message: str) -> None:
        self._append(message, "info")

    def status(self, message: str) -> None:
        self._append(message, "status")

    def error(self, message: str) -> None:
        self._append(message, "error")
