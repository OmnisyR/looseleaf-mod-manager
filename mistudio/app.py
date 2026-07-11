"""MI Studio main window (tkinter, reuses the mod manager's theme)."""
from __future__ import annotations

import queue
import threading
import time
import traceback
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import Any, Callable

from modmanager.core import ModManagerCore
from modmanager.i18n import LANGUAGES, Translator
from modmanager.model_info import JsonValue, decode_model_info_json
from modmanager.pathutils import normalize_key, now_label
from modmanager.ui.status_bar import StatusBar
from modmanager.ui.theme import apply_theme
from modmanager.ui.tooltip import ToolTip

from .catalog import CATEGORY_ORDER, MiEntry, build_catalog
from . import entry_display
from .fields import (
    field_help,
    field_is_integer,
    field_label,
    field_range,
    section_help,
    section_label,
)
from .import_dialog import ImportDialog
from .i18n import install_mistudio_translations
from .log_panel import MiLogPanel
from .references import ReferenceLibrary, ReferenceOption, build_reference_library, default_reference
from .tree_selection import SelectionRail
from .tree_state import StructTreeState, capture_struct_tree_state, restore_struct_tree_state
from .window_state import (
    MI_STUDIO_DEFAULT_GEOMETRY,
    MI_STUDIO_GEOMETRY_KEY,
    MI_STUDIO_STATE_KEY,
    WindowState,
)
from .workspace import (
    TWEAKS_MOD_ID,
    TWEAKS_MOD_NAME,
    MiWorkspace,
    SemanticPath,
    get_value,
    item_label,
    mirrored_path,
    resolve_path,
)

FAV_ROOT = "fav-root"

_FONT = "Microsoft YaHei UI"
FILTER_DROPDOWN_ROWS = 18

ORIGIN_FILTERS = [
    ("all", "mi_all_origins"),
    ("official", "mi_origin_official"),
    ("mod_override", "mi_origin_mod_override"),
    ("mod_new", "mi_origin_mod_new"),
    ("loose", "mi_origin_loose"),
    ("modified", "mi_origin_modified"),
]

CATEGORY_KEYS = {
    "角色": "mi_category_character",
    "装备": "mi_category_equipment",
    "怪物": "mi_category_monster",
    "物件": "mi_category_object",
    "地图": "mi_category_map",
    "特效": "mi_category_effect",
    "导力器": "mi_category_orbment",
    "小游戏": "mi_category_minigame",
    "其他": "mi_category_other",
}


def format_value(value: Any, translator: Translator | None = None) -> str:
    if isinstance(value, bool):
        if translator is not None:
            return translator.t("yes") if value else translator.t("no")
        return "是" if value else "否"
    if value is None:
        return "null"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, dict):
        return f"{{{len(value)} items}}" if translator and translator.language.startswith("en") else f"{{{len(value)} 项}}"
    if isinstance(value, list):
        return f"[{len(value)} items]" if translator and translator.language.startswith("en") else f"[{len(value)} 条]"
    return str(value)


def _normalize_number(value: float) -> int | float:
    # The decoder turns whole doubles into ints; mirror that so edited docs
    # compare equal to decoded baselines.
    return int(value) if float(value).is_integer() else float(value)


class MiStudioApp:
    def __init__(
        self,
        root: tk.Tk,
        core: ModManagerCore,
        on_open_mod_manager: Callable[[], None] | None = None,
    ) -> None:
        install_mistudio_translations()
        self.root = root
        self.core = core
        self.on_open_mod_manager = on_open_mod_manager
        self.translator = Translator(self.core.config.language)
        self.colors = apply_theme(root)
        self.window_state = WindowState(root, self.core.config)
        self.window_state.apply_initial_geometry()
        self._last_normal_geometry = self.window_state.last_normal_geometry
        root.minsize(1180, 720)

        style = ttk.Style()
        style.configure("Horizontal.TScale", background=self.colors["panel"], troughcolor=self.colors["panel2"])
        style.configure("Panel2.TFrame", background=self.colors["panel2"])
        style.configure("Panel2.TLabel", background=self.colors["panel2"], foreground=self.colors["text"])
        style.configure("Panel2Muted.TLabel", background=self.colors["panel2"], foreground=self.colors["muted"])
        style.configure("Header.TLabel", background=self.colors["bg"], foreground=self.colors["text"], font=(_FONT, 14, "bold"))
        style.configure("SubHeader.TLabel", background=self.colors["panel"], foreground=self.colors["text"], font=(_FONT, 12, "bold"))

        self.workspace = MiWorkspace(core)
        self.catalog: dict[str, MiEntry] = {}
        self._effective_cache: dict[str, JsonValue | None] = {}
        self._official_cache: dict[str, JsonValue | None] = {}
        self._diff_cache: dict[str, bool] = {}
        self.ref_library = ReferenceLibrary(files_by_mod={}, mod_labels={}, mod_ids=[None])
        self._ref_file_options: list[ReferenceOption] = []
        self._dirty = False
        self._unsaved_targets: set[str] = set()
        self._busy = False
        self._loading = False
        self._closing = False
        self._worker_threads: set[threading.Thread] = set()
        self._worker_threads_lock = threading.Lock()
        self._status_text = ""

        self.current_entry: MiEntry | None = None
        self._doc: JsonValue | None = None
        self._baseline: JsonValue | None = None
        self._reference: JsonValue | None = None
        self._ref_pref_mod: str | None = None
        self._ref_pref_target: str | None = None
        self._ref_locked_mod: str | None = None
        self._ref_locked_target: str | None = None
        self._leaf_paths: dict[str, SemanticPath] = {}
        self._branch_paths: dict[str, SemanticPath] = {}
        self._node_help: dict[str, str] = {}
        self._struct_view_state = StructTreeState()
        self._edit_path: SemanticPath | None = None
        self._edit_kind: str | None = None
        self._edit_field: str = ""
        self._selected_path: SemanticPath | None = None
        self._scope_options: list[tuple[str, Callable[[], list[str]]]] = []
        self._target_groups: dict[str, list[str]] = {}
        self._row_targets: dict[str, str] = {}
        self._category_values: list[str | None] = [None]
        self._group_filter_values: list[str | None] = [None]
        self._character_options: list[str] = []
        self._character_ids: list[str | None] = [None]
        self._slider_dragging = False
        self._suppress_list_event = False
        self.ref_lock_var = tk.BooleanVar(value=False)

        # Worker threads may not touch Tk on Python 3.13+ (`after` raises
        # "main thread is not in main loop"), so they post callables here and
        # the main thread drains the queue on a timer.
        self._ui_queue: queue.Queue[tuple[Callable[..., None], tuple]] = queue.Queue()
        self._ui_poll_job: str | None = None
        self._poll_ui_queue()
        root.bind("<Destroy>", self._cancel_ui_poll, add="+")

        self._build_ui()
        self.set_language()
        self.reload(initial=True)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.bind("<Configure>", self._on_root_configure)
        self._restore_window_layout()

    # ------------------------------------------------------------ threading --

    def _post(self, fn: Callable[..., None], *args: object) -> None:
        """Queue a callable to run on the UI thread (safe from any thread)."""
        if self._closing:
            return
        self._ui_queue.put((fn, args))

    def _poll_ui_queue(self) -> None:
        if self._closing:
            return
        try:
            while True:
                fn, args = self._ui_queue.get_nowait()
                try:
                    fn(*args)
                except Exception:  # keep the poller alive on callback errors
                    traceback.print_exc()
        except queue.Empty:
            pass
        try:
            self._ui_poll_job = self.root.after(50, self._poll_ui_queue)
        except tk.TclError:
            self._ui_poll_job = None  # window destroyed

    def _cancel_ui_poll_job(self) -> None:
        if self._ui_poll_job is None:
            return
        try:
            self.root.after_cancel(self._ui_poll_job)
        except tk.TclError:
            pass
        self._ui_poll_job = None

    def _cancel_ui_poll(self, event: object) -> None:
        if getattr(event, "widget", None) is not self.root:
            return
        self._cancel_ui_poll_job()

    def _start_worker(self, target: Callable[[], None], name: str) -> None:
        def run() -> None:
            try:
                target()
            finally:
                current = threading.current_thread()
                with self._worker_threads_lock:
                    self._worker_threads.discard(current)

        thread = threading.Thread(target=run, name=name, daemon=True)
        with self._worker_threads_lock:
            self._worker_threads.add(thread)
        thread.start()

    def _has_active_workers(self) -> bool:
        with self._worker_threads_lock:
            self._worker_threads = {thread for thread in self._worker_threads if thread.is_alive()}
            return bool(self._worker_threads)

    def _join_worker_threads(self, timeout: float = 0.8) -> None:
        deadline = time.monotonic() + timeout
        with self._worker_threads_lock:
            threads = list(self._worker_threads)
        for thread in threads:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if thread is threading.current_thread():
                continue
            thread.join(remaining)
        with self._worker_threads_lock:
            self._worker_threads = {thread for thread in self._worker_threads if thread.is_alive()}

    def _shutdown_tk_state(self) -> None:
        self._closing = True
        self._cancel_ui_poll_job()
        self.window_state.cancel_pending()
        for name in ("_list_tooltip", "_struct_tooltip"):
            tooltip = getattr(self, name, None)
            if tooltip is not None:
                try:
                    tooltip.hide()
                except tk.TclError:
                    pass
        self._join_worker_threads()
        for name in ("search_var", "sym_var", "bool_var", "value_var", "ref_lock_var"):
            if hasattr(self, name):
                setattr(self, name, None)

    # ------------------------------------------------------------------ UI --

    def _build_ui(self) -> None:
        root = self.root
        root.rowconfigure(2, weight=1)
        root.columnconfigure(0, weight=1)

        header = ttk.Frame(root, padding=(16, 14, 16, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        self.mod_manager_button = ttk.Button(header, style="Switch.TButton", command=self._switch_to_mod_manager)
        self.mod_manager_button.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 14))
        self.title_label = ttk.Label(header, style="Header.TLabel")
        self.title_label.grid(row=0, column=1, sticky="w")
        self.subtitle_label = ttk.Label(header, style="Muted.TLabel")
        self.subtitle_label.grid(row=1, column=1, sticky="w", pady=(4, 0))

        toolbar = ttk.Frame(header)
        toolbar.grid(row=0, column=2, rowspan=2, sticky="e")
        self.reload_button = ttk.Button(toolbar, command=self.reload)
        self.reload_button.grid(row=0, column=0, padx=(0, 6))
        self.save_button = ttk.Button(toolbar, style="Accent.TButton", command=self._save)
        self.save_button.grid(row=0, column=1, padx=(0, 6))
        self.apply_button = ttk.Button(toolbar, command=self._apply_to_game)
        self.apply_button.grid(row=0, column=2, padx=(0, 16))
        self.language_label = ttk.Label(toolbar, style="Muted.TLabel")
        self.language_label.grid(row=0, column=3, padx=(0, 6))
        self.language_combo = ttk.Combobox(toolbar, state="readonly", width=12)
        self.language_combo.grid(row=0, column=4)
        self.language_combo.bind("<<ComboboxSelected>>", self._on_language_selected)

        ttk.Separator(root, orient=tk.HORIZONTAL).grid(row=0, column=0, sticky="sew")

        main = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        main.grid(row=2, column=0, sticky="nsew", padx=16, pady=(10, 8))
        left = ttk.Frame(main, style="Panel.TFrame", padding=12)
        right = ttk.Frame(main, style="Panel.TFrame", padding=12)
        main.add(left, weight=11)
        main.add(right, weight=14)

        self._build_left(left)
        self._build_right(right)

        self.log_panel = MiLogPanel(root, self.colors, height=5)
        self.log_panel.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 0))

        self.status_bar = StatusBar(root, self.colors, self.translator)
        self.status_bar.grid(row=4, column=0, sticky="ew")
        self.status_label = self.status_bar.status_label

    def _build_left(self, left: ttk.Frame) -> None:
        left.rowconfigure(3, weight=1)
        left.columnconfigure(0, weight=1)

        filters = ttk.Frame(left, style="Panel.TFrame")
        filters.grid(row=0, column=0, sticky="ew")
        filters.columnconfigure(1, weight=1)
        self.search_label = ttk.Label(filters, style="PanelMuted.TLabel")
        self.search_label.grid(row=0, column=0, padx=(0, 6))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_list())
        search_entry = tk.Entry(
            filters,
            textvariable=self.search_var,
            bg=self.colors["input_bg"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            relief="flat",
            font=(_FONT, 10),
        )
        search_entry.grid(row=0, column=1, sticky="ew", ipady=4)
        self.category_combo = ttk.Combobox(filters, state="readonly", width=8, height=FILTER_DROPDOWN_ROWS)
        self.category_combo.grid(row=0, column=2, padx=(8, 0))
        self.category_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_list())
        self.origin_combo = ttk.Combobox(filters, state="readonly", width=12, height=FILTER_DROPDOWN_ROWS)
        self.origin_combo.grid(row=0, column=3, padx=(8, 0))
        self.origin_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_list())

        row2 = ttk.Frame(left, style="Panel.TFrame")
        row2.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        row2.columnconfigure(0, weight=1)
        row2.columnconfigure(1, weight=1)
        self.character_combo = ttk.Combobox(row2, state="readonly", height=FILTER_DROPDOWN_ROWS)
        self.character_combo.grid(row=0, column=0, sticky="ew")
        self.character_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_list())
        self.group_filter_combo = ttk.Combobox(row2, state="readonly", height=FILTER_DROPDOWN_ROWS)
        self.group_filter_combo.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self.group_filter_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_list())

        group_bar = ttk.Frame(left, style="Panel.TFrame")
        group_bar.grid(row=2, column=0, sticky="ew", pady=(8, 8))
        self.group_label = ttk.Label(group_bar, style="PanelMuted.TLabel")
        self.group_label.pack(side=tk.LEFT)
        self.create_group_button = ttk.Button(group_bar, command=self._create_group)
        self.create_group_button.pack(side=tk.LEFT, padx=(0, 6))
        self.add_group_button = ttk.Button(group_bar, command=self._add_selection_to_group)
        self.add_group_button.pack(side=tk.LEFT, padx=(0, 6))
        self.remove_group_button = ttk.Button(group_bar, command=self._remove_selection_from_group)
        self.remove_group_button.pack(side=tk.LEFT, padx=(0, 6))
        self.delete_group_button = ttk.Button(group_bar, command=self._delete_group)
        self.delete_group_button.pack(side=tk.LEFT)

        tree_holder = ttk.Frame(left, style="Panel.TFrame")
        tree_holder.grid(row=3, column=0, sticky="nsew")
        tree_holder.rowconfigure(0, weight=1)
        tree_holder.columnconfigure(0, weight=1)
        self.list_tree = ttk.Treeview(
            tree_holder,
            columns=("name", "file", "source", "group", "state"),
            show="headings",
            selectmode="extended",
            style="Rail.Treeview",
        )
        for column, width, minwidth, stretch in (
            ("name", 220, 150, True),
            ("file", 136, 112, False),
            ("source", 112, 96, False),
            ("group", 92, 76, False),
            ("state", 116, 108, False),
        ):
            self.list_tree.heading(column, text="", anchor="w")
            self.list_tree.column(column, width=width, minwidth=minwidth, anchor="w", stretch=stretch)
        self.list_tree.grid(row=0, column=0, sticky="nsew")
        list_scroll = ttk.Scrollbar(tree_holder, orient=tk.VERTICAL)
        list_scroll.grid(row=0, column=1, sticky="ns")
        self.list_rail = SelectionRail(tree_holder, self.list_tree, list_scroll, self.colors)
        self.list_tree.tag_configure("even", background=self.colors["panel"])
        self.list_tree.tag_configure("odd", background=self.colors["stripe"])
        self.list_tree.tag_configure("state-modified", foreground=self.colors["diff_changed_fg"])
        self.list_tree.tag_configure("state-unsaved", foreground=self.colors["accent"])
        self.list_tree.tag_configure("state-saved", foreground=self.colors["green"])
        self.list_tree.tag_configure("unrecognized", foreground=self.colors["muted"])
        self.list_tree.tag_configure("modnew", foreground=self.colors["green"])
        self.list_tree.bind("<<TreeviewSelect>>", self._on_list_select)
        self._list_tooltip = ToolTip(self.list_tree, self.colors)
        self.list_tree.bind("<Motion>", self._on_list_motion)
        self.list_tree.bind("<Leave>", lambda _e: self._list_tooltip.hide())

        self.count_label = ttk.Label(left, style="PanelMuted.TLabel")
        self.count_label.grid(row=4, column=0, sticky="w", pady=(6, 0))

    def _build_right(self, right: ttk.Frame) -> None:
        right.rowconfigure(3, weight=1)
        right.columnconfigure(0, weight=1)

        header = ttk.Frame(right, style="Panel.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        self.entry_title = ttk.Label(header, style="SubHeader.TLabel")
        self.entry_title.grid(row=0, column=0, sticky="w")
        self.entry_state_label = ttk.Label(header, style="PanelMuted.TLabel")
        self.entry_state_label.grid(row=0, column=1, sticky="e")
        self.entry_detail = ttk.Label(header, style="PanelMuted.TLabel", justify=tk.LEFT)
        self.entry_detail.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))

        toolbar = ttk.Frame(right, style="Panel.TFrame")
        toolbar.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        self.import_button = ttk.Button(toolbar, command=self._open_import_dialog)
        self.import_button.pack(side=tk.LEFT, padx=(0, 6))
        self.revert_button = ttk.Button(toolbar, command=self._revert_current)
        self.revert_button.pack(side=tk.LEFT, padx=(0, 6))
        self.expand_button = ttk.Button(toolbar, command=lambda: self._set_tree_open(True))
        self.expand_button.pack(side=tk.LEFT, padx=(0, 6))
        self.collapse_button = ttk.Button(toolbar, command=lambda: self._set_tree_open(False))
        self.collapse_button.pack(side=tk.LEFT)
        # Compatibility hook for tests/older callers; the visible favorite
        # action is the per-row star column in the structure tree.
        self.fav_button = ttk.Button(toolbar, text="★", command=self._toggle_favorite, state="disabled")

        # Reference pickers get their own full-width row so long mod and file
        # names stay readable instead of being squeezed into the toolbar.
        refbar = ttk.Frame(right, style="Panel.TFrame")
        refbar.grid(row=2, column=0, sticky="ew", pady=(4, 8))
        refbar.columnconfigure(1, weight=2, uniform="ref")
        refbar.columnconfigure(3, weight=3, uniform="ref")
        self.ref_mod_label = ttk.Label(refbar, style="PanelMuted.TLabel")
        self.ref_mod_label.grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.ref_combo = ttk.Combobox(refbar, state="readonly")
        self.ref_combo.bind("<<ComboboxSelected>>", self._on_ref_selected)
        self.ref_combo.grid(row=0, column=1, sticky="ew", padx=(0, 14))
        self.ref_file_label = ttk.Label(refbar, style="PanelMuted.TLabel")
        self.ref_file_label.grid(row=0, column=2, sticky="w", padx=(0, 6))
        self.ref_file_combo = ttk.Combobox(refbar, state="disabled", values=[""])
        self.ref_file_combo.bind("<<ComboboxSelected>>", self._on_ref_file_selected)
        self.ref_file_combo.grid(row=0, column=3, sticky="ew")
        self.ref_lock_check = ttk.Checkbutton(refbar, variable=self.ref_lock_var, command=self._on_ref_lock_changed)
        self.ref_lock_check.grid(row=0, column=4, sticky="e", padx=(10, 0))

        tree_holder = ttk.Frame(right, style="Panel.TFrame")
        tree_holder.grid(row=3, column=0, sticky="nsew")
        tree_holder.rowconfigure(0, weight=1)
        tree_holder.columnconfigure(0, weight=1)
        self.struct_tree = ttk.Treeview(
            tree_holder,
            columns=("value", "base", "ref", "fav"),
            show="tree headings",
            style="Rail.Treeview",
        )
        self.struct_tree.heading("#0", text="", anchor="w")
        self.struct_tree.heading("value", text="", anchor="w")
        self.struct_tree.heading("base", text="", anchor="w")
        self.struct_tree.heading("ref", text="", anchor="w")
        self.struct_tree.heading("fav", text="★", anchor="center")
        self.struct_tree.column("#0", width=300, minwidth=180, stretch=True)
        self.struct_tree.column("value", width=140, minwidth=90, anchor="w", stretch=False)
        self.struct_tree.column("base", width=140, minwidth=90, anchor="w", stretch=False)
        self.struct_tree.column("ref", width=140, minwidth=90, anchor="w", stretch=False)
        self.struct_tree.column("fav", width=36, minwidth=32, anchor="center", stretch=False)
        self.struct_tree.grid(row=0, column=0, sticky="nsew")
        struct_scroll = ttk.Scrollbar(tree_holder, orient=tk.VERTICAL)
        struct_scroll.grid(row=0, column=1, sticky="ns")
        self.struct_rail = SelectionRail(tree_holder, self.struct_tree, struct_scroll, self.colors)
        self.struct_tree.tag_configure("changed", background=self.colors["diff_changed_bg"], foreground=self.colors["diff_changed_fg"])
        self.struct_tree.tag_configure("branch-changed", foreground=self.colors["diff_changed_fg"])
        self.struct_tree.tag_configure("empty", foreground=self.colors["muted"])
        self.struct_tree.tag_configure("favorite", foreground=self.colors["accent"])
        self.struct_tree.bind("<<TreeviewSelect>>", self._on_struct_select)
        self.struct_tree.bind("<Button-1>", self._on_struct_click, add="+")
        self._struct_tooltip = ToolTip(self.struct_tree, self.colors)
        self.struct_tree.bind("<Motion>", self._on_struct_motion)
        self.struct_tree.bind("<Leave>", lambda _e: self._struct_tooltip.hide())

        self._build_edit_panel(right)

    def _build_edit_panel(self, right: ttk.Frame) -> None:
        panel = ttk.Frame(right, style="Panel2.TFrame", padding=10)
        panel.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        panel.columnconfigure(1, weight=1)
        self.edit_panel = panel

        self.edit_title = ttk.Label(panel, style="Panel2.TLabel", font=(_FONT, 10, "bold"))
        self.edit_title.grid(row=0, column=0, columnspan=4, sticky="w")
        self.edit_help = ttk.Label(panel, text="", style="Panel2Muted.TLabel", wraplength=680, justify=tk.LEFT)
        self.edit_help.grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 6))

        self.sym_var = tk.BooleanVar(value=True)
        self.sym_check = ttk.Checkbutton(panel, variable=self.sym_var)
        self.sym_check.grid(row=2, column=0, sticky="w", padx=(0, 12))
        self.bool_var = tk.BooleanVar(value=False)
        self.bool_check = ttk.Checkbutton(panel, variable=self.bool_var, command=self._commit_from_bool)
        self.value_var = tk.StringVar()
        self.value_box = tk.Frame(
            panel,
            bg=self.colors["line"],
            padx=1,
            pady=1,
            highlightthickness=0,
            borderwidth=0,
        )
        self.value_box.columnconfigure(0, weight=1)
        self.value_entry = tk.Entry(
            self.value_box,
            textvariable=self.value_var,
            width=14,
            bg=self.colors["input_bg"],
            fg=self.colors["text"],
            insertbackground=self.colors["text"],
            disabledbackground=self.colors["panel2"],
            disabledforeground=self.colors["disabled"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=(_FONT, 10),
        )
        self.value_entry.grid(row=0, column=0, sticky="ew", padx=8, ipady=4)
        self.value_entry.bind("<Return>", lambda _e: self._commit_from_entry())
        self.scale = ttk.Scale(panel, orient=tk.HORIZONTAL, from_=0.0, to=1.0, command=self._on_scale_move)
        self.scale.bind("<ButtonPress-1>", lambda _e: self._begin_slider())
        self.scale.bind("<ButtonRelease-1>", lambda _e: self._commit_from_slider())
        self.range_label = ttk.Label(panel, text="", style="Panel2Muted.TLabel")

        self.scale.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.value_box.grid(row=3, column=2, sticky="ew", padx=(10, 0))
        self.range_label.grid(row=2, column=1, sticky="w")
        self.bool_check.grid(row=2, column=2, sticky="e")

        buttons = ttk.Frame(panel, style="Panel2.TFrame")
        buttons.grid(row=3, column=3, sticky="e", padx=(10, 0))
        self.apply_edit_button = ttk.Button(buttons, style="Accent.TButton", command=self._commit_from_entry)
        self.apply_edit_button.pack(side=tk.LEFT, padx=(0, 6))
        self.reset_field_button = ttk.Button(buttons, command=self._reset_field)
        self.reset_field_button.pack(side=tk.LEFT)

        scope_row = ttk.Frame(panel, style="Panel2.TFrame")
        scope_row.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        self.scope_label = ttk.Label(scope_row, style="Panel2Muted.TLabel")
        self.scope_label.pack(side=tk.LEFT, padx=(0, 8))
        self.scope_combo = ttk.Combobox(scope_row, state="readonly", width=36)
        self.scope_combo.pack(side=tk.LEFT)
        self.bool_check.grid_remove()
        self._set_edit_enabled(False)

    def set_language(self) -> None:
        t = self.translator.t
        self.root.title(t("mi_app_title"))
        self.title_label.configure(text=t("mi_title"))
        game_root = self.core.game_root if self.core.game_root else ""
        self.subtitle_label.configure(text=t("mi_subtitle", game_root=game_root, mod_name=TWEAKS_MOD_NAME))
        self.mod_manager_button.configure(text=t("mi_open_mod_manager"))
        self.reload_button.configure(text=t("mi_reload"))
        self.save_button.configure(text=t("mi_save"))
        self.apply_button.configure(text=t("mi_apply_game"))
        self.language_label.configure(text=t("language"))
        self.language_combo.configure(values=list(LANGUAGES.values()))
        self.language_combo.set(LANGUAGES.get(self.translator.language, LANGUAGES["zh_CN"]))

        self.search_label.configure(text=t("mi_search"))
        self.group_label.configure(text=t("mi_group_label"))
        self.create_group_button.configure(text=t("mi_new_group"))
        self.add_group_button.configure(text=t("mi_add_group"))
        self.remove_group_button.configure(text=t("mi_remove_group"))
        self.delete_group_button.configure(text=t("mi_delete_group"))
        self.list_tree.heading("name", text=t("mi_col_name"))
        self.list_tree.heading("file", text=t("mi_col_file"))
        self.list_tree.heading("source", text=t("mi_col_source"))
        self.list_tree.heading("group", text=t("mi_col_group"))
        self.list_tree.heading("state", text=t("mi_col_state"))

        self.import_button.configure(text=t("mi_import_other"))
        self.revert_button.configure(text=t("mi_revert_file"))
        self.expand_button.configure(text=t("mi_expand_all"))
        self.collapse_button.configure(text=t("mi_collapse_all"))
        self.ref_file_label.configure(text=t("mi_ref_file"))
        self.ref_mod_label.configure(text=t("mi_ref_mod"))
        self.ref_lock_check.configure(text=t("mi_ref_lock"))
        self.struct_tree.heading("#0", text=t("mi_struct_item"))
        self.struct_tree.heading("value", text=t("mi_current_value"))
        self.struct_tree.heading("base", text=t("mi_baseline_value"))
        self.struct_tree.heading("ref", text=t("mi_reference_value"))
        self.sym_check.configure(text=t("mi_symmetry"))
        self.bool_check.configure(text=t("mi_enabled"))
        self.apply_edit_button.configure(text=t("mi_apply_edit"))
        self.reset_field_button.configure(text=t("mi_reset_field"))
        self.scope_label.configure(text=t("mi_scope"))
        self.log_panel.set_title(t("log"))
        self.status_bar.set_language()
        if not self.ref_combo.cget("values"):
            self.ref_combo.configure(values=[t("mi_no_reference")])
            self.ref_combo.current(0)
        if self._status_text in ("", "就绪", "Ready"):
            self._set_status(t("mi_ready"))

        origin_index = max(self.origin_combo.current(), 0)
        self.origin_combo.configure(values=[t(label_key) for _key, label_key in ORIGIN_FILTERS])
        if origin_index < len(ORIGIN_FILTERS):
            self.origin_combo.current(origin_index)

        if self.catalog:
            self._refresh_category_combo()
            self._refresh_character_combo()
            self._refresh_group_filter()
            self._refresh_scope_options()
            self._refresh_list()
            if self.current_entry is not None:
                self._show_entry(self.current_entry)
            else:
                self._show_entry(None)
        else:
            self._clear_edit_panel()

    def _on_language_selected(self, _event: object) -> None:
        index = max(self.language_combo.current(), 0)
        codes = list(LANGUAGES)
        if index >= len(codes):
            return
        language = codes[index]
        self.translator.set_language(language)
        self.core.config.language = language
        self.core.config.save()
        self.set_language()

    def _category_label(self, category: str) -> str:
        return self.translator.t(CATEGORY_KEYS.get(category, "mi_category_other"))

    def _origin_label(self, entry: MiEntry) -> str:
        key = {
            "official": "mi_origin_official",
            "mod_override": "mi_origin_mod_override",
            "mod_new": "mi_origin_mod_new",
            "loose": "mi_origin_loose",
        }.get(entry.origin)
        label = self.translator.t(key) if key else entry.origin
        if entry.origin in ("mod_override", "mod_new") and entry.baseline and entry.baseline.kind == "mod" and not entry.baseline.enabled:
            label += self.translator.t("mi_source_disabled")
        return label

    def _entry_character_id(self, entry: MiEntry) -> str | None:
        return entry_display.character_id(entry)

    def _entry_recognized(self, entry: MiEntry) -> bool:
        return entry_display.is_recognized(entry)

    def _entry_display_name(self, entry: MiEntry) -> str:
        return entry_display.display_name(entry, self.translator.language)

    def _entry_character_name(self, entry: MiEntry) -> str:
        return entry_display.character_name(entry, self.translator.language)

    def _entry_state_text(self, state: str) -> str:
        if state == "unsaved":
            return self.translator.t("mi_modified_unsaved")
        if state == "saved":
            return self.translator.t("mi_saved_tweak")
        if state == "modified":
            return self.translator.t("mi_modified_mark")
        return ""

    def _refresh_category_combo(self) -> None:
        current_raw = None
        current_index = self.category_combo.current()
        if 0 <= current_index < len(self._category_values):
            current_raw = self._category_values[current_index]
        raw_categories = [c for c in CATEGORY_ORDER if any(e.category == c for e in self.catalog.values())]
        self._category_values = [None] + raw_categories
        self.category_combo.configure(
            values=[self.translator.t("mi_all_categories")] + [self._category_label(category) for category in raw_categories]
        )
        if current_raw in raw_categories:
            self.category_combo.current(self._category_values.index(current_raw))
        elif "角色" in raw_categories:
            self.category_combo.current(self._category_values.index("角色"))
        else:
            self.category_combo.current(0)

    def _refresh_character_combo(self) -> None:
        current_raw = None
        current_index = self.character_combo.current()
        if 0 <= current_index < len(self._character_ids):
            current_raw = self._character_ids[current_index]

        characters: dict[str, str] = {}
        for entry in self.catalog.values():
            character_id = self._entry_character_id(entry)
            character_name = self._entry_character_name(entry)
            if character_id and character_name:
                characters.setdefault(character_id, character_name)

        ordered = sorted(characters.items(), key=lambda item: entry_display.character_sort_key(item[0]))
        self._character_options = [self.translator.t("mi_all_characters")] + [f"{name} ({cid})" for cid, name in ordered]
        self._character_ids = [None] + [cid for cid, _name in ordered]
        self.character_combo.configure(values=self._character_options)
        if current_raw in self._character_ids:
            self.character_combo.current(self._character_ids.index(current_raw))
        else:
            self.character_combo.current(0)

    # -------------------------------------------------------------- loading --

    def reload(self, initial: bool = False) -> None:
        """Reload data in a worker thread so the window stays responsive.

        The window opens (or keeps running) immediately with the busy
        animation in the status bar; the catalog scan, tweak decoding and
        mod-diff pre-computation all happen off the UI thread.
        """
        if self._busy or self._loading:
            return
        if not initial and self._dirty:
            if not messagebox.askyesno(self.translator.t("mi_reload_title"), self.translator.t("mi_reload_confirm"), parent=self.root):
                return
        self._loading = True
        self._set_busy(True, self.translator.t("mi_loading"))

        core = self.core

        def worker() -> None:
            try:
                state = core._load_state()
                core.state = state
                workspace = MiWorkspace(core)
                catalog = build_catalog(core.game_root, state, core.mod_files_root, TWEAKS_MOD_ID)
                ref_library = build_reference_library(catalog)
                effective_cache: dict[str, JsonValue | None] = {}
                official_cache: dict[str, JsonValue | None] = {}
                diff_cache: dict[str, bool] = {}
                # Pre-compute the mod-vs-official diff badges here so the UI
                # thread never has to decode files just to paint the list.
                for key, entry in catalog.items():
                    if entry.baseline is None or entry.baseline.kind == "pac":
                        diff_cache[key] = False
                        continue
                    effective = self._decode(entry.read_baseline())
                    official = self._decode(entry.read_official())
                    effective_cache[key] = effective
                    official_cache[key] = official
                    baseline = official if official is not None else effective
                    diff_cache[key] = effective is not None and baseline is not None and effective != baseline
                self._post(self._finish_reload, workspace, catalog, ref_library, effective_cache, official_cache, diff_cache, initial)
            except Exception as exc:
                self._post(self._fail_reload, exc)

        self._start_worker(worker, "mi-reload")

    def _finish_reload(
        self,
        workspace: MiWorkspace,
        catalog: dict[str, MiEntry],
        ref_library: ReferenceLibrary,
        effective_cache: dict[str, JsonValue | None],
        official_cache: dict[str, JsonValue | None],
        diff_cache: dict[str, bool],
        initial: bool,
    ) -> None:
        try:
            self.workspace = workspace
            self.catalog = catalog
            self.ref_library = ref_library
            self._effective_cache = effective_cache
            self._official_cache = official_cache
            self._diff_cache = diff_cache
            self._dirty = False
            self._unsaved_targets.clear()
            self.subtitle_label.configure(text=self.translator.t("mi_subtitle", game_root=self.core.game_root, mod_name=TWEAKS_MOD_NAME))
            self._refresh_category_combo()
            self._refresh_character_combo()

            self._refresh_group_filter()
            self._refresh_list()
            self._show_entry(None)
            if initial:
                self._log(self.translator.t("mi_loaded", count=len(self.catalog)))
                if self.workspace.docs:
                    self._log(self.translator.t("mi_loaded_tweaks", count=len(self.workspace.docs), mod_name=TWEAKS_MOD_NAME))
            else:
                self._log(self.translator.t("mi_reloaded"))
            self._set_status(self.translator.t("mi_ready"))
        finally:
            self._loading = False
            self._set_busy(False)

    def _fail_reload(self, exc: Exception) -> None:
        self._loading = False
        self._set_busy(False)
        self._log(self.translator.t("mi_load_failed", error=exc), "error")
        self.status_bar.set_error(self.translator.t("mi_load_failed", error=exc))

    def wait_until_loaded(self, timeout: float = 15.0) -> None:
        """Pump the event loop until the async load finishes (used by tests)."""
        import time

        deadline = time.monotonic() + timeout
        while self._loading and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)

    def _refresh_group_filter(self) -> None:
        current_raw = None
        current_index = self.group_filter_combo.current()
        if 0 <= current_index < len(self._group_filter_values):
            current_raw = self._group_filter_values[current_index]
        names = self.workspace.group_names()
        self._group_filter_values = [None, "__ungrouped__"] + names
        self.group_filter_combo.configure(values=[self.translator.t("mi_all_groups"), self.translator.t("mi_ungrouped")] + names)
        if current_raw in self._group_filter_values:
            self.group_filter_combo.current(self._group_filter_values.index(current_raw))
        else:
            self.group_filter_combo.current(0)
        self._rebuild_target_groups()

    def _rebuild_target_groups(self) -> None:
        mapping: dict[str, list[str]] = {}
        for name, members in self.workspace.groups.items():
            for member in members:
                mapping.setdefault(normalize_key(member), []).append(name)
        self._target_groups = mapping

    # -------------------------------------------------------------- list -----

    def _visible_entries(self) -> list[MiEntry]:
        search = self.search_var.get().strip().casefold()
        category_index = max(self.category_combo.current(), 0)
        category = self._category_values[category_index] if category_index < len(self._category_values) else None
        origin_key = ORIGIN_FILTERS[max(self.origin_combo.current(), 0)][0]
        char_index = max(self.character_combo.current(), 0)
        char_id = self._character_ids[char_index] if char_index < len(self._character_ids) else None
        group_index = max(self.group_filter_combo.current(), 0)
        group_choice = self._group_filter_values[group_index] if group_index < len(self._group_filter_values) else None

        entries = []
        for entry in self.catalog.values():
            if category is not None and entry.category != category:
                continue
            if char_id and self._entry_character_id(entry) != char_id:
                continue
            if origin_key == "modified":
                if not self._has_baseline_diff(entry.target):
                    continue
            elif origin_key != "all" and entry.origin != origin_key:
                continue
            groups = self._target_groups.get(normalize_key(entry.target), [])
            if group_choice == "__ungrouped__" and groups:
                continue
            if group_choice not in (None, "__ungrouped__") and group_choice not in groups:
                continue
            if search and not (
                search in entry.stem.casefold()
                or search in self._entry_display_name(entry).casefold()
                or search in self._entry_character_name(entry).casefold()
                or search in entry.file_name.casefold()
            ):
                continue
            entries.append(entry)

        entries.sort(key=entry_display.sort_key)
        return entries

    def _row_tags(self, entry: MiEntry, state: str, index: int) -> tuple[str, ...]:
        tags = ["even" if index % 2 == 0 else "odd"]
        if state:
            tags.append(f"state-{state}")
        if entry.origin == "mod_new":
            tags.append("modnew")
        if not self._entry_recognized(entry):
            tags.append("unrecognized")
        return tuple(tags)

    def _refresh_list(self) -> None:
        selected = {self._row_targets.get(iid) for iid in self.list_tree.selection()}
        self._suppress_list_event = True
        try:
            self.list_tree.delete(*self.list_tree.get_children())
            self._row_targets = {}
            entries = self._visible_entries()
            for index, entry in enumerate(entries):
                iid = f"row{index}"
                groups = self._target_groups.get(normalize_key(entry.target), [])
                state = self._state_key(entry.target)
                self.list_tree.insert(
                    "",
                    tk.END,
                    iid=iid,
                    values=(
                        self._entry_display_name(entry),
                        entry.file_name,
                        self._origin_label(entry),
                        ", ".join(groups),
                        self._entry_state_text(state),
                    ),
                    tags=self._row_tags(entry, state, index),
                )
                self._row_targets[iid] = entry.target
                if entry.target in selected:
                    self.list_tree.selection_add(iid)
        finally:
            self._suppress_list_event = False
        self.list_rail.update_now()
        self._update_count_label(len(entries))
        self.list_rail.schedule()

    def _update_list_rows(self, targets: list[str]) -> None:
        """Refresh state/tags of specific rows without rebuilding the list."""
        keys = {normalize_key(target) for target in targets}
        self._suppress_list_event = True
        try:
            for iid, target in self._row_targets.items():
                key = normalize_key(target)
                if key not in keys:
                    continue
                entry = self.catalog.get(key)
                if entry is None or not self.list_tree.exists(iid):
                    continue
                state = self._state_key(target)
                self.list_tree.set(iid, "state", self._entry_state_text(state))
                try:
                    index = int(iid.removeprefix("row"))
                except ValueError:
                    index = 0
                self.list_tree.item(iid, tags=self._row_tags(entry, state, index))
        finally:
            self._suppress_list_event = False
        self.list_rail.update_now()
        self._update_count_label(len(self._row_targets))

    def _update_count_label(self, shown: int) -> None:
        self.count_label.configure(
            text=self.translator.t(
                "mi_count",
                shown=shown,
                total=len(self.catalog),
                unsaved=self._state_count("unsaved"),
                saved=self._state_count("saved"),
                modified=self._state_count("modified"),
            )
        )

    def _modified_count(self) -> int:
        return self._state_count("modified")

    def _state_count(self, state: str) -> int:
        return sum(1 for entry in self.catalog.values() if self._state_key(entry.target) == state)

    def _state_key(self, target: str) -> str:
        key = normalize_key(target)
        if key in self._unsaved_targets:
            return "unsaved"
        if self.workspace.has_doc(target) and self.workspace.is_modified(target, self._effective_doc(target)):
            return "saved"
        if self._has_baseline_diff(target):
            return "modified"
        return ""

    def _has_baseline_diff(self, target: str) -> bool:
        key = normalize_key(target)
        cached = self._diff_cache.get(key)
        if cached is not None:
            return cached
        entry = self.catalog.get(key)
        result = False
        # Entries whose effective file IS the pac member can never differ from
        # it; skipping them avoids decoding the whole 2500+ file catalog just
        # to render state badges (this made startup take several seconds).
        if entry is not None and entry.baseline is not None and entry.baseline.kind != "pac":
            effective = self._effective_doc(target)
            baseline = self._baseline_doc(target)
            result = effective is not None and baseline is not None and effective != baseline
        self._diff_cache[key] = result
        return result

    def _is_modified(self, target: str) -> bool:
        if not self.workspace.has_doc(target):
            return False
        return self.workspace.is_modified(target, self._effective_doc(target))

    def _selected_targets(self) -> list[str]:
        return [self._row_targets[iid] for iid in self.list_tree.selection() if iid in self._row_targets]

    def _on_list_select(self, _event: object) -> None:
        if self._suppress_list_event:
            return
        targets = self._selected_targets()
        focus = self.list_tree.focus()
        target = self._row_targets.get(focus) or (targets[0] if targets else None)
        entry = self.catalog.get(normalize_key(target)) if target else None
        self._show_entry(entry)
        self._refresh_scope_options()

    def _on_list_motion(self, event: object) -> None:
        iid = self.list_tree.identify_row(event.y)
        target = self._row_targets.get(iid)
        if not target:
            self._list_tooltip.hide()
            return
        entry = self.catalog.get(normalize_key(target))
        if entry is None:
            return
        lines = [entry.target]
        for source in entry.sources:
            marker = self.translator.t("mi_list_baseline_prefix") if source is entry.baseline else self.translator.t("mi_list_source_prefix")
            state = "" if source.kind != "mod" or source.enabled else self.translator.t("mi_source_disabled")
            lines.append(f"{marker}{self.translator.t('mi_source_pac') if source.kind == 'pac' else source.label}{state}")
        groups = self._target_groups.get(normalize_key(entry.target), [])
        if groups:
            lines.append(self.translator.t("mi_groups_tip", groups=", ".join(groups)))
        self._list_tooltip.schedule("\n".join(lines), event.x_root, event.y_root)

    # -------------------------------------------------------------- groups ---

    def _create_group(self) -> None:
        name = simpledialog.askstring(self.translator.t("mi_create_group_title"), self.translator.t("mi_create_group_prompt"), parent=self.root)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in self.workspace.groups:
            messagebox.showinfo(self.translator.t("mi_create_group_title"), self.translator.t("mi_group_exists"), parent=self.root)
            return
        self.workspace.add_to_group(name, self._selected_targets())
        self._refresh_group_filter()
        self._refresh_list()
        self._refresh_scope_options()
        self._log(self.translator.t("mi_group_created", name=name, count=len(self._selected_targets())))

    def _pick_group(self, title: str) -> str | None:
        names = self.workspace.group_names()
        if not names:
            messagebox.showinfo(title, self.translator.t("mi_no_groups"), parent=self.root)
            return None
        current = self.group_filter_combo.get()
        if current in names:
            return current
        if len(names) == 1:
            return names[0]
        name = simpledialog.askstring(title, self.translator.t("mi_pick_group_prompt", names=", ".join(names)), parent=self.root)
        if name and name.strip() in names:
            return name.strip()
        if name:
            messagebox.showinfo(title, self.translator.t("mi_group_missing"), parent=self.root)
        return None

    def _add_selection_to_group(self) -> None:
        targets = self._selected_targets()
        if not targets:
            messagebox.showinfo(self.translator.t("mi_add_group"), self.translator.t("mi_select_files_first"), parent=self.root)
            return
        name = self._pick_group(self.translator.t("mi_add_group"))
        if not name:
            return
        self.workspace.add_to_group(name, targets)
        self._rebuild_target_groups()
        self._refresh_list()
        self._refresh_scope_options()
        self._log(self.translator.t("mi_added_to_group", count=len(targets), name=name))

    def _remove_selection_from_group(self) -> None:
        targets = self._selected_targets()
        if not targets:
            return
        name = self._pick_group(self.translator.t("mi_remove_group"))
        if not name:
            return
        self.workspace.remove_from_group(name, targets)
        self._rebuild_target_groups()
        self._refresh_list()
        self._refresh_scope_options()
        self._log(self.translator.t("mi_removed_from_group", count=len(targets), name=name))

    def _delete_group(self) -> None:
        name = self._pick_group(self.translator.t("mi_delete_group"))
        if not name:
            return
        if not messagebox.askyesno(self.translator.t("mi_delete_group"), self.translator.t("mi_delete_group_confirm", name=name), parent=self.root):
            return
        self.workspace.delete_group(name)
        self._refresh_group_filter()
        self._refresh_list()
        self._refresh_scope_options()

    # -------------------------------------------------------------- baseline --

    def _effective_doc(self, target: str) -> JsonValue | None:
        """What the game would load without MI Studio: winner mod, else pac."""
        key = normalize_key(target)
        if key not in self._effective_cache:
            entry = self.catalog.get(key)
            self._effective_cache[key] = self._decode(entry.read_baseline()) if entry else None
        return self._effective_cache[key]

    def _official_doc(self, target: str) -> JsonValue | None:
        """The untouched pac member, when the game shipped one for this target."""
        key = normalize_key(target)
        if key not in self._official_cache:
            entry = self.catalog.get(key)
            self._official_cache[key] = self._decode(entry.read_official()) if entry else None
        return self._official_cache[key]

    def _baseline_doc(self, target: str) -> JsonValue | None:
        """Display/reset baseline: official pac when present, otherwise the effective preset."""
        official = self._official_doc(target)
        return official if official is not None else self._effective_doc(target)

    @staticmethod
    def _decode(data: bytes | None) -> JsonValue | None:
        if data is None:
            return None
        try:
            return decode_model_info_json(data)
        except Exception:
            return None

    # -------------------------------------------------------------- structure --

    def _show_entry(self, entry: MiEntry | None) -> None:
        self._remember_struct_view()
        view_state = self._struct_view_state
        self.current_entry = entry
        self.struct_tree.delete(*self.struct_tree.get_children())
        self._leaf_paths = {}
        self._branch_paths = {}
        self._node_help = {}
        self._selected_path = None
        self.fav_button.configure(state="disabled", text="★")
        self._clear_edit_panel()
        if entry is None:
            self.entry_title.configure(text=self.translator.t("mi_no_selection"))
            self.entry_state_label.configure(text="")
            self.entry_detail.configure(text=self.translator.t("mi_no_selection_detail"))
            self._doc = None
            self._baseline = None
            self._rebuild_ref_sources(None)
            return

        official = self._official_doc(entry.target)
        baseline = self._baseline_doc(entry.target)
        doc = self.workspace.get_doc(entry.target) or self._effective_doc(entry.target)
        self._doc = doc
        self._baseline = baseline
        self._rebuild_ref_sources(entry)

        title = self._entry_display_name(entry) if self._entry_recognized(entry) else entry.file_name
        character_name = self._entry_character_name(entry)
        if character_name and character_name not in title:
            title = f"{character_name} — {title}"
        self.entry_title.configure(text=title)
        self.entry_state_label.configure(
            text=self._entry_state_text(self._state_key(entry.target)),
        )
        source_text = self._origin_label(entry)
        start_label = self.translator.t("mi_baseline_pac") if entry.baseline and entry.baseline.kind == "pac" else (entry.baseline.label if entry.baseline else "-")
        if official is not None:
            baseline_label = self.translator.t("mi_baseline_pac")
        elif entry.baseline is not None:
            baseline_label = self.translator.t("mi_baseline_preset", label=entry.baseline.label)
        else:
            baseline_label = self.translator.t("mi_baseline_none")
        self.entry_detail.configure(text=self.translator.t("mi_entry_detail", target=entry.target, start=start_label, source=source_text, baseline=baseline_label))

        if doc is None:
            self.struct_tree.insert("", tk.END, text=self.translator.t("mi_decode_failed"), tags=("empty",))
            return
        if not isinstance(doc, dict):
            self.struct_tree.insert("", tk.END, text=self.translator.t("mi_root_not_object"), tags=("empty",))
            return

        self.struct_tree.insert("", tk.END, iid=FAV_ROOT, text=self.translator.t("mi_favorites"), open=True, tags=("favorite",))
        self._rebuild_favorites()
        # Sections start collapsed; use 全部展开 or click to drill down.
        for section, value in doc.items():
            base_value = baseline.get(section) if isinstance(baseline, dict) else None
            ref_value = self._reference.get(section) if isinstance(self._reference, dict) else None
            path: SemanticPath = (("key", section),)
            self._insert_branch("", section_label(section, self.translator.language), value, base_value, path, section_help(section, self.translator.language), ref_value)
        self._restore_struct_view(view_state)
        self.struct_rail.schedule()

    def _rebuild_ref_sources(self, entry: MiEntry | None) -> None:
        """Populate reference mod/file dropdowns for the selected target."""
        labels = [self.translator.t("mi_no_reference")] + [self._reference_mod_label(mod_id) for mod_id in self.ref_library.mod_ids[1:]]
        self.ref_combo.configure(values=labels)
        mod_id, ref_target = self._preferred_reference(entry)
        index = self.ref_library.mod_ids.index(mod_id) if mod_id in self.ref_library.mod_ids else 0
        self.ref_combo.current(index)
        self._populate_ref_file_combo(ref_target, persist=False)

    def _preferred_reference(self, entry: MiEntry | None) -> tuple[str | None, str | None]:
        if entry is None:
            return None, None
        locked = self._locked_reference()
        if locked is not None:
            return locked
        saved = self.workspace.reference_for(entry.target)
        if saved is not None:
            mod_id = saved.get("mod_id") or None
            ref_target = saved.get("target") or None
            if mod_id is None:
                return None, None
            if mod_id in self.ref_library.files_by_mod and any(normalize_key(option.target) == normalize_key(ref_target) for option in self.ref_library.files_by_mod[mod_id]):
                return mod_id, ref_target
        return default_reference(entry, self.ref_library)

    def _locked_reference(self) -> tuple[str, str] | None:
        if self.ref_lock_var is None or not self.ref_lock_var.get():
            return None
        mod_id = self._ref_locked_mod
        target = self._ref_locked_target
        if not mod_id or not target:
            return None
        options = self.ref_library.files_by_mod.get(mod_id)
        if not options:
            return None
        target_key = normalize_key(target)
        if any(normalize_key(option.target) == target_key for option in options):
            return mod_id, target
        return None

    def _reference_mod_label(self, mod_id: str | None) -> str:
        if mod_id is None:
            return self.translator.t("mi_no_reference")
        label = self.ref_library.mod_labels.get(mod_id, mod_id)
        options = self.ref_library.files_by_mod.get(mod_id, [])
        if options and not options[0].source.enabled:
            label += self.translator.t("mi_source_disabled")
        return label

    def _reference_file_label(self, option: ReferenceOption) -> str:
        entry = self.catalog.get(normalize_key(option.target))
        if entry is None:
            return option.file_label
        return f"{self._entry_display_name(entry)} ({entry.file_name})"

    def _selected_ref_mod_id(self) -> str | None:
        index = max(self.ref_combo.current(), 0)
        if index >= len(self.ref_library.mod_ids):
            return None
        return self.ref_library.mod_ids[index]

    def _populate_ref_file_combo(self, preferred_target: str | None = None, persist: bool = False) -> None:
        mod_id = self._selected_ref_mod_id()
        if mod_id is None:
            self._ref_file_options = []
            self.ref_file_combo.configure(values=[""], state="disabled")
            self.ref_file_combo.set("")
            self._reference = None
            self._ref_pref_mod = None
            self._ref_pref_target = None
            self._update_locked_reference()
            if persist and self.current_entry is not None:
                self.workspace.set_reference(self.current_entry.target, None, None)
            return

        options = self.ref_library.files_by_mod.get(mod_id, [])
        self._ref_file_options = options
        if not options:
            self.ref_file_combo.configure(values=[""], state="disabled")
            self.ref_file_combo.set("")
            self._reference = None
            return

        values = [self._reference_file_label(option) for option in options]
        self.ref_file_combo.configure(values=values, state="readonly")
        index = 0
        preferred_key = normalize_key(preferred_target) if preferred_target else None
        if preferred_key is not None:
            for position, option in enumerate(options):
                if normalize_key(option.target) == preferred_key:
                    index = position
                    break
        self.ref_file_combo.current(index)
        self._set_reference_option(options[index], persist=persist)

    def _set_reference_option(self, option: ReferenceOption, persist: bool = False) -> None:
        self._ref_pref_mod = option.mod_id
        self._ref_pref_target = option.target
        self._update_locked_reference()
        if persist and self.current_entry is not None:
            self.workspace.set_reference(self.current_entry.target, option.mod_id, option.target)
        try:
            self._reference = self._decode(option.source.read_bytes())
        except OSError:
            self._reference = None

    def _update_locked_reference(self) -> None:
        if self.ref_lock_var is None or not self.ref_lock_var.get():
            return
        self._ref_locked_mod = self._ref_pref_mod
        self._ref_locked_target = self._ref_pref_target

    def _on_ref_lock_changed(self) -> None:
        if self.ref_lock_var is None:
            return
        if self.ref_lock_var.get():
            self._ref_locked_mod = self._ref_pref_mod
            self._ref_locked_target = self._ref_pref_target
        else:
            self._ref_locked_mod = None
            self._ref_locked_target = None

    def _on_ref_selected(self, _event: object) -> None:
        self._populate_ref_file_combo(self.current_entry.target if self.current_entry else None, persist=True)
        self._refresh_struct_values()

    def _on_ref_file_selected(self, _event: object) -> None:
        index = max(self.ref_file_combo.current(), 0)
        if index < len(self._ref_file_options):
            self._set_reference_option(self._ref_file_options[index], persist=True)
        else:
            self._reference = None
        self._refresh_struct_values()

    @staticmethod
    def _matching_child(container: JsonValue, label: str | None, key: object, from_dict: bool) -> JsonValue:
        """Locate the counterpart of a child in a parallel doc (official/reference)."""
        if from_dict:
            return container.get(key) if isinstance(container, dict) else None
        if not isinstance(container, list):
            return None
        if label:
            for candidate in container:
                if item_label(candidate) == label:
                    return candidate
        if isinstance(key, int) and key < len(container):
            return container[key]
        return None

    def _insert_branch(
        self,
        parent: str,
        text: str,
        value: JsonValue,
        base_value: JsonValue,
        path: SemanticPath,
        help_text: str = "",
        ref_value: JsonValue = None,
    ) -> str:
        base_text = lambda base: format_value(base, self.translator) if base is not None else "—"  # noqa: E731
        ref_text = format_value(ref_value, self.translator) if ref_value is not None else "—"
        fav_text = self._favorite_marker(path)
        if isinstance(value, (dict, list)):
            changed = base_value is not None and value != base_value
            tags = ("branch-changed",) if changed else (("empty",) if not value else ())
            iid = self.struct_tree.insert(
                parent,
                tk.END,
                text=text + (" ●" if changed else ""),
                values=(format_value(value, self.translator), base_text(base_value), ref_text, fav_text),
                tags=tags,
            )
            self._branch_paths[iid] = path
            if help_text:
                self._node_help[iid] = help_text
            children = value.items() if isinstance(value, dict) else enumerate(value)
            for key, child in children:
                if isinstance(value, dict):
                    child_path = path + (("key", key),)
                    child_text = field_label(key, self.translator.language)
                    child_help = field_help(key, self.translator.language)
                    label, from_dict = None, True
                else:
                    label = item_label(child)
                    child_path = path + (("item", label, key),)
                    child_text = label or f"[{key}]"
                    child_help = ""
                    from_dict = False
                child_base = self._matching_child(base_value, label, key, from_dict)
                child_ref = self._matching_child(ref_value, label, key, from_dict)
                self._insert_branch(iid, child_text, child, child_base, child_path, child_help, child_ref)
            return iid

        changed = base_value is not None and value != base_value
        iid = self.struct_tree.insert(
            parent,
            tk.END,
            text=text,
            values=(format_value(value, self.translator), base_text(base_value), ref_text, fav_text),
            tags=("changed",) if changed else (),
        )
        self._leaf_paths[iid] = path
        if help_text:
            self._node_help[iid] = help_text
        return iid

    def _set_tree_open(self, opened: bool) -> None:
        def walk(iid: str) -> None:
            self.struct_tree.item(iid, open=opened)
            for child in self.struct_tree.get_children(iid):
                walk(child)

        for iid in self.struct_tree.get_children():
            walk(iid)
        self._remember_struct_view()
        self.struct_rail.schedule()

    def _refresh_struct_values(self) -> None:
        doc = self._doc
        baseline = self._baseline
        reference = self._reference
        for iid, path in self._leaf_paths.items():
            value = get_value(doc, path)
            base = get_value(baseline, path) if baseline is not None else None
            ref = get_value(reference, path) if reference is not None else None
            changed = base is not None and value != base
            self.struct_tree.item(
                iid,
                values=(
                    format_value(value, self.translator),
                    format_value(base, self.translator) if base is not None else "—",
                    format_value(ref, self.translator) if ref is not None else "—",
                    self._favorite_marker(path),
                ),
                tags=("changed",) if changed else (),
            )
        for iid, path in self._branch_paths.items():
            value = get_value(doc, path)
            base = get_value(baseline, path) if baseline is not None else None
            ref = get_value(reference, path) if reference is not None else None
            changed = base is not None and value != base
            text = self.struct_tree.item(iid, "text").rstrip(" ●")
            tags = ("branch-changed",) if changed else (("empty",) if not value else ())
            self.struct_tree.item(
                iid,
                text=text + (" ●" if changed else ""),
                values=(
                    format_value(value, self.translator),
                    format_value(base, self.translator) if base is not None else "—",
                    format_value(ref, self.translator) if ref is not None else "—",
                    self._favorite_marker(path),
                ),
                tags=tags,
            )

    def _capture_struct_view(self) -> StructTreeState:
        return capture_struct_tree_state(self.struct_tree, self._leaf_paths, self._branch_paths, FAV_ROOT, self._selected_path)

    def _remember_struct_view(self) -> None:
        current = self._capture_struct_view()
        visible_branch_paths = set(self._branch_paths.values())
        self._struct_view_state.open_paths.difference_update(visible_branch_paths)
        self._struct_view_state.open_paths.update(current.open_paths)
        self._struct_view_state.favorite_open = current.favorite_open
        if current.selected_path is not None:
            self._struct_view_state.selected_path = current.selected_path
        self._struct_view_state.yview = current.yview

    def _restore_struct_view(self, state: StructTreeState) -> None:
        selected_iid = restore_struct_tree_state(self.struct_tree, self._leaf_paths, self._branch_paths, FAV_ROOT, state)
        if selected_iid:
            self._on_struct_select(None)

    # -------------------------------------------------------------- favorites --

    def _favorite_marker(self, path: SemanticPath | None) -> str:
        return "★" if path is not None and self.workspace.is_favorite(path) else "☆"

    def _refresh_favorite_marks(self) -> None:
        for mapping in (self._leaf_paths, self._branch_paths):
            for iid, path in list(mapping.items()):
                if not self.struct_tree.exists(iid):
                    continue
                values = list(self.struct_tree.item(iid, "values"))
                while len(values) < 4:
                    values.append("")
                values[3] = self._favorite_marker(path)
                self.struct_tree.item(iid, values=tuple(values))

    def _on_struct_click(self, event: object) -> str | None:
        column = self.struct_tree.identify_column(event.x)
        if column != "#4":
            return None
        iid = self.struct_tree.identify_row(event.y)
        path = self._leaf_paths.get(iid) or self._branch_paths.get(iid)
        if path is None:
            return "break"
        self._toggle_favorite_path(path)
        return "break"

    def _fav_text(self, path: SemanticPath) -> str:
        crumbs = []
        for step in path:
            crumbs.append(str(step[1]) if step[0] == "key" else str(step[1] or f"[{step[2]}]"))
        last = path[-1]
        if last[0] == "key":
            head = field_label(str(last[1]), self.translator.language)
        else:
            head = crumbs[-1]
        context = " / ".join(crumbs[:-1])
        return f"{head}（{context}）" if context else head

    def _rebuild_favorites(self) -> None:
        tree = self.struct_tree
        if not tree.exists(FAV_ROOT):
            return
        for child in tree.get_children(FAV_ROOT):
            tree.delete(child)
        for mapping in (self._leaf_paths, self._branch_paths, self._node_help):
            for iid in [iid for iid in mapping if not tree.exists(iid)]:
                del mapping[iid]
        if not isinstance(self._doc, dict):
            return
        added = 0
        for path in self.workspace.favorites:
            if resolve_path(self._doc, path) is None:
                continue
            value = get_value(self._doc, path)
            base = get_value(self._baseline, path) if self._baseline is not None else None
            ref = get_value(self._reference, path) if self._reference is not None else None
            field_name = str(path[-1][1]) if path[-1][0] == "key" else ""
            self._insert_branch(FAV_ROOT, self._fav_text(path), value, base, path, field_help(field_name, self.translator.language), ref)
            added += 1
        if added == 0:
            tree.insert(FAV_ROOT, tk.END, text=self.translator.t("mi_favorites_empty"), tags=("empty",))

    def _toggle_favorite(self) -> None:
        path = self._selected_path
        if path is None:
            return
        self._toggle_favorite_path(path)

    def _toggle_favorite_path(self, path: SemanticPath) -> None:
        added = self.workspace.toggle_favorite(path)
        self._rebuild_favorites()
        self._refresh_favorite_marks()
        self.fav_button.configure(text="★" if added else "☆")
        key = "mi_favorite_added" if added else "mi_favorite_removed"
        self._log(self.translator.t(key, path=self._fav_text(path)))

    def _on_struct_motion(self, event: object) -> None:
        iid = self.struct_tree.identify_row(event.y)
        help_text = self._node_help.get(iid, "")
        if not help_text:
            self._struct_tooltip.hide()
            return
        self._struct_tooltip.schedule(help_text, event.x_root, event.y_root)

    # -------------------------------------------------------------- editing ---

    def _clear_edit_panel(self) -> None:
        self._edit_path = None
        self._edit_kind = None
        self._edit_field = ""
        self.edit_title.configure(text=self.translator.t("mi_edit_placeholder"))
        self.edit_help.configure(text="")
        self.range_label.configure(text="")
        self.value_var.set("")
        self._set_edit_enabled(False)

    def _set_edit_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for widget in (self.value_entry, self.apply_edit_button, self.reset_field_button, self.sym_check, self.bool_check):
            widget.configure(state=state)
        # ttk.Scale has no -state option; toggle the disabled state flag instead.
        if enabled and self._edit_kind == "number":
            self.scale.state(["!disabled"])
        else:
            self.scale.state(["disabled"])

    def _on_struct_select(self, _event: object) -> None:
        selection = self.struct_tree.selection()
        iid = selection[0] if selection else ""
        self._selected_path = self._leaf_paths.get(iid) or self._branch_paths.get(iid)
        if self._selected_path is not None:
            self.fav_button.configure(
                state="normal",
                text="★" if self.workspace.is_favorite(self._selected_path) else "☆",
            )
        else:
            self.fav_button.configure(state="disabled", text="☆")
        if not iid or iid not in self._leaf_paths or self._doc is None:
            self._clear_edit_panel()
            return
        path = self._leaf_paths[iid]
        value = get_value(self._doc, path)
        field_name = path[-1][1] if path[-1][0] == "key" else str(path[-1][1] or path[-1][2])
        self._edit_path = path
        self._edit_field = field_name

        crumbs = []
        for step in path:
            crumbs.append(str(step[1]) if step[0] == "key" else str(step[1] or f"[{step[2]}]"))
        self.edit_title.configure(text=f"{field_label(field_name, self.translator.language)}    ({' / '.join(crumbs[:-1])})")
        help_text = field_help(field_name, self.translator.language) or self.translator.t("mi_no_help")
        mirror = mirrored_path(path)
        mirror_available = bool(mirror) and get_value(self._doc, mirror) is not None
        if mirror_available:
            mirror_names = [str(s[1]) for s in mirror if s[0] == "item" and s[1]]
            help_text += "\n" + self.translator.t("mi_symmetry_detected", names=" / ".join(mirror_names))
        self.edit_help.configure(text=help_text)

        if isinstance(value, bool):
            self._edit_kind = "bool"
            self.bool_var.set(value)
            self.range_label.configure(text="")
            self.bool_check.grid()
            self.scale.grid_remove()
            self.value_box.grid_remove()
        elif isinstance(value, (int, float)):
            self._edit_kind = "number"
            low, high = field_range(field_name, float(value))
            self.scale.configure(from_=low, to=high)
            self.scale.set(float(value))
            self.value_var.set(format_value(value, self.translator))
            self.range_label.configure(text=self.translator.t("mi_slider_range", low=f"{low:.6g}", high=f"{high:.6g}"))
            self.bool_check.grid_remove()
            self.scale.grid()
            self.value_box.grid()
        elif isinstance(value, str):
            self._edit_kind = "string"
            self.value_var.set(value)
            self.range_label.configure(text="")
            self.bool_check.grid_remove()
            self.scale.grid_remove()
            self.value_box.grid()
        else:
            self._edit_kind = None
            self._clear_edit_panel()
            return
        self._set_edit_enabled(True)
        self.sym_check.configure(state="normal" if mirror_available else "disabled")
        self._refresh_scope_options()

    def _refresh_scope_options(self) -> None:
        options: list[tuple[str, Callable[[], list[str]]]] = []
        selected = self._selected_targets()
        if len(selected) > 1:
            options.append((self.translator.t("mi_scope_selected", count=len(selected)), lambda s=tuple(selected): list(s)))
        options.append((self.translator.t("mi_scope_current"), lambda: [self.current_entry.target] if self.current_entry else []))
        for name in self.workspace.group_names():
            members = [t for t in self.workspace.groups.get(name, []) if normalize_key(t) in self.catalog]
            if members:
                options.append((self.translator.t("mi_scope_group", name=name, count=len(members)), lambda m=tuple(members): list(m)))
        self._scope_options = options
        current = self.scope_combo.current()
        self.scope_combo.configure(values=[label for label, _fn in options])
        if not (0 <= current < len(options)):
            current = 0
        self.scope_combo.current(current)

    def _scope_targets(self) -> list[str]:
        index = max(self.scope_combo.current(), 0)
        if index >= len(self._scope_options):
            index = 0
        return self._scope_options[index][1]()

    def _begin_slider(self) -> None:
        self._slider_dragging = True

    def _on_scale_move(self, raw: str) -> None:
        if self._edit_kind != "number":
            return
        try:
            value = float(raw)
        except ValueError:
            return
        if field_is_integer(self._edit_field):
            value = round(value)
        self.value_var.set(f"{value:.6g}")

    def _commit_from_slider(self) -> None:
        self._slider_dragging = False
        if self._edit_kind == "number":
            self._commit_from_entry()

    def _commit_from_bool(self) -> None:
        if self._edit_kind == "bool":
            self._apply_value(bool(self.bool_var.get()))

    def _commit_from_entry(self) -> None:
        if self._edit_path is None:
            return
        if self._edit_kind == "bool":
            self._apply_value(bool(self.bool_var.get()))
            return
        text = self.value_var.get().strip()
        if self._edit_kind == "number":
            try:
                value = float(text)
            except ValueError:
                messagebox.showerror(
                    self.translator.t("mi_parse_number_error_title"),
                    self.translator.t("mi_parse_number_error", value=text),
                    parent=self.root,
                )
                return
            if field_is_integer(self._edit_field):
                value = round(value)
            self._apply_value(_normalize_number(value))
        else:
            self._apply_value(text)

    def _reset_field(self) -> None:
        if self._edit_path is None:
            return
        if self._baseline is None:
            messagebox.showinfo(self.translator.t("mi_reset_field"), self.translator.t("mi_reset_no_baseline"), parent=self.root)
            return
        base = get_value(self._baseline, self._edit_path)
        if base is None:
            messagebox.showinfo(self.translator.t("mi_reset_field"), self.translator.t("mi_reset_missing_field"), parent=self.root)
            return
        if self._edit_kind == "bool":
            self.bool_var.set(bool(base))
        elif self._edit_kind == "number":
            self.scale.set(float(base))
            self.value_var.set(format_value(base, self.translator))
        else:
            self.value_var.set(str(base))
        self._apply_value(base)

    def _apply_value(self, value: Any) -> None:
        if self._edit_path is None or self.current_entry is None:
            return
        targets = self._scope_targets()
        if not targets:
            return
        pairs = []
        for target in targets:
            baseline = self._effective_doc(target)
            if baseline is None:
                continue
            pairs.append((target, baseline))
        result = self.workspace.apply_edit(pairs, self._edit_path, value, symmetric=bool(self.sym_var.get()) and str(self.sym_check.cget("state")) != "disabled")
        self._dirty = True
        for target, _baseline in pairs:
            self._unsaved_targets.add(normalize_key(target))
        # The current entry's doc object may have just been created by open_doc.
        self._doc = self.workspace.get_doc(self.current_entry.target) or self._doc
        self._refresh_struct_values()
        # Update the affected list rows in place: rebuilding the list would fire
        # a selection event and rebuild the structure tree, losing the current
        # field selection mid-edit.
        self._update_list_rows(targets)
        self.entry_state_label.configure(text=self._entry_state_text(self._state_key(self.current_entry.target)))
        message = self.translator.t("mi_edit_done", count=result.applied)
        if result.mirrored:
            message += self.translator.t("mi_edit_mirrored", count=result.mirrored)
        if result.skipped:
            message += self.translator.t("mi_edit_skipped", count=len(result.skipped))
        self._set_status(
            self.translator.t(
                "mi_status_value",
                field=field_label(self._edit_field, self.translator.language),
                value=format_value(value, self.translator),
                message=message,
            )
        )

    def _revert_current(self) -> None:
        if self.current_entry is None:
            return
        target = self.current_entry.target
        if not self.workspace.has_doc(target):
            return
        if not messagebox.askyesno(self.translator.t("mi_revert_title"), self.translator.t("mi_revert_confirm"), parent=self.root):
            return
        self.workspace.drop_doc(target)
        self._dirty = True
        self._unsaved_targets.add(normalize_key(target))
        self._effective_cache.pop(normalize_key(target), None)
        self._official_cache.pop(normalize_key(target), None)
        self._show_entry(self.current_entry)
        self._refresh_list()
        self._log(self.translator.t("mi_reverted", target=target))

    # -------------------------------------------------------------- import ----

    def _open_import_dialog(self) -> None:
        if self.current_entry is None:
            messagebox.showinfo(self.translator.t("mi_import_title"), self.translator.t("mi_import_select_target"), parent=self.root)
            return
        ImportDialog(self)

    # -------------------------------------------------------------- actions ---

    def _save(self) -> None:
        if self._busy:
            return
        written, removed = self.workspace.save_tweaks_mod(self._effective_doc)
        self._dirty = False
        self._unsaved_targets.clear()
        self._refresh_list()
        if self.current_entry is not None:
            self.entry_state_label.configure(text=self._entry_state_text(self._state_key(self.current_entry.target)))
        self._log(
            self.translator.t("mi_saved", written=written, mod_name=TWEAKS_MOD_NAME, removed=removed)
            + (self.translator.t("mi_save_apply_hint") if written else ""),
            "status",
        )
        self._set_status(self.translator.t("mi_save_done", time=now_label()))

    def _apply_to_game(self) -> None:
        if self._busy:
            return
        if self._dirty:
            self._save()
        if not messagebox.askyesno(
            self.translator.t("mi_apply_game"),
            self.translator.t("mi_apply_confirm"),
            parent=self.root,
        ):
            return
        self._set_busy(True, self.translator.t("mi_applying"))

        def worker() -> None:
            try:
                self.core.state = self.core._load_state()
                summary = self.core.apply_enabled(log=lambda message: self._post(self._log, message))
                self._post(
                    self._log,
                    self.translator.t("mi_apply_done", mods=summary["mods"], files=summary["files"], conflicts=summary["conflicts"]),
                    "status",
                )
                self._post(self._set_status, self.translator.t("apply_done", mods=summary["mods"], files=summary["files"]))
            except Exception as exc:  # surface every failure in the log panel
                self._post(self._log, self.translator.t("mi_apply_failed", error=exc), "error")
                self._post(self._set_status, self.translator.t("apply_failed", error=exc))
            finally:
                self._post(self._finish_busy)

        self._start_worker(worker, "mi-apply")

    def _finish_busy(self) -> None:
        self._set_busy(False)

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        self._busy = busy
        for button in (self.save_button, self.apply_button, self.reload_button, self.mod_manager_button):
            button.configure(state="disabled" if busy else "normal")
        if message:
            self._status_text = message
        if busy:
            self.status_bar.set_busy(self._status_text or self.translator.t("mi_applying"))
        else:
            self.status_bar.set_idle(self._status_text or self.translator.t("mi_ready"))

    def _restore_window_layout(self) -> None:
        self.window_state.restore()
        self._last_normal_geometry = self.window_state.last_normal_geometry

    def _on_root_configure(self, event: object) -> None:
        self.window_state.on_configure(event)
        self._last_normal_geometry = self.window_state.last_normal_geometry

    def _save_window_layout(self) -> None:
        self.window_state.last_normal_geometry = self._last_normal_geometry
        self.window_state.save()
        self._last_normal_geometry = self.window_state.last_normal_geometry

    def _confirm_close(self) -> bool:
        if self._busy or self._loading or self._has_active_workers():
            messagebox.showinfo(self.translator.t("mi_app_title"), self.translator.t("task_busy"), parent=self.root)
            return False
        if self._dirty:
            answer = messagebox.askyesnocancel(self.translator.t("mi_exit_title"), self.translator.t("mi_exit_confirm"), parent=self.root)
            if answer is None:
                return False
            if answer:
                self._save()
        return True

    def _destroy_window(self, destroy_root: bool = True) -> None:
        try:
            self._save_window_layout()
        except Exception:
            pass
        try:
            self._shutdown_tk_state()
        except Exception:
            pass
        if destroy_root:
            try:
                self.root.destroy()
            except tk.TclError:
                pass

    def _switch_to_mod_manager(self) -> None:
        if self._busy:
            messagebox.showinfo(self.translator.t("mi_app_title"), self.translator.t("task_busy"), parent=self.root)
            return
        if not self._confirm_close():
            return
        if self.on_open_mod_manager is None:
            return
        self._destroy_window(destroy_root=False)
        self.on_open_mod_manager()

    def _on_close(self) -> None:
        if not self._confirm_close():
            return
        self._destroy_window()

    # -------------------------------------------------------------- logging ---

    def _log(self, message: str, tag: str = "info") -> None:
        self.log_panel.append(now_label(), message, tag)

    def _set_status(self, message: str) -> None:
        self._status_text = message
        if self._busy:
            self.status_bar.set_busy(message)
        else:
            self.status_bar.set_idle(message)


def main() -> int:
    from modmanager.ui.router import main as _main

    return _main("mi_studio")
