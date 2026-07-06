from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable

from .constants import ARCHIVE_EXTENSIONS, IMAGE_EXTENSIONS
from .errors import ManagerError
from .i18n import DEFAULT_LANGUAGE, translate


def _t(tr: Callable[..., str] | None, key: str, **kwargs: object) -> str:
    if tr is not None:
        return tr(key, **kwargs)
    return translate(DEFAULT_LANGUAGE, key, **kwargs)


def now_label() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def posix_path(path: PurePosixPath | Path | str) -> str:
    return PurePosixPath(str(path).replace("\\", "/")).as_posix()


def normalize_key(path: str | PurePosixPath) -> str:
    return posix_path(path).casefold()


def is_table_dir_name(name: str) -> bool:
    return re.fullmatch(r"table_[a-z0-9]+", name.casefold()) is not None


def table_language(table_dir: str) -> str:
    lower = table_dir.casefold()
    return lower.removeprefix("table_")


def is_archive(path: Path) -> bool:
    name = path.name.casefold()
    return any(name.endswith(ext) for ext in ARCHIVE_EXTENSIONS)


def is_preview_image(path: Path) -> bool:
    return path.suffix.casefold() in IMAGE_EXTENSIONS


def archive_stem(path: Path) -> str:
    name = path.name
    lower = name.casefold()
    for ext in sorted(ARCHIVE_EXTENSIONS, key=len, reverse=True):
        if lower.endswith(ext):
            return name[: -len(ext)]
    return path.stem


def clean_mod_name(path: Path, fallback: str = "MOD") -> str:
    name = archive_stem(path) if path.is_file() else path.name
    name = " ".join(name.replace("_", " ").replace("-", " ").split())
    return name or fallback


def slugify(text: str) -> str:
    valid = []
    for char in text:
        if char.isascii() and char.isalnum():
            valid.append(char.lower())
        elif char in (" ", "_", "-", "."):
            valid.append("-")
    slug = "".join(valid).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "mod"


def safe_destination(
    base: Path, member_name: str, tr: Callable[..., str] | None = None
) -> Path:
    member = PurePosixPath(member_name.replace("\\", "/"))
    if member.is_absolute() or ".." in member.parts:
        raise ManagerError(_t(tr, "archive_unsafe_path", path=member_name))
    destination = (base / Path(*member.parts)).resolve()
    base_resolved = base.resolve()
    try:
        destination.relative_to(base_resolved)
    except ValueError as exc:
        raise ManagerError(_t(tr, "archive_path_escape", path=member_name)) from exc
    return destination


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def remove_empty_parents(path: Path, stop_at: Path) -> None:
    current = path.parent
    stop = stop_at.resolve()
    while current.exists():
        try:
            current.resolve().relative_to(stop)
        except ValueError:
            break
        if current == stop:
            break
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def unique_child(parent: Path, name: str, tr: Callable[..., str] | None = None) -> Path:
    candidate = parent / name
    if not candidate.exists():
        return candidate
    for index in range(2, 1000):
        candidate = parent / f"{name}-{index}"
        if not candidate.exists():
            return candidate
    raise ManagerError(_t(tr, "unique_dir_failed", path=parent / name))
