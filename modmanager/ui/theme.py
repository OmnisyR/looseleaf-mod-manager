from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# Shared dark tool palette. It uses a muted teal/brass split-complementary
# relationship: cool graphite surfaces, aged brass actions, and restrained
# green/red status colors. The MI Studio file list uses a no-fill selection
# style with a rail/outline, so row state colors remain legible.
PALETTE = {
    "bg": "#0E1110",
    "panel": "#151A18",
    "panel2": "#1D2421",
    "panel3": "#28312C",
    "line": "#3A463F",
    "text": "#ECE7DA",
    "muted": "#A0AAA1",
    "accent": "#C6A15B",
    "accent_hover": "#D8B96E",
    "accent_pressed": "#A98442",
    "green": "#7FB58A",
    "red": "#D6725F",
    "disabled": "#69746B",
    "stripe": "#18201C",
    "heading_bg": "#202923",
    "heading_hover": "#29362F",
    "heading_pressed": "#334139",
    "selected_bg": "#263A36",
    "selected_fg": "#F6F0E3",
    "tree_selected_bg": "#151A18",
    "winner_bg": "#1D3528",
    "winner_fg": "#AAD9B5",
    "loser_bg": "#3D2825",
    "loser_fg": "#EFB1A6",
    "mixed_bg": "#332D43",
    "mixed_fg": "#D0C4EA",
    "partner_bg": "#22363D",
    "partner_fg": "#B2D6DE",
    "selection_rail": "#C6A15B",
    "selection_line": "#657368",
    "diff_changed_bg": "#332B1B",
    "diff_changed_fg": "#E2C06D",
    "diff_same_bg": "#1F3427",
    "diff_same_fg": "#B2D9B9",
    "diff_missing_fg": "#77827A",
    "diff_error_fg": "#D6725F",
    "drag_bg": "#C6A15B",
    "drag_fg": "#14120B",
    "input_bg": "#101512",
    "log_bg": "#0B0E0D",
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
        foreground="#0c1524",
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
        "Switch.TButton",
        background=colors["panel3"],
        foreground=colors["accent"],
        bordercolor=colors["accent"],
        focuscolor=colors["panel3"],
        focusthickness=0,
        padding=(14, 7),
        relief="flat",
        font=("Microsoft YaHei UI", 10, "bold"),
    )
    style.map(
        "Switch.TButton",
        background=[
            ("disabled", colors["panel"]),
            ("focus", colors["panel3"]),
            ("pressed", colors["accent"]),
            ("active", colors["heading_hover"]),
        ],
        bordercolor=[
            ("disabled", colors["line"]),
            ("focus", colors["accent"]),
            ("pressed", colors["accent"]),
            ("active", colors["accent_hover"]),
        ],
        foreground=[
            ("disabled", colors["disabled"]),
            ("pressed", colors["input_bg"]),
            ("active", colors["accent_hover"]),
        ],
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
        "Rail.Treeview",
        background=colors["panel"],
        fieldbackground=colors["panel"],
        foreground=colors["text"],
        rowheight=30,
        bordercolor=colors["line"],
        lightcolor=colors["line"],
        darkcolor=colors["line"],
    )
    style.map(
        "Rail.Treeview",
        background=[
            ("disabled", colors["panel"]),
        ],
        foreground=[
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
    style.configure(
        "TCheckbutton",
        background=colors["panel"],
        foreground=colors["text"],
        focuscolor=colors["panel"],
        focusthickness=0,
        indicatorcolor=colors["input_bg"],
        bordercolor=colors["line"],
        lightcolor=colors["line"],
        darkcolor=colors["line"],
        padding=(4, 2),
    )
    style.map(
        "TCheckbutton",
        background=[
            ("disabled", colors["panel"]),
            ("focus", colors["panel"]),
            ("pressed", colors["panel"]),
            ("active", colors["panel"]),
        ],
        foreground=[
            ("disabled", colors["disabled"]),
            ("focus", colors["text"]),
            ("pressed", colors["text"]),
            ("active", colors["text"]),
        ],
        indicatorcolor=[
            ("disabled", colors["panel2"]),
            ("selected", colors["accent"]),
            ("pressed", colors["input_bg"]),
            ("active", colors["input_bg"]),
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
