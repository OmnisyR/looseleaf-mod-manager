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
        focusthickness=2,
        focuscolor=colors["accent"],
        padding=(10, 6),
    )
    style.map(
        "TButton",
        background=[
            ("pressed", colors["panel3"]),
            ("active", colors["heading_hover"]),
            ("disabled", colors["panel"]),
        ],
        foreground=[("disabled", colors["disabled"])],
    )
    style.configure(
        "Accent.TButton",
        background=colors["accent"],
        foreground="#191510",
        bordercolor=colors["accent"],
    )
    style.map(
        "Accent.TButton",
        background=[("pressed", colors["accent_pressed"]), ("active", colors["accent_hover"])],
        foreground=[("disabled", colors["disabled"])],
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
            ("pressed", colors["heading_pressed"]),
            ("active", colors["heading_hover"]),
            ("disabled", colors["panel2"]),
        ],
        foreground=[
            ("pressed", colors["text"]),
            ("active", colors["text"]),
            ("disabled", colors["disabled"]),
        ],
        relief=[("pressed", "flat"), ("active", "flat")],
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
        selectbackground=colors["panel2"],
        selectforeground=colors["text"],
        insertcolor=colors["text"],
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", colors["input_bg"]), ("disabled", colors["panel"])],
        background=[
            ("active", colors["heading_hover"]),
            ("readonly", colors["panel2"]),
            ("disabled", colors["panel"]),
        ],
        foreground=[("readonly", colors["text"]), ("disabled", colors["disabled"])],
        selectbackground=[("readonly", colors["selected_bg"])],
        selectforeground=[("readonly", colors["text"])],
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
                ("pressed", colors["heading_pressed"]),
                ("active", colors["heading_hover"]),
                ("disabled", colors["panel"]),
            ],
            troughcolor=[("disabled", colors["panel"])],
            arrowcolor=[
                ("pressed", colors["text"]),
                ("active", colors["text"]),
                ("disabled", colors["disabled"]),
            ],
            bordercolor=[("disabled", colors["line"])],
            lightcolor=[
                ("pressed", colors["heading_pressed"]),
                ("active", colors["heading_hover"]),
                ("disabled", colors["panel"]),
            ],
            darkcolor=[
                ("pressed", colors["heading_pressed"]),
                ("active", colors["heading_hover"]),
                ("disabled", colors["panel"]),
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
