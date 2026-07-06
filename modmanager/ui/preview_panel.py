from __future__ import annotations

import tkinter as tk
from collections import OrderedDict
from pathlib import Path
from tkinter import ttk
from typing import Callable

from PIL import Image, ImageDraw, ImageOps, ImageSequence, ImageTk
from tkinterdnd2 import DND_FILES

from ..costumes import modified_costumes
from ..i18n import Translator
from ..pathutils import normalize_key
from .tooltip import ToolTip

CHECKER_SIZE = 12
RESIZE_DEBOUNCE_MS = 100
FRAME_CACHE_LIMIT = 6


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
    ) -> None:
        super().__init__(parent, style="Panel.TFrame")
        self.colors = colors
        self.translator = translator
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
        self._hover_costume_iid: str | None = None

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
        self.costume_title.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 4))

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
        self.costume_tree.column("status", width=78, minwidth=70, anchor="center", stretch=False)
        self.costume_tree.column("name", width=220, minwidth=150, anchor="w", stretch=True)
        self.costume_tree.column("file", width=150, minwidth=120, anchor="w", stretch=True)
        self.costume_tree.grid(row=0, column=0, sticky="nsew")
        costume_scroll = ttk.Scrollbar(tree_holder, orient=tk.VERTICAL, command=self.costume_tree.yview)
        costume_scroll.grid(row=0, column=1, sticky="ns")
        self.costume_tree.configure(yscrollcommand=costume_scroll.set)
        self.costume_tree.tag_configure("recognized", background=colors["panel"])
        self.costume_tree.tag_configure("unrecognized", background=colors["stripe"], foreground=colors["muted"])
        self.costume_tree.tag_configure("costume-winner", background=colors["winner_bg"], foreground=colors["winner_fg"])
        self.costume_tree.tag_configure("costume-loser", background=colors["loser_bg"], foreground=colors["loser_fg"])
        self.costume_tree.tag_configure("costume-mixed", background=colors["mixed_bg"], foreground=colors["mixed_fg"])
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
        self.costume_title.configure(text=self.translator.t("modified_costumes"))
        self.costume_tree.heading("status", text=self.translator.t("costume_status"), anchor="w")
        self.costume_tree.heading("name", text=self.translator.t("costume_name"), anchor="w")
        self.costume_tree.heading("file", text=self.translator.t("costume_file"), anchor="w")
        self.status_label.configure(
            text=self.translator.t("preview_ready") if self._pending_mod else self.translator.t("preview_help")
        )
        self._refresh_costume_tree(self._pending_mod)
        self._render()

    def show(
        self,
        mod: dict | None,
        preview_path: Path | None,
        costume_conflicts: dict[str, dict[str, object]] | None = None,
    ) -> None:
        self._pending_mod = mod
        self._pending_preview_path = preview_path
        self._costume_conflicts = costume_conflicts or {}
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

    def _refresh_costume_tree(self, mod: dict | None) -> None:
        self._costume_tooltip.hide()
        self._hover_costume_iid = None
        self._costume_iid_conflicts = {}
        for item in self.costume_tree.get_children():
            self.costume_tree.delete(item)
        if not mod:
            self.costume_tree.insert("", tk.END, values=("-", "-", "-"), tags=("empty",))
            return

        changes = modified_costumes(list(mod.get("files") or []), self.translator.language)
        if not changes:
            self.costume_tree.insert(
                "",
                tk.END,
                values=("", self.translator.t("no_costumes"), ""),
                tags=("empty",),
            )
            return

        for index, change in enumerate(changes):
            tags = []
            status = self.translator.t("recognized" if change.recognized else "unrecognized")
            conflict = self._costume_conflicts.get(normalize_key(change.target))
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

    def _on_costume_motion(self, event: object) -> None:
        iid = self.costume_tree.identify_row(event.y)
        if not iid:
            self._hover_costume_iid = None
            self._costume_tooltip.hide()
            return
        text = self._costume_tooltip_text(iid)
        if iid != self._hover_costume_iid:
            self._costume_tooltip.hide()
            self._hover_costume_iid = iid
        self._costume_tooltip.schedule(text, event.x_root, event.y_root)

    def _on_costume_leave(self, _event: object) -> None:
        self._hover_costume_iid = None
        self._costume_tooltip.hide()

    def _costume_tooltip_text(self, iid: str) -> str:
        conflict = self._costume_iid_conflicts.get(iid)
        if not conflict:
            return ""
        role = str(conflict.get("role") or "")
        if role == "winner":
            mods = ", ".join(str(name) for name in conflict.get("others", []) if name)
            return self.translator.t("costume_conflict_winner_tip", mods=mods or "-")
        if role == "loser":
            return self.translator.t("costume_conflict_loser_tip", winner=conflict.get("winner", "-"))
        return ""

    def _on_configure(self, _event: object) -> None:
        if self._resize_job is not None:
            self.canvas.after_cancel(self._resize_job)
        self._resize_job = self.canvas.after(RESIZE_DEBOUNCE_MS, self._on_resize_settled)

    def _on_resize_settled(self) -> None:
        self._resize_job = None
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
        if len(self.frames) <= 1 or self.canvas_image_id is None:
            return
        delay = self.frame_durations[self.frame_index]
        self.animation_job = self.canvas.after(delay, self._advance_frame)

    def _advance_frame(self) -> None:
        self.animation_job = None
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
