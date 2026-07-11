"""Editing workspace: pending documents, groups, and the shared tweaks mod.

All edits made in MI Studio are stored as full re-encoded .mi files inside a
single mod (`mi-studio-tweaks`) registered in the manager's state.json and
kept at the very bottom of the load order, so it wins every conflict.
"""
from __future__ import annotations

import copy
import json
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from modmanager.model_info import JsonValue, decode_model_info_json
from modmanager.pathutils import normalize_key, now_label, posix_path

from .binjson import encode_model_info_json
from .fields import mirror_name

TWEAKS_MOD_ID = "mi-studio-tweaks"
TWEAKS_MOD_NAME = "MI Studio 参数调整"


# A semantic path addresses a value inside a model info document in a way
# that transfers across files: dict hops go by key, list hops by entry label
# (falling back to index). Steps: ("key", name) | ("item", label, index).
SemanticStep = tuple
SemanticPath = tuple[SemanticStep, ...]

DEFAULT_FAVORITES: list[SemanticPath] = [
    (("key", "DynamicBone"), ("item", "LeftBreast", 0), ("key", "Joint"), ("item", "LeftBreast", 0)),
    (("key", "DynamicBone"), ("item", "LeftBreast", 0), ("key", "Joint"), ("item", "LeftBreast_Top", 1)),
]

_LABEL_KEYS = ("name", "node", "joint", "root", "target", "top", "middle")


def item_label(value: JsonValue) -> str | None:
    if isinstance(value, dict):
        for key in _LABEL_KEYS:
            label = value.get(key)
            if isinstance(label, str) and label:
                return label
        # DynamicBone chains: label by the first joint's node.
        joints = value.get("Joint")
        if isinstance(joints, list) and joints and isinstance(joints[0], dict):
            label = joints[0].get("node")
            if isinstance(label, str) and label:
                return label
    return None


def resolve_path(doc: JsonValue, path: SemanticPath) -> tuple[Any, Any] | None:
    """Return (container, key_or_index) for the final step, or None."""
    current: Any = doc
    for index, step in enumerate(path):
        last = index == len(path) - 1
        if step[0] == "key":
            if not isinstance(current, dict) or step[1] not in current:
                return None
            if last:
                return current, step[1]
            current = current[step[1]]
        else:
            _kind, label, fallback_index = step
            if not isinstance(current, list):
                return None
            position = _find_item(current, label, fallback_index)
            if position is None:
                return None
            if last:
                return current, position
            current = current[position]
    return None


def _find_item(items: list, label: str | None, fallback_index: int) -> int | None:
    if label:
        for position, item in enumerate(items):
            if item_label(item) == label:
                return position
    if label is None and 0 <= fallback_index < len(items):
        return fallback_index
    return None


def get_value(doc: JsonValue, path: SemanticPath) -> Any:
    resolved = resolve_path(doc, path)
    if resolved is None:
        return None
    container, key = resolved
    try:
        return container[key]
    except (KeyError, IndexError, TypeError):
        return None


def set_value(doc: JsonValue, path: SemanticPath, value: Any) -> bool:
    resolved = resolve_path(doc, path)
    if resolved is None:
        return False
    container, key = resolved
    container[key] = value
    return True


def mirrored_path(path: SemanticPath) -> SemanticPath | None:
    """Mirror every L/R-labelled item step; None when nothing is symmetric."""
    mirrored: list[SemanticStep] = []
    changed = False
    for step in path:
        if step[0] == "item" and step[1]:
            other = mirror_name(step[1])
            if other and other != step[1]:
                mirrored.append(("item", other, step[2]))
                changed = True
                continue
        mirrored.append(step)
    return tuple(mirrored) if changed else None


@dataclass
class EditResult:
    applied: int
    mirrored: int
    skipped: list[str]


@dataclass
class ImportResult:
    applied: int
    skipped: list[str]
    changed_targets: list[str]
    matched_fields: int = 0
    changed_fields: int = 0


def _primitive_kind(value: JsonValue) -> str | None:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    return None


def merge_matching_leaf_values(target: JsonValue, source: JsonValue) -> tuple[JsonValue, int, int]:
    """Merge compatible source leaves into the target's existing structure.

    Dictionaries are intersected by key and lists by index. No containers,
    keys, or list items are added or replaced. The counters are
    ``(matched_leaves, changed_leaves)``.
    """
    if isinstance(target, dict) and isinstance(source, dict):
        matched = 0
        changed = 0
        for key in target.keys() & source.keys():
            merged, child_matched, child_changed = merge_matching_leaf_values(target[key], source[key])
            if child_matched:
                target[key] = merged
                matched += child_matched
                changed += child_changed
        return target, matched, changed

    if isinstance(target, list) and isinstance(source, list):
        matched = 0
        changed = 0
        for index in range(min(len(target), len(source))):
            merged, child_matched, child_changed = merge_matching_leaf_values(target[index], source[index])
            if child_matched:
                target[index] = merged
                matched += child_matched
                changed += child_changed
        return target, matched, changed

    target_kind = _primitive_kind(target)
    source_kind = _primitive_kind(source)
    if target_kind is not None and target_kind == source_kind:
        return copy.deepcopy(source), 1, int(target != source)
    return target, 0, 0


class MiWorkspace:
    """Pending edited documents plus persistence into the shared tweaks mod."""

    def __init__(self, core) -> None:
        self.core = core
        self.docs: dict[str, JsonValue] = {}  # normalized target -> edited doc
        self.targets: dict[str, str] = {}  # normalized target -> display target
        self.groups: dict[str, list[str]] = {}
        self.favorites: list[SemanticPath] = []  # pinned paths, shared by all files
        self.references: dict[str, dict[str, str]] = {}  # normalized target -> {"mod_id": str, "target": str}
        self._studio_file = core.game_data_dir / "mi_studio.json"
        self._load_studio_file()
        self._load_existing_tweaks()

    # -- persistence -----------------------------------------------------

    def _load_studio_file(self) -> None:
        try:
            raw = json.loads(self._studio_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        groups = raw.get("groups", {})
        self.groups = {
            str(name): [posix_path(t) for t in targets]
            for name, targets in groups.items()
            if isinstance(targets, list)
        }
        self.favorites = []
        raw_favorites = raw.get("favorites", DEFAULT_FAVORITES)
        for item in raw_favorites:
            if isinstance(item, list) and all(isinstance(step, list) for step in item):
                self.favorites.append(tuple(tuple(step) for step in item))
            elif isinstance(item, tuple) and all(isinstance(step, tuple) for step in item):
                self.favorites.append(item)
        raw_refs = raw.get("references", {})
        if isinstance(raw_refs, dict):
            self.references = {
                normalize_key(target): {"mod_id": str(value.get("mod_id") or ""), "target": posix_path(value.get("target") or "")}
                for target, value in raw_refs.items()
                if isinstance(value, dict)
            }

    def save_studio_file(self) -> None:
        payload = {
            "groups": self.groups,
            "favorites": [[list(step) for step in path] for path in self.favorites],
            "references": self.references,
        }
        temp = self._studio_file.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self._studio_file)

    # -- favorites ----------------------------------------------------------

    def is_favorite(self, path: SemanticPath) -> bool:
        return path in self.favorites

    def toggle_favorite(self, path: SemanticPath) -> bool:
        """Add or remove a pinned path; returns True when now favorited."""
        if path in self.favorites:
            self.favorites.remove(path)
            added = False
        else:
            self.favorites.append(path)
            added = True
        self.save_studio_file()
        return added

    # -- reference preferences -------------------------------------------------

    def reference_for(self, target: str) -> dict[str, str] | None:
        return self.references.get(normalize_key(target))

    def set_reference(self, target: str, mod_id: str | None, ref_target: str | None) -> None:
        key = normalize_key(target)
        if mod_id and ref_target:
            self.references[key] = {"mod_id": mod_id, "target": posix_path(ref_target)}
        else:
            self.references[key] = {"mod_id": "", "target": ""}
        self.save_studio_file()

    def tweaks_files_root(self) -> Path:
        return self.core.mods_dir / TWEAKS_MOD_ID / "files"

    def _load_existing_tweaks(self) -> None:
        root = self.tweaks_files_root() / "asset" / "common" / "model_info"
        if not root.is_dir():
            return
        for path in sorted(root.glob("*.mi")):
            target = f"asset/common/model_info/{path.name}"
            try:
                doc = decode_model_info_json(path.read_bytes())
            except Exception:
                continue
            key = normalize_key(target)
            self.docs[key] = doc
            self.targets[key] = target

    # -- pending documents -------------------------------------------------

    def has_doc(self, target: str) -> bool:
        return normalize_key(target) in self.docs

    def get_doc(self, target: str) -> JsonValue | None:
        return self.docs.get(normalize_key(target))

    def open_doc(self, target: str, baseline_doc: JsonValue) -> JsonValue:
        key = normalize_key(target)
        if key not in self.docs:
            self.docs[key] = copy.deepcopy(baseline_doc)
            self.targets[key] = posix_path(target)
        return self.docs[key]

    def drop_doc(self, target: str) -> None:
        key = normalize_key(target)
        self.docs.pop(key, None)
        self.targets.pop(key, None)

    def is_modified(self, target: str, baseline_doc: JsonValue | None) -> bool:
        doc = self.get_doc(target)
        if doc is None:
            return False
        return doc != baseline_doc

    # -- editing -------------------------------------------------------------

    def apply_edit(
        self,
        targets_with_baselines: list[tuple[str, JsonValue]],
        path: SemanticPath,
        value: Any,
        symmetric: bool,
    ) -> EditResult:
        applied = 0
        mirrored_count = 0
        skipped: list[str] = []
        mirror = mirrored_path(path) if symmetric else None
        for target, baseline_doc in targets_with_baselines:
            doc = self.open_doc(target, baseline_doc)
            if set_value(doc, path, copy.deepcopy(value)):
                applied += 1
            else:
                skipped.append(target)
                continue
            if mirror is not None and set_value(doc, mirror, copy.deepcopy(value)):
                mirrored_count += 1
        return EditResult(applied=applied, mirrored=mirrored_count, skipped=skipped)

    def import_sections(
        self,
        source_doc: JsonValue,
        sections: list[str],
        targets_with_baselines: list[tuple[str, JsonValue]],
    ) -> ImportResult:
        applied = 0
        skipped: list[str] = []
        changed_targets: list[str] = []
        matched_fields = 0
        changed_fields = 0
        if not isinstance(source_doc, dict):
            return ImportResult(0, [], [])
        for target, baseline_doc in targets_with_baselines:
            key = normalize_key(target)
            current_doc = self.docs.get(key, baseline_doc)
            if not isinstance(current_doc, dict):
                skipped.append(target)
                continue
            doc = copy.deepcopy(current_doc)
            target_matched = 0
            target_changed = 0
            for section in sections:
                if section not in source_doc or section not in doc:
                    continue
                merged, section_matched, section_changed = merge_matching_leaf_values(
                    doc[section], source_doc[section]
                )
                if section_matched:
                    doc[section] = merged
                    target_matched += section_matched
                    target_changed += section_changed
            matched_fields += target_matched
            changed_fields += target_changed
            if not target_changed:
                skipped.append(target)
                continue
            self.docs[key] = doc
            self.targets[key] = posix_path(target)
            applied += 1
            changed_targets.append(posix_path(target))
        return ImportResult(
            applied=applied,
            skipped=skipped,
            changed_targets=changed_targets,
            matched_fields=matched_fields,
            changed_fields=changed_fields,
        )

    # -- saving into the shared mod ---------------------------------------------

    def modified_targets(self, baseline_of: Callable[[str], JsonValue | None]) -> list[str]:
        result = []
        for key, doc in self.docs.items():
            target = self.targets.get(key, key)
            if doc != baseline_of(target):
                result.append(target)
        return sorted(result, key=normalize_key)

    def save_tweaks_mod(self, baseline_of: Callable[[str], JsonValue | None]) -> tuple[int, int]:
        """Write modified docs into the tweaks mod and register it in state.json.

        Returns (written_files, removed_files). Documents identical to their
        baseline are treated as "no tweak" and removed from the mod.
        """
        keep_targets = self.modified_targets(baseline_of)
        files_root = self.tweaks_files_root()
        mi_root = files_root / "asset" / "common" / "model_info"

        keep_names = set()
        written = 0
        for target in keep_targets:
            doc = self.get_doc(target)
            data = encode_model_info_json(doc)
            destination = files_root / Path(*PurePosixPath(target).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            existing = destination.read_bytes() if destination.exists() else None
            if existing != data:
                destination.write_bytes(data)
            written += 1
            keep_names.add(destination.name.casefold())

        removed = 0
        if mi_root.is_dir():
            for path in mi_root.glob("*.mi"):
                if path.name.casefold() not in keep_names:
                    path.unlink()
                    removed += 1

        self._register_mod(keep_targets)
        return written, removed

    def _register_mod(self, targets: list[str]) -> None:
        core = self.core
        core.state = core._load_state()
        mods = core.state["mods"]
        order = core.state["order"]

        if not targets:
            if TWEAKS_MOD_ID in mods:
                mods.pop(TWEAKS_MOD_ID, None)
                core.state["order"] = [mod_id for mod_id in order if mod_id != TWEAKS_MOD_ID]
                mod_dir = core.mods_dir / TWEAKS_MOD_ID
                if mod_dir.exists():
                    shutil.rmtree(mod_dir, ignore_errors=True)
                core.save()
            return

        record = mods.get(TWEAKS_MOD_ID) or {
            "id": TWEAKS_MOD_ID,
            "name": TWEAKS_MOD_NAME,
            "enabled": True,
            "source": "MI Studio",
            "created_at": now_label(),
            "table_sources": [],
            "preview": None,
        }
        record["files"] = [posix_path(t) for t in targets]
        record["updated_at"] = now_label()
        mods[TWEAKS_MOD_ID] = record
        # Keep the tweaks mod at the very bottom so it overrides everything.
        core.state["order"] = [mod_id for mod_id in order if mod_id != TWEAKS_MOD_ID] + [TWEAKS_MOD_ID]
        core.save()

    # -- groups -----------------------------------------------------------------

    def group_names(self) -> list[str]:
        return sorted(self.groups, key=str.casefold)

    def group_of(self, target: str) -> list[str]:
        key = normalize_key(target)
        return [name for name, members in self.groups.items() if key in {normalize_key(m) for m in members}]

    def add_to_group(self, name: str, targets: list[str]) -> None:
        members = self.groups.setdefault(name, [])
        known = {normalize_key(m) for m in members}
        for target in targets:
            if normalize_key(target) not in known:
                members.append(posix_path(target))
                known.add(normalize_key(target))
        self.save_studio_file()

    def remove_from_group(self, name: str, targets: list[str]) -> None:
        members = self.groups.get(name)
        if members is None:
            return
        drop = {normalize_key(t) for t in targets}
        self.groups[name] = [m for m in members if normalize_key(m) not in drop]
        self.save_studio_file()

    def delete_group(self, name: str) -> None:
        self.groups.pop(name, None)
        self.save_studio_file()
