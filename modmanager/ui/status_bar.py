from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..i18n import Translator


class StatusBar(ttk.Frame):
    """Bottom status line with live text plus a progress indicator for busy work."""

    def __init__(self, parent: tk.Misc, colors: dict[str, str], translator: Translator) -> None:
        super().__init__(parent, padding=(16, 6))
        self.colors = colors
        self.translator = translator
        self.columnconfigure(0, weight=1)

        self.status_label = ttk.Label(self, style="Muted.TLabel")
        self.status_label.grid(row=0, column=0, sticky="w")

        self.progress = ttk.Progressbar(
            self,
            mode="indeterminate",
            length=160,
            style="Status.Horizontal.TProgressbar",
        )
        self.progress.grid(row=0, column=1, sticky="e")
        self.progress.grid_remove()
        self.set_idle()

    def set_language(self) -> None:
        if not self.progress.winfo_ismapped():
            self.set_idle()

    def set_idle(self, text: str | None = None) -> None:
        self.progress.stop()
        self.progress.grid_remove()
        self.status_label.configure(text=text or self.translator.t("ready"), foreground=self.colors["muted"])

    def set_busy(self, text: str) -> None:
        self.status_label.configure(text=text, foreground=self.colors["accent"])
        self.progress.grid()
        self.progress.start(12)

    def set_error(self, text: str) -> None:
        self.progress.stop()
        self.progress.grid_remove()
        self.status_label.configure(text=text, foreground=self.colors["red"])
