from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from ..costumes import describe_target
from ..i18n import Translator

COLUMNS = ("target", "costume", "winner", "others")
HEADING_KEYS = {
    "target": "target_file",
    "costume": "costume",
    "winner": "winner",
    "others": "overwritten",
}


class ConflictPanel(ttk.Frame):
    """Shows which mods overwrite the same target file and which mod wins."""

    def __init__(self, parent: tk.Misc, colors: dict[str, str], translator: Translator) -> None:
        super().__init__(parent, style="Panel.TFrame")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.translator = translator
        self._conflicts: list[dict] = []
        self._mods: dict[str, dict] = {}
        self._base_tags: dict[str, list[str]] = {}
        self._selected_mod_id: str | None = None

        self.title_label = ttk.Label(self, style="Panel.TLabel", font=("Microsoft YaHei UI", 11, "bold"))
        self.title_label.grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.tree = ttk.Treeview(
            self,
            columns=COLUMNS,
            show="headings",
            height=6,
            selectmode="none",
        )
        self.tree.column("target", width=300, minwidth=180, anchor="w", stretch=True)
        self.tree.column("costume", width=240, minwidth=150, anchor="w", stretch=True)
        self.tree.column("winner", width=260, minwidth=160, anchor="w", stretch=True)
        self.tree.column("others", width=300, minwidth=180, anchor="w", stretch=True)
        self.tree.grid(row=1, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        yscroll.grid(row=1, column=1, sticky="ns")
        xscroll = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.tree.xview)
        xscroll.grid(row=2, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.tag_configure(
            "selected-conflict", background=colors["partner_bg"], foreground=colors["partner_fg"]
        )
        self.tree.tag_configure("empty", foreground=colors["muted"])
        self.tree.tag_configure("even", background=colors["panel"])
        self.tree.tag_configure("odd", background=colors["stripe"])
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.tree.selection_remove(self.tree.selection()))
        self.set_language()

    def set_language(self) -> None:
        self.title_label.configure(text=self.translator.t("conflict_files"))
        for column in COLUMNS:
            self.tree.heading(column, text=self.translator.t(HEADING_KEYS[column]), anchor="w")
        self.refresh(self._conflicts, self._mods)

    def refresh(self, conflicts: list[dict], mods: dict[str, dict]) -> None:
        self._conflicts = conflicts
        self._mods = mods
        self._base_tags = {}
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not conflicts:
            self.tree.insert(
                "",
                tk.END,
                iid="empty",
                values=(self.translator.t("no_conflicts"), "", "", ""),
                tags=("empty",),
            )
            self._autosize_columns([(self.translator.t("no_conflicts"), "", "", "")])
            return

        rows = []
        for index, conflict in enumerate(conflicts):
            winner = mods.get(conflict["winner"], {}).get("name", conflict["winner"])
            losers = [mods.get(mod_id, {}).get("name", mod_id) for mod_id in conflict["losers"]]
            costume = describe_target(conflict["target"], self.translator.language) or "-"
            values = (conflict["target"], costume, winner, ", ".join(losers))
            rows.append(values)
            iid = f"conflict-{index}"
            tags = ["even" if index % 2 == 0 else "odd"]
            self._base_tags[iid] = tags
            self.tree.insert(
                "",
                tk.END,
                iid=iid,
                values=values,
                tags=tags,
            )

        self._autosize_columns(rows)
        self._apply_highlight()

    def set_selected_mod(self, mod_id: str | None) -> None:
        self._selected_mod_id = mod_id
        self._apply_highlight()

    def _apply_highlight(self) -> None:
        mod_id = self._selected_mod_id
        for index, conflict in enumerate(self._conflicts):
            iid = f"conflict-{index}"
            base = self._base_tags.get(iid, [])
            if mod_id and mod_id in conflict["mods"]:
                self.tree.item(iid, tags=("selected-conflict",))
            else:
                self.tree.item(iid, tags=tuple(base))

    def _autosize_columns(self, rows: list[tuple[str, str, str, str]]) -> None:
        try:
            font = tkfont.nametofont("TkDefaultFont")
        except tk.TclError:
            font = tkfont.Font(font=("Microsoft YaHei UI", 10))
        limits = {
            "target": (180, 520),
            "costume": (150, 360),
            "winner": (160, 420),
            "others": (180, 520),
        }
        for index, column in enumerate(COLUMNS):
            header = self.translator.t(HEADING_KEYS[column])
            measured = font.measure(header) + 36
            for row in rows:
                measured = max(measured, font.measure(str(row[index])) + 36)
            min_width, max_width = limits[column]
            self.tree.column(column, width=max(min_width, min(measured, max_width)))
