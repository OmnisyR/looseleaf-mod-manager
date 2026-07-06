from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from tkinterdnd2 import DND_FILES

from ..costumes import character_sort_key, costume_characters
from ..i18n import Translator
from .tooltip import ToolTip

DRAG_HANDLE = "⠿"


class ModListPanel(ttk.Frame):
    """Mod list tree: enable/disable, reordering by drag, and action buttons."""

    def __init__(
        self,
        parent: tk.Misc,
        colors: dict[str, str],
        translator: Translator,
        on_drop: Callable[[object], None],
        on_select: Callable[[str | None], None],
        on_toggle: Callable[[str], None],
        on_move: Callable[[str, int], None],
        on_delete: Callable[[str], None],
        on_open_data_dir: Callable[[], None],
        on_reorder: Callable[[list[str]], None],
    ) -> None:
        super().__init__(parent, style="Panel.TFrame")
        self.colors = colors
        self.translator = translator
        self.on_select = on_select
        self.on_toggle = on_toggle
        self.on_move = on_move
        self.on_delete = on_delete
        self.on_reorder = on_reorder
        self.selected_mod_id: str | None = None
        self.dragging_iid: str | None = None
        self.dragging_started = False
        self.dragging_last_target: str | None = None
        self._drag_values: tuple[str, ...] | None = None
        self._drag_tags: tuple[str, ...] | None = None
        self._drag_ghost: tk.Toplevel | None = None
        self._drag_ghost_width = 0
        self._drag_ghost_height = 0
        self._drag_origin_x = 0
        self._drag_offset_x = 0
        self._drag_offset_y = 0
        self._press_y = 0
        self._base_tags: dict[str, list[str]] = {}
        self._partner_ids: set[str] = set()
        self._last_mods: dict[str, dict] = {}
        self._last_order: list[str] = []
        self._last_conflict_counts: dict[str, int] = {}
        self._last_conflict_roles: dict[str, dict[str, int]] = {}
        self._hover_iid: str | None = None
        self._character_filter_key = ""
        self._character_filter_options: list[tuple[str, str]] = []

        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        header = ttk.Frame(self, style="Panel.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.columnconfigure(0, weight=1)
        self.drop_hint = ttk.Label(header, style="PanelMuted.TLabel")
        self.drop_hint.grid(row=0, column=0, sticky="w")
        self.character_filter_label = ttk.Label(header, style="PanelMuted.TLabel")
        self.character_filter_label.grid(row=0, column=1, sticky="e", padx=(8, 6))
        self.character_filter_combo = ttk.Combobox(header, state="readonly", width=24)
        self.character_filter_combo.grid(row=0, column=2, sticky="e")
        self.character_filter_combo.bind("<<ComboboxSelected>>", self._on_character_filter_selected)

        tree_holder = ttk.Frame(self, style="Panel.TFrame")
        tree_holder.grid(row=1, column=0, columnspan=2, sticky="nsew")
        tree_holder.rowconfigure(0, weight=1)
        tree_holder.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tree_holder,
            columns=("enabled", "name", "files", "conflicts"),
            show="headings",
            selectmode="browse",
        )
        self.tree.column("enabled", width=64, minwidth=58, anchor="center", stretch=False)
        self.tree.column("name", width=360, minwidth=180, anchor="w", stretch=True)
        self.tree.column("files", width=72, minwidth=60, anchor="center", stretch=False)
        self.tree.column("conflicts", width=72, minwidth=60, anchor="center", stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll = ttk.Scrollbar(tree_holder, orient=tk.VERTICAL, command=self.tree.yview)
        tree_scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.tag_configure("dragging", background=colors["drag_bg"], foreground=colors["drag_fg"])
        self.tree.tag_configure("drag-placeholder", background=colors["panel2"], foreground=colors["panel2"])
        self.tree.tag_configure("partner", background=colors["partner_bg"], foreground=colors["partner_fg"])
        self.tree.tag_configure("conflict-winner", background=colors["winner_bg"], foreground=colors["winner_fg"])
        self.tree.tag_configure("conflict-loser", background=colors["loser_bg"], foreground=colors["loser_fg"])
        self.tree.tag_configure("conflict-mixed", background=colors["mixed_bg"], foreground=colors["mixed_fg"])
        self.tree.tag_configure("disabled", foreground=colors["disabled"])
        self.tree.tag_configure("even", background=colors["panel"])
        self.tree.tag_configure("odd", background=colors["stripe"])

        self._tooltip = ToolTip(self.tree, colors)

        self.empty_hint = ttk.Label(tree_holder, style="PanelMuted.TLabel", justify=tk.CENTER)

        self.tree.drop_target_register(DND_FILES)
        self.tree.dnd_bind("<<Drop>>", on_drop)
        self.drop_target_register(DND_FILES)
        self.dnd_bind("<<Drop>>", on_drop)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<ButtonPress-1>", self._on_press)
        self.tree.bind("<B1-Motion>", self._on_drag)
        self.tree.bind("<ButtonRelease-1>", self._on_release)
        self.tree.bind("<Delete>", lambda _event: self._request_delete())
        self.tree.bind("<Return>", lambda _event: self._request_toggle())
        self.tree.bind("<space>", lambda _event: self._request_toggle())
        self.tree.bind("<Motion>", self._on_motion)
        self.tree.bind("<Leave>", self._on_leave)

        buttons = ttk.Frame(self, style="Panel.TFrame")
        buttons.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        buttons.columnconfigure(6, weight=1)
        self.toggle_button = ttk.Button(buttons, command=self._request_toggle)
        self.toggle_button.grid(row=0, column=0, padx=(0, 6))
        self.up_button = ttk.Button(buttons, command=lambda: self._request_move(-1))
        self.up_button.grid(row=0, column=1, padx=(0, 6))
        self.down_button = ttk.Button(buttons, command=lambda: self._request_move(1))
        self.down_button.grid(row=0, column=2, padx=(0, 6))
        self.delete_button = ttk.Button(buttons, command=self._request_delete)
        self.delete_button.grid(row=0, column=3, padx=(0, 6))
        self.open_data_button = ttk.Button(buttons, command=on_open_data_dir)
        self.open_data_button.grid(row=0, column=4)

        self.set_language()

    def set_language(self) -> None:
        self.drop_hint.configure(text=self.translator.t("drop_hint"))
        self.character_filter_label.configure(text=self.translator.t("character_filter"))
        self.tree.heading("enabled", text=self.translator.t("enabled"))
        self.tree.heading("name", text=self.translator.t("mod_column"))
        self.tree.heading("files", text=self.translator.t("files"))
        self.tree.heading("conflicts", text=self.translator.t("conflicts"))
        self.empty_hint.configure(text=self.translator.t("empty_mods"))
        self.toggle_button.configure(text=self.translator.t("toggle"))
        self.up_button.configure(text=self.translator.t("move_up"))
        self.down_button.configure(text=self.translator.t("move_down"))
        self.delete_button.configure(text=self.translator.t("delete"))
        self.open_data_button.configure(text=self.translator.t("open_data_dir"))
        if self._last_mods:
            self.refresh(
                self._last_mods,
                self._last_order,
                self._last_conflict_counts,
                self._last_conflict_roles,
                self.selected_mod_id,
            )

    def get_selected_mod_id(self) -> str | None:
        selection = self.tree.selection()
        if selection:
            return selection[0]
        return self.selected_mod_id

    def _request_toggle(self) -> None:
        mod_id = self.get_selected_mod_id()
        if mod_id:
            self.on_toggle(mod_id)

    def _request_move(self, direction: int) -> None:
        mod_id = self.get_selected_mod_id()
        if mod_id:
            self.on_move(mod_id, direction)

    def _request_delete(self) -> None:
        mod_id = self.get_selected_mod_id()
        if mod_id:
            self.on_delete(mod_id)

    def _on_tree_select(self, _event: object) -> None:
        self.selected_mod_id = self.get_selected_mod_id()
        self.on_select(self.selected_mod_id)

    def _on_double_click(self, event: object) -> None:
        row_id = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        if row_id and column in ("#1", "#2"):
            self.on_toggle(row_id)

    def _on_press(self, event: object) -> None:
        self._tooltip.hide()
        self.dragging_iid = self.tree.identify_row(event.y)
        self.dragging_started = False
        self.dragging_last_target = self.dragging_iid
        self._press_y = event.y

    def _on_drag(self, event: object) -> None:
        if not self.dragging_iid:
            return
        if not self.dragging_started:
            if abs(event.y - self._press_y) < 4:
                return
            self.dragging_started = True
            self._begin_drag_visual(event)
        self._move_drag_ghost(event)

        target_iid = self.tree.identify_row(event.y)
        if not target_iid or target_iid == self.dragging_last_target:
            return
        self.dragging_last_target = target_iid
        if target_iid == self.dragging_iid:
            return
        children = list(self.tree.get_children())
        target_index = children.index(target_iid)
        self.tree.move(self.dragging_iid, "", target_index)
        self.tree.selection_set(self.dragging_iid)

    def _on_release(self, _event: object) -> None:
        if self.dragging_started and self.dragging_iid:
            self._restore_dragged_row()
            self._destroy_drag_ghost()
            self.on_reorder(self._reordered_full_order())
        self.dragging_iid = None
        self.dragging_started = False
        self.dragging_last_target = None
        self._drag_values = None
        self._drag_tags = None

    def _begin_drag_visual(self, event: object) -> None:
        if not self.dragging_iid:
            return
        self._drag_values = tuple(str(value) for value in self.tree.item(self.dragging_iid, "values"))
        self._drag_tags = tuple(self.tree.item(self.dragging_iid, "tags"))
        self.tree.item(
            self.dragging_iid,
            values=("", "", "", ""),
            tags=("drag-placeholder",),
        )
        self._create_drag_ghost(event)

    def _restore_dragged_row(self) -> None:
        if not self.dragging_iid:
            return
        values = self._drag_values
        if values is not None:
            self.tree.item(self.dragging_iid, values=values)
        base = self._base_tags.get(self.dragging_iid)
        if base is not None:
            self.tree.item(self.dragging_iid, tags=tuple(base))
        elif self._drag_tags is not None:
            self.tree.item(self.dragging_iid, tags=self._drag_tags)

    def _create_drag_ghost(self, event: object) -> None:
        self._destroy_drag_ghost()
        if not self._drag_values:
            return
        bbox = self.tree.bbox(self.dragging_iid) if self.dragging_iid else ""
        if not bbox:
            return
        row_x, row_y, row_width, row_height = bbox
        row_left = self.tree.winfo_rootx() + row_x
        row_top = self.tree.winfo_rooty() + row_y
        self._drag_ghost_width = max(row_width, 1)
        self._drag_ghost_height = max(row_height, 1)
        self._drag_origin_x = row_left
        self._drag_offset_x = max(0, getattr(event, "x_root", row_left) - row_left)
        self._drag_offset_y = max(0, getattr(event, "y_root", row_top) - row_top)
        bg, fg = self._drag_row_colors()

        ghost = tk.Toplevel(self.winfo_toplevel())
        ghost.overrideredirect(True)
        ghost.configure(bg=bg)
        try:
            ghost.attributes("-topmost", True)
        except tk.TclError:
            pass

        frame = tk.Frame(
            ghost,
            bg=bg,
            highlightthickness=0,
            width=self._drag_ghost_width,
            height=self._drag_ghost_height,
        )
        frame.pack(fill=tk.BOTH, expand=True)
        frame.pack_propagate(False)

        label_specs = (
            ("enabled", self._drag_values[0], tk.CENTER),
            ("name", self._drag_values[1], tk.W),
            ("files", self._drag_values[2], tk.CENTER),
            ("conflicts", self._drag_values[3], tk.CENTER),
        )
        x = 0
        for index, (column_name, text, anchor) in enumerate(label_specs):
            width = int(self.tree.column(column_name, "width"))
            if index == len(label_specs) - 1:
                width = max(1, self._drag_ghost_width - x)
            label = tk.Label(
                frame,
                text=text,
                anchor=anchor,
                bg=bg,
                fg=fg,
                font=("Microsoft YaHei UI", 10),
                padx=8 if column_name == "name" else 0,
            )
            label.place(x=x, y=0, width=width, height=self._drag_ghost_height)
            x += width
            if x >= self._drag_ghost_width:
                break
        self._drag_ghost = ghost
        ghost.geometry(f"{self._drag_ghost_width}x{self._drag_ghost_height}+{row_left}+{row_top}")

    def _move_drag_ghost(self, event: object) -> None:
        if self._drag_ghost is None:
            return
        x = self._drag_origin_x
        y = getattr(event, "y_root", 0) - self._drag_offset_y
        self._drag_ghost.geometry(f"{self._drag_ghost_width}x{self._drag_ghost_height}+{x}+{y}")

    def _destroy_drag_ghost(self) -> None:
        if self._drag_ghost is None:
            return
        try:
            self._drag_ghost.destroy()
        except tk.TclError:
            pass
        self._drag_ghost = None

    def _drag_row_colors(self) -> tuple[str, str]:
        tags = set(self._drag_tags or ())
        if self.dragging_iid and self.dragging_iid in self.tree.selection():
            return (self.colors["selected_bg"], self.colors["selected_fg"])
        if "partner" in tags:
            return (self.colors["partner_bg"], self.colors["partner_fg"])
        if "conflict-winner" in tags:
            return (self.colors["winner_bg"], self.colors["winner_fg"])
        if "conflict-loser" in tags:
            return (self.colors["loser_bg"], self.colors["loser_fg"])
        if "conflict-mixed" in tags:
            return (self.colors["mixed_bg"], self.colors["mixed_fg"])
        background = self.colors["stripe"] if "odd" in tags else self.colors["panel"]
        foreground = self.colors["text"]
        if "disabled" in tags:
            foreground = self.colors["disabled"]
        return (background, foreground)

    def refresh(
        self,
        mods: dict[str, dict],
        order: list[str],
        conflict_counts: dict[str, int],
        conflict_roles: dict[str, dict[str, int]] | None = None,
        keep_selection: str | None = None,
    ) -> None:
        self._destroy_drag_ghost()
        self._tooltip.hide()
        self._hover_iid = None
        self._last_mods = mods
        self._last_order = order
        self._last_conflict_counts = conflict_counts
        self._last_conflict_roles = conflict_roles or {}
        self._refresh_character_filter(mods, order)
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._base_tags = {}

        visible_order = [mod_id for mod_id in order if self._mod_matches_character_filter(mods.get(mod_id))]
        for index, mod_id in enumerate(visible_order):
            mod = mods.get(mod_id)
            if not mod:
                continue
            enabled = mod.get("enabled", True)
            conflicts = conflict_counts.get(mod_id, 0)
            role_tag = self._role_tag(mod_id)
            tags = [role_tag] if role_tag else ["even" if index % 2 == 0 else "odd"]
            if not enabled:
                tags.append("disabled")
            self._base_tags[mod_id] = tags
            self.tree.insert(
                "",
                tk.END,
                iid=mod_id,
                values=(
                    self.translator.t("yes") if enabled else self.translator.t("no"),
                    f"{DRAG_HANDLE} {mod.get('name', mod_id)}",
                    len(mod.get("files", [])),
                    conflicts if conflicts else "",
                ),
                tags=tags,
            )

        self._apply_partner_highlight()

        visible_ids = set(visible_order)
        if keep_selection and keep_selection in visible_ids:
            self.tree.selection_set(keep_selection)
            self.tree.focus(keep_selection)
            self.tree.see(keep_selection)
            self.selected_mod_id = keep_selection
        elif self.tree.get_children():
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self.selected_mod_id = first
        else:
            self.selected_mod_id = None

        if self.tree.get_children():
            self.empty_hint.place_forget()
        else:
            self.empty_hint.place(relx=0.5, rely=0.5, anchor="center")

    def set_conflict_partners(self, mod_ids: set[str]) -> None:
        self._partner_ids = mod_ids
        self._apply_partner_highlight()

    def _apply_partner_highlight(self) -> None:
        children = set(self.tree.get_children())
        for mod_id, base in self._base_tags.items():
            if mod_id not in children:
                continue
            has_role_color = any(
                tag in base for tag in ("conflict-winner", "conflict-loser", "conflict-mixed")
            )
            if mod_id in self._partner_ids and not has_role_color:
                self.tree.item(mod_id, tags=("partner",))
            else:
                self.tree.item(mod_id, tags=tuple(base))

    def _role_tag(self, mod_id: str) -> str | None:
        roles = self._last_conflict_roles.get(mod_id, {})
        winners = int(roles.get("winner", 0) or 0)
        losers = int(roles.get("loser", 0) or 0)
        if winners and losers:
            return "conflict-mixed"
        if winners:
            return "conflict-winner"
        if losers:
            return "conflict-loser"
        return None

    def _on_motion(self, event: object) -> None:
        if self.dragging_started:
            self._tooltip.hide()
            return
        iid = self.tree.identify_row(event.y)
        if not iid:
            self._hover_iid = None
            self._tooltip.hide()
            return
        text = self._tooltip_text(iid)
        if iid != self._hover_iid:
            self._tooltip.hide()
            self._hover_iid = iid
        self._tooltip.schedule(text, event.x_root, event.y_root)

    def _on_leave(self, _event: object) -> None:
        self._hover_iid = None
        self._tooltip.hide()

    def _tooltip_text(self, mod_id: str) -> str:
        roles = self._last_conflict_roles.get(mod_id, {})
        winners = int(roles.get("winner", 0) or 0)
        losers = int(roles.get("loser", 0) or 0)
        lines = []
        if winners:
            lines.append(self.translator.t("mod_conflict_winner_tip", count=winners))
        if losers:
            lines.append(self.translator.t("mod_conflict_loser_tip", count=losers))
        return "\n".join(lines)

    def _refresh_character_filter(self, mods: dict[str, dict], order: list[str]) -> None:
        characters: dict[str, str] = {}
        for mod_id in order:
            mod = mods.get(mod_id)
            if not mod:
                continue
            for key, name in costume_characters(list(mod.get("files") or []), self.translator.language):
                characters.setdefault(key, name)

        self._character_filter_options = [("", self.translator.t("all_characters"))]
        self._character_filter_options.extend(
            (key, f"{name} ({key})")
            for key, name in sorted(characters.items(), key=lambda item: character_sort_key(item[0]))
        )
        valid_keys = {key for key, _label in self._character_filter_options}
        if self._character_filter_key not in valid_keys:
            self._character_filter_key = ""

        labels = [label for _key, label in self._character_filter_options]
        self.character_filter_combo.configure(
            values=labels,
            state="readonly" if len(labels) > 1 else tk.DISABLED,
        )
        selected_index = next(
            index
            for index, (key, _label) in enumerate(self._character_filter_options)
            if key == self._character_filter_key
        )
        self.character_filter_combo.set(labels[selected_index])

    def _on_character_filter_selected(self, _event: object) -> None:
        index = self.character_filter_combo.current()
        if index < 0 or index >= len(self._character_filter_options):
            return
        self._character_filter_key = self._character_filter_options[index][0]
        previous_selection = self.get_selected_mod_id()
        self.refresh(
            self._last_mods,
            self._last_order,
            self._last_conflict_counts,
            self._last_conflict_roles,
            previous_selection,
        )
        self.on_select(self.selected_mod_id)

    def _mod_matches_character_filter(self, mod: dict | None) -> bool:
        if not self._character_filter_key:
            return True
        if not mod:
            return False
        return any(
            key == self._character_filter_key
            for key, _name in costume_characters(list(mod.get("files") or []), self.translator.language)
        )

    def _reordered_full_order(self) -> list[str]:
        visible_order = list(self.tree.get_children())
        if not self._character_filter_key:
            return visible_order

        visible_iter = iter(visible_order)
        visible_set = set(visible_order)
        result: list[str] = []
        used: set[str] = set()
        for mod_id in self._last_order:
            if mod_id in visible_set:
                replacement = next(visible_iter, mod_id)
                result.append(replacement)
                used.add(replacement)
            else:
                result.append(mod_id)
                used.add(mod_id)
        result.extend(mod_id for mod_id in visible_order if mod_id not in used)
        return result
