from __future__ import annotations

import itertools
import os
import queue
import threading
from pathlib import Path
from typing import Iterable

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from tkinterdnd2 import DND_FILES, TkinterDnD

from .. import costumes
from ..core import ModManagerCore
from ..games import default_game_picker_dir, looks_like_game_dir
from ..i18n import LANGUAGES, Translator
from ..pathutils import is_preview_image, normalize_key
from .conflict_list import ConflictPanel
from .dnd import parse_drop_paths
from .log_panel import LogPanel
from .mod_list import ModListPanel
from .preview_panel import PreviewPanel
from .status_bar import StatusBar
from .theme import apply_theme

MODEL_INFO_DIFF_PRIORITY_HOVER = 0
MODEL_INFO_DIFF_PRIORITY_SELECTED = 20
QUEUE_POLL_ITEM_LIMIT = 120


class ModManagerApp:
    def __init__(self, root: TkinterDnD.Tk, core: ModManagerCore) -> None:
        self.root = root
        self.core = core
        self.translator = Translator(self.core.config.language)
        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self._status_error_pending = False
        self._conflicts_cache: list[dict] = []
        self._last_normal_geometry = str(self.core.config.get_window_value("geometry", "1180x800"))
        self._layout_ready = False
        self._layout_wait_size: tuple[int, int, int] | None = None

        self._game_ids: list[str] = []
        self._model_info_diff_cache: dict[tuple[str, str, str], dict[str, object]] = {}
        self._model_info_diff_pending: set[tuple[str, str, str]] = set()
        self._model_info_diff_queue: queue.PriorityQueue[tuple[int, int, str, str, str]] = queue.PriorityQueue()
        self._model_info_diff_counter = itertools.count()
        self._model_info_diff_lock = threading.Lock()
        self._model_info_diff_shutdown = False
        self._model_info_diff_worker_count = 1
        self._start_model_info_diff_workers()

        self.root.geometry(self._last_normal_geometry)
        self.root.minsize(980, 660)
        self.colors = apply_theme(self.root)
        self._build_ui()
        self.set_language()
        self._update_game_controls()
        self.refresh_all()
        self._update_action_states()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Configure>", self._on_root_configure)
        self.root.after(120, self._restore_window_and_layout)
        self.root.after(100, self._poll_queue)
        self.root.after(300, self._ensure_game_selected)

    # -- layout ---------------------------------------------------------------

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        header = ttk.Frame(self.root, padding=(16, 14, 16, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        self.title_label = ttk.Label(header, font=("Microsoft YaHei UI", 15, "bold"))
        self.title_label.grid(row=0, column=0, sticky="w")
        self.subtitle_label = ttk.Label(header, style="Muted.TLabel")
        self.subtitle_label.grid(row=1, column=0, sticky="w", pady=(4, 0))

        toolbar = ttk.Frame(header)
        toolbar.grid(row=0, column=1, rowspan=2, sticky="e")

        # Toolbar row 0: game selector + language.
        self.game_label = ttk.Label(toolbar, style="Muted.TLabel")
        self.game_label.grid(row=0, column=0, padx=(0, 6))
        self.game_combo = ttk.Combobox(toolbar, state="readonly", width=18)
        self.game_combo.grid(row=0, column=1, padx=(0, 6))
        self.game_combo.bind("<<ComboboxSelected>>", self._on_game_selected)
        self.add_game_button = ttk.Button(toolbar, command=self.add_game)
        self.add_game_button.grid(row=0, column=2, padx=(0, 6))
        self.remove_game_button = ttk.Button(toolbar, command=self.remove_active_game)
        self.remove_game_button.grid(row=0, column=3, padx=(0, 16))
        self.language_label = ttk.Label(toolbar, style="Muted.TLabel")
        self.language_label.grid(row=0, column=4, padx=(0, 6))
        self.language_combo = ttk.Combobox(toolbar, state="readonly", width=12)
        self.language_combo.grid(row=0, column=5)
        self.language_combo.bind("<<ComboboxSelected>>", self._on_language_selected)

        # Toolbar row 1: mod actions.
        actions = ttk.Frame(toolbar)
        actions.grid(row=1, column=0, columnspan=6, sticky="e", pady=(8, 0))
        self.import_file_button = ttk.Button(actions, command=self.import_files_dialog)
        self.import_file_button.grid(row=0, column=0, padx=(0, 6))
        self.import_folder_button = ttk.Button(actions, command=self.import_folder_dialog)
        self.import_folder_button.grid(row=0, column=1, padx=(0, 6))
        self.apply_button = ttk.Button(actions, style="Accent.TButton", command=self.apply_mods)
        self.apply_button.grid(row=0, column=2, padx=(0, 6))
        self.restore_button = ttk.Button(actions, command=self.restore_game)
        self.restore_button.grid(row=0, column=3)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).grid(row=0, column=0, sticky="sew")

        # xinput warning banner (row 1) — only shown when the DLL is missing.
        self.xinput_banner = tk.Frame(self.root, bg=self.colors["red"])
        self.xinput_banner.columnconfigure(0, weight=1)
        self.xinput_label = tk.Label(
            self.xinput_banner,
            bg=self.colors["red"],
            fg="#ffffff",
            anchor="w",
            padx=14,
            pady=6,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        self.xinput_label.grid(row=0, column=0, sticky="ew")
        self.xinput_download_button = ttk.Button(self.xinput_banner, command=self.download_xinput)
        self.xinput_download_button.grid(row=0, column=1, padx=(0, 6), pady=4)
        self.xinput_recheck_button = ttk.Button(self.xinput_banner, command=self._update_xinput_banner)
        self.xinput_recheck_button.grid(row=0, column=2, padx=(0, 6), pady=4)
        self.xinput_open_button = ttk.Button(self.xinput_banner, command=self.open_game_dir)
        self.xinput_open_button.grid(row=0, column=3, padx=(0, 8), pady=4)

        self.main_pane = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        self.main_pane.grid(row=2, column=0, sticky="nsew", padx=16, pady=(10, 8))

        left = ttk.Frame(self.main_pane, style="Panel.TFrame", padding=12)
        right = ttk.Frame(self.main_pane, style="Panel.TFrame", padding=12)
        self.main_pane.add(left, weight=3)
        self.main_pane.add(right, weight=2)

        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.left_pane = ttk.Panedwindow(left, orient=tk.VERTICAL)
        self.left_pane.grid(row=0, column=0, sticky="nsew")
        mod_frame = ttk.Frame(self.left_pane, style="Panel.TFrame")
        conflict_frame = ttk.Frame(self.left_pane, style="Panel.TFrame")
        mod_frame.rowconfigure(0, weight=1)
        mod_frame.columnconfigure(0, weight=1)
        conflict_frame.rowconfigure(0, weight=1)
        conflict_frame.columnconfigure(0, weight=1)
        self.left_pane.add(mod_frame, weight=4)
        self.left_pane.add(conflict_frame, weight=1)

        self.mod_list = ModListPanel(
            mod_frame,
            self.colors,
            self.translator,
            on_drop=self.on_mod_drop,
            on_select=self._on_mod_selected,
            on_toggle=self.toggle_mod,
            on_move=self.move_mod,
            on_delete=self.delete_mod,
            on_open_data_dir=self.open_data_dir,
            on_reorder=self.reorder_mods,
        )
        self.mod_list.grid(row=0, column=0, sticky="nsew")

        self.conflict_panel = ConflictPanel(conflict_frame, self.colors, self.translator)
        self.conflict_panel.grid(row=0, column=0, sticky="nsew")

        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        self.right_pane = ttk.Panedwindow(right, orient=tk.VERTICAL)
        self.right_pane.grid(row=0, column=0, sticky="nsew")
        preview_frame = ttk.Frame(self.right_pane, style="Panel.TFrame")
        log_frame = ttk.Frame(self.right_pane, style="Panel.TFrame")
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.right_pane.add(preview_frame, weight=3)
        self.right_pane.add(log_frame, weight=1)

        self.preview_panel = PreviewPanel(
            preview_frame,
            self.colors,
            self.translator,
            on_choose_file=self.choose_preview,
            on_choose_url=self.choose_preview_url,
            on_drop=self.on_preview_drop,
            model_info_diff_enabled=self.core.config.model_info_diff_enabled,
            on_model_info_diff_toggle=self.set_model_info_diff_enabled,
            on_model_info_hover=self.prioritize_model_info_diff,
            get_model_info_diff=self.model_info_diff_for_tooltip,
        )
        self.preview_panel.grid(row=0, column=0, sticky="nsew")

        self.log_title_label = ttk.Label(log_frame, style="Panel.TLabel", font=("Microsoft YaHei UI", 11, "bold"))
        self.log_title_label.grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.log_panel = LogPanel(log_frame, self.colors, height=9)
        self.log_panel.grid(row=1, column=0, sticky="nsew")

        self.status_bar = StatusBar(self.root, self.colors, self.translator)
        self.status_bar.grid(row=3, column=0, sticky="ew")

        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind("<<Drop>>", self.on_mod_drop)

    def set_language(self) -> None:
        t = self.translator.t
        self.root.title(t("app_title"))
        self.title_label.configure(text=t("app_title"))
        if self.core.has_active_game:
            self.subtitle_label.configure(text=t("subtitle", game_root=self.core.game_root))
        else:
            self.subtitle_label.configure(text=t("subtitle_no_game"))
        self.game_label.configure(text=t("game_label"))
        self.add_game_button.configure(text=t("add_game"))
        self.remove_game_button.configure(text=t("remove_game"))
        self.language_label.configure(text=t("language"))
        self.language_combo.configure(values=list(LANGUAGES.values()))
        self.language_combo.set(LANGUAGES.get(self.translator.language, LANGUAGES["zh_CN"]))
        self.import_file_button.configure(text=t("import_file"))
        self.import_folder_button.configure(text=t("import_folder"))
        self.apply_button.configure(text=t("apply"))
        self.restore_button.configure(text=t("restore"))
        self.xinput_label.configure(text=t("xinput_missing"))
        self.xinput_download_button.configure(text=t("xinput_download"))
        self.xinput_recheck_button.configure(text=t("xinput_recheck"))
        self.xinput_open_button.configure(text=t("open_game_dir"))
        self.log_title_label.configure(text=t("log"))
        self.mod_list.set_language()
        self.preview_panel.set_model_info_diff_enabled(self.core.config.model_info_diff_enabled)
        self.preview_panel.set_language()
        self.conflict_panel.set_language()
        self.status_bar.set_language()

    # -- game management ------------------------------------------------------

    def _update_game_controls(self) -> None:
        games = self.core.list_games()
        self._game_ids = [game["id"] for game in games]
        self.game_combo.configure(values=[game["name"] for game in games])
        if self.core.game_id in self._game_ids:
            self.game_combo.current(self._game_ids.index(self.core.game_id))
        else:
            self.game_combo.set("")

    def _update_action_states(self) -> None:
        enabled = self.core.has_active_game and not self.busy
        state = tk.NORMAL if enabled else tk.DISABLED
        for button in (self.import_file_button, self.import_folder_button, self.apply_button, self.restore_button):
            button.configure(state=state)
        self.remove_game_button.configure(
            state=tk.NORMAL if (self.core.has_active_game and not self.busy) else tk.DISABLED
        )

    def _update_xinput_banner(self) -> None:
        if self.core.has_active_game and not self.core.xinput_ok():
            self.xinput_banner.grid(row=1, column=0, sticky="ew")
        else:
            self.xinput_banner.grid_remove()

    def _on_active_game_changed(self) -> None:
        self._clear_model_info_diff_cache()
        self.set_language()
        self._update_game_controls()
        self.refresh_all()
        self._update_action_states()

    def _on_game_selected(self, _event: object) -> None:
        if self.busy:
            return
        index = self.game_combo.current()
        if index < 0 or index >= len(self._game_ids):
            return
        game_id = self._game_ids[index]
        if game_id == self.core.game_id:
            return
        try:
            self.core.switch_game(game_id)
        except Exception as exc:
            messagebox.showerror(self.translator.t("operation_failed"), str(exc))
            return
        self.log_panel.status(self.translator.t("game_switched", name=self.core.active_game_name()))
        self._on_active_game_changed()

    def _pick_and_add_game(self) -> bool:
        folder = filedialog.askdirectory(
            title=self.translator.t("select_game_dir_title"),
            initialdir=str(self._game_dialog_initial_dir()),
        )
        if not folder:
            return False
        path = Path(folder)
        if not looks_like_game_dir(path):
            if not messagebox.askyesno(
                self.translator.t("invalid_game_dir_title"),
                self.translator.t("invalid_game_dir"),
            ):
                return False
        try:
            self.core.add_and_activate_game(path)
        except Exception as exc:
            messagebox.showerror(self.translator.t("operation_failed"), str(exc))
            return False
        self.log_panel.status(self.translator.t("game_added", name=self.core.active_game_name()))
        self._on_active_game_changed()
        return True

    def _game_dialog_initial_dir(self) -> Path:
        steam_dir = default_game_picker_dir()
        if steam_dir is not None:
            return steam_dir
        if self.core.game_root and self.core.game_root.exists():
            return self.core.game_root.parent
        return self.core.app_dir.parent

    def add_game(self) -> None:
        if self.busy:
            return
        self._pick_and_add_game()

    def remove_active_game(self) -> None:
        if self.busy or not self.core.has_active_game:
            return
        name = self.core.active_game_name()
        if not messagebox.askyesno(
            self.translator.t("remove_game_title"),
            self.translator.t("remove_game_confirm", name=name),
        ):
            return
        self.core.remove_game(self.core.game_id)
        self.log_panel.status(self.translator.t("game_removed", name=name))
        self._on_active_game_changed()
        if not self.core.has_active_game:
            self._ensure_game_selected()

    def _ensure_game_selected(self) -> None:
        if self.core.has_active_game:
            return
        messagebox.showinfo(self.translator.t("app_title"), self.translator.t("first_run_prompt"))
        while not self.core.has_active_game:
            if not self._pick_and_add_game():
                break

    def open_game_dir(self) -> None:
        if self.core.game_root and self.core.game_root.exists():
            os.startfile(self.core.game_root)

    def download_xinput(self) -> None:
        if self.busy or not self.core.has_active_game:
            return
        self.set_busy(True, self.translator.t("busy_xinput_download"))

        def worker() -> None:
            try:
                destination = self.core.download_xinput(log=self.thread_log)
                self.queue.put(("status", self.translator.t("xinput_download_done", path=destination)))
                self.queue.put(("xinput", None))
            except Exception as exc:
                self.queue.put(("error", self.translator.t("xinput_download_failed", error=exc)))
            finally:
                self.queue.put(("busy", False))

        threading.Thread(target=worker, daemon=True).start()

    def _on_language_selected(self, _event: object) -> None:
        label = self.language_combo.get()
        language = next((code for code, name in LANGUAGES.items() if name == label), "zh_CN")
        if language == self.translator.language:
            return
        self.core.set_language(language)
        self.translator.set_language(language)
        self.set_language()
        self.refresh_all(keep_selection=self.mod_list.get_selected_mod_id())

    # -- config persistence ---------------------------------------------------

    def _sash_panes(self) -> tuple[tuple[ttk.Panedwindow, str, str], ...]:
        # (pane, config key, axis) -- horizontal panes divide along x, vertical along y.
        return (
            (self.main_pane, "main_sash", "x"),
            (self.left_pane, "left_sash", "y"),
            (self.right_pane, "right_sash", "y"),
        )

    def _pane_extent(self, pane: ttk.Panedwindow, axis: str) -> int:
        return pane.winfo_width() if axis == "x" else pane.winfo_height()

    def _restore_window_and_layout(self) -> None:
        state = self.core.config.get_window_value("state", "normal")
        if state == "zoomed":
            try:
                self.root.state("zoomed")
            except tk.TclError:
                pass
        # Maximizing is handled asynchronously by the window manager, so the panes
        # are not at their final size yet. Wait until the geometry stops changing
        # before applying sash positions, otherwise sashpos() clamps against a
        # transient (pre-zoom) size and the divider sticks at the wrong place.
        self._layout_wait_size = None
        self._await_stable_layout(0)

    def _await_stable_layout(self, attempts: int) -> None:
        self.root.update_idletasks()
        size = (
            self.main_pane.winfo_width(),
            self.left_pane.winfo_height(),
            self.right_pane.winfo_height(),
        )
        settled = size == self._layout_wait_size and min(size) > 1
        self._layout_wait_size = size
        if not settled and attempts < 40:
            self.root.after(50, lambda: self._await_stable_layout(attempts + 1))
            return
        self._apply_sash_fractions()
        self._layout_ready = True

    def _apply_sash_fractions(self) -> None:
        for pane, key, axis in self._sash_panes():
            fraction = self.core.config.get_window_value(key)
            if not isinstance(fraction, (int, float)) or isinstance(fraction, bool):
                continue
            # Ignore legacy absolute-pixel values (and fully-collapsed panes); a
            # valid saved divider is a fraction strictly inside the pane.
            if not 0.05 < fraction < 0.95:
                continue
            extent = self._pane_extent(pane, axis)
            if extent <= 1:
                continue
            try:
                pane.sashpos(0, round(fraction * extent))
            except tk.TclError:
                pass

    def _on_root_configure(self, event: object) -> None:
        if not self._layout_ready or getattr(event, "widget", None) is not self.root:
            return
        try:
            if self.root.state() == "normal":
                self._last_normal_geometry = self.root.geometry()
        except tk.TclError:
            pass

    def _sash_fraction(self, pane: ttk.Panedwindow, axis: str) -> float | None:
        try:
            position = pane.sashpos(0)
        except tk.TclError:
            return None
        extent = self._pane_extent(pane, axis)
        if extent <= 1 or position <= 0:
            return None
        return max(0.05, min(0.95, position / extent))

    def _save_layout_config(self) -> None:
        try:
            state = self.root.state()
        except tk.TclError:
            state = "normal"
        self.core.config.set_window_value("state", "zoomed" if state == "zoomed" else "normal")
        self.core.config.set_window_value("geometry", self._last_normal_geometry or self.root.geometry())
        for pane, key, axis in self._sash_panes():
            fraction = self._sash_fraction(pane, axis)
            if fraction is not None:
                self.core.config.set_window_value(key, round(fraction, 4))
        self.core.save_config()

    def close(self) -> None:
        self._save_layout_config()
        self._model_info_diff_shutdown = True
        for _index in range(self._model_info_diff_worker_count):
            self._model_info_diff_queue.put((9999, next(self._model_info_diff_counter), "", "", ""))
        self.root.destroy()

    # -- drag & drop ----------------------------------------------------------

    def on_mod_drop(self, event: object) -> None:
        paths = parse_drop_paths(event.widget, event.data)
        if paths:
            self.import_paths(paths)

    def on_preview_drop(self, event: object) -> None:
        paths = parse_drop_paths(event.widget, event.data)
        images = [path for path in paths if path.is_file() and is_preview_image(path)]
        if not images:
            self.log_panel.info(self.translator.t("preview_drop_rejected"))
            return
        self.set_preview_image(images[0])

    # -- dialogs --------------------------------------------------------------

    def import_files_dialog(self) -> None:
        filenames = filedialog.askopenfilenames(
            title=self.translator.t("choose_mod_file_title"),
            filetypes=[
                (self.translator.t("filetype_mod_archives"), "*.zip *.7z *.rar *.tar *.tgz *.tbz2 *.txz *.mdl *.dds *.tbl"),
                (self.translator.t("filetype_all"), "*.*"),
            ],
        )
        if filenames:
            self.import_paths([Path(name) for name in filenames])

    def import_folder_dialog(self) -> None:
        folder = filedialog.askdirectory(title=self.translator.t("choose_mod_folder_title"))
        if folder:
            self.import_paths([Path(folder)])

    def choose_preview(self) -> None:
        filename = filedialog.askopenfilename(
            title=self.translator.t("choose_preview_title"),
            filetypes=[
                (self.translator.t("filetype_images"), "*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff"),
                (self.translator.t("filetype_all"), "*.*"),
            ],
        )
        if filename:
            self.set_preview_image(Path(filename))

    def choose_preview_url(self) -> None:
        if not self.mod_list.get_selected_mod_id():
            messagebox.showinfo(
                self.translator.t("select_mod_required_title"),
                self.translator.t("select_mod_required"),
            )
            return
        url = simpledialog.askstring(
            self.translator.t("preview_url_title"),
            self.translator.t("preview_url_prompt"),
            parent=self.root,
        )
        if url:
            self.set_preview_url(url)

    # -- actions --------------------------------------------------------------

    def set_preview_image(self, image_path: Path) -> None:
        mod_id = self.mod_list.get_selected_mod_id()
        if not mod_id:
            messagebox.showinfo(
                self.translator.t("select_mod_required_title"),
                self.translator.t("select_mod_required"),
            )
            return
        try:
            self.core.set_preview(mod_id, image_path)
        except Exception as exc:
            messagebox.showerror(self.translator.t("preview_set_failed"), str(exc))
            return
        self.log_panel.info(self.translator.t("preview_set", name=image_path.name))
        self.refresh_all(keep_selection=mod_id)

    def set_preview_url(self, url: str) -> None:
        if self.busy:
            self.log_panel.info(self.translator.t("task_busy"))
            return
        mod_id = self.mod_list.get_selected_mod_id()
        if not mod_id:
            messagebox.showinfo(
                self.translator.t("select_mod_required_title"),
                self.translator.t("select_mod_required"),
            )
            return
        self.set_busy(True, self.translator.t("busy_preview_url"))

        def worker() -> None:
            try:
                destination = self.core.set_preview_from_url(mod_id, url, self.thread_log)
                self.queue.put(("status", self.translator.t("url_preview_done", name=destination.name)))
                self.queue.put(("refresh", mod_id))
            except Exception as exc:
                self.queue.put(("error", self.translator.t("url_preview_failed", error=exc)))
            finally:
                self.queue.put(("busy", False))

        threading.Thread(target=worker, daemon=True).start()

    def set_model_info_diff_enabled(self, enabled: bool) -> None:
        self.core.set_model_info_diff_enabled(enabled)
        self.preview_panel.set_model_info_diff_enabled(enabled)
        mod_id = self.mod_list.get_selected_mod_id()
        self._sync_preview(mod_id)

    def prioritize_model_info_diff(self, target: str) -> None:
        if not self.core.config.model_info_diff_enabled:
            return
        mod_id = self.mod_list.get_selected_mod_id()
        if not mod_id:
            return
        self._schedule_model_info_diffs(mod_id, [target], priority=MODEL_INFO_DIFF_PRIORITY_HOVER)

    def model_info_diff_for_tooltip(self, target: str) -> dict[str, object] | None:
        if not self.core.config.model_info_diff_enabled:
            return None
        mod_id = self.mod_list.get_selected_mod_id()
        if not mod_id:
            return None
        if not costumes.is_model_info_target(target):
            return None
        entry = self._model_info_diff_entry_for_target(mod_id, target)
        if entry.get("status") == "queued":
            self._schedule_model_info_diffs(mod_id, [target], priority=MODEL_INFO_DIFF_PRIORITY_HOVER)
            entry = self._model_info_diff_entry_for_target(mod_id, target)
        return entry

    def import_paths(self, paths: Iterable[Path]) -> None:
        if self.busy:
            self.log_panel.info(self.translator.t("task_busy"))
            return
        path_list = list(paths)
        if not path_list:
            return
        self.set_busy(True, self.translator.t("busy_import"))

        def worker() -> None:
            imported = []
            try:
                for path in path_list:
                    imported.append(self.core.import_path(path, self.thread_log))
                self.queue.put(("status", self.translator.t("import_done", count=len(imported))))
                self.queue.put(("refresh", imported[-1] if imported else None))
            except Exception as exc:
                self.queue.put(("error", self.translator.t("import_failed", error=exc)))
            finally:
                self.queue.put(("busy", False))

        threading.Thread(target=worker, daemon=True).start()

    def apply_mods(self) -> None:
        if self.busy:
            self.log_panel.info(self.translator.t("task_busy"))
            return
        conflicts = self.core.compute_conflicts()
        if conflicts:
            proceed = messagebox.askyesno(
                self.translator.t("conflict_title"),
                self.translator.t("conflict_confirm", count=len(conflicts)),
            )
            if not proceed:
                return
        self.set_busy(True, self.translator.t("busy_apply"))

        def worker() -> None:
            try:
                result = self.core.apply_enabled(self.thread_log)
                self.queue.put(
                    (
                        "status",
                        self.translator.t("apply_done", mods=result["mods"], files=result["files"]),
                    )
                )
                self.queue.put(("refresh", self.mod_list.get_selected_mod_id()))
            except Exception as exc:
                self.queue.put(("error", self.translator.t("apply_failed", error=exc)))
            finally:
                self.queue.put(("busy", False))

        threading.Thread(target=worker, daemon=True).start()

    def restore_game(self) -> None:
        if self.busy:
            self.log_panel.info(self.translator.t("task_busy"))
            return
        proceed = messagebox.askyesno(
            self.translator.t("restore_title"),
            self.translator.t("restore_confirm"),
        )
        if not proceed:
            return
        self.set_busy(True, self.translator.t("busy_restore"))

        def worker() -> None:
            try:
                result = self.core.restore_game(self.thread_log)
                self.queue.put(
                    (
                        "status",
                        self.translator.t(
                            "restore_done",
                            restored=result["restored"],
                            removed=result["removed"],
                        ),
                    )
                )
                self.queue.put(("refresh", self.mod_list.get_selected_mod_id()))
            except Exception as exc:
                self.queue.put(("error", self.translator.t("restore_failed", error=exc)))
            finally:
                self.queue.put(("busy", False))

        threading.Thread(target=worker, daemon=True).start()

    def toggle_mod(self, mod_id: str) -> None:
        self.core.toggle_enabled(mod_id)
        self.refresh_all(keep_selection=mod_id)

    def delete_mod(self, mod_id: str) -> None:
        mod = self.core.state["mods"].get(mod_id)
        if not mod:
            return
        proceed = messagebox.askyesno(
            self.translator.t("delete_title"),
            self.translator.t("delete_confirm", name=mod["name"]),
        )
        if not proceed:
            return
        self.core.delete_mod(mod_id)
        self._clear_model_info_diff_cache(mod_id)
        self.refresh_all()
        self.log_panel.info(self.translator.t("deleted_mod", name=mod["name"]))

    def move_mod(self, mod_id: str, direction: int) -> None:
        order = list(self.core.state["order"])
        index = order.index(mod_id)
        new_index = index + direction
        if new_index < 0 or new_index >= len(order):
            return
        order[index], order[new_index] = order[new_index], order[index]
        self.core.set_order(order)
        self.refresh_all(keep_selection=mod_id)

    def reorder_mods(self, order: list[str]) -> None:
        self.core.set_order(order)
        self.refresh_all(keep_selection=self.mod_list.get_selected_mod_id())

    def open_data_dir(self) -> None:
        mod_id = self.mod_list.get_selected_mod_id()
        if not mod_id:
            messagebox.showinfo(
                self.translator.t("select_mod_required_title"),
                self.translator.t("select_mod_required"),
            )
            return
        mod_dir = self.core.mods_dir / mod_id
        mod_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(mod_dir)

    # -- selection / refresh --------------------------------------------------

    def _on_mod_selected(self, mod_id: str | None) -> None:
        self._sync_selection(mod_id)

    def _sync_selection(self, mod_id: str | None) -> None:
        self._sync_preview(mod_id)
        self._sync_conflict_highlight(mod_id)

    def _sync_preview(self, mod_id: str | None) -> None:
        mod = self.core.state["mods"].get(mod_id) if mod_id else None
        preview_path = None
        if mod and mod.get("preview"):
            preview_path = self.core.absolute_data_path(mod.get("preview"))
        model_info_diffs = {}
        if mod_id and self.core.config.model_info_diff_enabled:
            model_info_diffs = self._model_info_active_entries_for_mod(mod_id)
        self.preview_panel.show(
            mod,
            preview_path,
            self._costume_conflicts_for_mod(mod_id),
            model_info_diffs,
        )

    def _sync_conflict_highlight(self, mod_id: str | None) -> None:
        partners: set[str] = set()
        if mod_id:
            for conflict in self._conflicts_cache:
                if mod_id in conflict["mods"]:
                    partners.update(other for other in conflict["mods"] if other != mod_id)
        self.mod_list.set_conflict_partners(partners)
        self.conflict_panel.set_selected_mod(mod_id)

    def refresh_all(self, keep_selection: str | None = None) -> None:
        self._conflicts_cache = self.core.compute_conflicts()
        conflict_counts = self.core.conflict_counts_by_mod()
        conflict_roles = self._conflict_roles_by_mod()
        self.mod_list.refresh(
            self.core.state["mods"],
            self.core.state["order"],
            conflict_counts,
            conflict_roles,
            keep_selection,
        )
        self.conflict_panel.refresh(self._conflicts_cache, self.core.state["mods"])
        self._sync_selection(self.mod_list.get_selected_mod_id())
        self._update_xinput_banner()

    def _conflict_roles_by_mod(self) -> dict[str, dict[str, int]]:
        roles = {mod_id: {"winner": 0, "loser": 0} for mod_id in self.core.state["mods"]}
        for conflict in self._conflicts_cache:
            winner = conflict.get("winner")
            if winner in roles:
                roles[winner]["winner"] += 1
            for loser in conflict.get("losers", []):
                if loser in roles:
                    roles[loser]["loser"] += 1
        return roles

    def _costume_conflicts_for_mod(self, mod_id: str | None) -> dict[str, dict[str, object]]:
        if not mod_id:
            return {}
        mods = self.core.state["mods"]
        result: dict[str, dict[str, object]] = {}
        for conflict in self._conflicts_cache:
            if mod_id not in conflict.get("mods", []):
                continue
            target = conflict.get("target", "")
            key = normalize_key(target)
            winner_id = conflict.get("winner")
            winner_name = mods.get(winner_id, {}).get("name", winner_id)
            loser_names = [
                mods.get(other_id, {}).get("name", other_id)
                for other_id in conflict.get("losers", [])
                if other_id != mod_id
            ]
            if mod_id == winner_id:
                result[key] = {
                    "role": "winner",
                    "winner": winner_name,
                    "others": loser_names,
                    "target": target,
                }
            else:
                result[key] = {
                    "role": "loser",
                    "winner": winner_name,
                    "others": [winner_name],
                    "target": target,
                }
        return result

    # -- model-info diff workers --------------------------------------------

    def _start_model_info_diff_workers(self) -> None:
        for index in range(self._model_info_diff_worker_count):
            thread = threading.Thread(
                target=self._model_info_diff_worker,
                name=f"model-info-diff-{index + 1}",
                daemon=True,
            )
            thread.start()

    def _model_info_diff_worker(self) -> None:
        while True:
            priority, _counter, game_id, mod_id, target = self._model_info_diff_queue.get()
            try:
                if self._model_info_diff_shutdown:
                    return
                if not game_id or not mod_id or not target:
                    continue
                cache_key = self._model_info_diff_cache_key(game_id, mod_id, target)
                if game_id != self.core.game_id:
                    with self._model_info_diff_lock:
                        self._model_info_diff_pending.discard(cache_key)
                    continue
                with self._model_info_diff_lock:
                    if cache_key in self._model_info_diff_cache:
                        continue
                diff = self.core.model_info_diff_for_target(mod_id, target)
                if diff is None:
                    diff = {"status": "error", "error": self.core.t("model_info_diff_source_missing")}
                with self._model_info_diff_lock:
                    self._model_info_diff_cache[cache_key] = diff
                    self._model_info_diff_pending.discard(cache_key)
                self.queue.put(("model_info_diff_done", {"game_id": game_id, "mod_id": mod_id, "target": target}))
            finally:
                self._model_info_diff_queue.task_done()

    def _model_info_targets_for_mod(self, mod_id: str) -> list[str]:
        mod = self.core.state["mods"].get(mod_id)
        if not mod:
            return []
        return [target for target in mod.get("files", []) if costumes.is_model_info_target(target)]

    def _next_unscheduled_model_info_targets(self, mod_id: str, limit: int) -> list[str]:
        game_id = self.core.game_id
        if not game_id or limit <= 0:
            return []
        result: list[str] = []
        for target in self._model_info_targets_for_mod(mod_id):
            cache_key = self._model_info_diff_cache_key(game_id, mod_id, target)
            with self._model_info_diff_lock:
                unavailable = cache_key in self._model_info_diff_cache or cache_key in self._model_info_diff_pending
            if unavailable:
                continue
            result.append(target)
            if len(result) >= limit:
                break
        return result

    def _schedule_model_info_diffs(
        self,
        mod_id: str,
        targets: Iterable[str] | None = None,
        priority: int = MODEL_INFO_DIFF_PRIORITY_SELECTED,
    ) -> int:
        game_id = self.core.game_id
        if not game_id:
            return 0
        target_list = list(targets) if targets is not None else self._model_info_targets_for_mod(mod_id)
        scheduled = 0
        for target in target_list:
            if not costumes.is_model_info_target(target):
                continue
            cache_key = self._model_info_diff_cache_key(game_id, mod_id, target)
            enqueue = False
            with self._model_info_diff_lock:
                if cache_key in self._model_info_diff_cache:
                    continue
                if cache_key not in self._model_info_diff_pending:
                    self._model_info_diff_pending.add(cache_key)
                    enqueue = True
                elif priority == MODEL_INFO_DIFF_PRIORITY_HOVER:
                    enqueue = True
            if enqueue:
                self._model_info_diff_queue.put(
                    (priority, next(self._model_info_diff_counter), game_id, mod_id, target)
                )
                scheduled += 1
        return scheduled

    def _model_info_active_entries_for_mod(self, mod_id: str) -> dict[str, dict[str, object]]:
        game_id = self.core.game_id
        if not game_id:
            return {}
        entries: dict[str, dict[str, object]] = {}
        with self._model_info_diff_lock:
            cache_items = list(self._model_info_diff_cache.items())
            pending_keys = list(self._model_info_diff_pending)
        for key, value in cache_items:
            if key[0] == game_id and key[1] == mod_id:
                entries[key[2]] = value
        for key in pending_keys:
            if key[0] == game_id and key[1] == mod_id and key[2] not in entries:
                entries[key[2]] = {"status": "loading"}
        return entries

    def _model_info_diff_entry_for_target(self, mod_id: str, target: str) -> dict[str, object]:
        game_id = self.core.game_id
        if not game_id:
            return {"status": "queued"}
        cache_key = self._model_info_diff_cache_key(game_id, mod_id, target)
        with self._model_info_diff_lock:
            cached = self._model_info_diff_cache.get(cache_key)
            pending = cache_key in self._model_info_diff_pending
        if cached is not None:
            return cached
        if pending:
            return {"status": "loading"}
        return {"status": "queued"}

    def _clear_model_info_diff_cache(self, mod_id: str | None = None) -> None:
        with self._model_info_diff_lock:
            if mod_id is None:
                self._model_info_diff_cache.clear()
                self._model_info_diff_pending.clear()
                return
            self._model_info_diff_cache = {
                key: value
                for key, value in self._model_info_diff_cache.items()
                if key[1] != mod_id
            }
            self._model_info_diff_pending = {
                key for key in self._model_info_diff_pending if key[1] != mod_id
            }

    def _model_info_diff_cache_key(self, game_id: str, mod_id: str, target: str) -> tuple[str, str, str]:
        return (game_id, mod_id, normalize_key(target))

    # -- busy / logging -------------------------------------------------------

    def set_busy(self, busy: bool, label: str | None = None) -> None:
        self.busy = busy
        # Action buttons also stay disabled when no game is active.
        self._update_action_states()
        combo_state = tk.DISABLED if busy else "readonly"
        self.language_combo.configure(state=combo_state)
        self.game_combo.configure(state=combo_state)
        self.add_game_button.configure(state=tk.DISABLED if busy else tk.NORMAL)
        for button in (self.xinput_download_button, self.xinput_recheck_button, self.xinput_open_button):
            button.configure(state=tk.DISABLED if busy else tk.NORMAL)
        if busy:
            self._status_error_pending = False
            self.status_bar.set_busy(label or self.translator.t("busy"))
        elif not self._status_error_pending:
            self.status_bar.set_idle()

    def thread_log(self, message: str) -> None:
        self.queue.put(("log", message))

    def _poll_queue(self) -> None:
        processed = 0
        try:
            while processed < QUEUE_POLL_ITEM_LIMIT:
                kind, payload = self.queue.get_nowait()
                processed += 1
                if kind == "log":
                    self.log_panel.info(str(payload))
                elif kind == "status":
                    self.log_panel.status(str(payload))
                elif kind == "error":
                    self.log_panel.error(str(payload))
                    self._status_error_pending = True
                    self.status_bar.set_error(str(payload))
                    messagebox.showerror(self.translator.t("operation_failed"), str(payload))
                elif kind == "refresh":
                    self.refresh_all(keep_selection=payload if isinstance(payload, str) else None)
                elif kind == "xinput":
                    self._update_xinput_banner()
                elif kind == "busy":
                    self.set_busy(bool(payload))
                elif kind == "model_info_diff_done":
                    if isinstance(payload, dict):
                        game_id = payload.get("game_id")
                        mod_id = payload.get("mod_id")
                        target = payload.get("target")
                        if (
                            game_id == self.core.game_id
                            and mod_id == self.mod_list.get_selected_mod_id()
                            and isinstance(target, str)
                        ):
                            diff = self._model_info_diff_entry_for_target(str(mod_id), target)
                            self.preview_panel.update_model_info_diff_for_target(target, diff)
        except queue.Empty:
            pass
        delay = 1 if processed >= QUEUE_POLL_ITEM_LIMIT else 100
        self.root.after(delay, self._poll_queue)


def main() -> int:
    core = ModManagerCore()
    root = TkinterDnD.Tk()
    ModManagerApp(root, core)
    root.mainloop()
    return 0
