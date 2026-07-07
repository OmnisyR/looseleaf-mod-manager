from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .errors import ManagerError
from .pathutils import posix_path


@dataclass(frozen=True)
class PacEntry:
    name: str
    offset: int
    size: int
    hash_value: int


def read_pac_entries(path: Path) -> list[PacEntry]:
    with path.open("rb") as file:
        if file.read(4) != b"FPAC":
            raise ManagerError(f"Not an FPAC archive: {path.name}")
        header = file.read(12)
        if len(header) != 12:
            raise ManagerError(f"Invalid FPAC header: {path.name}")
        count, _header_size, _unknown = struct.unpack("<3I", header)
        raw_entries = []
        for _index in range(count):
            entry_data = file.read(32)
            if len(entry_data) != 32:
                raise ManagerError(f"Truncated FPAC index: {path.name}")
            hash_value, name_offset, size, data_offset = struct.unpack("<4Q", entry_data)
            raw_entries.append((hash_value, name_offset, size, data_offset))

        entries: list[PacEntry] = []
        for hash_value, name_offset, size, data_offset in raw_entries:
            entries.append(
                PacEntry(
                    name=_read_null_terminated_string(file, name_offset),
                    offset=data_offset,
                    size=size,
                    hash_value=hash_value,
                )
            )
        return entries


def read_pac_member(path: Path, entry: PacEntry) -> bytes:
    with path.open("rb") as file:
        file.seek(entry.offset)
        data = file.read(entry.size)
    if len(data) != entry.size:
        raise ManagerError(f"Truncated FPAC member: {entry.name}")
    return data


def find_pac_entry(path: Path, candidates: Iterable[str]) -> PacEntry | None:
    candidate_keys = [posix_path(candidate).casefold() for candidate in candidates]
    basename_keys = {Path(candidate).name.casefold() for candidate in candidate_keys}
    fallback: PacEntry | None = None
    for entry in read_pac_entries(path):
        entry_key = posix_path(entry.name).casefold()
        if entry_key in candidate_keys:
            return entry
        if any(entry_key.endswith(f"/{candidate}") for candidate in candidate_keys):
            return entry
        if Path(entry_key).name.casefold() in basename_keys and "/model_info/" in f"/{entry_key}":
            fallback = fallback or entry
    return fallback


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
