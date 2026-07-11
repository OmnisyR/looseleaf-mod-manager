"""Monitor-aware window geometry validation.

Saved window positions can reference a monitor that is no longer connected
(or an arrangement that changed). Restoring such a geometry materializes the
window entirely off-screen — it looks like the app opens to a black/blank
screen. Sanitize saved geometry against the current virtual screen before
applying it.
"""
from __future__ import annotations

import re
import sys
import tkinter as tk

_GEOMETRY_RE = re.compile(r"^=?(\d+)x(\d+)(?:([+-][-+]?\d+)([+-][-+]?\d+))?$")

# Minimum part of the window (roughly the title bar) that must remain on a
# connected monitor for a saved position to be considered usable.
_MIN_VISIBLE_X = 160
_MIN_VISIBLE_Y = 40


def virtual_screen_bounds(root: tk.Misc) -> tuple[int, int, int, int]:
    """(x, y, width, height) of the full desktop across all monitors."""
    if sys.platform == "win32":
        try:
            import ctypes

            metrics = ctypes.windll.user32.GetSystemMetrics
            x, y = metrics(76), metrics(77)  # SM_XVIRTUALSCREEN / SM_YVIRTUALSCREEN
            width, height = metrics(78), metrics(79)  # SM_CXVIRTUALSCREEN / SM_CYVIRTUALSCREEN
            if width > 0 and height > 0:
                return x, y, width, height
        except Exception:
            pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def sanitize_geometry(geometry: str, bounds: tuple[int, int, int, int], default: str) -> str:
    """Return a geometry string that is guaranteed to be reachable on screen.

    Off-screen positions are dropped (size is kept, the window manager picks
    a visible position); oversized windows are clamped to the desktop.
    """
    match = _GEOMETRY_RE.match(str(geometry or "").strip())
    if not match:
        return default
    width, height = int(match.group(1)), int(match.group(2))
    screen_x, screen_y, screen_w, screen_h = bounds
    width = max(320, min(width, screen_w))
    height = max(240, min(height, screen_h))

    if match.group(3) is None:
        return f"{width}x{height}"

    x = _parse_offset(match.group(3))
    y = _parse_offset(match.group(4))
    if x is None or y is None:
        return f"{width}x{height}"
    visible_x = x + width > screen_x + _MIN_VISIBLE_X and x < screen_x + screen_w - _MIN_VISIBLE_X
    visible_y = y + _MIN_VISIBLE_Y > screen_y and y < screen_y + screen_h - _MIN_VISIBLE_Y
    if visible_x and visible_y:
        # Tk geometry syntax: a leading "-" means "from the right/bottom edge",
        # so negative absolute coordinates must be written as "+-2076".
        return f"{width}x{height}+{x}+{y}"
    return f"{width}x{height}"


def _parse_offset(token: str) -> int | None:
    """Absolute offset from a Tk geometry token; None for right/bottom-relative."""
    if token.startswith("+"):
        return int(token[1:])
    # "-X" positions relative to the far edge; treat as unknown and drop it.
    return None


def sanitize_geometry_for(root: tk.Misc, geometry: str, default: str) -> str:
    return sanitize_geometry(geometry, virtual_screen_bounds(root), default)
