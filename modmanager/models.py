from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class FileMapping:
    source: Path
    target: PurePosixPath
    source_table_dir: str | None = None
