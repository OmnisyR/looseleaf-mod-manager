"""Encoder for the FDK binary JSON format used by .mi (model info) files.

The matching decoder lives in modmanager.model_info.decode_model_info_json.
Layout mirrors the official writer: header, name dictionary (~crc32 + NUL
string), then values depth-first with children immediately after their
parent's address table.
"""
from __future__ import annotations

import struct
import zlib
from typing import Any

JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None

_HEADER_SIZE = 16
_KIND_NULL = 0x01
_KIND_STRING = 0x02
_KIND_NUMBER = 0x03
_KIND_OBJECT = 0x04
_KIND_ARRAY = 0x05
_KIND_BOOL = 0x06
_UNNAMED = 0x10


class ModelInfoEncodeError(ValueError):
    pass


def encode_model_info_json(value: JsonValue) -> bytes:
    names = _collect_names(value)
    dictionary = bytearray()
    name_addresses: dict[str, int] = {}
    for name in names:
        name_addresses[name] = _HEADER_SIZE + len(dictionary)
        dictionary += struct.pack("<I", 0xFFFFFFFF ^ zlib.crc32(name.encode("utf-8")))
        dictionary += name.encode("utf-8") + b"\0"

    data_start = _HEADER_SIZE + len(dictionary)
    body = bytearray()
    _write_value(body, data_start, value, "", name_addresses)

    header = b"JSON" + struct.pack("<III", 0, data_start, 0)
    return header + bytes(dictionary) + bytes(body)


def _collect_names(value: JsonValue) -> list[str]:
    # The root value is named with the empty string, so "" is always first.
    names: list[str] = [""]
    seen = {""}

    def walk(item: JsonValue) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key not in seen:
                    seen.add(key)
                    names.append(key)
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return names


def _write_value(
    body: bytearray,
    data_start: int,
    value: JsonValue,
    name: str | None,
    name_addresses: dict[str, int],
) -> None:
    kind = _kind_of(value)
    opcode = kind if name is not None else kind | _UNNAMED
    body.append(opcode)
    if name is not None:
        body += struct.pack("<I", name_addresses[name])

    if kind == _KIND_NULL:
        return
    if kind == _KIND_BOOL:
        body.append(1 if value else 0)
        return
    if kind == _KIND_NUMBER:
        body += struct.pack("<d", float(value))
        return
    if kind == _KIND_STRING:
        encoded = value.encode("utf-8")
        if b"\0" in encoded:
            raise ModelInfoEncodeError("string values cannot contain NUL bytes")
        body += encoded + b"\0"
        return

    if kind == _KIND_OBJECT:
        children: list[tuple[str | None, JsonValue]] = list(value.items())
    else:
        children = [(None, child) for child in value]
    body += struct.pack("<I", len(children))
    table_offset = len(body)
    body += b"\0\0\0\0" * len(children)
    for index, (child_name, child) in enumerate(children):
        struct.pack_into("<I", body, table_offset + index * 4, data_start + len(body))
        _write_value(body, data_start, child, child_name, name_addresses)


def _kind_of(value: JsonValue) -> int:
    if value is None:
        return _KIND_NULL
    if isinstance(value, bool):
        return _KIND_BOOL
    if isinstance(value, (int, float)):
        return _KIND_NUMBER
    if isinstance(value, str):
        return _KIND_STRING
    if isinstance(value, dict):
        return _KIND_OBJECT
    if isinstance(value, list):
        return _KIND_ARRAY
    raise ModelInfoEncodeError(f"unsupported value type: {type(value).__name__}")
