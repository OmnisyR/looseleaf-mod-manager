from __future__ import annotations

import copy
import locale
import os
import json
from pathlib import Path
from typing import Any, Iterable


DEFAULT_CONFIG: dict[str, Any] = {
    "version": 2,
    "language": "en",
    "active_game_id": None,
    "games": {},  # game_id -> {"name": str, "path": str, "exe": str | None}
    "xinput_download_url": "",
    "advanced": {
        "model_info_diff": False,
    },
    "window": {
        "geometry": "1180x800",
        "state": "normal",
        "main_sash": None,
        "left_sash": None,
        "right_sash": None,
    },
}


def _windows_user_locale() -> str | None:
    if os.name != "nt":
        return None
    try:
        import ctypes
    except ImportError:
        return None
    try:
        buffer = ctypes.create_unicode_buffer(85)
        if ctypes.windll.kernel32.GetUserDefaultLocaleName(buffer, len(buffer)):
            return buffer.value
    except (AttributeError, OSError, ValueError):
        return None
    return None


def _locale_candidates() -> Iterable[str]:
    windows_locale = _windows_user_locale()
    if windows_locale:
        yield windows_locale
    for category in (getattr(locale, "LC_MESSAGES", locale.LC_CTYPE), locale.LC_CTYPE):
        try:
            value = locale.getlocale(category)[0]
        except (TypeError, ValueError):
            value = None
        if value:
            yield value
    for key in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(key)
        if value:
            yield value


def normalize_language(value: object, default: str | None = None) -> str:
    if isinstance(value, str):
        normalized = value.strip().replace("-", "_")
        lowered = normalized.casefold()
        if lowered in {"zh", "zh_cn", "zh_sg", "zh_tw", "zh_hk", "zh_mo"}:
            return "zh_CN"
        if lowered.startswith("zh_") or "chinese" in lowered or "中文" in normalized:
            return "zh_CN"
        if lowered == "en" or lowered.startswith("en_") or "english" in lowered:
            return "en"
    return "en" if default is None else default


def detect_default_language() -> str:
    for candidate in _locale_candidates():
        language = normalize_language(candidate, default="")
        if language:
            return language
    return "en"


def default_config() -> dict[str, Any]:
    data = copy.deepcopy(DEFAULT_CONFIG)
    data["language"] = detect_default_language()
    return data


def _merge_defaults(value: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(defaults)
    for key, item in value.items():
        if isinstance(item, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_defaults(item, merged[key])
        else:
            merged[key] = item
    return merged


class ManagerConfig:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        defaults = default_config()
        if not self.path.exists():
            return defaults
        try:
            with self.path.open("r", encoding="utf-8") as file:
                raw = json.load(file)
        except (OSError, json.JSONDecodeError):
            return defaults
        if not isinstance(raw, dict):
            return defaults
        merged = _merge_defaults(raw, defaults)
        merged["language"] = normalize_language(merged.get("language"), defaults["language"])
        return merged

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_file = self.path.with_suffix(".json.tmp")
        with temp_file.open("w", encoding="utf-8") as file:
            json.dump(self.data, file, ensure_ascii=False, indent=2)
        temp_file.replace(self.path)

    @property
    def language(self) -> str:
        language = self.data.get("language")
        return normalize_language(language, detect_default_language())

    @language.setter
    def language(self, value: str) -> None:
        self.data["language"] = normalize_language(value, self.language)

    # -- games ----------------------------------------------------------------

    @property
    def games(self) -> dict[str, Any]:
        games = self.data.setdefault("games", {})
        if not isinstance(games, dict):
            self.data["games"] = {}
        return self.data["games"]

    @property
    def active_game_id(self) -> str | None:
        value = self.data.get("active_game_id")
        return value if isinstance(value, str) else None

    @active_game_id.setter
    def active_game_id(self, value: str | None) -> None:
        self.data["active_game_id"] = value

    def get_game(self, game_id: str) -> dict[str, Any] | None:
        entry = self.games.get(game_id)
        return entry if isinstance(entry, dict) else None

    def add_game(self, game_id: str, name: str, path: str, exe: str | None = None) -> None:
        self.games[game_id] = {"name": name, "path": path, "exe": exe}

    def remove_game(self, game_id: str) -> None:
        self.games.pop(game_id, None)
        if self.active_game_id == game_id:
            self.active_game_id = None

    @property
    def xinput_download_url(self) -> str:
        value = self.data.get("xinput_download_url")
        return value if isinstance(value, str) else ""

    @xinput_download_url.setter
    def xinput_download_url(self, value: str) -> None:
        self.data["xinput_download_url"] = value

    @property
    def advanced(self) -> dict[str, Any]:
        advanced = self.data.setdefault("advanced", {})
        if not isinstance(advanced, dict):
            self.data["advanced"] = copy.deepcopy(DEFAULT_CONFIG["advanced"])
        return self.data["advanced"]

    @property
    def model_info_diff_enabled(self) -> bool:
        return bool(self.advanced.get("model_info_diff", False))

    @model_info_diff_enabled.setter
    def model_info_diff_enabled(self, value: bool) -> None:
        self.advanced["model_info_diff"] = bool(value)

    @property
    def window(self) -> dict[str, Any]:
        window = self.data.setdefault("window", {})
        if not isinstance(window, dict):
            self.data["window"] = copy.deepcopy(DEFAULT_CONFIG["window"])
        return self.data["window"]

    def get_window_value(self, key: str, default: Any = None) -> Any:
        return self.window.get(key, default)

    def set_window_value(self, key: str, value: Any) -> None:
        self.window[key] = value
