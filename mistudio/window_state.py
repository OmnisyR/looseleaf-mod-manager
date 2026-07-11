"""Window geometry persistence for MI Studio."""
from __future__ import annotations

import tkinter as tk
from typing import Any

from modmanager.ui.screen import sanitize_geometry_for

MI_STUDIO_GEOMETRY_KEY = "mi_studio_geometry"
MI_STUDIO_STATE_KEY = "mi_studio_state"
MI_STUDIO_DEFAULT_GEOMETRY = "1500x920"


class WindowState:
    def __init__(self, root: tk.Tk, config: Any) -> None:
        self.root = root
        self.config = config
        # A position saved on a monitor that is no longer connected would open
        # the window fully off-screen (it looks like a black window).
        self.last_normal_geometry = sanitize_geometry_for(
            root,
            str(config.get_window_value(MI_STUDIO_GEOMETRY_KEY, MI_STUDIO_DEFAULT_GEOMETRY)),
            MI_STUDIO_DEFAULT_GEOMETRY,
        )
        self.ready = False
        self._zoom_job: str | None = None

    def apply_initial_geometry(self) -> None:
        self.root.geometry(self.last_normal_geometry)

    def restore(self) -> None:
        state = self.config.get_window_value(MI_STUDIO_STATE_KEY, "normal")
        if state == "zoomed":
            # Zooming before the window is first mapped leaves it unpainted
            # (black) and can maximize onto the wrong monitor. Wait until the
            # window is actually visible at its normal geometry, then zoom —
            # Windows then maximizes onto the monitor the window is on.
            attempts = [0]

            def zoom() -> None:
                self._zoom_job = None
                try:
                    if not self.root.winfo_viewable() and attempts[0] < 25:
                        attempts[0] += 1
                        self._zoom_job = self.root.after(80, zoom)
                        return
                    if self.root.state() == "normal":
                        self.root.state("zoomed")
                except tk.TclError:
                    pass

            try:
                self._zoom_job = self.root.after(80, zoom)
            except tk.TclError:
                pass
        self.ready = True

    def cancel_pending(self) -> None:
        if self._zoom_job is None:
            return
        try:
            self.root.after_cancel(self._zoom_job)
        except tk.TclError:
            pass
        self._zoom_job = None

    def on_configure(self, event: object) -> None:
        if not self.ready or getattr(event, "widget", None) is not self.root:
            return
        try:
            if self.root.state() == "normal":
                self.last_normal_geometry = self.root.geometry()
        except tk.TclError:
            pass

    def save(self) -> None:
        try:
            state = self.root.state()
        except tk.TclError:
            state = "normal"
        self.config.set_window_value(MI_STUDIO_STATE_KEY, "zoomed" if state == "zoomed" else "normal")
        self.config.set_window_value(MI_STUDIO_GEOMETRY_KEY, self.last_normal_geometry or self.root.geometry())
        self.config.save()
