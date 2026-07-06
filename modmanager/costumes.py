from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import NamedTuple

from .constants import APP_DIR, DATA_DIR_NAME
from .pathutils import posix_path

COSTUMES_DIR = APP_DIR / DATA_DIR_NAME / "costumes"
# Base (shipped) catalog for the active game. Defaults to Sora 1st so tests and a
# fresh launch resolve its costumes; core points this at the active game's catalog.
BASE_DATA_PATH = COSTUMES_DIR / "sora_1st.json"
# Per-game catalog generated from that game's merged tables during apply.
EXTRA_DATA_PATH = APP_DIR / DATA_DIR_NAME / "extra_costume_names.json"


def configure_paths(base: Path | None = None, extra: Path | None = None) -> None:
    """Point the catalog at the active game's data files and drop the cache."""
    global BASE_DATA_PATH, EXTRA_DATA_PATH
    if base is not None:
        BASE_DATA_PATH = base
    if extra is not None:
        EXTRA_DATA_PATH = extra
    reload_catalog()


class CostumeInfo(NamedTuple):
    base_model: str
    en: str | None
    cn: str | None

    def display(self, language: str = "zh_CN") -> str:
        if language == "en":
            return self.en or self.cn or self.base_model
        return self.cn or self.en or self.base_model


@dataclass(frozen=True)
class CostumeChange:
    target: str
    file_name: str
    stem: str
    display_name: str
    character_id: str
    character_name: str
    recognized: bool


@lru_cache(maxsize=1)
def _catalog() -> dict[str, CostumeInfo]:
    catalog: dict[str, CostumeInfo] = {}
    catalog.update(_load_catalog_file(BASE_DATA_PATH))
    catalog.update(_load_catalog_file(EXTRA_DATA_PATH))
    return catalog


def _load_catalog_file(path: Path) -> dict[str, CostumeInfo]:
    try:
        with path.open(encoding="utf-8") as file:
            raw = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        key.casefold(): CostumeInfo(entry["base_model"], entry.get("en"), entry.get("cn"))
        for key, entry in raw.items()
        if isinstance(entry, dict) and entry.get("base_model")
    }


def reload_catalog() -> None:
    _catalog.cache_clear()


def lookup(stem: str) -> CostumeInfo | None:
    return _catalog().get(stem.casefold())


def character_id_from_stem(stem: str) -> str | None:
    match = re.match(r"(chr\d+)", stem.casefold())
    return match.group(1) if match else None


def character_sort_key(character_id: str) -> tuple[int, int, str]:
    match = re.fullmatch(r"chr(\d+)", character_id.casefold())
    if match:
        return (0, int(match.group(1)), character_id.casefold())
    return (1, 0, character_id.casefold())


def character_name(character_id: str | None, language: str = "zh_CN") -> str:
    if not character_id:
        return "-"
    base_info = lookup(character_id)
    return base_info.display(language) if base_info else character_id


def describe_target(target: str, language: str = "zh_CN") -> str | None:
    stem = Path(posix_path(target)).stem
    info = lookup(stem)
    return info.display(language) if info else None


def is_costume_model_target(target: str) -> bool:
    path = PurePosixPath(posix_path(target))
    parts = [part.casefold() for part in path.parts]
    if len(parts) < 4 or parts[:3] != ["asset", "common", "model"]:
        return False
    if path.suffix.casefold() != ".mdl":
        return False

    stem = path.stem.casefold()
    if stem.endswith("_face") or stem.startswith("equ"):
        return False
    if "_m_" in stem:
        return False
    return re.fullmatch(r"chr\d+(?:_c[0-9a-z]+)?", stem) is not None


def modified_costumes(files: list[str], language: str = "zh_CN") -> list[CostumeChange]:
    known: list[CostumeChange] = []
    raw: list[CostumeChange] = []
    seen: set[str] = set()
    for target in files:
        if not is_costume_model_target(target):
            continue
        path = PurePosixPath(posix_path(target))
        stem = path.stem
        key = stem.casefold()
        if key in seen:
            continue
        seen.add(key)

        info = lookup(stem)
        character_id = info.base_model if info else character_id_from_stem(stem)
        display_character = character_name(character_id, language)
        if info:
            known.append(
                CostumeChange(
                    target=posix_path(target),
                    file_name=path.name,
                    stem=stem,
                    display_name=info.display(language),
                    character_id=character_id or stem,
                    character_name=display_character,
                    recognized=True,
                )
            )
        else:
            raw.append(
                CostumeChange(
                    target=posix_path(target),
                    file_name=path.name,
                    stem=stem,
                    display_name=path.name,
                    character_id=character_id or stem,
                    character_name=display_character,
                    recognized=False,
                )
            )

    known.sort(key=lambda item: item.display_name.casefold())
    raw.sort(key=lambda item: item.file_name.casefold())
    return known + raw


def costume_characters(files: list[str], language: str = "zh_CN") -> list[tuple[str, str]]:
    characters: dict[str, str] = {}
    for change in modified_costumes(files, language):
        characters.setdefault(change.character_id, change.character_name)
    return sorted(characters.items(), key=lambda item: character_sort_key(item[0]))
