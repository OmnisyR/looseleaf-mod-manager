from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re

from .pathutils import slugify

# Executable basenames that are never the game itself (installers, crash handlers,
# redistributables shipped alongside Falcom titles). Excluded from auto-naming.
_IGNORED_EXE_NAMES = {
    "unins000.exe",
    "uninstall.exe",
    "crashpad_handler.exe",
    "vc_redist.x64.exe",
    "vc_redist.x86.exe",
    "dxwebsetup.exe",
    "notification_helper.exe",
}

XINPUT_DLL = "xinput1_4.dll"
_LIBRARYFOLDERS_VDF = Path("steamapps") / "libraryfolders.vdf"


@dataclass(frozen=True)
class GameProfile:
    id: str
    display_name: str
    exe_names: tuple[str, ...] = ()
    costume_catalog: str | None = None
    known: bool = field(default=True)


# Known Falcom titles that share this asset/table mod layout. Add new games here as
# one-line entries; only games with a shipped costume catalog set `costume_catalog`.
# Unknown folders fall back to a generic profile (mod management still works fully).
KNOWN_GAMES: tuple[GameProfile, ...] = (
    GameProfile(
        id="sora_1st",
        display_name="空之轨迹 the 1st",
        exe_names=("sora_1st.exe",),
        costume_catalog="sora_1st.json",
    ),
    GameProfile(
        id="sora_2nd",
        display_name="空之轨迹 the 2nd",
        exe_names=("sora_2nd.exe",),
    ),
    GameProfile(
        id="sora_3rd",
        display_name="空之轨迹 the 3rd",
        exe_names=("sora_3rd.exe",),
    ),
)

_KNOWN_BY_EXE: dict[str, GameProfile] = {
    exe.casefold(): profile for profile in KNOWN_GAMES for exe in profile.exe_names
}


def _root_exes(game_root: Path) -> list[Path]:
    try:
        return sorted(
            (p for p in game_root.iterdir() if p.is_file() and p.suffix.casefold() == ".exe"),
            key=lambda p: p.name.casefold(),
        )
    except OSError:
        return []


def _primary_exe(game_root: Path) -> Path | None:
    candidates = [p for p in _root_exes(game_root) if p.name.casefold() not in _IGNORED_EXE_NAMES]
    if not candidates:
        return None
    # The game executable is almost always the largest one in the root.
    try:
        return max(candidates, key=lambda p: p.stat().st_size)
    except OSError:
        return candidates[0]


def detect_profile(game_root: Path) -> GameProfile:
    """Identify the game in `game_root`, falling back to a generic profile."""
    game_root = Path(game_root)
    for exe in _root_exes(game_root):
        profile = _KNOWN_BY_EXE.get(exe.name.casefold())
        if profile is not None:
            return profile

    primary = _primary_exe(game_root)
    if primary is not None:
        stem = primary.stem
        return GameProfile(
            id=slugify(stem),
            display_name=stem,
            exe_names=(primary.name,),
            known=False,
        )

    name = game_root.name or "game"
    return GameProfile(id=slugify(name), display_name=name, known=False)


def resolve_game_id(game_root: Path) -> str:
    return detect_profile(game_root).id


def looks_like_game_dir(path: Path) -> bool:
    """Lenient check used to warn (not block) on an obviously-wrong folder pick."""
    path = Path(path)
    if not path.is_dir():
        return False
    if (path / "asset").is_dir():
        return True
    try:
        if any(child.is_dir() and child.name.casefold().startswith("table_") for child in path.iterdir()):
            return True
    except OSError:
        return False
    return bool(_root_exes(path))


def xinput_present(game_root: Path) -> bool:
    return (Path(game_root) / XINPUT_DLL).is_file()


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            key = str(path.resolve()).casefold()
        except OSError:
            key = str(path.absolute()).casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _raw_path(value: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(value))).resolve()


def _vdf_unescape(value: str) -> str:
    return value.replace("\\\\", "\\").replace('\\"', '"').replace("\\/", "/")


def parse_steam_library_paths(vdf_text: str) -> list[Path]:
    paths = []
    for match in re.finditer(r'"path"\s+"((?:\\.|[^"\\])*)"', vdf_text, re.IGNORECASE):
        raw = _vdf_unescape(match.group(1))
        if raw:
            paths.append(_raw_path(raw))
    return _dedupe_paths(paths)


def _steam_roots_from_registry() -> list[Path]:
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []

    candidates: list[Path] = []
    registry_keys = (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam"),
    )
    for hive, key_name in registry_keys:
        try:
            with winreg.OpenKey(hive, key_name) as key:
                for value_name in ("SteamPath", "InstallPath"):
                    try:
                        value, _value_type = winreg.QueryValueEx(key, value_name)
                    except OSError:
                        continue
                    if isinstance(value, str) and value:
                        candidates.append(_raw_path(value))
        except OSError:
            continue
    return _dedupe_paths(candidates)


def _candidate_steam_roots() -> list[Path]:
    candidates: list[Path] = []
    for key in ("STEAM_PATH", "STEAM_HOME"):
        value = os.environ.get(key)
        if value:
            candidates.append(_raw_path(value))

    candidates.extend(_steam_roots_from_registry())

    if os.name == "nt":
        for key in ("ProgramFiles(x86)", "ProgramFiles"):
            value = os.environ.get(key)
            if value:
                candidates.append(_raw_path(str(Path(value) / "Steam")))
    else:
        home = Path.home()
        candidates.extend(
            [
                home / ".steam" / "steam",
                home / ".local" / "share" / "Steam",
                home / "Library" / "Application Support" / "Steam",
            ]
        )
    return _dedupe_paths(candidates)


def steam_library_dirs(steam_root: Path | None = None) -> list[Path]:
    roots = [_raw_path(str(steam_root))] if steam_root else _candidate_steam_roots()
    libraries: list[Path] = []
    for root in roots:
        if root.is_dir():
            libraries.append(root)
        library_vdf = root / _LIBRARYFOLDERS_VDF
        try:
            text = library_vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        libraries.extend(path for path in parse_steam_library_paths(text) if path.is_dir())
    return _dedupe_paths(libraries)


def steam_common_dirs(steam_root: Path | None = None) -> list[Path]:
    common_dirs = [library / "steamapps" / "common" for library in steam_library_dirs(steam_root)]
    return _dedupe_paths([path for path in common_dirs if path.is_dir()])


def default_game_picker_dir() -> Path | None:
    common_dirs = steam_common_dirs()
    if common_dirs:
        return common_dirs[0]
    libraries = steam_library_dirs()
    return libraries[0] if libraries else None
