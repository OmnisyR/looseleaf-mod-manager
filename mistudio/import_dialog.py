"""Section import dialog for MI Studio."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from modmanager.model_info import JsonValue, decode_model_info_json
from modmanager.pathutils import normalize_key

from .catalog import MiEntry
from .fields import section_label

if TYPE_CHECKING:
    from .app import MiStudioApp


class ImportDialog(tk.Toplevel):
    """Merge matching primitive fields from another model info."""

    def __init__(self, app: MiStudioApp) -> None:
        super().__init__(app.root)
        self.app = app
        self.t = app.translator.t
        self.title(self.t("mi_import_dialog_title"))
        self.configure(bg=app.colors["bg"], padx=12, pady=12)
        self.transient(app.root)
        self.grab_set()
        self.geometry("760x640")

        self.source_doc: JsonValue | None = None
        self.source_label = ""
        self._section_vars: dict[str, tk.BooleanVar] = {}
        self._entries: list[MiEntry] = []

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=3)
        self.rowconfigure(3, weight=2)

        top = ttk.Frame(self, style="Panel.TFrame", padding=8)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text=self.t("mi_import_source_label"), style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_source_list())
        search = tk.Entry(
            top,
            textvariable=self.search_var,
            bg=app.colors["input_bg"],
            fg=app.colors["text"],
            insertbackground=app.colors["text"],
            relief="flat",
        )
        search.grid(row=0, column=1, sticky="ew", padx=(10, 10), ipady=3)
        ttk.Button(top, text=self.t("mi_import_browse"), command=self._browse_file).grid(row=0, column=2)

        list_holder = ttk.Frame(self, style="Panel.TFrame", padding=(8, 4))
        list_holder.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        list_holder.rowconfigure(0, weight=1)
        list_holder.columnconfigure(0, weight=1)
        self.source_list = ttk.Treeview(list_holder, columns=("name", "file", "origin"), show="headings", selectmode="browse")
        for column, text, width in (
            ("name", self.t("mi_col_name"), 260),
            ("file", self.t("mi_col_file"), 170),
            ("origin", self.t("mi_col_source"), 110),
        ):
            self.source_list.heading(column, text=text, anchor="w")
            self.source_list.column(column, width=width, anchor="w")
        self.source_list.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(list_holder, orient=tk.VERTICAL, command=self.source_list.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.source_list.configure(yscrollcommand=scroll.set)
        self.source_list.bind("<Double-Button-1>", lambda _e: self._use_selected())
        ttk.Button(list_holder, text=self.t("mi_import_use_selected"), command=self._use_selected).grid(row=1, column=0, sticky="w", pady=(6, 2))

        self.source_status = ttk.Label(self, style="Muted.TLabel", text=self.t("mi_import_no_source"))
        self.source_status.grid(row=2, column=0, sticky="w", pady=(8, 0))

        self.section_frame = ttk.Frame(self, style="Panel.TFrame", padding=8)
        self.section_frame.grid(row=3, column=0, sticky="nsew", pady=(8, 0))

        bottom = ttk.Frame(self, style="Panel.TFrame", padding=8)
        bottom.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        bottom.columnconfigure(1, weight=1)
        ttk.Label(bottom, text=self.t("mi_import_to"), style="PanelMuted.TLabel").grid(row=0, column=0, padx=(0, 8))
        self.scope_combo = ttk.Combobox(bottom, state="readonly", width=40)
        self.scope_combo.grid(row=0, column=1, sticky="w")
        self._scope_options = list(app._scope_options)
        self.scope_combo.configure(values=[label for label, _fn in self._scope_options])
        if self._scope_options:
            self.scope_combo.current(0)
        ttk.Label(
            bottom,
            style="PanelMuted.TLabel",
            wraplength=700,
            justify=tk.LEFT,
            text=self.t("mi_import_hint"),
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Button(bottom, text=self.t("mi_import_action"), style="Accent.TButton", command=self._do_import).grid(row=0, column=2, sticky="e")

        self._refresh_source_list()

    def _refresh_source_list(self) -> None:
        search = self.search_var.get().strip().casefold()
        self.source_list.delete(*self.source_list.get_children())
        self._entries = []
        for entry in self.app._visible_entries() if not search else self.app.catalog.values():
            if search and not (
                search in entry.stem.casefold()
                or search in self.app._entry_display_name(entry).casefold()
                or search in self.app._entry_character_name(entry).casefold()
            ):
                continue
            iid = f"src{len(self._entries)}"
            self.source_list.insert(
                "",
                tk.END,
                iid=iid,
                values=(self.app._entry_display_name(entry), entry.file_name, self.app._origin_label(entry)),
            )
            self._entries.append(entry)
            if len(self._entries) >= 400:
                break

    def _use_selected(self) -> None:
        selection = self.source_list.selection()
        if not selection:
            return
        index = int(selection[0][3:])
        entry = self._entries[index]
        doc = self.app.workspace.get_doc(entry.target) or self.app._effective_doc(entry.target)
        if not isinstance(doc, dict):
            messagebox.showerror(self.t("mi_import_title"), self.t("mi_import_decode_failed"), parent=self)
            return
        self._set_source(doc, f"{self.app._entry_display_name(entry)} ({entry.file_name})")

    def _browse_file(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title=self.t("mi_import_choose_file"),
            filetypes=[(self.t("mi_filetype_model_info"), "*.mi"), (self.t("filetype_all"), "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "rb") as file:
                doc = decode_model_info_json(file.read())
        except Exception as exc:
            messagebox.showerror(self.t("mi_import_title"), self.t("mi_decode_file_failed", error=exc), parent=self)
            return
        if not isinstance(doc, dict):
            messagebox.showerror(self.t("mi_import_title"), self.t("mi_import_root_not_object"), parent=self)
            return
        self._set_source(doc, path)

    def _set_source(self, doc: dict, label: str) -> None:
        self.source_doc = doc
        self.source_label = label
        self.source_status.configure(text=self.t("mi_import_source_status", label=label))
        for widget in self.section_frame.winfo_children():
            widget.destroy()
        self._section_vars = {}
        ttk.Label(self.section_frame, text=self.t("mi_import_sections"), style="Panel.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        row, column = 1, 0
        default_on = {"DynamicBone", "DynamicBoneCollider", "SpecificCollider", "NeighborBones"}
        for section, value in doc.items():
            size = len(value) if isinstance(value, (dict, list)) else 1
            var = tk.BooleanVar(value=section in default_on and bool(size))
            self._section_vars[section] = var
            check = ttk.Checkbutton(self.section_frame, text=f"{section_label(section, self.app.translator.language)} ({size})", variable=var)
            check.grid(row=row, column=column, sticky="w", padx=(0, 14), pady=2)
            column += 1
            if column >= 3:
                column = 0
                row += 1

    def _do_import(self) -> None:
        if self.source_doc is None:
            messagebox.showinfo(self.t("mi_import_title"), self.t("mi_import_select_source"), parent=self)
            return
        sections = [name for name, var in self._section_vars.items() if var.get()]
        if not sections:
            messagebox.showinfo(self.t("mi_import_title"), self.t("mi_import_select_section"), parent=self)
            return
        index = max(self.scope_combo.current(), 0)
        targets = self._scope_options[index][1]() if self._scope_options else []
        pairs = []
        for target in targets:
            baseline = self.app._effective_doc(target)
            if baseline is not None:
                pairs.append((target, baseline))
        if not pairs:
            messagebox.showinfo(self.t("mi_import_title"), self.t("mi_import_no_targets"), parent=self)
            return
        result = self.app.workspace.import_sections(self.source_doc, sections, pairs)
        if result.changed_targets:
            self.app._dirty = True
        for target in result.changed_targets:
            self.app._unsaved_targets.add(normalize_key(target))
        if self.app.current_entry is not None:
            self.app._show_entry(self.app.current_entry)
        self.app._refresh_list()
        self.app._log(
            self.t("mi_import_done", source=self.source_label, sections=len(sections), targets=result.applied)
            + (self.t("mi_import_skipped", count=len(result.skipped)) if result.skipped else self.t("mi_import_sentence_end")),
            "status",
        )
        self.destroy()
