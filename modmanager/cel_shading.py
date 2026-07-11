from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable

from .constants import MODEL_TARGET
from .errors import ManagerError
from .i18n import DEFAULT_LANGUAGE, translate
from .pac import PacEntry, read_pac_entries, read_pac_member
from .pathutils import normalize_key, posix_path

COPY_FIELDS = [
    "shader_name",
    "str3",
    "shader_switches_hash_referenceonly",
    "shaders",
    "material_switches",
    "uv_map_indices",
    "unknown1",
    "unknown2",
]
BODY_TEMPLATE_NAMES = {"body_skin", "body_skin_slender"}
FACE_TEMPLATE_NAMES = {"face", "face_02"}
PRESERVE_MATERIAL_NAMES = {"shadow"}
PRESERVE_MATERIAL_TOKENS = ("eye", "mouth", "lip", "tooth", "teeth")
MODEL_PAC_NAME = "asset_common_model.pac"
KURO_MDL_TOOL_FILES = (
    "kuro_mdl_export_meshes.py",
    "kuro_mdl_import_meshes.py",
    "lib_fmtibvb.py",
)
KURO_MDL_PYTHON_DEPS = ("blowfish", "numpy", "xxhash", "zstandard")


@dataclass(frozen=True)
class CelShadingPatchResult:
    generated_files: list[str]
    changed_material_count: int
    changed_names: dict[str, int]
    skipped: list[tuple[str, str]]


def _t(tr: Callable[..., str] | None, key: str, **kwargs: object) -> str:
    if tr is not None:
        return tr(key, **kwargs)
    return translate(DEFAULT_LANGUAGE, key, **kwargs)


def _is_within(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _safe_rmtree(path: Path, base: Path) -> None:
    if not path.exists():
        return
    if not _is_within(path, base):
        raise ManagerError(f"Refusing to remove outside base: {path}")
    shutil.rmtree(path)


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _material_name(material: dict) -> str:
    return str(material.get("material_name", ""))


def _shader_name(material: dict) -> str:
    return str(material.get("shader_name", ""))


def _can_use_body_fallback(material: dict) -> bool:
    name = _material_name(material).casefold()
    if any(token in name for token in PRESERVE_MATERIAL_TOKENS):
        return False
    return _shader_name(material).casefold() == "chr_skin"


def _should_preserve_material(material: dict) -> bool:
    name = _material_name(material).casefold()
    return name in PRESERVE_MATERIAL_NAMES or any(
        token in name for token in PRESERVE_MATERIAL_TOKENS
    )


def _texture_slot(texture: dict) -> object:
    return texture.get("texture_slot")


def _texture_name(texture: dict) -> str:
    return str(texture.get("texture_image_name", ""))


def _is_toon_texture(texture: dict) -> bool:
    return _texture_slot(texture) == 9 or "toon" in _texture_name(texture).casefold()


def _template_by_name(materials: list[dict]) -> dict[str, dict]:
    return {_material_name(material).casefold(): material for material in materials}


def _body_template_materials(materials: list[dict]) -> list[dict]:
    return [
        material
        for material in materials
        if _material_name(material).casefold() in BODY_TEMPLATE_NAMES
    ]


def _choose_template_material(target: dict, templates: list[dict]) -> dict | None:
    target_name = _material_name(target).casefold()
    exact = _template_by_name(templates).get(target_name)
    if exact is not None:
        return exact

    if not _can_use_body_fallback(target):
        return None

    skins = _body_template_materials(templates)
    preferred_names = (
        ("body_skin_slender", "body_skin")
        if "slender" in target_name
        else ("body_skin", "body_skin_slender")
    )
    for preferred in preferred_names:
        for material in skins:
            if _material_name(material).casefold() == preferred:
                return material
    return skins[0] if skins else None


def _slot_sort_key(texture: dict) -> tuple[int, str]:
    slot = _texture_slot(texture)
    try:
        slot_value = int(slot)
    except (TypeError, ValueError):
        slot_value = 999
    return slot_value, _texture_name(texture)


def _copy_render_fields(target: dict, template: dict) -> None:
    for field in COPY_FIELDS:
        if field in template:
            target[field] = copy.deepcopy(template[field])
        elif field in target:
            del target[field]


def _apply_skin_template(target: dict, template: dict) -> bool:
    before = copy.deepcopy(target)
    _copy_render_fields(target, template)

    target_textures = copy.deepcopy(target.get("textures", []))
    template_textures = template.get("textures", [])
    template_slots = {_texture_slot(texture) for texture in template_textures}
    template_toon = [copy.deepcopy(texture) for texture in template_textures if _is_toon_texture(texture)]
    toon_slots = {_texture_slot(texture) for texture in template_toon}

    new_textures = []
    for texture in target_textures:
        slot = _texture_slot(texture)
        if slot == 3 and slot not in template_slots:
            continue
        if slot in toon_slots or _is_toon_texture(texture):
            continue
        new_textures.append(texture)
    new_textures.extend(template_toon)
    new_textures.sort(key=_slot_sort_key)
    target["textures"] = new_textures
    return target != before


def _apply_face_template(target: dict, template: dict) -> bool:
    template_textures = template.get("textures")
    if not isinstance(template_textures, list):
        return False

    before = copy.deepcopy(target)
    _copy_render_fields(target, template)
    target["textures"] = copy.deepcopy(template_textures)
    return target != before


def _apply_material_templates(
    target_materials: list[dict],
    template_materials: list[dict],
) -> list[str]:
    changed: list[str] = []
    templates_by_name = _template_by_name(template_materials)

    for material in target_materials:
        name = _material_name(material)
        lowered_name = name.casefold()
        if _should_preserve_material(material):
            continue

        if lowered_name in FACE_TEMPLATE_NAMES:
            template = templates_by_name.get(lowered_name)
            if template is not None and _apply_face_template(material, template):
                changed.append(name)
            continue

        template = _choose_template_material(material, template_materials)
        if template is not None and _apply_skin_template(material, template):
            changed.append(name)

    return changed


def _candidate_template_names(rel_path: str) -> list[str]:
    base = Path(rel_path).name.casefold()
    stem = Path(base).stem
    result = [base]
    match = re.match(r"^(chr\d{4})", stem)
    if match:
        char = match.group(1)
        for candidate in (f"{char}_c01.mdl", f"{char}_c00.mdl", f"{char}.mdl"):
            if candidate not in result:
                result.append(candidate)
    return result


def _read_materials(folder: Path) -> list[dict] | None:
    path = folder / "material_info.json"
    if not path.exists():
        return None
    data = _load_json(path)
    return data if isinstance(data, list) else None


def _check_kuro_mdl_tool(tool_dir: Path, tr: Callable[..., str] | None) -> None:
    if not tool_dir.exists():
        raise ManagerError(_t(tr, "cel_shading_tool_missing", path=tool_dir))
    missing_files = [name for name in KURO_MDL_TOOL_FILES if not (tool_dir / name).exists()]
    if missing_files:
        raise ManagerError(_t(tr, "cel_shading_tool_incomplete", files=", ".join(missing_files)))
    missing_deps = [
        name for name in KURO_MDL_PYTHON_DEPS if importlib.util.find_spec(name) is None
    ]
    if missing_deps:
        raise ManagerError(_t(tr, "cel_shading_deps_missing", deps=", ".join(missing_deps)))


def _load_mdl_tools(tool_dir: Path, tr: Callable[..., str] | None):
    _check_kuro_mdl_tool(tool_dir, tr)
    old_path = sys.path[:]
    sys.path.insert(0, str(tool_dir))
    try:
        import kuro_mdl_export_meshes as mdl_export
        import kuro_mdl_import_meshes as mdl_import
    except ModuleNotFoundError as exc:
        raise ManagerError(_t(tr, "cel_shading_deps_missing", deps=exc.name or str(exc))) from exc
    finally:
        sys.path[:] = old_path
    return mdl_export, mdl_import


def _export_model(mdl_export: object, mdl_path: Path) -> bool:
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return mdl_export.process_mdl(str(mdl_path), overwrite=True) is not False
    except SystemExit:
        return False


def _import_model(mdl_import: object, mdl_path: Path) -> bool:
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return mdl_import.process_mdl(str(mdl_path)) is not False
    except SystemExit:
        return False


def _official_entries_by_basename(pac_path: Path) -> dict[str, PacEntry]:
    by_base: dict[str, PacEntry] = {}
    for entry in read_pac_entries(pac_path):
        base = Path(entry.name).name.casefold()
        entry_key = posix_path(entry.name).casefold()
        if base not in by_base or entry_key.startswith(f"{MODEL_TARGET.as_posix()}/"):
            by_base[base] = entry
    return by_base


def _target_mdl_files(target_files: list[str]) -> list[str]:
    prefix = f"{MODEL_TARGET.as_posix()}/"
    return [
        rel
        for rel in target_files
        if normalize_key(rel).startswith(prefix) and rel.casefold().endswith(".mdl")
    ]


def _template_entry_for(
    rel: str,
    entries_by_base: dict[str, PacEntry],
) -> tuple[str, PacEntry] | None:
    for name in _candidate_template_names(rel):
        entry = entries_by_base.get(name)
        if entry is not None:
            return name, entry
    return None


def generate_cel_shading_patch_files(
    *,
    target_files: list[str],
    target_files_dir: Path,
    patch_dir: Path,
    game_root: Path,
    tools_dir: Path,
    log: Callable[[str], None] | None = None,
    tr: Callable[..., str] | None = None,
    keep_work: bool = False,
) -> CelShadingPatchResult:
    logger = log or (lambda _message: None)
    tool_dir = tools_dir / "kuro_mdl_tool"
    pac_path = game_root / "pac" / "steam" / MODEL_PAC_NAME
    work_root = tools_dir / "mdl_celshade_material_work"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    work_dir = work_root / stamp
    tmp_output = patch_dir / f"files_material_tmp_{stamp}"

    mdl_rels = _target_mdl_files(target_files)
    if not mdl_rels:
        raise ManagerError(_t(tr, "cel_shading_no_model_files"))
    if not pac_path.exists():
        raise ManagerError(_t(tr, "cel_shading_pac_missing", path=pac_path))

    mdl_export, mdl_import = _load_mdl_tools(tool_dir, tr)
    logger(_t(tr, "cel_shading_target_mdl_count", count=len(mdl_rels)))

    entries_by_base = _official_entries_by_basename(pac_path)
    patch_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=False)
    tmp_output.mkdir(parents=True, exist_ok=False)

    generated: list[str] = []
    skipped: list[tuple[str, str]] = []
    changed_material_count = 0
    changed_names: dict[str, int] = {}

    try:
        template_materials_by_key: dict[str, list[dict] | None] = {}
        for index, rel in enumerate(mdl_rels, 1):
            if index == 1 or index % 10 == 0 or index == len(mdl_rels):
                logger(
                    _t(
                        tr,
                        "cel_shading_progress",
                        index=index,
                        total=len(mdl_rels),
                        target=rel,
                    )
                )

            source_mdl = target_files_dir / Path(*PurePosixPath(rel).parts)
            if not source_mdl.exists():
                skipped.append((rel, _t(tr, "cel_shading_skip_target_missing")))
                continue

            template_match = _template_entry_for(rel, entries_by_base)
            if template_match is None:
                skipped.append((rel, _t(tr, "cel_shading_skip_no_template")))
                continue
            template_key, entry = template_match

            if template_key not in template_materials_by_key:
                template_mdl = work_dir / "official" / template_key
                template_mdl.parent.mkdir(parents=True, exist_ok=True)
                template_mdl.write_bytes(read_pac_member(pac_path, entry))
                if _export_model(mdl_export, template_mdl):
                    template_materials_by_key[template_key] = _read_materials(
                        template_mdl.with_suffix("")
                    )
                else:
                    template_materials_by_key[template_key] = None

            template_materials = template_materials_by_key[template_key]
            if not template_materials:
                skipped.append((rel, _t(tr, "cel_shading_skip_template_no_material")))
                continue

            target_mdl = work_dir / "target" / Path(*PurePosixPath(rel).parts)
            target_mdl.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_mdl, target_mdl)
            if not _export_model(mdl_export, target_mdl):
                skipped.append((rel, _t(tr, "cel_shading_skip_target_no_material")))
                continue

            target_materials = _read_materials(target_mdl.with_suffix(""))
            if not target_materials:
                skipped.append((rel, _t(tr, "cel_shading_skip_missing_material_json")))
                continue

            changed_in_file = _apply_material_templates(target_materials, template_materials)
            if not changed_in_file:
                skipped.append((rel, _t(tr, "cel_shading_skip_no_changes")))
                continue

            _save_json(target_mdl.with_suffix("") / "material_info.json", target_materials)
            if not _import_model(mdl_import, target_mdl):
                skipped.append((rel, _t(tr, "cel_shading_skip_import_failed")))
                continue

            out_path = tmp_output / Path(*PurePosixPath(rel).parts)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target_mdl, out_path)
            generated.append(rel)
            changed_material_count += len(changed_in_file)
            for name in changed_in_file:
                changed_names[name] = changed_names.get(name, 0) + 1

        if not generated:
            raise ManagerError(_t(tr, "cel_shading_no_generated"))

        old_files = patch_dir / "files"
        backup_files = patch_dir / f"files_backup_{stamp}"
        if old_files.exists():
            if not _is_within(old_files, patch_dir):
                raise ManagerError(f"Refusing to move unexpected files dir: {old_files}")
            old_files.rename(backup_files)
        tmp_output.rename(old_files)
    except Exception:
        if tmp_output.exists():
            _safe_rmtree(tmp_output, patch_dir)
        raise
    finally:
        if not keep_work and work_dir.exists():
            _safe_rmtree(work_dir, work_root)

    logger(
        _t(
            tr,
            "cel_shading_result_summary",
            files=len(generated),
            materials=changed_material_count,
            skipped=len(skipped),
        )
    )
    for name, count in sorted(changed_names.items(), key=lambda item: item[0].casefold()):
        logger(_t(tr, "cel_shading_changed_material", name=name, count=count))
    for rel, reason in skipped[:20]:
        logger(_t(tr, "cel_shading_skipped", target=rel, reason=reason))
    if len(skipped) > 20:
        logger(_t(tr, "cel_shading_skipped_more", count=len(skipped) - 20))

    return CelShadingPatchResult(
        generated_files=generated,
        changed_material_count=changed_material_count,
        changed_names=changed_names,
        skipped=skipped,
    )
