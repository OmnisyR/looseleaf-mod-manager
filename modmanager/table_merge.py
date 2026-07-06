from __future__ import annotations

import copy
import json
import re
import shutil
import struct
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable

from .constants import CUSTOM_TABLE_FILES
from .errors import ManagerError
from .i18n import DEFAULT_LANGUAGE, translate
from .models import FileMapping
from .network import download_url_to_file
from .pathutils import is_table_dir_name


KUROTOOLS_ZIP_URL = "https://github.com/nnguyen259/KuroTools/archive/refs/heads/master.zip"
MAX_KUROTOOLS_DOWNLOAD_BYTES = 50 * 1024 * 1024


def _t(tr: Callable[..., str] | None, key: str, **kwargs: object) -> str:
    if tr is not None:
        return tr(key, **kwargs)
    return translate(DEFAULT_LANGUAGE, key, **kwargs)


PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    "ItemTableData": ("id",),
    "ItemKindParam2": ("id",),
    "ItemTabType": ("id", "int1", "int2"),
    "ItemShopTabType": ("int1", "int2"),
    "CostumeParam": ("character_id", "item_id"),
    "CostumeAttachOffset": ("int0", "int1", "text"),
    "CostumeTable": ("character_id", "item_id", "costume_model"),
    "CostumeAttachTable": ("character_id", "item_id", "base_model", "equip_model", "attach_point"),
    "CostumeMaterialTable": ("character_id", "item_id", "base_model", "equip_model"),
    "CostumeUIFaceTable": ("character_id", "int0", "int1", "int2"),
    "DLCTableData": ("int1",),
    "DLCTable": ("id",),
    "ShopInfo": ("id",),
    "ShopItem": ("shop_id", "item_id"),
    "ShopTypeDesc": ("id",),
    "ShopConv": ("id",),
    "TradeItem": ("offered_item_id",),
    "BargainItem": ("id",),
    "ProductInfo": ("shop_id",),
    "ShopNameInfo": ("id",),
    "CharaSettingInfo": ("id", "float1", "float2", "float3", "float4"),
    "CharaArrange": ("chr_id", "int1", "animation"),
}


FALLBACK_KEY_CANDIDATES: tuple[tuple[str, ...], ...] = (
    ("shop_id", "item_id"),
    ("character_id", "item_id"),
    ("chr_id", "int1"),
    ("offered_item_id",),
    ("shop_id",),
    ("item_id",),
    ("id",),
)


@dataclass(frozen=True)
class TableSource:
    source: Path
    table_name: str
    source_table_dir: str


@dataclass
class MergeState:
    key_fields: dict[str, tuple[str, ...]]
    protected_keys: dict[str, set[tuple]]
    row_indexes: dict[str, dict[tuple, int]]


@dataclass(frozen=True)
class TableMergeChanges:
    added_by_section: dict[str, int]
    replaced_by_section: dict[str, int]

    @property
    def changed_count(self) -> int:
        return sum(self.added_by_section.values()) + sum(self.replaced_by_section.values())


@dataclass(frozen=True)
class MergeSummary:
    table_name: str
    source_table_dir: str
    target: PurePosixPath
    added_by_section: dict[str, int]

    @property
    def added_count(self) -> int:
        return sum(self.added_by_section.values())


def collect_table_sources(
    root: Path,
    tables,
    log: Callable[[str], None],
    tr: Callable[..., str] | None = None,
) -> list[TableSource]:
    candidates: dict[str, list[TableSource]] = {}
    active_table_dir = tables.active_table_dir()
    for file_path in root.rglob("*.tbl"):
        table_name = file_path.name.casefold()
        if table_name not in CUSTOM_TABLE_FILES:
            continue
        source_table_dir = _source_table_dir(file_path, root) or active_table_dir
        candidates.setdefault(table_name, []).append(
            TableSource(file_path, table_name, source_table_dir)
        )

    selected: list[TableSource] = []
    skipped = 0
    for table_name, table_candidates in sorted(candidates.items()):
        choice = min(table_candidates, key=lambda item: tables.source_rank(item.source_table_dir))
        selected.append(choice)
        skipped += len(table_candidates) - 1
        source_dirs = sorted({item.source_table_dir for item in table_candidates})
        if len(source_dirs) > 1:
            log(
                _t(
                    tr,
                    "table_sources_localized",
                    table=table_name,
                    dirs=", ".join(source_dirs),
                    kept=choice.source_table_dir,
                )
            )

    if selected:
        log(_t(tr, "table_sources_cached", count=len(selected)))
    if skipped:
        log(_t(tr, "table_sources_duplicate_skipped", count=skipped))
    return selected


def build_merged_tables(
    table_sources: Iterable[dict],
    output_root: Path,
    work_root: Path,
    game_root: Path,
    table_cache_dir: Path,
    tools_dir: Path,
    tables,
    log: Callable[[str], None],
    tr: Callable[..., str] | None = None,
) -> list[FileMapping]:
    sources = list(table_sources)
    if not sources:
        return []

    active_table_dir = tables.active_table_dir()
    grouped: dict[str, list[dict]] = {}
    for source in sources:
        table_name = str(source.get("table_name", "")).casefold()
        if table_name in CUSTOM_TABLE_FILES:
            grouped.setdefault(table_name, []).append(source)

    if not grouped:
        return []

    mappings: list[FileMapping] = []
    kurotools: Path | None = None
    output_root.mkdir(parents=True, exist_ok=True)
    work_root.mkdir(parents=True, exist_ok=True)
    for table_name, table_group in sorted(grouped.items()):
        base_bytes = read_cached_official_table(
            game_root,
            table_cache_dir,
            active_table_dir,
            table_name,
            log,
            tr,
        )
        if base_bytes is None:
            log(_t(tr, "table_base_missing", table=table_name, dir=active_table_dir))
            continue
        if kurotools is None:
            try:
                kurotools = ensure_kurotools(tools_dir, log, tr)
            except Exception as exc:
                log(_t(tr, "table_merge_kurotools_unavailable", error=exc))
                return mappings

        table_work = work_root / table_name
        if table_work.exists():
            shutil.rmtree(table_work)
        base_table = table_work / "base" / table_name
        base_table.parent.mkdir(parents=True, exist_ok=True)
        base_table.write_bytes(base_bytes)

        try:
            base_json = parse_tbl(kurotools, base_table)
        except Exception as exc:
            log(_t(tr, "table_base_parse_failed", table=table_name, error=exc))
            continue

        merge_state = create_merge_state(base_json)
        total_added: dict[str, int] = {}
        total_replaced: dict[str, int] = {}
        for source_info in table_group:
            source_path = Path(str(source_info.get("source", "")))
            if not source_path.exists():
                log(_t(tr, "table_source_missing", path=source_path))
                continue
            try:
                source_json = parse_tbl(kurotools, source_path)
                changes = merge_table_json_changes(
                    base_json,
                    source_json,
                    merge_state,
                    replace_added=True,
                )
            except Exception as exc:
                mod_name = source_info.get("mod_name") or source_info.get("source_table_dir") or source_path.name
                log(_t(tr, "table_source_merge_failed", mod=mod_name, table=table_name, error=exc))
                continue

            for section, count in changes.added_by_section.items():
                total_added[section] = total_added.get(section, 0) + count
            for section, count in changes.replaced_by_section.items():
                total_replaced[section] = total_replaced.get(section, 0) + count
            if changes.changed_count:
                mod_name = source_info.get("mod_name") or source_info.get("source_table_dir") or source_path.name
                detail = _format_change_detail(changes)
                log(_t(tr, "table_rows_merged", table=table_name, mod=mod_name, detail=detail))

        if not total_added and not total_replaced:
            log(_t(tr, "table_no_extra_rows", table=table_name))
            continue

        output_table = output_root / active_table_dir / table_name
        try:
            pack_tbl(kurotools, base_json, table_name, output_table)
        except Exception as exc:
            log(_t(tr, "table_pack_failed", table=table_name, error=exc))
            continue
        mappings.append(FileMapping(output_table, PurePosixPath(active_table_dir, table_name)))
        added_text = ", ".join(f"{name}+{count}" for name, count in sorted(total_added.items()))
        replaced_text = ", ".join(f"{name}~{count}" for name, count in sorted(total_replaced.items()))
        detail = "; ".join(part for part in (added_text, replaced_text) if part)
        log(_t(tr, "table_built_merged", dir=active_table_dir, table=table_name, detail=detail))

    return mappings


def build_extra_costume_catalog(
    table_sources: Iterable[dict],
    output_path: Path,
    game_root: Path,
    table_cache_dir: Path,
    tools_dir: Path,
    tables,
    log: Callable[[str], None],
    tr: Callable[..., str] | None = None,
) -> int:
    sources = [
        source for source in table_sources
        if str(source.get("table_name", "")).casefold() in {"t_costume.tbl", "t_item.tbl"}
    ]
    if not sources:
        _write_extra_costume_catalog(output_path, {})
        return 0

    costume_sources = [
        source for source in sources
        if str(source.get("table_name", "")).casefold() == "t_costume.tbl"
    ]
    if not costume_sources:
        _write_extra_costume_catalog(output_path, {})
        return 0

    active_table_dir = tables.active_table_dir()
    base_costume_bytes = read_cached_official_table(
        game_root,
        table_cache_dir,
        active_table_dir,
        "t_costume.tbl",
        log,
        tr,
    )
    if base_costume_bytes is None:
        log(_t(tr, "extra_catalog_base_missing"))
        _write_extra_costume_catalog(output_path, {})
        return 0

    try:
        kurotools = ensure_kurotools(tools_dir, log, tr)
    except Exception as exc:
        log(_t(tr, "extra_catalog_kurotools_unavailable", error=exc))
        _write_extra_costume_catalog(output_path, {})
        return 0

    work_root = output_path.parent / "_generated" / "_extra_catalog_work"
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True, exist_ok=True)
    try:
        base_costume = work_root / "base" / "t_costume.tbl"
        base_costume.parent.mkdir(parents=True, exist_ok=True)
        base_costume.write_bytes(base_costume_bytes)
        base_costume_json = parse_tbl(kurotools, base_costume)
    except Exception as exc:
        log(_t(tr, "extra_catalog_base_parse_failed", error=exc))
        _write_extra_costume_catalog(output_path, {})
        shutil.rmtree(work_root, ignore_errors=True)
        return 0

    base_state = create_merge_state(base_costume_json)
    item_sources_by_mod: dict[str, dict] = {}
    for source in sources:
        if str(source.get("table_name", "")).casefold() != "t_item.tbl":
            continue
        mod_id = str(source.get("mod_id") or "")
        if mod_id and mod_id not in item_sources_by_mod:
            item_sources_by_mod[mod_id] = source

    item_cache: dict[str, dict[int, str]] = {}
    catalog: dict[str, dict[str, object]] = {}
    for source_info in costume_sources:
        source_path = Path(str(source_info.get("source", "")))
        if not source_path.exists():
            continue
        try:
            source_json = parse_tbl(kurotools, source_path)
        except Exception as exc:
            mod_name = source_info.get("mod_name") or source_path.name
            log(_t(tr, "extra_catalog_source_parse_failed", mod=mod_name, error=exc))
            continue

        mod_id = str(source_info.get("mod_id") or "")
        item_names = _item_names_for_source(
            kurotools,
            item_sources_by_mod.get(mod_id),
            item_cache,
            log,
            tr,
        )
        language_field = _catalog_language_field(str(source_info.get("source_table_dir") or ""))
        for model, item_id in _iter_extra_costume_rows(source_json, base_state):
            base_model = _base_model_from_costume_model(model)
            if base_model is None:
                continue
            display_name = item_names.get(item_id) or model
            key = model.casefold()
            entry = catalog.setdefault(key, {"base_model": base_model})
            entry["base_model"] = base_model
            entry[language_field] = display_name
            entry["item_id"] = item_id
            entry["source_mod"] = source_info.get("mod_name") or source_info.get("mod_id") or ""
            entry["source_table_dir"] = source_info.get("source_table_dir") or ""

    shutil.rmtree(work_root, ignore_errors=True)
    _write_extra_costume_catalog(output_path, catalog)
    count = len(catalog)
    if count:
        log(_t(tr, "extra_catalog_built", count=count))
    else:
        log(_t(tr, "extra_catalog_empty"))
    return count


def extra_costume_catalog_from_json(
    costume_json: dict,
    item_json: dict | None,
    base_costume_json: dict,
    language_field: str = "en",
) -> dict[str, dict[str, object]]:
    base_state = create_merge_state(base_costume_json)
    item_names = _item_names_by_id(item_json or {})
    catalog: dict[str, dict[str, object]] = {}
    for model, item_id in _iter_extra_costume_rows(costume_json, base_state):
        base_model = _base_model_from_costume_model(model)
        if base_model is None:
            continue
        catalog[model.casefold()] = {
            "base_model": base_model,
            language_field: item_names.get(item_id) or model,
            "item_id": item_id,
        }
    return catalog


def merge_table_file(
    kurotools: Path,
    base_table: Path,
    foreign_table: Path,
    output_table: Path,
    table_name: str,
    source_table_dir: str,
    target: PurePosixPath,
) -> MergeSummary:
    base_json = parse_tbl(kurotools, base_table)
    foreign_json = parse_tbl(kurotools, foreign_table)
    added_by_section = merge_table_json(base_json, foreign_json)
    if sum(added_by_section.values()) > 0:
        pack_tbl(kurotools, base_json, table_name, output_table)
    return MergeSummary(table_name, source_table_dir, target, added_by_section)


def merge_table_json(base_json: dict, foreign_json: dict) -> dict[str, int]:
    return merge_table_json_changes(base_json, foreign_json).added_by_section


def create_merge_state(base_json: dict) -> MergeState:
    key_fields: dict[str, tuple[str, ...]] = {}
    protected_keys: dict[str, set[tuple]] = {}
    row_indexes: dict[str, dict[tuple, int]] = {}
    base_sections = {section["name"]: section for section in base_json.get("data", [])}
    for name, section in base_sections.items():
        base_rows = section.get("data") or []
        if not base_rows:
            continue
        fields = _key_fields(name, base_rows[0])
        if not fields:
            continue
        key_fields[name] = fields
        protected_keys[name] = set()
        row_indexes[name] = {}
        for index, row in enumerate(base_rows):
            if not _has_fields(row, fields):
                continue
            key = _row_key(row, fields)
            protected_keys[name].add(key)
            row_indexes[name][key] = index
    return MergeState(key_fields, protected_keys, row_indexes)


def merge_table_json_changes(
    base_json: dict,
    foreign_json: dict,
    state: MergeState | None = None,
    replace_added: bool = False,
) -> TableMergeChanges:
    base_sections = {section["name"]: section for section in base_json.get("data", [])}
    if state is None:
        state = create_merge_state(base_json)
    added_by_section: dict[str, int] = {}
    replaced_by_section: dict[str, int] = {}
    for foreign_section in foreign_json.get("data", []):
        name = foreign_section.get("name")
        if not isinstance(name, str) or name not in base_sections:
            continue
        foreign_rows = foreign_section.get("data") or []
        base_rows = base_sections[name].get("data") or []
        if not foreign_rows:
            continue
        key_fields = state.key_fields.get(name) or _key_fields(name, foreign_rows[0])
        if not key_fields:
            continue
        state.key_fields.setdefault(name, key_fields)
        protected = state.protected_keys.setdefault(name, set())
        row_index = state.row_indexes.setdefault(
            name,
            {_row_key(row, key_fields): index for index, row in enumerate(base_rows) if _has_fields(row, key_fields)},
        )
        added = 0
        replaced = 0
        for row in foreign_rows:
            if not _has_fields(row, key_fields):
                continue
            key = _row_key(row, key_fields)
            if key in protected:
                continue
            if key in row_index:
                if replace_added:
                    base_rows[row_index[key]] = copy.deepcopy(row)
                    replaced += 1
                continue
            base_rows.append(copy.deepcopy(row))
            row_index[key] = len(base_rows) - 1
            added += 1
        if added:
            added_by_section[name] = added
        if replaced:
            replaced_by_section[name] = replaced
    return TableMergeChanges(added_by_section, replaced_by_section)


def ensure_kurotools(
    tools_dir: Path,
    log: Callable[[str], None],
    tr: Callable[..., str] | None = None,
) -> Path:
    target = tools_dir / "KuroTools"
    if _is_kurotools_ready(target):
        return target

    tools_dir.mkdir(parents=True, exist_ok=True)
    temp_zip = tools_dir / "KuroTools-main.zip"
    temp_extract = tools_dir / "KuroTools-download"
    if temp_extract.exists():
        shutil.rmtree(temp_extract)
    temp_extract.mkdir(parents=True, exist_ok=True)

    log(_t(tr, "kurotools_downloading"))
    download_url_to_file(KUROTOOLS_ZIP_URL, temp_zip, MAX_KUROTOOLS_DOWNLOAD_BYTES, log, tr)
    try:
        with zipfile.ZipFile(temp_zip) as archive:
            for info in archive.infolist():
                safe_destination(temp_extract, info.filename, tr)
            archive.extractall(temp_extract)
        extracted_candidates = [path for path in temp_extract.iterdir() if path.is_dir()]
        if not extracted_candidates:
            raise ManagerError(_t(tr, "kurotools_archive_missing_dir"))
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(extracted_candidates[0]), target)
    finally:
        temp_zip.unlink(missing_ok=True)
        shutil.rmtree(temp_extract, ignore_errors=True)

    if not _is_kurotools_ready(target):
        raise ManagerError(_t(tr, "kurotools_incomplete"))
    return target


def parse_tbl(kurotools: Path, table_path: Path) -> dict:
    output_json = kurotools / f"{table_path.stem}.json"
    output_json.unlink(missing_ok=True)
    result = subprocess.run(
        _python_script_command(kurotools / "tbl2json.py", "-g", "Sora1", str(table_path)),
        cwd=kurotools,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not output_json.exists():
        details = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        raise ManagerError(details)
    try:
        with output_json.open("r", encoding="utf-8") as file:
            return json.load(file)
    finally:
        output_json.unlink(missing_ok=True)


def pack_tbl(kurotools: Path, table_json: dict, table_name: str, output_table: Path) -> None:
    stem = Path(table_name).stem
    input_json = kurotools / f"{stem}.json"
    packed_table = kurotools / f"{stem}.tbl"
    input_json.unlink(missing_ok=True)
    packed_table.unlink(missing_ok=True)
    try:
        with input_json.open("w", encoding="utf-8") as file:
            json.dump(table_json, file, ensure_ascii=False, indent="\t")
        result = subprocess.run(
            _python_script_command(kurotools / "json2tbl.py", str(input_json)),
            cwd=kurotools,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0 or not packed_table.exists():
            details = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
            raise ManagerError(details)
        output_table.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(packed_table), output_table)
    finally:
        input_json.unlink(missing_ok=True)
        packed_table.unlink(missing_ok=True)


def _python_script_command(script: Path, *args: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--looseleaf-run-python", str(script), *args]
    return [sys.executable, str(script), *args]


def read_official_table(game_root: Path, table_dir: str, table_name: str) -> bytes | None:
    member_name = f"{table_dir}/{table_name}"
    pac_path = game_root / "pac" / "steam" / f"{table_dir}.pac"
    if pac_path.exists():
        data = read_fpac_member(pac_path, member_name)
        if data is not None:
            return data

    loose = game_root / table_dir / table_name
    if loose.exists():
        return loose.read_bytes()
    return None


def read_cached_official_table(
    game_root: Path,
    table_cache_dir: Path,
    table_dir: str,
    table_name: str,
    log: Callable[[str], None] | None = None,
    tr: Callable[..., str] | None = None,
) -> bytes | None:
    cache_file = table_cache_dir / table_dir / table_name
    if cache_file.exists():
        return cache_file.read_bytes()
    data = read_official_table(game_root, table_dir, table_name)
    if data is None:
        return None
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(data)
    if log:
        log(_t(tr, "table_cached_original", dir=table_dir, table=table_name))
    return data


def read_fpac_member(pac_path: Path, member_name: str) -> bytes | None:
    wanted = member_name.replace("\\", "/").casefold()
    with pac_path.open("rb") as file:
        if file.read(4) != b"FPAC":
            return None
        count, _header_size, _unknown = struct.unpack("<3I", file.read(12))
        entries = []
        for _index in range(count):
            file_hash, name_offset, size, location = struct.unpack("<4Q", file.read(32))
            entries.append((file_hash, name_offset, size, location))
        for _file_hash, name_offset, size, location in entries:
            name = _read_null_terminated_string(file, name_offset).replace("\\", "/")
            if name.casefold() != wanted:
                continue
            file.seek(location)
            return file.read(size)
    return None


def safe_destination(
    root: Path,
    name: str,
    tr: Callable[..., str] | None = None,
) -> Path:
    destination = (root / Path(*PurePosixPath(name).parts)).resolve()
    root_resolved = root.resolve()
    if destination != root_resolved and root_resolved not in destination.parents:
        raise ManagerError(_t(tr, "unsafe_archive_entry", path=name))
    return destination


def _read_null_terminated_string(file, offset: int) -> str:
    current = file.tell()
    file.seek(offset)
    data = bytearray()
    while True:
        char = file.read(1)
        if not char or char == b"\0":
            break
        data.extend(char)
    file.seek(current)
    return data.decode("utf-8", errors="replace")


def _is_kurotools_ready(path: Path) -> bool:
    return (
        (path / "tbl2json.py").exists()
        and (path / "json2tbl.py").exists()
        and (path / "schemas").is_dir()
        and (path / "schemas" / "headers").is_dir()
    )


def _source_table_dir(file_path: Path, root: Path) -> str | None:
    relative = file_path.resolve().relative_to(root.resolve())
    for part in relative.parts[:-1]:
        if is_table_dir_name(part):
            return part.casefold()
    return None


def _key_fields(section_name: str, row: dict) -> tuple[str, ...] | None:
    configured = PRIMARY_KEYS.get(section_name)
    if configured and _has_fields(row, configured):
        return configured
    for candidate in FALLBACK_KEY_CANDIDATES:
        if _has_fields(row, candidate):
            return candidate
    return None


def _has_fields(row: dict, fields: tuple[str, ...]) -> bool:
    return all(field in row for field in fields)


def _row_key(row: dict, fields: tuple[str, ...]) -> tuple:
    return tuple(_freeze(row[field]) for field in fields)


def _format_change_detail(changes: TableMergeChanges) -> str:
    added = ", ".join(f"{section}+{count}" for section, count in sorted(changes.added_by_section.items()))
    replaced = ", ".join(
        f"{section}~{count}" for section, count in sorted(changes.replaced_by_section.items())
    )
    return "; ".join(part for part in (added, replaced) if part) or "no changes"


def _write_extra_costume_catalog(output_path: Path, catalog: dict[str, dict[str, object]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = {
        key: catalog[key]
        for key in sorted(catalog)
    }
    temp_file = output_path.with_suffix(".json.tmp")
    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(normalized, file, ensure_ascii=False, indent=2)
    temp_file.replace(output_path)


def _item_names_for_source(
    kurotools: Path,
    source_info: dict | None,
    cache: dict[str, dict[int, str]],
    log: Callable[[str], None],
    tr: Callable[..., str] | None = None,
) -> dict[int, str]:
    if not source_info:
        return {}
    source_path = Path(str(source_info.get("source", "")))
    cache_key = str(source_path)
    if cache_key in cache:
        return cache[cache_key]
    if not source_path.exists():
        cache[cache_key] = {}
        return cache[cache_key]
    try:
        table_json = parse_tbl(kurotools, source_path)
    except Exception as exc:
        mod_name = source_info.get("mod_name") or source_path.name
        log(_t(tr, "item_names_parse_failed", mod=mod_name, error=exc))
        cache[cache_key] = {}
        return cache[cache_key]
    cache[cache_key] = _item_names_by_id(table_json)
    return cache[cache_key]


def _item_names_by_id(table_json: dict) -> dict[int, str]:
    names: dict[int, str] = {}
    for section in table_json.get("data", []):
        if section.get("name") != "ItemTableData":
            continue
        for row in section.get("data") or []:
            item_id = _int_or_none(row.get("id"))
            name = str(row.get("name") or "").strip()
            if item_id is not None and name:
                names[item_id] = name
    return names


def _iter_extra_costume_rows(table_json: dict, base_state: MergeState) -> Iterable[tuple[str, int]]:
    for section in table_json.get("data", []):
        section_name = section.get("name")
        if section_name not in {"CostumeParam", "CostumeTable"}:
            continue
        rows = section.get("data") or []
        if not rows:
            continue
        key_fields = base_state.key_fields.get(section_name) or _key_fields(section_name, rows[0])
        protected = base_state.protected_keys.get(section_name, set())
        for row in rows:
            if key_fields and _has_fields(row, key_fields) and _row_key(row, key_fields) in protected:
                continue
            model = _costume_model_from_row(row)
            item_id = _int_or_none(row.get("item_id"))
            if model and item_id is not None:
                yield model, item_id


def _costume_model_from_row(row: dict) -> str | None:
    for field in ("name", "costume_model", "base_model"):
        value = str(row.get(field) or "").strip()
        if re.fullmatch(r"chr\d+(?:_c[0-9a-z]+)?", value.casefold()):
            return value
    return None


def _base_model_from_costume_model(model: str) -> str | None:
    match = re.match(r"(chr\d+)", model.casefold())
    return match.group(1) if match else None


def _catalog_language_field(source_table_dir: str) -> str:
    normalized = source_table_dir.casefold()
    if normalized in {"table_sc", "table_tc"}:
        return "cn"
    return "en"


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _freeze(value):
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, dict):
        return tuple(sorted((key, _freeze(item)) for key, item in value.items()))
    return value
