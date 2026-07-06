from __future__ import annotations

import tkinter as tk
from tkinter import ttk

PALETTE = {
    "bg": "#121513",
    "panel": "#1b211f",
    "panel2": "#242c29",
    "panel3": "#303a36",
    "line": "#4f5b53",
    "text": "#f0eadf",
    "muted": "#aeb8ae",
    "accent": "#d2b45f",
    "accent_hover": "#e4c875",
    "accent_pressed": "#b99541",
    "green": "#79c79a",
    "red": "#e07968",
    "disabled": "#6f7a72",
    "stripe": "#202723",
    "heading_bg": "#29322e",
    "heading_hover": "#34423b",
    "heading_pressed": "#405249",
    "selected_bg": "#5b4930",
    "selected_fg": "#fff3d2",
    "winner_bg": "#1f3d31",
    "winner_fg": "#b4efc8",
    "loser_bg": "#44282e",
    "loser_fg": "#f5b4bb",
    "mixed_bg": "#3b3150",
    "mixed_fg": "#dcc7ff",
    "partner_bg": "#22394d",
    "partner_fg": "#b8ddff",
    "drag_bg": "#d2b45f",
    "drag_fg": "#16130a",
    "input_bg": "#161c1a",
    "log_bg": "#101412",
}


def apply_theme(root: tk.Misc) -> dict[str, str]:
    colors = PALETTE
    root.configure(bg=colors["bg"])
    root.option_add("*TCombobox*Listbox.background", colors["panel"])
    root.option_add("*TCombobox*Listbox.foreground", colors["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", colors["selected_bg"])
    root.option_add("*TCombobox*Listbox.selectForeground", colors["selected_fg"])
    root.option_add("*TCombobox*Listbox.activeBackground", colors["heading_hover"])
    root.option_add("*TCombobox*Listbox.activeForeground", colors["text"])
    root.option_add("*TCombobox*Listbox.highlightThickness", 0)
    root.option_add("*TCombobox*Listbox.relief", "flat")
    style = ttk.Style()
    style.theme_use("clam")
    style.configure(".", font=("Microsoft YaHei UI", 10), background=colors["bg"], foreground=colors["text"])
    style.configure("TFrame", background=colors["bg"])
    style.configure("Panel.TFrame", background=colors["panel"])
    style.configure("TLabel", background=colors["bg"], foreground=colors["text"])
    style.configure("Muted.TLabel", background=colors["bg"], foreground=colors["muted"])
    style.configure("Panel.TLabel", background=colors["panel"], foreground=colors["text"])
    style.configure("PanelMuted.TLabel", background=colors["panel"], foreground=colors["muted"])
    style.configure("TSeparator", background=colors["line"])
    style.configure(
        "TButton",
        background=colors["panel2"],
        foreground=colors["text"],
        bordercolor=colors["line"],
        focusthickness=0,
        focuscolor=colors["panel2"],
        padding=(10, 6),
        relief="flat",
    )
    style.map(
        "TButton",
        background=[
            ("disabled", colors["panel"]),
            ("focus", colors["panel2"]),
            ("pressed", colors["panel2"]),
            ("active", colors["panel2"]),
        ],
        bordercolor=[
            ("disabled", colors["line"]),
            ("focus", colors["line"]),
            ("pressed", colors["line"]),
            ("active", colors["line"]),
        ],
        foreground=[("disabled", colors["disabled"])],
        relief=[("focus", "flat"), ("pressed", "flat"), ("active", "flat")],
    )
    style.configure(
        "Accent.TButton",
        background=colors["accent"],
        foreground="#191510",
        bordercolor=colors["accent"],
        focuscolor=colors["accent"],
        focusthickness=0,
        relief="flat",
    )
    style.map(
        "Accent.TButton",
        background=[
            ("disabled", colors["panel"]),
            ("focus", colors["accent"]),
            ("pressed", colors["accent"]),
            ("active", colors["accent"]),
        ],
        bordercolor=[
            ("disabled", colors["line"]),
            ("focus", colors["accent"]),
            ("pressed", colors["accent"]),
            ("active", colors["accent"]),
        ],
        foreground=[("disabled", colors["disabled"])],
        relief=[("focus", "flat"), ("pressed", "flat"), ("active", "flat")],
    )
    style.configure(
        "Treeview",
        background=colors["panel"],
        fieldbackground=colors["panel"],
        foreground=colors["text"],
        rowheight=30,
        bordercolor=colors["line"],
        lightcolor=colors["line"],
        darkcolor=colors["line"],
    )
    style.configure(
        "Treeview.Heading",
        background=colors["heading_bg"],
        foreground=colors["muted"],
        relief="flat",
        padding=(8, 8),
        bordercolor=colors["line"],
        lightcolor=colors["line"],
        darkcolor=colors["line"],
    )
    style.map(
        "Treeview.Heading",
        background=[
            ("disabled", colors["panel2"]),
            ("focus", colors["heading_bg"]),
            ("pressed", colors["heading_bg"]),
            ("active", colors["heading_bg"]),
        ],
        foreground=[
            ("disabled", colors["disabled"]),
            ("focus", colors["muted"]),
            ("pressed", colors["muted"]),
            ("active", colors["muted"]),
        ],
        relief=[("focus", "flat"), ("pressed", "flat"), ("active", "flat")],
    )
    style.map(
        "Treeview",
        background=[
            ("selected", colors["selected_bg"]),
            ("disabled", colors["panel"]),
        ],
        foreground=[
            ("selected", colors["selected_fg"]),
            ("disabled", colors["disabled"]),
        ],
    )
    style.configure(
        "TCombobox",
        fieldbackground=colors["input_bg"],
        background=colors["panel2"],
        foreground=colors["text"],
        bordercolor=colors["line"],
        arrowcolor=colors["text"],
        selectbackground=colors["input_bg"],
        selectforeground=colors["text"],
        insertcolor=colors["text"],
        focuscolor=colors["input_bg"],
        focusthickness=0,
        relief="flat",
    )
    style.map(
        "TCombobox",
        fieldbackground=[
            ("disabled", colors["panel"]),
            ("focus", colors["input_bg"]),
            ("readonly", colors["input_bg"]),
        ],
        background=[
            ("disabled", colors["panel"]),
            ("focus", colors["panel2"]),
            ("pressed", colors["panel2"]),
            ("active", colors["panel2"]),
            ("readonly", colors["panel2"]),
        ],
        foreground=[("disabled", colors["disabled"]), ("focus", colors["text"]), ("readonly", colors["text"])],
        selectbackground=[
            ("disabled", colors["panel"]),
            ("focus", colors["input_bg"]),
            ("readonly", colors["input_bg"]),
        ],
        selectforeground=[("disabled", colors["disabled"]), ("focus", colors["text"]), ("readonly", colors["text"])],
        bordercolor=[
            ("disabled", colors["line"]),
            ("focus", colors["line"]),
            ("pressed", colors["line"]),
            ("active", colors["line"]),
        ],
        arrowcolor=[
            ("disabled", colors["disabled"]),
            ("focus", colors["text"]),
            ("pressed", colors["text"]),
            ("active", colors["text"]),
        ],
    )
    for scrollbar_style in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(
            scrollbar_style,
            background=colors["panel2"],
            troughcolor=colors["panel"],
            bordercolor=colors["line"],
            arrowcolor=colors["muted"],
            lightcolor=colors["panel2"],
            darkcolor=colors["panel2"],
            gripcount=0,
        )
        style.map(
            scrollbar_style,
            background=[
                ("disabled", colors["panel"]),
                ("focus", colors["panel2"]),
                ("pressed", colors["panel2"]),
                ("active", colors["panel2"]),
            ],
            troughcolor=[("disabled", colors["panel"])],
            arrowcolor=[
                ("disabled", colors["disabled"]),
                ("focus", colors["muted"]),
                ("pressed", colors["muted"]),
                ("active", colors["muted"]),
            ],
            bordercolor=[("disabled", colors["line"])],
            lightcolor=[
                ("disabled", colors["panel"]),
                ("focus", colors["panel2"]),
                ("pressed", colors["panel2"]),
                ("active", colors["panel2"]),
            ],
            darkcolor=[
                ("disabled", colors["panel"]),
                ("focus", colors["panel2"]),
                ("pressed", colors["panel2"]),
                ("active", colors["panel2"]),
            ],
        )
    style.configure(
        "Status.Horizontal.TProgressbar",
        troughcolor=colors["panel2"],
        background=colors["accent"],
        bordercolor=colors["panel2"],
        lightcolor=colors["accent"],
        darkcolor=colors["accent"],
    )
    return colors
