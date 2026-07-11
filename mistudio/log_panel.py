"""MI Studio log panel."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class MiLogPanel(ttk.Frame):
    """Compact scrolling log styled like the mod manager log surface."""

    def __init__(self, parent: tk.Misc, colors: dict[str, str], height: int = 5) -> None:
        super().__init__(parent, style="Panel.TFrame", padding=(10, 8))
        self.colors = colors
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self.title_label = ttk.Label(self, style="Panel.TLabel", font=("Microsoft YaHei UI", 10, "bold"))
        self.title_label.grid(row=0, column=0, sticky="w", pady=(0, 6))

        body = ttk.Frame(self, style="Panel.TFrame")
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.text = tk.Text(
            body,
            height=height,
            bg=colors.get("log_bg", colors["bg"]),
            fg=colors["text"],
            insertbackground=colors["text"],
            relief=tk.FLAT,
            wrap=tk.WORD,
            font=("Consolas", 9),
            padx=8,
            pady=6,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=colors["line"],
            highlightcolor=colors["line"],
        )
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self.text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scroll.set)
        self.text.tag_configure("info", foreground=colors["muted"])
        self.text.tag_configure("status", foreground=colors["green"])
        self.text.tag_configure("error", foreground=colors["red"])
        self.text.tag_configure("time", foreground=colors["diff_missing_fg"])
        self.text.configure(state=tk.DISABLED)

    def set_title(self, text: str) -> None:
        self.title_label.configure(text=text)

    def append(self, timestamp: str, message: str, tag: str = "info") -> None:
        self.text.configure(state=tk.NORMAL)
        self.text.insert(tk.END, f"[{timestamp}] ", "time")
        self.text.insert(tk.END, message + "\n", tag)
        self.text.see(tk.END)
        self.text.configure(state=tk.DISABLED)

    def info(self, timestamp: str, message: str) -> None:
        self.append(timestamp, message, "info")

    def status(self, timestamp: str, message: str) -> None:
        self.append(timestamp, message, "status")

    def error(self, timestamp: str, message: str) -> None:
        self.append(timestamp, message, "error")
