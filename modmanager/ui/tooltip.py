from __future__ import annotations

import tkinter as tk


class ToolTip:
    def __init__(self, widget: tk.Misc, colors: dict[str, str], delay_ms: int = 350) -> None:
        self.widget = widget
        self.colors = colors
        self.delay_ms = delay_ms
        self._job: str | None = None
        self._tip: tk.Toplevel | None = None
        self._label: tk.Label | None = None
        self._text = ""
        self._x = 0
        self._y = 0

    def schedule(self, text: str, x_root: int, y_root: int) -> None:
        if not text:
            self.hide()
            return
        self._text = text
        self._x = x_root + 16
        self._y = y_root + 16
        if self._tip is not None:
            if self._label is not None:
                self._label.configure(text=self._text)
            self._position()
            return
        if self._job is None:
            self._job = self.widget.after(self.delay_ms, self._show)

    def update_text(self, text: str) -> None:
        if not text:
            self.hide()
            return
        self._text = text
        if self._label is not None:
            self._label.configure(text=self._text)

    def hide(self) -> None:
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None
            self._label = None

    def _show(self) -> None:
        self._job = None
        if not self._text:
            return
        tip = tk.Toplevel(self.widget.winfo_toplevel())
        tip.overrideredirect(True)
        tip.configure(bg=self.colors["line"])
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass
        label = tk.Label(
            tip,
            text=self._text,
            justify=tk.LEFT,
            bg=self.colors["panel2"],
            fg=self.colors["text"],
            padx=10,
            pady=7,
            font=("Microsoft YaHei UI", 9),
        )
        label.pack()
        self._tip = tip
        self._label = label
        self._position()

    def _position(self) -> None:
        if self._tip is None:
            return
        try:
            self._tip.geometry(f"+{self._x}+{self._y}")
        except tk.TclError:
            self._tip = None
