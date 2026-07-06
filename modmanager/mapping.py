from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Callable

from .constants import (
    CUSTOM_TABLE_FILES,
    DEFAULT_TABLE_TARGET,
    IMAGE_TARGET,
    MODEL_INFO_TARGET,
    MODEL_TARGET,
    TABLE_LANGUAGE_PRIORITY,
)
from .i18n import DEFAULT_LANGUAGE, translate
from .models import FileMapping
from .pathutils import is_archive, is_table_dir_name, normalize_key, posix_path, table_language


def _t(tr: Callable[..., str] | None, key: str, **kwargs: object) -> str:
    if tr is not None:
        return tr(key, **kwargs)
    return translate(DEFAULT_LANGUAGE, key, **kwargs)


class TableResolver:
    """Figures out which localized `table_*` folder mod files should target."""

    def __init__(self, game_root: Path) -> None:
        self.game_root = game_root
        self._active_table_dir: str | None = None

    def reset(self) -> None:
        self._active_table_dir = None

    def active_table_dir(self) -> str:
        if self._active_table_dir:
            return self._active_table_dir

        console_log = self.game_root / "console.log"
        if console_log.exists():
            try:
                text = console_log.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                text = ""
            matches = re.findall(r"(table_[a-z0-9]+)[\\/]+t_costume\.tbl", text, flags=re.IGNORECASE)
            if matches:
                self._active_table_dir = matches[-1].casefold()
                return self._active_table_dir

        pac_dir = self.game_root / "pac" / "steam"
        pac_tables = {path.stem.casefold() for path in pac_dir.glob("table_*.pac")} if pac_dir.exists() else set()
        for candidate in (DEFAULT_TABLE_TARGET, "table_en", "table_tc", "table_kr"):
            if candidate in pac_tables:
                self._active_table_dir = candidate
                return self._active_table_dir
        if pac_tables:
            self._active_table_dir = sorted(pac_tables)[0]
            return self._active_table_dir

        self._active_table_dir = DEFAULT_TABLE_TARGET
        return self._active_table_dir

    def source_table_dir(self, file_path: Path, root: Path) -> str | None:
        relative = file_path.resolve().relative_to(root.resolve())
        for part in relative.parts[:-1]:
            if is_table_dir_name(part):
                return part.casefold()
        return None

    def source_rank(self, source_table_dir: str) -> tuple[int, str]:
        active_language = table_language(self.active_table_dir())
        language = table_language(source_table_dir)
        priority = [active_language]
        for candidate in TABLE_LANGUAGE_PRIORITY:
            if candidate not in priority:
                priority.append(candidate)
        try:
            return (priority.index(language), source_table_dir)
        except ValueError:
            return (len(priority), source_table_dir)


def normalize_asset_target(target: PurePosixPath | str) -> PurePosixPath:
    path = PurePosixPath(posix_path(target))
    parts = [part.casefold() for part in path.parts]
    if path.suffix.casefold() == ".mi" and parts[:2] == ["asset", "model_info"]:
        return MODEL_INFO_TARGET / path.name
    return path


def infer_target(file_path: Path, root: Path, tables: TableResolver) -> PurePosixPath | None:
    relative = file_path.resolve().relative_to(root.resolve())
    parts = relative.parts
    lowered = [part.casefold() for part in parts]
    if "asset" in lowered:
        asset_index = lowered.index("asset")
        return normalize_asset_target(PurePosixPath(*parts[asset_index:]))

    suffix = file_path.suffix.casefold()
    if suffix == ".tbl" and file_path.name.casefold() in CUSTOM_TABLE_FILES:
        return None
    if suffix == ".mdl":
        return MODEL_TARGET / file_path.name
    if suffix == ".mi":
        return MODEL_INFO_TARGET / file_path.name
    if suffix == ".dds":
        return IMAGE_TARGET / file_path.name
    return None


def collect_mappings(
    root: Path,
    tables: TableResolver,
    log: Callable[[str], None],
    tr: Callable[..., str] | None = None,
) -> list[FileMapping]:
    mappings: list[FileMapping] = []
    ignored = 0
    table_files = 0
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        if is_archive(file_path):
            continue
        if (
            file_path.suffix.casefold() == ".tbl"
            and file_path.name.casefold() in CUSTOM_TABLE_FILES
        ):
            table_files += 1
            ignored += 1
            continue
        target = infer_target(file_path, root, tables)
        if target is None:
            ignored += 1
            continue
        mappings.append(FileMapping(file_path, target, None))
    mappings = deduplicate_table_mappings(mappings, tables, log, tr)
    if table_files:
        log(_t(tr, "mapping_table_files_deferred", count=table_files))
    log(_t(tr, "mapping_recognized", count=len(mappings), ignored=ignored))
    return mappings


def deduplicate_table_mappings(
    mappings: list[FileMapping],
    tables: TableResolver,
    log: Callable[[str], None],
    tr: Callable[..., str] | None = None,
) -> list[FileMapping]:
    table_mappings: dict[str, list[FileMapping]] = {}
    result: list[FileMapping] = []
    for mapping in mappings:
        if mapping.source_table_dir:
            table_mappings.setdefault(normalize_key(mapping.target), []).append(mapping)
        else:
            result.append(mapping)

    if not table_mappings:
        return mappings

    source_dirs = sorted(
        {
            mapping.source_table_dir
            for candidates in table_mappings.values()
            for mapping in candidates
            if mapping.source_table_dir
        }
    )
    skipped = 0
    kept_dirs: set[str] = set()
    for _target_key, candidates in sorted(table_mappings.items()):
        selected = min(candidates, key=lambda item: tables.source_rank(item.source_table_dir or ""))
        result.append(selected)
        if selected.source_table_dir:
            kept_dirs.add(selected.source_table_dir)
        skipped += len(candidates) - 1

    if len(source_dirs) > 1:
        log(
            _t(
                tr,
                "mapping_localized_dirs",
                dirs=", ".join(source_dirs),
                target=tables.active_table_dir(),
                kept=", ".join(sorted(kept_dirs)),
            )
        )
    if skipped:
        log(_t(tr, "mapping_duplicate_localized", count=skipped))
    return result
