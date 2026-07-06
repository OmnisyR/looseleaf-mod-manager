from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

from .config import ManagerConfig
from .games import GameProfile, detect_profile, looks_like_game_dir

# Per-game data that lived directly under manager_data/ in the old single-game layout.
_LEGACY_GAME_ITEMS = (
    "mods",
    "backups",
    "table_cache",
    "_generated",
    "_staging",
    "state.json",
    "extra_costume_names.json",
    "state.before-table-language-fix.json",
)

# Per-game subdirectories that must never end up nested (e.g. mods/mods/...).
_NESTABLE_DIRS = ("mods", "backups", "table_cache", "_generated", "_staging")


def _safe_move(source: Path, destination: Path) -> None:
    """Move `source` to `destination`, merging into an existing directory.

    Plain shutil.move() drops `source` *inside* `destination` when the latter
    already exists (creating mods/mods/...). Merging avoids that.
    """
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        return
    if source.is_dir() and destination.is_dir():
        for child in source.iterdir():
            _safe_move(child, destination / child.name)
        source.rmdir()
        return
    # Type mismatch or an existing file: replace it.
    if destination.is_dir():
        shutil.rmtree(destination)
    else:
        destination.unlink()
    shutil.move(str(source), str(destination))


def repair_nested_game_data(game_dir: Path, log: Callable[[str], None] | None = None) -> bool:
    """Un-nest a `<dir>/<dir>` (e.g. mods/mods/...) left by an older buggy migration.

    Cheap to call on every activation: it only does work when the corruption
    signature is actually present. Returns True if anything was repaired.
    """
    logger = log or (lambda _message: None)
    repaired = False
    for name in _NESTABLE_DIRS:
        outer = game_dir / name
        inner = outer / name
        if not (outer.is_dir() and inner.is_dir()):
            continue
        for child in list(inner.iterdir()):
            target = outer / child.name
            if target.exists():
                continue  # never clobber an existing entry
            shutil.move(str(child), str(target))
        try:
            inner.rmdir()
        except OSError:
            pass
        else:
            repaired = True
            logger(f"repaired nested game data: {name}/{name} -> {name}")
    return repaired


def migrate_legacy_layout(
    data_home: Path,
    app_parent: Path,
    config: ManagerConfig,
    log: Callable[[str], None] | None = None,
) -> str | None:
    """Move an old flat manager_data/ into manager_data/games/<id>/ exactly once.

    `app_parent` is where the app currently sits (historically inside the game
    root), used to auto-detect which game the existing data belongs to. Returns
    the migrated game id, or None if there was nothing to migrate.
    """
    logger = log or (lambda _message: None)
    games_dir = data_home / "games"
    state_file = data_home / "state.json"
    # The flat state.json is the sole trigger: it only exists in the old layout, and
    # migration moves it away, so this is idempotent even though core pre-creates
    # games/ before calling us.
    if not state_file.exists():
        return None

    if looks_like_game_dir(app_parent):
        profile = detect_profile(app_parent)
        game_path = str(app_parent)
    else:
        profile = GameProfile(id="legacy", display_name="Legacy", known=False)
        game_path = ""

    destination = games_dir / profile.id
    destination.mkdir(parents=True, exist_ok=True)
    moved = 0
    for name in _LEGACY_GAME_ITEMS:
        source = data_home / name
        if source.exists():
            _safe_move(source, destination / name)
            moved += 1

    exe = profile.exe_names[0] if profile.exe_names else None
    config.add_game(profile.id, profile.display_name, game_path, exe)
    config.active_game_id = profile.id
    config.save()
    logger(f"migrated legacy data -> games/{profile.id} ({moved} items)")
    return profile.id
