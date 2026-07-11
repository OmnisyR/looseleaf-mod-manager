"""Treeview state capture/restore helpers for the MI structure tree."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import tkinter as tk
from tkinter import ttk

from .workspace import SemanticPath


@dataclass
class StructTreeState:
    open_paths: set[SemanticPath] = field(default_factory=set)
    favorite_open: bool = True
    selected_path: SemanticPath | None = None
    yview: tuple[float, float] = (0.0, 1.0)


def capture_struct_tree_state(
    tree: ttk.Treeview,
    leaf_paths: Mapping[str, SemanticPath],
    branch_paths: Mapping[str, SemanticPath],
    favorite_root: str,
    selected_path: SemanticPath | None,
) -> StructTreeState:
    state = StructTreeState(selected_path=selected_path)
    if state.selected_path is None:
        selection = tree.selection()
        if selection:
            iid = selection[0]
            state.selected_path = leaf_paths.get(iid) or branch_paths.get(iid)

    def walk(parent: str = "") -> None:
        for iid in tree.get_children(parent):
            if iid == favorite_root:
                state.favorite_open = bool(tree.item(iid, "open"))
            path = leaf_paths.get(iid) or branch_paths.get(iid)
            if path is not None and bool(tree.item(iid, "open")):
                state.open_paths.add(path)
            walk(iid)

    try:
        state.yview = tree.yview()
        walk()
    except tk.TclError:
        state.yview = (0.0, 1.0)
    return state


def iid_for_path(
    tree: ttk.Treeview,
    path: object,
    leaf_paths: Mapping[str, SemanticPath],
    branch_paths: Mapping[str, SemanticPath],
) -> str | None:
    for mapping in (leaf_paths, branch_paths):
        for iid, candidate in mapping.items():
            if candidate == path and tree.exists(iid):
                return iid
    return None


def restore_struct_tree_state(
    tree: ttk.Treeview,
    leaf_paths: Mapping[str, SemanticPath],
    branch_paths: Mapping[str, SemanticPath],
    favorite_root: str,
    state: StructTreeState,
) -> str | None:
    if tree.exists(favorite_root):
        tree.item(favorite_root, open=state.favorite_open)
    for iid, path in branch_paths.items():
        if tree.exists(iid) and path in state.open_paths:
            tree.item(iid, open=True)

    selected_iid = iid_for_path(tree, state.selected_path, leaf_paths, branch_paths)
    if selected_iid:
        tree.selection_set(selected_iid)
        tree.focus(selected_iid)

    try:
        tree.yview_moveto(float(state.yview[0]))
    except (tk.TclError, ValueError, TypeError, IndexError):
        pass
    return selected_iid
