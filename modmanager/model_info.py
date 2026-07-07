from __future__ import annotations

import hashlib
import re
import struct
from dataclasses import dataclass
from typing import Any


JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None

SECTION_NAMES = {
    "Animation",
    "Bounding",
    "Collider",
    "DrivenKeys",
    "Drivers",
    "DynamicBone",
    "DynamicBoneCollider",
    "Extra",
    "Keys",
    "Lights",
    "Locators",
    "LOD",
    "LookIK",
    "NeighborBones",
    "Occluder",
    "SpecificCollider",
    "TwoBoneIK",
}

FIELD_NAMES = {
    "attr",
    "axis_x",
    "axis_y",
    "axis_z",
    "blend",
    "collision_radius",
    "damping",
    "damping_max",
    "damping_min",
    "damping_velocity_ratio",
    "door_type",
    "driven",
    "driven_attr",
    "driven_infl",
    "freeze_axis",
    "gravity",
    "ignore_collision",
    "in_x",
    "in_y",
    "interp",
    "is_disable",
    "is_dynamic_damping",
    "is_enable_stretch",
    "is_valid",
    "joint",
    "length_limit",
    "look_offset_x",
    "look_offset_y",
    "look_offset_z",
    "middle",
    "mid_rot_max",
    "mid_rot_min",
    "name",
    "need_specific",
    "node",
    "offset",
    "offset_rot_x",
    "offset_rot_y",
    "offset_rot_z",
    "offset_x",
    "offset_y",
    "offset_z",
    "off_x",
    "off_y",
    "off_z",
    "omit_middle",
    "out_x",
    "out_y",
    "param0",
    "param1",
    "param2",
    "param3",
    "post",
    "pre",
    "resilience",
    "root",
    "root_rot_max",
    "root_rot_min",
    "rot_order",
    "rot_x",
    "rot_y",
    "rot_z",
    "rotation_limit",
    "rx_limit_max",
    "rx_limit_min",
    "ry_limit_max",
    "ry_limit_min",
    "size",
    "stretch_limit",
    "stretch_resilience",
    "stype",
    "target",
    "time",
    "top",
    "type",
    "up_vec_x",
    "up_vec_y",
    "up_vec_z",
    "value",
    "wind_influence",
    "x",
    "y",
    "z",
}

FIELD_NAMES_CASEFOLD = {name.casefold() for name in FIELD_NAMES}

IMPACT_RULES: dict[str, dict[str, set[str]]] = {
    "physics": {
        "sections": {"DynamicBone", "NeighborBones"},
        "fields": {
            "damping",
            "damping_max",
            "damping_min",
            "damping_velocity_ratio",
            "freeze_axis",
            "gravity",
            "is_disable",
            "is_dynamic_damping",
            "is_enable_stretch",
            "resilience",
            "rotation_limit",
            "stretch_limit",
            "stretch_resilience",
            "wind_influence",
        },
    },
    "collision": {
        "sections": {"Collider", "DynamicBoneCollider", "SpecificCollider"},
        "fields": {
            "collision_radius",
            "ignore_collision",
            "need_specific",
            "offset_rot_x",
            "offset_rot_y",
            "offset_z",
            "offset_rot_z",
            "offset_x",
            "offset_y",
            "param0",
            "param1",
            "param2",
            "param3",
        },
    },
    "ik": {
        "sections": {"LookIK", "TwoBoneIK"},
        "fields": {
            "axis_x",
            "axis_y",
            "axis_z",
            "length_limit",
            "look_offset_x",
            "look_offset_y",
            "look_offset_z",
            "mid_rot_max",
            "mid_rot_min",
            "root_rot_max",
            "root_rot_min",
            "rx_limit_max",
            "rx_limit_min",
            "ry_limit_max",
            "ry_limit_min",
            "up_vec_x",
            "up_vec_y",
            "up_vec_z",
        },
    },
    "locator": {
        "sections": {"Locators"},
        "fields": {"name", "node", "off_x", "off_y", "off_z", "rot_x", "rot_y", "rot_z"},
    },
    "animation": {
        "sections": {"Animation", "DrivenKeys", "Drivers", "Keys"},
        "fields": {"attr", "blend", "driven", "driven_attr", "in_x", "in_y", "interp", "out_x", "out_y", "target", "time", "value"},
    },
    "render_bounds": {
        "sections": {"Bounding", "Lights", "LOD", "Occluder"},
        "fields": {"is_valid", "offset", "size", "stype", "type", "x", "y", "z"},
    },
}

NOTABLE_IDENTIFIER_HINTS = (
    "Breast",
    "Chest",
    "Hair",
    "Kami",
    "Maegami",
    "Skirt",
    "Suso",
    "Cloth",
    "Hips",
    "Spine",
    "Head",
    "Neck",
    "Arm",
    "Hand",
    "Leg",
    "Foot",
    "Point",
    "DLC",
    "Megane",
    "atari",
)

SEMANTIC_CHANGE_LIMIT = 48


class ModelInfoDecodeError(ValueError):
    pass


@dataclass(frozen=True)
class ModelInfoSummary:
    size: int
    sha256: str
    valid_json_binary: bool
    decoded_json: bool
    fields: tuple[str, ...]
    sections: tuple[str, ...]
    identifiers: tuple[str, ...]


@dataclass(frozen=True)
class ModelInfoDiff:
    status: str
    original: ModelInfoSummary | None
    modified: ModelInfoSummary
    changed_bytes: int = 0
    size_delta: int = 0
    changed_regions: tuple[tuple[int, int], ...] = ()
    fields_added: tuple[str, ...] = ()
    fields_removed: tuple[str, ...] = ()
    sections_added: tuple[str, ...] = ()
    sections_removed: tuple[str, ...] = ()
    identifiers_added: tuple[str, ...] = ()
    identifiers_removed: tuple[str, ...] = ()
    impact_keys: tuple[str, ...] = ()
    parameter_only: bool = False
    notable_identifiers_added: tuple[str, ...] = ()
    notable_identifiers_removed: tuple[str, ...] = ()
    notable_identifiers: tuple[str, ...] = ()
    semantic_change_count: int = 0
    changed_sections: tuple[tuple[str, int], ...] = ()
    semantic_changes: tuple[dict[str, object], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "original_size": self.original.size if self.original else None,
            "modified_size": self.modified.size,
            "changed_bytes": self.changed_bytes,
            "size_delta": self.size_delta,
            "changed_regions": [list(region) for region in self.changed_regions],
            "fields_added": list(self.fields_added),
            "fields_removed": list(self.fields_removed),
            "sections_added": list(self.sections_added),
            "sections_removed": list(self.sections_removed),
            "identifiers_added": list(self.identifiers_added),
            "identifiers_removed": list(self.identifiers_removed),
            "impact_keys": list(self.impact_keys),
            "parameter_only": self.parameter_only,
            "notable_identifiers_added": list(self.notable_identifiers_added),
            "notable_identifiers_removed": list(self.notable_identifiers_removed),
            "notable_identifiers": list(self.notable_identifiers),
            "valid_json_binary": self.modified.valid_json_binary,
            "decoded_json": self.modified.decoded_json,
            "semantic_change_count": self.semantic_change_count,
            "changed_sections": dict(self.changed_sections),
            "semantic_changes": [dict(change) for change in self.semantic_changes],
        }


def decode_model_info_json(data: bytes) -> JsonValue:
    return _BinaryJsonReader(data).read()


def summarize_model_info(data: bytes) -> ModelInfoSummary:
    decoded = _try_decode_model_info(data)
    decoded_strings = set(_json_strings(decoded)) if decoded is not None else set()
    field_table = _field_table_names(data)
    strings = _ascii_strings(data)
    clean_strings = {_clean_string(item) for item in strings | decoded_strings}
    clean_strings.discard("")
    fields = sorted(item for item in (field_table | clean_strings) if item.casefold() in FIELD_NAMES_CASEFOLD)
    sections = sorted((field_table | clean_strings) & SECTION_NAMES)
    identifiers = sorted(
        item
        for item in clean_strings
        if _looks_like_identifier(item)
    )
    return ModelInfoSummary(
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        valid_json_binary=data.startswith(b"JSON"),
        decoded_json=decoded is not None,
        fields=tuple(fields),
        sections=tuple(sections),
        identifiers=tuple(identifiers),
    )


def compare_model_info(original: bytes | None, modified: bytes) -> ModelInfoDiff:
    modified_summary = summarize_model_info(modified)
    modified_json = _try_decode_model_info(modified)
    if original is None:
        return ModelInfoDiff(
            status="missing_original",
            original=None,
            modified=modified_summary,
            impact_keys=_impact_keys(None, modified_summary),
            notable_identifiers=_notable_identifiers(modified_summary.identifiers),
        )

    original_summary = summarize_model_info(original)
    original_json = _try_decode_model_info(original)
    if original == modified:
        return ModelInfoDiff(
            status="identical",
            original=original_summary,
            modified=modified_summary,
            impact_keys=_impact_keys(original_summary, modified_summary),
            notable_identifiers=_notable_identifiers(modified_summary.identifiers),
        )

    fields_added = _added(original_summary.fields, modified_summary.fields)
    fields_removed = _removed(original_summary.fields, modified_summary.fields)
    sections_added = _added(original_summary.sections, modified_summary.sections)
    sections_removed = _removed(original_summary.sections, modified_summary.sections)
    identifiers_added = _added(original_summary.identifiers, modified_summary.identifiers)
    identifiers_removed = _removed(original_summary.identifiers, modified_summary.identifiers)
    semantic_changes = _semantic_changes(original_json, modified_json) if original_json is not None and modified_json is not None else []
    changed_sections = _semantic_section_counts(semantic_changes)
    parameter_only = _semantic_parameter_only(semantic_changes) if semantic_changes else not any(
        (
            fields_added,
            fields_removed,
            sections_added,
            sections_removed,
            identifiers_added,
            identifiers_removed,
        )
    )
    impact_keys = (
        _impact_keys_for_semantic_changes(semantic_changes, modified_summary)
        if semantic_changes
        else _parameter_impact_keys(modified_summary) if parameter_only else _impact_keys(original_summary, modified_summary)
    )

    return ModelInfoDiff(
        status="changed",
        original=original_summary,
        modified=modified_summary,
        changed_bytes=_count_changed_bytes(original, modified),
        size_delta=len(modified) - len(original),
        changed_regions=tuple(_changed_regions(original, modified, limit=12)),
        fields_added=fields_added,
        fields_removed=fields_removed,
        sections_added=sections_added,
        sections_removed=sections_removed,
        identifiers_added=identifiers_added,
        identifiers_removed=identifiers_removed,
        impact_keys=impact_keys,
        parameter_only=parameter_only,
        notable_identifiers_added=_notable_identifiers(identifiers_added),
        notable_identifiers_removed=_notable_identifiers(identifiers_removed),
        notable_identifiers=_notable_identifiers(_semantic_contexts(semantic_changes) or modified_summary.identifiers),
        semantic_change_count=len(semantic_changes),
        changed_sections=tuple(changed_sections.items()),
        semantic_changes=tuple(semantic_changes[:SEMANTIC_CHANGE_LIMIT]),
    )


class _BinaryJsonReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def read(self) -> JsonValue:
        if len(self.data) < 13 or not self.data.startswith(b"JSON"):
            raise ModelInfoDecodeError("not an FDK binary JSON file")
        data_start = self._u32_at(8)
        if data_start >= len(self.data):
            raise ModelInfoDecodeError("invalid JSON data offset")
        self.offset = data_start
        _name, value = self._read_value()
        return value

    def _read_value(self) -> tuple[str, JsonValue]:
        opcode = self._read_u8()
        name = self._read_dictionary_string() if opcode < 0x10 else ""
        kind = opcode & 0x0F
        if kind == 0x01:
            value = None
        elif kind == 0x02:
            value = self._read_string()
        elif kind == 0x03:
            value = self._read_number()
        elif kind == 0x04:
            value = self._read_object()
        elif kind == 0x05:
            value = self._read_array()
        elif kind == 0x06:
            value = self._read_bool()
        else:
            raise ModelInfoDecodeError(f"unknown opcode 0x{opcode:02x} at 0x{self.offset - 1:x}")
        return name, value

    def _read_object(self) -> dict[str, JsonValue]:
        addresses = self._read_address_table()
        end_offset = self.offset
        result: dict[str, JsonValue] = {}
        for address in addresses:
            self._seek(address)
            key, value = self._read_value()
            result[key] = value
            end_offset = max(end_offset, self.offset)
        self._seek(end_offset)
        return result

    def _read_array(self) -> list[JsonValue]:
        addresses = self._read_address_table()
        end_offset = self.offset
        result: list[JsonValue] = []
        for address in addresses:
            self._seek(address)
            _key, value = self._read_value()
            result.append(value)
            end_offset = max(end_offset, self.offset)
        self._seek(end_offset)
        return result

    def _read_address_table(self) -> tuple[int, ...]:
        count = self._read_u32()
        if count > 1_000_000:
            raise ModelInfoDecodeError("unreasonable entry count")
        return tuple(self._read_u32() for _ in range(count))

    def _read_dictionary_string(self) -> str:
        address = self._read_u32()
        if address + 4 > len(self.data):
            raise ModelInfoDecodeError("invalid dictionary string offset")
        return self._string_at(address + 4)

    def _read_string(self) -> str:
        end = self.data.find(b"\0", self.offset)
        if end < 0:
            raise ModelInfoDecodeError("unterminated string")
        raw = self.data[self.offset:end]
        self.offset = end + 1
        return raw.decode("utf-8")

    def _string_at(self, offset: int) -> str:
        end = self.data.find(b"\0", offset)
        if end < 0:
            raise ModelInfoDecodeError("unterminated dictionary string")
        return self.data[offset:end].decode("utf-8")

    def _read_number(self) -> int | float:
        number = self._unpack("<d", 8)
        return int(number) if round(number) == number else number

    def _read_bool(self) -> bool:
        value = self._read_u8()
        if value not in {0, 1}:
            raise ModelInfoDecodeError("invalid boolean value")
        return bool(value)

    def _read_u8(self) -> int:
        return self._unpack("<B", 1)

    def _read_u32(self) -> int:
        return self._unpack("<I", 4)

    def _u32_at(self, offset: int) -> int:
        if offset + 4 > len(self.data):
            raise ModelInfoDecodeError("unexpected end of file")
        return struct.unpack_from("<I", self.data, offset)[0]

    def _unpack(self, fmt: str, size: int) -> Any:
        if self.offset + size > len(self.data):
            raise ModelInfoDecodeError("unexpected end of file")
        value = struct.unpack_from(fmt, self.data, self.offset)[0]
        self.offset += size
        return value

    def _seek(self, offset: int) -> None:
        if offset > len(self.data):
            raise ModelInfoDecodeError("invalid data offset")
        self.offset = offset


def _try_decode_model_info(data: bytes) -> JsonValue | None:
    try:
        return decode_model_info_json(data)
    except (ModelInfoDecodeError, UnicodeDecodeError, struct.error):
        return None


def _field_table_names(data: bytes) -> set[str]:
    if len(data) < 16 or not data.startswith(b"JSON"):
        return set()
    table_size = int.from_bytes(data[8:12], "little", signed=False)
    start = 16
    end = min(len(data), start + table_size)
    names: set[str] = set()
    offset = start
    while offset + 5 <= end:
        offset += 4
        nul = data.find(b"\0", offset, end)
        if nul < 0:
            break
        raw = data[offset:nul]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="ignore")
        text = _clean_string(text)
        if text:
            names.add(text)
        offset = nul + 1
    return names


def _ascii_strings(data: bytes) -> set[str]:
    return {
        match.decode("ascii", errors="ignore")
        for match in re.findall(rb"[ -~]{3,}", data)
    }


def _json_strings(value: JsonValue) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key:
                result.add(key)
            result.update(_json_strings(child))
    elif isinstance(value, list):
        for child in value:
            result.update(_json_strings(child))
    elif isinstance(value, str) and value:
        result.add(value)
    return result


def _clean_string(value: str) -> str:
    value = value.strip("\0 \t\r\n")
    match = re.search(r"[A-Za-z_][A-Za-z0-9_.$-]*$", value)
    return match.group(0) if match else value


def _looks_like_identifier(value: str) -> bool:
    if value in SECTION_NAMES or value.casefold() in FIELD_NAMES_CASEFOLD or value == "JSON":
        return False
    if not 3 <= len(value) <= 80:
        return False
    if value.isdigit() or value.islower():
        return False
    if not re.fullmatch(r"[A-Za-z0-9_.$-]+", value):
        return False
    return True


def _semantic_changes(before: JsonValue, after: JsonValue, path: tuple[object, ...] = ()) -> list[dict[str, object]]:
    changes: list[dict[str, object]] = []
    _collect_semantic_changes(before, after, path, changes)
    return changes


def _collect_semantic_changes(before: JsonValue, after: JsonValue, path: tuple[object, ...], changes: list[dict[str, object]]) -> None:
    if _both_numbers(before, after):
        if before != after:
            changes.append({"path": _format_path(path), "change": "value_changed", "before": before, "after": after})
        return
    if type(before) is not type(after):
        changes.append({"path": _format_path(path), "change": "type_changed", "before": _compact_value(before), "after": _compact_value(after)})
        return
    if isinstance(before, dict) and isinstance(after, dict):
        before_keys = set(before)
        after_keys = set(after)
        for key in sorted(before_keys - after_keys):
            changes.append({"path": _format_path(path + (key,)), "change": "removed", "before": _compact_value(before[key]), "after": None})
        for key in sorted(after_keys - before_keys):
            changes.append({"path": _format_path(path + (key,)), "change": "added", "before": None, "after": _compact_value(after[key])})
        for key in before.keys():
            if key in after:
                _collect_semantic_changes(before[key], after[key], path + (key,), changes)
        return
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            changes.append({"path": _format_path(path), "change": "list_length_changed", "before": len(before), "after": len(after)})
        shared = min(len(before), len(after))
        for index in range(shared):
            label = _value_label(before[index]) or _value_label(after[index])
            start = len(changes)
            _collect_semantic_changes(before[index], after[index], path + (index,), changes)
            if label:
                for change in changes[start:]:
                    change.setdefault("context", label)
        for index in range(shared, len(before)):
            changes.append({"path": _format_path(path + (index,)), "change": "removed", "before": _compact_value(before[index]), "after": None, "context": _value_label(before[index]) or ""})
        for index in range(shared, len(after)):
            changes.append({"path": _format_path(path + (index,)), "change": "added", "before": None, "after": _compact_value(after[index]), "context": _value_label(after[index]) or ""})
        return
    if before != after:
        changes.append({"path": _format_path(path), "change": "value_changed", "before": before, "after": after})


def _both_numbers(before: object, after: object) -> bool:
    return isinstance(before, (int, float)) and not isinstance(before, bool) and isinstance(after, (int, float)) and not isinstance(after, bool)


def _compact_value(value: JsonValue) -> object:
    if isinstance(value, dict):
        return {"type": "object", "size": len(value), "label": _value_label(value) or ""}
    if isinstance(value, list):
        return {"type": "array", "size": len(value)}
    return value


def _value_label(value: JsonValue) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("name", "node", "target", "root", "joint", "top", "middle"):
        label = value.get(key)
        if isinstance(label, str) and label:
            return label
    return None


def _format_path(parts: tuple[object, ...]) -> str:
    result = "$"
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        elif isinstance(part, str) and part.isidentifier():
            result += f".{part}"
        else:
            result += f"[{part!r}]"
    return result


def _semantic_parameter_only(changes: list[dict[str, object]]) -> bool:
    return all(change.get("change") == "value_changed" for change in changes)


def _semantic_section_counts(changes: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for change in changes:
        section = _section_from_path(str(change.get("path") or ""))
        if not section:
            continue
        counts[section] = counts.get(section, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _semantic_contexts(changes: list[dict[str, object]]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for change in changes:
        context = str(change.get("context") or "")
        if context and context not in seen:
            result.append(context)
            seen.add(context)
    return tuple(result)


def _section_from_path(path: str) -> str:
    if not path.startswith("$."):
        return ""
    return path[2:].split(".", 1)[0].split("[", 1)[0]


def _field_from_path(path: str) -> str:
    match = re.search(r"\.([A-Za-z_][A-Za-z0-9_]*)$", path)
    return match.group(1) if match else ""


def _count_changed_bytes(left: bytes, right: bytes) -> int:
    shared = min(len(left), len(right))
    count = sum(1 for index in range(shared) if left[index] != right[index])
    return count + abs(len(left) - len(right))


def _changed_regions(left: bytes, right: bytes, limit: int) -> list[tuple[int, int]]:
    regions: list[tuple[int, int]] = []
    max_len = max(len(left), len(right))
    index = 0
    while index < max_len and len(regions) < limit:
        left_byte = left[index] if index < len(left) else None
        right_byte = right[index] if index < len(right) else None
        if left_byte == right_byte:
            index += 1
            continue
        start = index
        while index < max_len:
            left_byte = left[index] if index < len(left) else None
            right_byte = right[index] if index < len(right) else None
            if left_byte == right_byte:
                break
            index += 1
        regions.append((start, index))
    return regions


def _added(original: tuple[str, ...], modified: tuple[str, ...]) -> tuple[str, ...]:
    original_set = set(original)
    return tuple(item for item in modified if item not in original_set)


def _removed(original: tuple[str, ...], modified: tuple[str, ...]) -> tuple[str, ...]:
    modified_set = set(modified)
    return tuple(item for item in original if item not in modified_set)


def _impact_keys(original: ModelInfoSummary | None, modified: ModelInfoSummary) -> tuple[str, ...]:
    sections = set(modified.sections)
    fields = {field.casefold() for field in modified.fields}
    if original is not None:
        sections.update(original.sections)
        fields.update(field.casefold() for field in original.fields)

    impacts = []
    for key, rule in IMPACT_RULES.items():
        if sections & rule["sections"] or fields & {field.casefold() for field in rule["fields"]}:
            impacts.append(key)
    return tuple(impacts)


def _impact_keys_for_semantic_changes(changes: list[dict[str, object]], fallback: ModelInfoSummary) -> tuple[str, ...]:
    sections = {_section_from_path(str(change.get("path") or "")) for change in changes}
    fields = {_field_from_path(str(change.get("path") or "")).casefold() for change in changes}
    sections.discard("")
    fields.discard("")
    impacts = []
    for key, rule in IMPACT_RULES.items():
        rule_fields = {field.casefold() for field in rule["fields"]}
        if sections & rule["sections"] or fields & rule_fields:
            impacts.append(key)
    return tuple(impacts) or _parameter_impact_keys(fallback)


def _parameter_impact_keys(summary: ModelInfoSummary) -> tuple[str, ...]:
    identifiers = " ".join(summary.identifiers).casefold()
    impacts = []
    if any(hint in identifiers for hint in ("breast", "chest", "hair", "kami", "maegami", "skirt", "suso", "cloth", "hips", "spine")):
        impacts.append("physics")
    if any(hint in identifiers for hint in ("atari", "collider", "breast", "chest", "hips", "spine", "leg", "arm")):
        impacts.append("collision")
    if any(hint in identifiers for hint in ("head", "neck", "arm", "hand", "leg", "foot")):
        impacts.append("ik")
    if any(hint in identifiers for hint in ("point", "dlc", "megane")):
        impacts.append("locator")
    return tuple(impacts) or _impact_keys(None, summary)


def _notable_identifiers(values: tuple[str, ...], limit: int = 12) -> tuple[str, ...]:
    notable = [
        value
        for value in values
        if any(hint.casefold() in value.casefold() for hint in NOTABLE_IDENTIFIER_HINTS)
    ]
    if not notable:
        notable = list(values)
    return tuple(notable[:limit])
