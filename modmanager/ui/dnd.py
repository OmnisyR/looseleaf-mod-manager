from __future__ import annotations

import tkinter as tk
from pathlib import Path


def parse_drop_paths(widget: tk.Misc, data: str) -> list[Path]:
    return [Path(item) for item in widget.tk.splitlist(data)]
