"""Enumerate every model info file visible to the game and resolve baselines.

Three origins are merged per target path:
  - the official pac archive (asset_common_model_info.pac)
  - mod-provided overrides / new registrations from the manager's state
  - loose files placed in the game directory outside the manager

The *baseline* of a target is the bytes the game would load if MI Studio's
tweak mod did not exist: the last enabled mod in load order providing the
target, else a manual loose file, else the pac member.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from modmanager import costumes
from modmanager.constants import MODEL_INFO_PAC_NAME
from modmanager.model_info import JsonValue, decode_model_info_json
from modmanager.pac import PacEntry, read_pac_entries, read_pac_member
from modmanager.pathutils import normalize_key, posix_path

CATEGORY_LABELS = {
    "chr": "角色",
    "equ": "装备",
    "mon": "怪物",
    "ob": "物件",
    "mp": "地图",
    "ef": "特效",
    "orbment": "导力器",
    "mg": "小游戏",
    "etc": "其他",
}
CATEGORY_ORDER = ["角色", "装备", "怪物", "物件", "地图", "特效", "导力器", "小游戏", "其他"]


@dataclass(frozen=True)
class MiSource:
    kind: str  # "pac" | "mod" | "loose"
    label: str
    mod_id: str | None = None
    enabled: bool = True
    path: Path | None = None
    pac_path: Path | None = None
    pac_entry: PacEntry | None = None

    def read_bytes(self) -> bytes:
        if self.kind == "pac":
            return read_pac_member(self.pac_path, self.pac_entry)
        return self.path.read_bytes()


@dataclass
class MiEntry:
    target: str
    stem: str
    file_name: str
    category: str
    character_id: str | None
    character_name: str
    display_name: str
    recognized: bool
    origin: str  # "official" | "mod_override" | "mod_new" | "loose"
    sources: list[MiSource] = field(default_factory=list)
    baseline: MiSource | None = None  # effective file the game would load (mods win)
    pac_source: MiSource | None = None  # the untouched official pac member

    def read_baseline(self) -> bytes | None:
        if self.baseline is None:
            return None
        try:
            return self.baseline.read_bytes()
        except OSError:
            return None

    def read_official(self) -> bytes | None:
        if self.pac_source is None:
            return None
        try:
            return self.pac_source.read_bytes()
        except OSError:
            return None

    def decode_baseline(self) -> JsonValue | None:
        data = self.read_baseline()
        if data is None:
            return None
        return decode_model_info_json(data)


def category_of(stem: str) -> str:
    # Longest known prefix that the stem starts with.
    best = ""
    for known in CATEGORY_LABELS:
        if stem.casefold().startswith(known) and len(known) > len(best):
            best = known
    return CATEGORY_LABELS.get(best, "其他")


def _describe(target: str) -> tuple[str | None, str, str, bool]:
    stem = PurePosixPath(posix_path(target)).stem
    info = costumes.lookup(stem)
    character_id = info.base_model if info else costumes.character_id_from_stem(stem)
    character = costumes.character_name(character_id)
    display = info.display() if info else PurePosixPath(posix_path(target)).name
    return character_id, character if character != "-" else "", display, info is not None


def build_catalog(
    game_root: Path,
    state: dict,
    mod_files_root,
    exclude_mod_id: str,
) -> dict[str, MiEntry]:
    """Return target -> MiEntry for every known model info file.

    `mod_files_root` is a callable mod_id -> Path (the manager core method).
    """
    entries: dict[str, MiEntry] = {}

    def ensure(target: str) -> MiEntry:
        key = normalize_key(target)
        entry = entries.get(key)
        if entry is None:
            stem = PurePosixPath(posix_path(target)).stem
            character_id, character, display, recognized = _describe(target)
            entry = MiEntry(
                target=posix_path(target),
                stem=stem,
                file_name=PurePosixPath(posix_path(target)).name,
                category=category_of(stem),
                character_id=character_id,
                character_name=character,
                display_name=display,
                recognized=recognized,
                origin="official",
            )
            entries[key] = entry
        return entry

    pac_path = game_root / "pac" / "steam" / MODEL_INFO_PAC_NAME
    if pac_path.exists():
        for pac_entry in read_pac_entries(pac_path):
            name = posix_path(pac_entry.name)
            target = name if name.startswith("asset/") else f"asset/common/model_info/{PurePosixPath(name).name}"
            entry = ensure(target)
            entry.sources.append(
                MiSource(kind="pac", label="官方", pac_path=pac_path, pac_entry=pac_entry)
            )

    applied = {normalize_key(item) for item in state.get("last_applied_targets", [])}
    model_info_dir = game_root / "asset" / "common" / "model_info"
    if model_info_dir.is_dir():
        for path in sorted(model_info_dir.glob("*.mi")):
            target = f"asset/common/model_info/{path.name}"
            if normalize_key(target) in applied:
                continue  # manager output, not a manual loose file
            entry = ensure(target)
            entry.sources.append(MiSource(kind="loose", label="散装文件", path=path))

    for mod_id in state.get("order", []):
        if mod_id == exclude_mod_id:
            continue
        mod = state.get("mods", {}).get(mod_id)
        if not mod:
            continue
        enabled = bool(mod.get("enabled", True))
        for target_text in mod.get("files", []):
            if not costumes.is_model_info_target(target_text):
                continue
            source_path = mod_files_root(mod_id) / Path(*PurePosixPath(target_text).parts)
            if not source_path.exists():
                continue
            entry = ensure(target_text)
            entry.sources.append(
                MiSource(
                    kind="mod",
                    label=str(mod.get("name", mod_id)),
                    mod_id=mod_id,
                    enabled=enabled,
                    path=source_path,
                )
            )

    for entry in entries.values():
        _resolve(entry)
    return entries


def _resolve(entry: MiEntry) -> None:
    pac = next((s for s in entry.sources if s.kind == "pac"), None)
    entry.pac_source = pac
    loose = next((s for s in entry.sources if s.kind == "loose"), None)
    enabled_mods = [s for s in entry.sources if s.kind == "mod" and s.enabled]
    any_mods = [s for s in entry.sources if s.kind == "mod"]

    if enabled_mods:
        entry.baseline = enabled_mods[-1]
    elif loose is not None:
        entry.baseline = loose
    elif pac is not None:
        entry.baseline = pac
    elif any_mods:
        entry.baseline = any_mods[-1]

    if pac is not None and enabled_mods:
        entry.origin = "mod_override"
    elif pac is not None:
        entry.origin = "official"
    elif any_mods:
        entry.origin = "mod_new"
    else:
        entry.origin = "loose"


ORIGIN_LABELS = {
    "official": "官方",
    "mod_override": "Mod 覆盖",
    "mod_new": "Mod 新增",
    "loose": "散装文件",
}


def origin_label(entry: MiEntry) -> str:
    label = ORIGIN_LABELS.get(entry.origin, entry.origin)
    if entry.origin in ("mod_override", "mod_new") and entry.baseline and entry.baseline.kind == "mod":
        if not entry.baseline.enabled:
            label += "（未启用）"
    return label
