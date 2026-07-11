"""Manager-style selection indicator for ttk.Treeview.

Mirrors the mod manager's mod list: a 3px accent rail on the left edge plus
1px top/bottom lines around the focused row, drawn as overlay frames. This
keeps row background colors (state badges, diff highlights) fully visible
instead of flooding the row with a selection fill.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class SelectionRail:
    def __init__(
        self,
        holder: tk.Misc,
        tree: ttk.Treeview,
        scrollbar: ttk.Scrollbar,
        colors: dict[str, str],
    ) -> None:
        self.tree = tree
        self.scrollbar = scrollbar
        self.rail = tk.Frame(holder, bg=colors["selection_rail"], width=3)
        self.top_line = tk.Frame(holder, bg=colors["selection_line"], height=1)
        self.bottom_line = tk.Frame(holder, bg=colors["selection_line"], height=1)
        self._job: str | None = None

        # Route scrolling through this helper so the indicator tracks the view.
        scrollbar.configure(command=self._on_scroll)
        tree.configure(yscrollcommand=self._on_yview)
        for sequence in (
            "<<TreeviewSelect>>",
            "<<TreeviewOpen>>",
            "<<TreeviewClose>>",
            "<Configure>",
            "<Visibility>",
            "<ButtonRelease-1>",
            "<KeyRelease>",
            "<MouseWheel>",
            "<Button-4>",
            "<Button-5>",
        ):
            tree.bind(sequence, lambda _e: self.schedule(), add="+")
        tree.bind("<Destroy>", self._on_destroy, add="+")
        self.schedule()

    def _on_scroll(self, *args: object) -> None:
        self.tree.yview(*args)
        self.schedule()

    def _on_yview(self, first: str, last: str) -> None:
        self.scrollbar.set(first, last)
        self.schedule()

    def schedule(self) -> None:
        if self._job is not None:
            try:
                self.tree.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        if not self.tree.winfo_exists():
            return
        try:
            self._job = self.tree.after(1, self._update)
        except tk.TclError:
            self._job = None

    def _cancel_job(self) -> None:
        if self._job is None:
            return
        try:
            self.tree.after_cancel(self._job)
        except tk.TclError:
            pass
        self._job = None

    def _on_destroy(self, event: object) -> None:
        if getattr(event, "widget", None) is self.tree:
            self._cancel_job()

    def update_now(self) -> None:
        self._cancel_job()
        try:
            self._update()
        except tk.TclError:
            self._job = None

    def _hide(self) -> None:
        self.rail.place_forget()
        self.top_line.place_forget()
        self.bottom_line.place_forget()

    def _update(self) -> None:
        self._job = None
        try:
            selection = self.tree.selection()
            iid = self.tree.focus()
            if iid not in selection:
                iid = selection[0] if selection else ""
            bbox = self.tree.bbox(iid) if iid else None
        except tk.TclError:
            return
        if not bbox:
            self._hide()
            return
        _x, y, _width, height = bbox
        height = max(1, int(height))
        tree_height = max(1, int(self.tree.winfo_height()))
        tree_width = max(1, int(self.tree.winfo_width()))
        top_y = max(0, int(y))
        bottom_y = min(tree_height - 1, int(y) + height - 1)
        if bottom_y < top_y:
            self._hide()
            return
        visible_height = max(1, bottom_y - top_y + 1)
        self.rail.place(in_=self.tree, x=0, y=top_y, width=3, height=visible_height)
        self.top_line.place(in_=self.tree, x=0, y=top_y, width=tree_width, height=1)
        self.bottom_line.place(in_=self.tree, x=0, y=bottom_y, width=tree_width, height=1)
        self.rail.lift()
        self.top_line.lift()
        self.bottom_line.lift()
