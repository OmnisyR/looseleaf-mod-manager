"""Reference MOD/file selection helpers for MI Studio."""
from __future__ import annotations

from dataclasses import dataclass

from modmanager.pathutils import normalize_key

from .catalog import MiEntry, MiSource
from .workspace import TWEAKS_MOD_ID


@dataclass(frozen=True)
class ReferenceOption:
    mod_id: str
    mod_label: str
    target: str
    file_label: str
    source: MiSource


@dataclass
class ReferenceLibrary:
    files_by_mod: dict[str, list[ReferenceOption]]
    mod_labels: dict[str, str]
    mod_ids: list[str | None]


def build_reference_library(catalog: dict[str, MiEntry]) -> ReferenceLibrary:
    files_by_mod: dict[str, list[ReferenceOption]] = {}
    mod_labels: dict[str, str] = {}
    seen: set[tuple[str, str]] = set()
    for entry in catalog.values():
        for source in entry.sources:
            if source.kind != "mod" or not source.mod_id or source.mod_id == TWEAKS_MOD_ID:
                continue
            key = (source.mod_id, normalize_key(entry.target))
            if key in seen:
                continue
            seen.add(key)
            mod_labels.setdefault(source.mod_id, source.label)
            files_by_mod.setdefault(source.mod_id, []).append(
                ReferenceOption(
                    mod_id=source.mod_id,
                    mod_label=mod_labels[source.mod_id],
                    target=entry.target,
                    file_label=entry.file_name,
                    source=source,
                )
            )

    for options in files_by_mod.values():
        options.sort(key=lambda option: (option.file_label.casefold(), normalize_key(option.target)))
    mod_ids = sorted(files_by_mod, key=lambda mod_id: mod_labels.get(mod_id, mod_id).casefold())
    return ReferenceLibrary(files_by_mod=files_by_mod, mod_labels=mod_labels, mod_ids=[None] + mod_ids)


def default_reference(entry: MiEntry | None, library: ReferenceLibrary) -> tuple[str | None, str | None]:
    if entry is None:
        return None, None
    same_file_sources = [
        source
        for source in entry.sources
        if source.kind == "mod" and source.mod_id in library.files_by_mod
    ]
    if not same_file_sources:
        return None, None
    if entry.baseline and entry.baseline.kind == "mod" and entry.baseline.mod_id in library.files_by_mod:
        return entry.baseline.mod_id, entry.target
    return same_file_sources[-1].mod_id, entry.target
