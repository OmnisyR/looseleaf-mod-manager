"""Runtime display metadata for MI catalog entries."""
from __future__ import annotations

from modmanager import costumes

from .catalog import CATEGORY_ORDER, MiEntry


def model_info_asset(entry: MiEntry, language: str) -> costumes.ModifiedAsset | None:
    assets = costumes.modified_assets([entry.target], "model_info", language)
    return assets[0] if assets else None


def character_id(entry: MiEntry) -> str | None:
    info = costumes.lookup(entry.stem)
    if info is not None:
        return info.base_model
    return costumes.character_id_from_stem(entry.stem)


def character_name(entry: MiEntry, language: str) -> str:
    name = costumes.character_name(character_id(entry), language)
    return "" if name == "-" else name


def display_name(entry: MiEntry, language: str) -> str:
    asset = model_info_asset(entry, language)
    return asset.display_name if asset is not None else entry.file_name


def is_recognized(entry: MiEntry) -> bool:
    return costumes.lookup(entry.stem) is not None


def character_sort_key(cid: str) -> tuple[int, int, str]:
    return costumes.character_sort_key(cid)


def sort_key(entry: MiEntry) -> tuple[object, ...]:
    category_index = CATEGORY_ORDER.index(entry.category) if entry.category in CATEGORY_ORDER else 99
    cid = character_id(entry)
    char_key = character_sort_key(cid) if cid else (9, 0, entry.stem)
    return (category_index, char_key, entry.stem.casefold())
