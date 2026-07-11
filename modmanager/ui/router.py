from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Literal

from tkinterdnd2 import TkinterDnD

from ..core import ModManagerCore
from ..i18n import Translator
from .theme import apply_theme

ScreenName = Literal["manager", "mi_studio"]


def _show_loading_shell(root: tk.Tk, title: str, message: str) -> None:
    apply_theme(root)
    root.title(title)
    root.geometry("520x170")
    root.minsize(420, 150)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    frame = ttk.Frame(root, padding=24)
    frame.grid(row=0, column=0, sticky="nsew")
    frame.columnconfigure(0, weight=1)
    label = ttk.Label(frame, text=message, style="Header.TLabel")
    label.grid(row=0, column=0, sticky="w")
    progress = ttk.Progressbar(frame, mode="indeterminate", length=220, style="Status.Horizontal.TProgressbar")
    progress.grid(row=1, column=0, sticky="ew", pady=(18, 0))
    progress.start(12)
    root.update_idletasks()
    root.update()


def _clear_shell(root: tk.Tk) -> None:
    for child in root.winfo_children():
        child.destroy()
    root.rowconfigure(0, weight=0)
    root.columnconfigure(0, weight=0)


def _clear_screen(root: tk.Tk) -> None:
    try:
        root.unbind("<Configure>")
    except tk.TclError:
        pass
    for child in root.winfo_children():
        try:
            child.destroy()
        except tk.TclError:
            pass
    for index in range(8):
        root.rowconfigure(index, weight=0, minsize=0)
        root.columnconfigure(index, weight=0, minsize=0)


def main(start: ScreenName = "manager") -> int:
    """Run the integrated manager / MI Studio shell."""
    from mistudio.i18n import install_mistudio_translations

    install_mistudio_translations()
    root = TkinterDnD.Tk()
    core: ModManagerCore | None = None

    def switch_to(screen: ScreenName) -> None:
        try:
            root.after_idle(lambda: show_screen(screen))
        except tk.TclError:
            pass

    def ensure_core() -> ModManagerCore:
        nonlocal core
        if core is None:
            _show_loading_shell(root, "Looseleaf Mod Manager", "Loading manager... / 正在加载管理器…")
            core = ModManagerCore()
            _clear_shell(root)
        return core

    def show_screen(screen: ScreenName) -> None:
        active_core = ensure_core()
        _clear_screen(root)

        if screen == "manager":
            from .app import ModManagerApp

            ModManagerApp(root, active_core, on_open_mi_studio=lambda: switch_to("mi_studio"))
            return

        if not active_core.has_active_game or not active_core.game_root:
            translator = Translator(active_core.config.language)
            messagebox.showinfo("MI Studio", translator.t("mi_no_active_game"))
            show_screen("manager")
            return

        from mistudio.app import MiStudioApp

        MiStudioApp(root, active_core, on_open_mod_manager=lambda: switch_to("manager"))

    show_screen(start)
    root.mainloop()

    return 0
