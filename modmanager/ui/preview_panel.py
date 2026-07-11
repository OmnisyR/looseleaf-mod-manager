from __future__ import annotations
import tkinter as tk
from collections import OrderedDict
from pathlib import Path
from tkinter import ttk
from typing import Callable

from PIL import Image, ImageDraw, ImageOps, ImageSequence, ImageTk
from tkinterdnd2 import DND_FILES

from ..costumes import ModifiedAsset, modified_assets
from ..i18n import Translator
from ..pathutils import normalize_key
from .tooltip import ToolTip

CHECKER_SIZE = 12
RESIZE_DEBOUNCE_MS = 100
FRAME_CACHE_LIMIT = 6

MODEL_INFO_SECTION_LABELS = {
    "zh_CN": {
        "Animation": "动画",
        "Bounding": "包围盒",
        "Collider": "碰撞体",
        "DrivenKeys": "驱动关键帧",
        "DynamicBone": "动态骨骼",
        "DynamicBoneCollider": "动态骨骼碰撞",
        "Extra": "额外参数",
        "Lights": "灯光",
        "Locators": "挂点",
        "LOD": "LOD",
        "LookIK": "视线 IK",
        "Occluder": "遮挡",
        "TwoBoneIK": "双骨骼 IK",
    },
    "en": {
        "Animation": "Animation",
        "Bounding": "Bounds",
        "Collider": "Collider",
        "DrivenKeys": "Driven Keys",
        "DynamicBone": "Dynamic Bone",
        "DynamicBoneCollider": "Dynamic Bone Collider",
        "Extra": "Extra",
        "Lights": "Lights",
        "Locators": "Locators",
        "LOD": "LOD",
        "LookIK": "Look IK",
        "Occluder": "Occluder",
        "TwoBoneIK": "Two Bone IK",
    },
}

MODEL_INFO_FIELD_LABELS = {
    "zh_CN": {
        "axis_x": "轴向 X",
        "axis_y": "轴向 Y",
        "axis_z": "轴向 Z",
        "collision_radius": "碰撞半径",
        "damping": "阻尼",
        "damping_max": "最大阻尼",
        "damping_min": "最小阻尼",
        "damping_velocity_ratio": "速度阻尼比",
        "freeze_axis": "冻结轴",
        "gravity": "重力",
        "ignore_collision": "忽略碰撞",
        "is_disable": "禁用",
        "length_limit": "长度限制",
        "look_offset_x": "视线偏移 X",
        "look_offset_y": "视线偏移 Y",
        "look_offset_z": "视线偏移 Z",
        "mid_rot_max": "中段最大旋转",
        "mid_rot_min": "中段最小旋转",
        "name": "名称",
        "node": "节点",
        "off_x": "位置 X",
        "off_y": "位置 Y",
        "off_z": "位置 Z",
        "offset_x": "偏移 X",
        "offset_y": "偏移 Y",
        "offset_z": "偏移 Z",
        "offset_rot_x": "旋转偏移 X",
        "offset_rot_y": "旋转偏移 Y",
        "offset_rot_z": "旋转偏移 Z",
        "param0": "参数 0",
        "param1": "参数 1",
        "param2": "参数 2",
        "param3": "参数 3",
        "resilience": "弹性",
        "root_rot_max": "根部最大旋转",
        "root_rot_min": "根部最小旋转",
        "rot_x": "旋转 X",
        "rot_y": "旋转 Y",
        "rot_z": "旋转 Z",
        "rotation_limit": "旋转限制",
        "rx_limit_max": "X 最大限制",
        "rx_limit_min": "X 最小限制",
        "ry_limit_max": "Y 最大限制",
        "ry_limit_min": "Y 最小限制",
        "size": "大小",
        "stretch_limit": "拉伸限制",
        "stretch_resilience": "拉伸弹性",
        "target": "目标",
        "type": "类型",
        "up_vec_x": "上方向 X",
        "up_vec_y": "上方向 Y",
        "up_vec_z": "上方向 Z",
        "wind_influence": "风影响",
    },
    "en": {
        "axis_x": "Axis X",
        "axis_y": "Axis Y",
        "axis_z": "Axis Z",
        "collision_radius": "Collision Radius",
        "damping": "Damping",
        "damping_max": "Max Damping",
        "damping_min": "Min Damping",
        "damping_velocity_ratio": "Velocity Damping Ratio",
        "freeze_axis": "Freeze Axis",
        "gravity": "Gravity",
        "ignore_collision": "Ignore Collision",
        "is_disable": "Disabled",
        "length_limit": "Length Limit",
        "look_offset_x": "Look Offset X",
        "look_offset_y": "Look Offset Y",
        "look_offset_z": "Look Offset Z",
        "mid_rot_max": "Mid Max Rotation",
        "mid_rot_min": "Mid Min Rotation",
        "name": "Name",
        "node": "Node",
        "off_x": "Position X",
        "off_y": "Position Y",
        "off_z": "Position Z",
        "offset_x": "Offset X",
        "offset_y": "Offset Y",
        "offset_z": "Offset Z",
        "offset_rot_x": "Rotation Offset X",
        "offset_rot_y": "Rotation Offset Y",
        "offset_rot_z": "Rotation Offset Z",
        "param0": "Param 0",
        "param1": "Param 1",
        "param2": "Param 2",
        "param3": "Param 3",
        "resilience": "Resilience",
        "root_rot_max": "Root Max Rotation",
        "root_rot_min": "Root Min Rotation",
        "rot_x": "Rotation X",
        "rot_y": "Rotation Y",
        "rot_z": "Rotation Z",
        "rotation_limit": "Rotation Limit",
        "rx_limit_max": "Max X Limit",
        "rx_limit_min": "Min X Limit",
        "ry_limit_max": "Max Y Limit",
        "ry_limit_min": "Min Y Limit",
        "size": "Size",
        "stretch_limit": "Stretch Limit",
        "stretch_resilience": "Stretch Resilience",
        "target": "Target",
        "type": "Type",
        "up_vec_x": "Up Vector X",
        "up_vec_y": "Up Vector Y",
        "up_vec_z": "Up Vector Z",
        "wind_influence": "Wind Influence",
    },
}


class PreviewPanel(ttk.Frame):
    """Preview image (with GIF/WebP animation) plus the selected-mod summary."""

    def __init__(
        self,
        parent: tk.Misc,
        colors: dict[str, str],
        translator: Translator,
        on_choose_file: Callable[[], None],
        on_choose_url: Callable[[], None],
        on_drop: Callable[[object], None],
        model_info_diff_enabled: bool = False,
        on_model_info_diff_toggle: Callable[[bool], None] | None = None,
        on_model_info_hover: Callable[[str], None] | None = None,
        get_model_info_diff: Callable[[str], dict[str, object] | None] | None = None,
    ) -> None:
        super().__init__(parent, style="Panel.TFrame")
        self.colors = colors
        self.translator = translator
        self._closed = False
        self.animation_job: str | None = None
        self.frames: list[ImageTk.PhotoImage] = []
        self.frame_durations: list[int] = []
        self.frame_index = 0
        self.current_image: ImageTk.PhotoImage | None = None
        self.canvas_image_id: int | None = None
        self._resize_job: str | None = None
        self._last_rendered_size: tuple[int, int] | None = None
        self._checker_cache: tuple[int, int, ImageTk.PhotoImage] | None = None
        self._frame_cache: OrderedDict[tuple, tuple[list[ImageTk.PhotoImage], list[int]]] = OrderedDict()
        self._pending_mod: dict | None = None
        self._pending_preview_path: Path | None = None
        self._costume_conflicts: dict[str, dict[str, object]] = {}
        self._costume_iid_conflicts: dict[str, dict[str, object]] = {}
        self._model_info_diffs: dict[str, dict[str, object]] = {}
        self._model_info_iid_targets: dict[str, str] = {}
        self._hover_costume_iid: str | None = None
        self._visible_model_info_job: str | None = None
        self._asset_filter_key = "costumes"
        self._asset_filter_options: list[tuple[str, str]] = []
        self._model_info_diff_var: tk.BooleanVar | None = tk.BooleanVar(value=model_info_diff_enabled)
        self._on_model_info_diff_toggle = on_model_info_diff_toggle
        self._on_model_info_hover = on_model_info_hover
        self._get_model_info_diff = get_model_info_diff

        self.rowconfigure(2, weight=3)
        self.rowconfigure(3, weight=1)
        self.columnconfigure(0, weight=1)

        header = ttk.Frame(self, style="Panel.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        self.title_label = ttk.Label(header, style="Panel.TLabel", font=("Microsoft YaHei UI", 11, "bold"))
        self.title_label.grid(row=0, column=0, sticky="w")
        self.choose_button = ttk.Button(header, command=on_choose_file)
        self.choose_button.grid(row=0, column=1, sticky="e")
        self.url_button = ttk.Button(header, command=on_choose_url)
        self.url_button.grid(row=0, column=2, sticky="e", padx=(6, 0))

        self.status_label = ttk.Label(self, style="PanelMuted.TLabel")
        self.status_label.grid(row=1, column=0, sticky="w", pady=(8, 8))

        self.canvas = tk.Canvas(
            self,
            bg=colors["panel2"],
            highlightthickness=1,
            highlightbackground=colors["line"],
            height=260,
        )
        self.canvas.grid(row=2, column=0, sticky="nsew")
        self.canvas.drop_target_register(DND_FILES)
        self.canvas.dnd_bind("<<Drop>>", on_drop)
        self.canvas.bind("<Configure>", self._on_configure)

        selected_box = ttk.Frame(self, style="Panel.TFrame")
        selected_box.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        selected_box.columnconfigure(1, weight=1)
        selected_box.rowconfigure(3, weight=1)
        self.current_mod_label = ttk.Label(selected_box, style="PanelMuted.TLabel")
        self.current_mod_label.grid(row=0, column=0, sticky="w")
        self.selected_label = ttk.Label(selected_box, text="-", style="Panel.TLabel")
        self.selected_label.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.file_count_title = ttk.Label(selected_box, style="PanelMuted.TLabel")
        self.file_count_title.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.file_count_label = ttk.Label(selected_box, text="-", style="Panel.TLabel")
        self.file_count_label.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(4, 0))
        self.costume_title = ttk.Label(selected_box, style="PanelMuted.TLabel")
        self.costume_title.grid(row=2, column=0, sticky="w", pady=(10, 4))
        asset_controls = ttk.Frame(selected_box, style="Panel.TFrame")
        asset_controls.grid(row=2, column=1, sticky="e", pady=(10, 4))
        self.model_info_diff_check = ttk.Checkbutton(
            asset_controls,
            variable=self._model_info_diff_var,
            command=self._on_model_info_diff_changed,
        )
        self.model_info_diff_check.grid(row=0, column=0, sticky="e", padx=(0, 8))
        self.asset_filter_combo = ttk.Combobox(selected_box, state="readonly", width=18)
        self.asset_filter_combo.grid(row=0, column=1, sticky="e")
        self.asset_filter_combo.bind("<<ComboboxSelected>>", self._on_asset_filter_selected)

        tree_holder = ttk.Frame(selected_box, style="Panel.TFrame")
        tree_holder.grid(row=3, column=0, columnspan=2, sticky="nsew")
        tree_holder.rowconfigure(0, weight=1)
        tree_holder.columnconfigure(0, weight=1)
        self.costume_tree = ttk.Treeview(
            tree_holder,
            columns=("status", "name", "file"),
            show="headings",
            height=7,
            selectmode="none",
        )
        self.costume_tree.column("status", width=96, minwidth=82, anchor="center", stretch=False)
        self.costume_tree.column("name", width=220, minwidth=150, anchor="w", stretch=True)
        self.costume_tree.column("file", width=150, minwidth=120, anchor="w", stretch=True)
        self.costume_tree.grid(row=0, column=0, sticky="nsew")
        self.costume_scroll = ttk.Scrollbar(tree_holder, orient=tk.VERTICAL, command=self._on_costume_scroll)
        self.costume_scroll.grid(row=0, column=1, sticky="ns")
        self.costume_tree.configure(yscrollcommand=self._on_costume_yview)
        self.costume_tree.tag_configure("recognized", background=colors["panel"])
        self.costume_tree.tag_configure("unrecognized", background=colors["stripe"], foreground=colors["muted"])
        self.costume_tree.tag_configure("costume-winner", background=colors["winner_bg"], foreground=colors["winner_fg"])
        self.costume_tree.tag_configure("costume-loser", background=colors["loser_bg"], foreground=colors["loser_fg"])
        self.costume_tree.tag_configure("costume-mixed", background=colors["mixed_bg"], foreground=colors["mixed_fg"])
        self.costume_tree.tag_configure("model-info-changed", background=colors["diff_changed_bg"], foreground=colors["diff_changed_fg"])
        self.costume_tree.tag_configure("model-info-identical", background=colors["diff_same_bg"], foreground=colors["diff_same_fg"])
        self.costume_tree.tag_configure("model-info-missing", foreground=colors["diff_missing_fg"])
        self.costume_tree.tag_configure("model-info-error", foreground=colors["diff_error_fg"])
        self.costume_tree.tag_configure("model-info-loading", background=colors["stripe"], foreground=colors["muted"])
        self.costume_tree.tag_configure("empty", foreground=colors["muted"])
        self.costume_tree.bind("<Motion>", self._on_costume_motion)
        self.costume_tree.bind("<Leave>", self._on_costume_leave)
        self.costume_tree.bind("<<TreeviewSelect>>", lambda _event: self.costume_tree.selection_remove(self.costume_tree.selection()))
        self._costume_tooltip = ToolTip(self.costume_tree, colors)

        self.set_language()

    def set_language(self) -> None:
        self.title_label.configure(text=self.translator.t("preview"))
        self.choose_button.configure(text=self.translator.t("choose_preview"))
        self.url_button.configure(text=self.translator.t("preview_url_button"))
        self.current_mod_label.configure(text=self.translator.t("current_mod"))
        self.file_count_title.configure(text=self.translator.t("file_count"))
        self.costume_title.configure(text=self.translator.t("modified_assets"))
        self.model_info_diff_check.configure(text=self.translator.t("model_info_diff_toggle"))
        self._refresh_asset_filter_combo()
        self.costume_tree.heading("status", text=self.translator.t("costume_status"), anchor="w")
        self.costume_tree.heading("name", text=self.translator.t("asset_name"), anchor="w")
        self.costume_tree.heading("file", text=self.translator.t("costume_file"), anchor="w")
        self.status_label.configure(
            text=self.translator.t("preview_ready") if self._pending_mod else self.translator.t("preview_help")
        )
        self._refresh_costume_tree(self._pending_mod)
        self._render()

    def _refresh_asset_filter_combo(self) -> None:
        self._asset_filter_options = [
            ("costumes", self.translator.t("asset_filter_costumes")),
            ("model_info", self.translator.t("asset_filter_model_info")),
            ("textures", self.translator.t("asset_filter_textures")),
            ("all", self.translator.t("asset_filter_all")),
        ]
        labels = [label for _key, label in self._asset_filter_options]
        self.asset_filter_combo.configure(values=labels)
        selected_index = next(
            (
                index
                for index, (key, _label) in enumerate(self._asset_filter_options)
                if key == self._asset_filter_key
            ),
            0,
        )
        self.asset_filter_combo.set(labels[selected_index])

    def _on_asset_filter_selected(self, _event: object) -> None:
        index = self.asset_filter_combo.current()
        if index < 0 or index >= len(self._asset_filter_options):
            return
        self._asset_filter_key = self._asset_filter_options[index][0]
        self._refresh_costume_tree(self._pending_mod)

    def _on_model_info_diff_changed(self) -> None:
        if self._closed or self._model_info_diff_var is None:
            return
        if self._on_model_info_diff_toggle is not None:
            self._on_model_info_diff_toggle(bool(self._model_info_diff_var.get()))
        else:
            self._refresh_costume_tree(self._pending_mod)

    def set_model_info_diff_enabled(self, enabled: bool) -> None:
        if self._closed or self._model_info_diff_var is None:
            return
        self._model_info_diff_var.set(bool(enabled))
        if enabled:
            self._schedule_visible_model_info_rows()

    def show(
        self,
        mod: dict | None,
        preview_path: Path | None,
        costume_conflicts: dict[str, dict[str, object]] | None = None,
        model_info_diffs: dict[str, dict[str, object]] | None = None,
    ) -> None:
        self._pending_mod = mod
        self._pending_preview_path = preview_path
        self._costume_conflicts = costume_conflicts or {}
        self._model_info_diffs = model_info_diffs or {}
        if mod:
            self.selected_label.configure(text=mod.get("name", "-"))
            self.file_count_label.configure(text=str(len(mod.get("files", []))))
            self.status_label.configure(text=self.translator.t("preview_ready"))
        else:
            self.selected_label.configure(text="-")
            self.file_count_label.configure(text="-")
            self.status_label.configure(text=self.translator.t("preview_help"))
        self._refresh_costume_tree(mod)
        self._render()

    def update_model_info_diff_for_target(self, target: str, diff: dict[str, object]) -> None:
        target_key = normalize_key(target)
        self._model_info_diffs[target_key] = diff
        for iid, row_target in self._model_info_iid_targets.items():
            if normalize_key(row_target) != target_key or not self.costume_tree.exists(iid):
                continue
            self._update_model_info_row(iid, diff)
            if iid == self._hover_costume_iid:
                self._costume_tooltip.update_text(self._costume_tooltip_text(iid))

    def _refresh_costume_tree(self, mod: dict | None) -> None:
        self._costume_tooltip.hide()
        self._hover_costume_iid = None
        self._costume_iid_conflicts = {}
        self._model_info_iid_targets = {}
        for item in self.costume_tree.get_children():
            self.costume_tree.delete(item)
        if not mod:
            self.costume_tree.insert("", tk.END, values=("-", "-", "-"), tags=("empty",))
            return

        changes = modified_assets(list(mod.get("files") or []), self._asset_filter_key, self.translator.language)
        if not changes:
            self.costume_tree.insert(
                "",
                tk.END,
                values=("", self.translator.t("no_modified_assets"), ""),
                tags=("empty",),
            )
            return

        for index, change in enumerate(changes):
            tags = []
            status = self._asset_status_text(change)
            conflict = self._costume_conflicts.get(normalize_key(change.target))
            model_info_diff = self._model_info_diffs.get(normalize_key(change.target))
            if conflict:
                role = str(conflict.get("role") or "")
                if role == "winner":
                    tags.append("costume-winner")
                    status = self.translator.t("costume_status_winner")
                elif role == "loser":
                    tags.append("costume-loser")
                    status = self.translator.t("costume_status_loser")
                else:
                    tags.append("costume-mixed")
                    status = self.translator.t("costume_status_mixed")
            elif model_info_diff:
                status = self._model_info_diff_status_text(model_info_diff)
                tags.append(self._model_info_diff_tag(model_info_diff))
            else:
                tags.append("recognized" if change.recognized else "unrecognized")
            iid = f"costume-{index}"
            self.costume_tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(status, change.display_name, change.file_name),
                tags=tuple(tags),
            )
            if conflict:
                self._costume_iid_conflicts[iid] = conflict
            if change.kind == "model_info":
                self._model_info_iid_targets[iid] = change.target
        self._schedule_visible_model_info_rows()

    def _asset_status_text(self, change: ModifiedAsset) -> str:
        if self._asset_filter_key == "all":
            return self.translator.t(f"asset_kind_{change.kind}")
        return self.translator.t("recognized" if change.recognized else "unrecognized")

    def _on_costume_scroll(self, *args: object) -> None:
        self.costume_tree.yview(*args)
        self._schedule_visible_model_info_rows()

    def _on_costume_yview(self, first: str, last: str) -> None:
        self.costume_scroll.set(first, last)
        self._schedule_visible_model_info_rows()

    def _schedule_visible_model_info_rows(self) -> None:
        if self._closed:
            return
        if self._model_info_diff_var is None or not self._model_info_diff_var.get() or not self._model_info_iid_targets:
            return
        if self._visible_model_info_job is not None:
            try:
                self.after_cancel(self._visible_model_info_job)
            except tk.TclError:
                pass
        self._visible_model_info_job = self.after_idle(self._request_visible_model_info_rows)

    def _request_visible_model_info_rows(self) -> None:
        self._visible_model_info_job = None
        if self._closed:
            return
        if self._model_info_diff_var is None or not self._model_info_diff_var.get():
            return
        for iid in self._visible_model_info_iids():
            self._dynamic_model_info_diff_for_iid(iid)

    def _visible_model_info_iids(self) -> list[str]:
        children = list(self.costume_tree.get_children())
        visible = [
            iid
            for iid in children
            if iid in self._model_info_iid_targets and self.costume_tree.exists(iid) and self.costume_tree.bbox(iid)
        ]
        if visible:
            return visible
        try:
            height = int(self.costume_tree.cget("height"))
        except (tk.TclError, TypeError, ValueError):
            height = 7
        return [iid for iid in children if iid in self._model_info_iid_targets][:height]

    def _on_costume_motion(self, event: object) -> None:
        iid = self.costume_tree.identify_row(event.y)
        if not iid:
            self._hover_costume_iid = None
            self._costume_tooltip.hide()
            return
        if iid != self._hover_costume_iid:
            self._costume_tooltip.hide()
            self._hover_costume_iid = iid
            target = self._model_info_iid_targets.get(iid)
            if target and self._on_model_info_hover is not None:
                self._on_model_info_hover(target)
        text = self._costume_tooltip_text(iid)
        self._costume_tooltip.schedule(text, event.x_root, event.y_root)

    def _on_costume_leave(self, _event: object) -> None:
        self._hover_costume_iid = None
        self._costume_tooltip.hide()

    def _costume_tooltip_text(self, iid: str) -> str:
        parts: list[str] = []
        conflict = self._costume_iid_conflicts.get(iid)
        if conflict:
            role = str(conflict.get("role") or "")
            if role == "winner":
                mods = ", ".join(str(name) for name in conflict.get("others", []) if name)
                parts.append(self.translator.t("asset_conflict_winner_tip", mods=mods or "-"))
            elif role == "loser":
                parts.append(self.translator.t("asset_conflict_loser_tip", winner=conflict.get("winner", "-")))
        model_info_diff = self._dynamic_model_info_diff_for_iid(iid)
        if model_info_diff:
            parts.append(self._model_info_diff_tooltip_text(model_info_diff))
        return "\n\n".join(part for part in parts if part)

    def _dynamic_model_info_diff_for_iid(self, iid: str) -> dict[str, object] | None:
        target = self._model_info_iid_targets.get(iid)
        if not target:
            return None
        if self._get_model_info_diff is not None:
            diff = self._get_model_info_diff(target)
            if diff is not None:
                self._model_info_diffs[normalize_key(target)] = diff
                self._update_model_info_row(iid, diff)
                return diff
        return self._model_info_diffs.get(normalize_key(target))

    def _update_model_info_row(self, iid: str, diff: dict[str, object]) -> None:
        if iid in self._costume_iid_conflicts or not self.costume_tree.exists(iid):
            return
        values = list(self.costume_tree.item(iid, "values"))
        if not values:
            return
        values[0] = self._model_info_diff_status_text(diff)
        self.costume_tree.item(iid, values=tuple(values), tags=(self._model_info_diff_tag(diff),))

    def _model_info_diff_status_text(self, diff: dict[str, object]) -> str:
        status = str(diff.get("status") or "")
        if status in {"loading", "queued"}:
            return self.translator.t("model_info_diff_loading")
        if status == "identical":
            return self.translator.t("model_info_diff_identical")
        if status == "missing_original":
            return self.translator.t("model_info_diff_missing")
        if status == "error":
            return self.translator.t("model_info_diff_error")
        return self.translator.t("model_info_diff_changed")

    def _model_info_diff_tag(self, diff: dict[str, object]) -> str:
        status = str(diff.get("status") or "")
        if status in {"loading", "queued"}:
            return "model-info-loading"
        if status == "identical":
            return "model-info-identical"
        if status == "missing_original":
            return "model-info-missing"
        if status == "error":
            return "model-info-error"
        return "model-info-changed"

    def _model_info_diff_tooltip_text(self, diff: dict[str, object]) -> str:
        status = str(diff.get("status") or "")
        if status in {"loading", "queued"}:
            return self.translator.t("model_info_diff_loading_tip")
        if status == "missing_original":
            return self.translator.t("model_info_diff_missing_tip")
        if status == "error":
            return self.translator.t("model_info_diff_error_tip", error=diff.get("error", "-"))
        if status == "identical":
            return self.translator.t("model_info_diff_identical_tip")

        return self.translator.t(
            "model_info_diff_changed_tip",
            semantic_count=diff.get("semantic_change_count", "-"),
            semantic_changes=self._format_model_info_semantic_changes(diff),
        )

    def _format_impacts(self, diff: dict[str, object]) -> str:
        impact_keys = [str(item) for item in diff.get("impact_keys", []) if item]
        labels = [self.translator.t(f"model_info_impact_{key}") for key in impact_keys]
        return "\n".join(f"  {label}" for label in labels) or f"  {self.translator.t('model_info_impact_unknown')}"

    def _format_change_type(self, diff: dict[str, object]) -> str:
        if bool(diff.get("parameter_only")):
            return self.translator.t("model_info_change_parameter_only")
        return self.translator.t("model_info_change_structure_or_parameter")

    def _format_identifier_changes(self, diff: dict[str, object]) -> str:
        added = self._format_names(diff.get("notable_identifiers_added"))
        removed = self._format_names(diff.get("notable_identifiers_removed"))
        if added == "-" and removed == "-":
            return self.translator.t(
                "model_info_identifier_context",
                names=self._format_names(diff.get("notable_identifiers")),
            )
        return self.translator.t("model_info_identifier_changes", added=added, removed=removed)

    def _format_names(self, values: object) -> str:
        if not isinstance(values, list):
            return "-"
        names = [str(item) for item in values if item]
        return ", ".join(names[:12]) or "-"

    def _format_added_removed(self, diff: dict[str, object], added_key: str, removed_key: str) -> str:
        added = [str(item) for item in diff.get(added_key, []) if item]
        removed = [str(item) for item in diff.get(removed_key, []) if item]
        parts = []
        if added:
            parts.append("+" + ", ".join(added[:8]))
        if removed:
            parts.append("-" + ", ".join(removed[:8]))
        return "; ".join(parts) or "-"

    def _format_changed_sections(self, diff: dict[str, object]) -> str:
        sections = diff.get("changed_sections")
        if isinstance(sections, dict) and sections:
            return ", ".join(f"{name} x{count}" for name, count in list(sections.items())[:8])
        return self._format_added_removed(diff, "sections_added", "sections_removed")

    def _format_model_info_semantic_changes(self, diff: dict[str, object]) -> str:
        changes = diff.get("semantic_changes")
        if not isinstance(changes, list) or not changes:
            if diff.get("decoded_json"):
                return self.translator.t("model_info_no_semantic_changes")
            return self.translator.t("model_info_decode_unavailable")

        grouped = self._group_model_info_semantic_changes(changes)
        lines = [text for text, _count in grouped[:8]]
        shown_count = sum(count for _text, count in grouped[:8])

        try:
            total = int(diff.get("semantic_change_count") or len(changes))
        except (TypeError, ValueError):
            total = len(changes)
        remaining = max(total - shown_count, 0)
        if remaining > 0:
            lines.append(self.translator.t("model_info_semantic_changes_more", count=remaining))
        return "\n".join(lines) or self.translator.t("model_info_no_semantic_changes")

    def _group_model_info_semantic_changes(self, changes: list[object]) -> list[tuple[str, int]]:
        context_changes: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
        context_order: list[tuple[str, str]] = []
        fallback: list[tuple[str, int]] = []
        for change in changes:
            if not isinstance(change, dict):
                continue
            path = str(change.get("path") or "")
            section = self._section_from_diff_path(path)
            field = self._field_from_diff_path(path)
            context = str(change.get("context") or "")
            before = self._short_diff_value(change.get("before"))
            after = self._short_diff_value(change.get("after"))
            if not field:
                fallback.append((f"  {path or '-'}: {before} -> {after}", 1))
                continue
            key = (section, context or "-")
            if key not in context_changes:
                context_changes[key] = []
                context_order.append(key)
            context_changes[key].append((field, before, after))

        signature_groups: dict[tuple[str, tuple[tuple[str, str, str], ...]], list[str]] = {}
        signature_order: list[tuple[str, tuple[tuple[str, str, str], ...]]] = []
        for section, context in context_order:
            signature = tuple(context_changes[(section, context)])
            group_key = (section, signature)
            if group_key not in signature_groups:
                signature_groups[group_key] = []
                signature_order.append(group_key)
            signature_groups[group_key].append(context)

        grouped: list[tuple[str, int]] = []
        for section, signature in signature_order:
            contexts = signature_groups[(section, signature)]
            count = len(signature) * len(contexts)
            grouped.append((self._format_model_info_change_group(section, contexts, list(signature)), count))
        grouped.extend(fallback)
        return grouped

    def _format_model_info_change_group(
        self,
        section: str,
        contexts: list[str],
        fields: list[tuple[str, str, str]],
    ) -> str:
        target = self._format_context_group(contexts)
        section_label = self._model_info_section_label(section)
        header = f"  [{section_label}] {target}" if target else f"  [{section_label}]"
        lines = [header]
        for field, before, after in fields:
            label = self._model_info_field_label(field)
            lines.append(f"    {label}: {before} -> {after}")
        return "\n".join(lines)

    def _format_context_group(self, contexts: list[str]) -> str:
        clean = [context for context in contexts if context and context != "-"]
        if not clean:
            return ""
        shown = ", ".join(clean[:4])
        hidden = len(clean) - 4
        if hidden > 0:
            shown += f", +{hidden}"
        return shown

    def _model_info_section_label(self, section: str) -> str:
        labels = MODEL_INFO_SECTION_LABELS.get(self.translator.language, MODEL_INFO_SECTION_LABELS["en"])
        return labels.get(section, section)

    def _model_info_field_label(self, field: str) -> str:
        labels = MODEL_INFO_FIELD_LABELS.get(self.translator.language, MODEL_INFO_FIELD_LABELS["en"])
        return labels.get(field, field)

    def _section_from_diff_path(self, path: str) -> str:
        if not path.startswith("$."):
            return "-"
        return path[2:].split(".", 1)[0].split("[", 1)[0] or "-"

    def _field_from_diff_path(self, path: str) -> str:
        if "." not in path:
            return ""
        return path.rsplit(".", 1)[-1].split("[", 1)[0]

    def _short_diff_value(self, value: object) -> str:
        if isinstance(value, float):
            return f"{value:.6g}"
        if isinstance(value, dict):
            label = value.get("label")
            size = value.get("size")
            kind = value.get("type", "object")
            if label:
                return f"{kind}({label})"
            return f"{kind}({size})"
        text = str(value)
        return text if len(text) <= 36 else text[:33] + "..."

    def _format_regions(self, regions: object) -> str:
        if not isinstance(regions, list):
            return "-"
        formatted = []
        for region in regions[:8]:
            if not isinstance(region, list) or len(region) != 2:
                continue
            try:
                start = int(region[0])
                end = int(region[1])
            except (TypeError, ValueError):
                continue
            formatted.append(f"0x{start:x}-0x{end:x}")
        return ", ".join(formatted) or "-"

    def _signed(self, value: object) -> str:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return "-"
        return f"{number:+d}"

    def _on_configure(self, _event: object) -> None:
        if self._closed:
            return
        if self._resize_job is not None:
            self.canvas.after_cancel(self._resize_job)
        self._resize_job = self.canvas.after(RESIZE_DEBOUNCE_MS, self._on_resize_settled)

    def _on_resize_settled(self) -> None:
        self._resize_job = None
        if self._closed:
            return
        width = max(self.canvas.winfo_width(), 320)
        height = max(self.canvas.winfo_height(), 220)
        if (width, height) == self._last_rendered_size:
            return
        self._render()

    def _checkerboard_image(self, width: int, height: int) -> ImageTk.PhotoImage:
        cached = self._checker_cache
        if cached is not None and cached[0] == width and cached[1] == height:
            return cached[2]

        tile_size = CHECKER_SIZE * 2
        tile = Image.new("RGB", (tile_size, tile_size), self.colors["panel2"])
        draw = ImageDraw.Draw(tile)
        draw.rectangle([CHECKER_SIZE, 0, tile_size, CHECKER_SIZE], fill=self.colors["stripe"])
        draw.rectangle([0, CHECKER_SIZE, CHECKER_SIZE, tile_size], fill=self.colors["stripe"])

        board = Image.new("RGB", (width, height))
        for y in range(0, height, tile_size):
            for x in range(0, width, tile_size):
                board.paste(tile, (x, y))

        photo = ImageTk.PhotoImage(board)
        self._checker_cache = (width, height, photo)
        return photo

    def _empty_text(self, width: int, height: int, text: str, color: str) -> None:
        self.canvas.create_text(
            width // 2,
            height // 2,
            text=text,
            fill=color,
            justify=tk.CENTER,
            font=("Microsoft YaHei UI", 12),
        )

    def _render(self) -> None:
        self._cancel_animation()
        self.canvas.delete("all")
        self.frames = []
        self.frame_durations = []
        self.frame_index = 0
        self.canvas_image_id = None
        width = max(self.canvas.winfo_width(), 320)
        height = max(self.canvas.winfo_height(), 220)
        self._last_rendered_size = (width, height)
        self.checker_image = self._checkerboard_image(width, height)
        self.canvas.create_image(0, 0, image=self.checker_image, anchor=tk.NW)

        mod = self._pending_mod
        if not mod or not mod.get("preview"):
            self.current_image = None
            self._empty_text(width, height, self.translator.t("no_preview"), self.colors["muted"])
            return

        preview = self._pending_preview_path
        if not preview or not preview.exists():
            self.current_image = None
            self._empty_text(width, height, self.translator.t("missing_preview"), self.colors["red"])
            return

        try:
            frames, durations = self._load_frames(preview, width, height)
        except Exception as exc:
            self.current_image = None
            self._empty_text(width, height, self.translator.t("bad_preview", error=exc), self.colors["red"])
            return

        if not frames:
            self.current_image = None
            self._empty_text(width, height, self.translator.t("empty_preview"), self.colors["red"])
            return

        self.frames = frames
        self.frame_durations = durations
        self.current_image = frames[0]
        self.canvas_image_id = self.canvas.create_image(
            width // 2, height // 2, image=self.current_image, anchor=tk.CENTER
        )
        if len(frames) > 1:
            self._schedule_next_frame()

    def _load_frames(
        self, preview: Path, width: int, height: int
    ) -> tuple[list[ImageTk.PhotoImage], list[int]]:
        try:
            stat = preview.stat()
            cache_key = (str(preview), stat.st_mtime_ns, stat.st_size, width, height)
        except OSError:
            cache_key = None

        if cache_key is not None:
            cached = self._frame_cache.get(cache_key)
            if cached is not None:
                self._frame_cache.move_to_end(cache_key)
                return cached

        with Image.open(preview) as image:
            result = self._build_frames(image, width, height)

        if cache_key is not None:
            self._frame_cache[cache_key] = result
            self._frame_cache.move_to_end(cache_key)
            while len(self._frame_cache) > FRAME_CACHE_LIMIT:
                self._frame_cache.popitem(last=False)
        return result

    def _build_frames(
        self, image: Image.Image, canvas_width: int, canvas_height: int
    ) -> tuple[list[ImageTk.PhotoImage], list[int]]:
        max_size = (max(canvas_width - 28, 1), max(canvas_height - 28, 1))
        is_animated = bool(getattr(image, "is_animated", False))
        frames: list[ImageTk.PhotoImage] = []
        durations: list[int] = []

        if not is_animated:
            frame = ImageOps.exif_transpose(image.convert("RGBA"))
            frame.thumbnail(max_size, Image.Resampling.LANCZOS)
            return [ImageTk.PhotoImage(frame)], [0]

        previous: Image.Image | None = None
        for raw_frame in ImageSequence.Iterator(image):
            frame = raw_frame.copy().convert("RGBA")
            if previous is not None and frame.getbbox() is not None:
                composed = previous.copy()
                composed.alpha_composite(frame)
                frame = composed
            previous = frame.copy()

            frame = ImageOps.exif_transpose(frame)
            # Animated previews can have many frames; BILINEAR is much cheaper than
            # LANCZOS per-frame and the quality difference is invisible at preview size.
            frame.thumbnail(max_size, Image.Resampling.BILINEAR)
            frames.append(ImageTk.PhotoImage(frame))
            duration = int(raw_frame.info.get("duration", image.info.get("duration", 100)) or 100)
            durations.append(max(duration, 20))

        return frames, durations

    def _schedule_next_frame(self) -> None:
        if self._closed:
            return
        if len(self.frames) <= 1 or self.canvas_image_id is None:
            return
        delay = self.frame_durations[self.frame_index]
        self.animation_job = self.canvas.after(delay, self._advance_frame)

    def _advance_frame(self) -> None:
        self.animation_job = None
        if self._closed:
            return
        if len(self.frames) <= 1 or self.canvas_image_id is None:
            return
        self.frame_index = (self.frame_index + 1) % len(self.frames)
        self.current_image = self.frames[self.frame_index]
        self.canvas.itemconfigure(self.canvas_image_id, image=self.current_image)
        self._schedule_next_frame()

    def _cancel_animation(self) -> None:
        if not self.animation_job:
            return
        try:
            self.canvas.after_cancel(self.animation_job)
        except tk.TclError:
            pass
        self.animation_job = None

    def shutdown(self) -> None:
        self._closed = True
        self._costume_tooltip.hide()
        if self._model_info_diff_var is not None:
            try:
                self.model_info_diff_check.configure(variable="")
            except tk.TclError:
                pass
            self._model_info_diff_var = None
        if self._visible_model_info_job is not None:
            try:
                self.after_cancel(self._visible_model_info_job)
            except tk.TclError:
                pass
            self._visible_model_info_job = None
        if self._resize_job is not None:
            try:
                self.canvas.after_cancel(self._resize_job)
            except tk.TclError:
                pass
            self._resize_job = None
        self._cancel_animation()
        try:
            self.canvas.delete("all")
        except tk.TclError:
            pass
        self.frames.clear()
        self.frame_durations.clear()
        self.current_image = None
        self.canvas_image_id = None
        self._checker_cache = None
        self._frame_cache.clear()
        if hasattr(self, "checker_image"):
            self.checker_image = None
