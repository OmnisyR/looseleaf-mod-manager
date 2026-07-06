from __future__ import annotations

import json
import shutil
import threading
import time
import urllib.parse
import uuid
from pathlib import Path, PurePosixPath
from typing import Callable

from PIL import Image

from .archives import ArchiveExtractor
from .config import ManagerConfig
from .constants import (
    APP_DIR,
    CUSTOM_TABLE_FILES,
    DATA_DIR_NAME,
    IMAGE_EXTENSIONS,
    MAX_PREVIEW_DOWNLOAD_BYTES,
    MAX_XINPUT_DOWNLOAD_BYTES,
    PREVIEW_FORMAT_EXTENSIONS,
    XINPUT_DOWNLOAD_URL,
)
from .errors import ManagerError
from .games import XINPUT_DLL, detect_profile, xinput_present
from .i18n import Translator
from .mapping import TableResolver, collect_mappings, normalize_asset_target
from .migration import migrate_legacy_layout, repair_nested_game_data
from .network import download_url_to_file
from .pathutils import (
    clean_mod_name,
    copy_file,
    is_archive,
    is_preview_image,
    normalize_key,
    now_label,
    posix_path,
    remove_empty_parents,
    slugify,
)
from .sevenzip import SevenZipManager
from .table_merge import build_extra_costume_catalog, build_merged_tables, collect_table_sources
from . import costumes


class ModManagerCore:
    def __init__(self, app_dir: Path = APP_DIR, game_root: Path | None = None) -> None:
        self.app_dir = app_dir.resolve()
        self.data_dir = self.app_dir / DATA_DIR_NAME
        # Global (game-agnostic) locations.
        self.tools_dir = self.data_dir / "tools"
        self.costumes_dir = self.data_dir / "costumes"
        self.games_dir = self.data_dir / "games"
        self.config_file = self.data_dir / "config.json"
        self._lock = threading.RLock()
        for directory in (self.data_dir, self.tools_dir, self.costumes_dir, self.games_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self.config = ManagerConfig(self.config_file)
        self.translator = Translator(self.config.language)
        self.seven_zip = SevenZipManager(self.tools_dir, self.t)
        self.archive_extractor = ArchiveExtractor(self.seven_zip, self.t)

        # Per-game state; None until a game is activated.
        self.game_id: str | None = None
        self.game_root: Path | None = None
        self.tables: TableResolver | None = None
        self.state = self._empty_state()
        self._clear_game_paths()

        if game_root is not None:
            # Direct/test mode: activate the given folder without touching config.
            self.set_active_game(Path(game_root), persist=False)
        else:
            migrate_legacy_layout(self.data_dir, self.app_dir.parent, self.config)
            active = self.config.active_game_id
            entry = self.config.get_game(active) if active else None
            if entry:
                path = entry.get("path")
                self._activate(active, Path(path) if path else None)

    def t(self, key: str, **kwargs: object) -> str:
        return self.translator.t(key, **kwargs)

    # -- game management ------------------------------------------------------

    @property
    def has_active_game(self) -> bool:
        return self.game_id is not None

    def _clear_game_paths(self) -> None:
        self.game_data_dir: Path | None = None
        self.mods_dir: Path | None = None
        self.backups_dir: Path | None = None
        self.table_cache_dir: Path | None = None
        self.generated_dir: Path | None = None
        self.staging_dir: Path | None = None
        self.state_file: Path | None = None
        self.extra_costume_names_file: Path | None = None

    def _activate(self, game_id: str, game_root: Path | None) -> None:
        self.game_id = game_id
        self.game_root = game_root.resolve() if game_root else None
        game_data = self.games_dir / game_id
        self.game_data_dir = game_data
        self.mods_dir = game_data / "mods"
        self.backups_dir = game_data / "backups"
        self.table_cache_dir = game_data / "table_cache"
        self.generated_dir = game_data / "_generated"
        self.staging_dir = game_data / "_staging"
        self.state_file = game_data / "state.json"
        self.extra_costume_names_file = game_data / "extra_costume_names.json"
        for directory in (
            game_data,
            self.mods_dir,
            self.backups_dir,
            self.table_cache_dir,
            self.generated_dir,
            self.staging_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        # Heal any mods/mods/... nesting left by an older buggy migration.
        repair_nested_game_data(game_data)
        self.tables = TableResolver(self.game_root) if self.game_root else None
        # Base catalog filename mirrors the game id (sora_1st -> costumes/sora_1st.json);
        # unknown games simply have no base file and rely on their generated extra catalog.
        costumes.configure_paths(
            base=self.costumes_dir / f"{game_id}.json",
            extra=self.extra_costume_names_file,
        )
        self.state = self._load_state()

    def set_active_game(self, path: Path, persist: bool = True) -> str:
        path = Path(path).resolve()
        profile = detect_profile(path)
        game_id = profile.id
        if persist:
            exe = profile.exe_names[0] if profile.exe_names else None
            self.config.add_game(game_id, profile.display_name, str(path), exe)
            self.config.active_game_id = game_id
            self.config.save()
        self._activate(game_id, path)
        return game_id

    def add_and_activate_game(self, path: Path) -> str:
        return self.set_active_game(path, persist=True)

    def switch_game(self, game_id: str) -> None:
        entry = self.config.get_game(game_id)
        if entry is None:
            raise ManagerError(self.t("game_not_registered", game=game_id))
        self.config.active_game_id = game_id
        self.config.save()
        path = entry.get("path")
        self._activate(game_id, Path(path) if path else None)

    def remove_game(self, game_id: str) -> None:
        was_active = self.game_id == game_id
        self.config.remove_game(game_id)
        self.config.save()
        if not was_active:
            return
        self.game_id = None
        self.game_root = None
        self.tables = None
        self.state = self._empty_state()
        self._clear_game_paths()
        remaining = sorted(self.config.games)
        if remaining:
            self.switch_game(remaining[0])

    def list_games(self) -> list[dict]:
        games = []
        for game_id, entry in self.config.games.items():
            games.append(
                {
                    "id": game_id,
                    "name": entry.get("name", game_id),
                    "path": entry.get("path", ""),
                    "active": game_id == self.game_id,
                }
            )
        games.sort(key=lambda item: item["name"].casefold())
        return games

    def active_game_name(self) -> str:
        if not self.game_id:
            return ""
        entry = self.config.get_game(self.game_id)
        return entry.get("name", self.game_id) if entry else self.game_id

    def xinput_ok(self) -> bool:
        return xinput_present(self.game_root) if self.game_root else False

    def xinput_path(self) -> Path | None:
        return self.game_root / XINPUT_DLL if self.game_root else None

    def set_xinput_download_url(self, url: str) -> None:
        self.config.xinput_download_url = url.strip()
        self.save_config()

    def download_xinput(
        self,
        url: str | None = None,
        log: Callable[[str], None] | None = None,
    ) -> Path:
        if not self.game_root:
            raise ManagerError(self.t("no_active_game"))
        url = (url or self.config.xinput_download_url or XINPUT_DOWNLOAD_URL).strip()
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ManagerError(self.t("xinput_url_invalid"))

        destination = self.game_root / XINPUT_DLL
        if destination.exists():
            raise ManagerError(self.t("xinput_already_exists", path=destination))

        logger = log or (lambda _message: None)
        logger(self.t("xinput_download_started", url=url))
        try:
            download_url_to_file(url, destination, MAX_XINPUT_DOWNLOAD_BYTES, logger, self.t)
            if not self._looks_like_windows_dll(destination):
                destination.unlink(missing_ok=True)
                raise ManagerError(self.t("xinput_download_invalid"))
        except Exception:
            destination.unlink(missing_ok=True)
            raise

        self.set_xinput_download_url(url)
        logger(self.t("xinput_downloaded", path=destination))
        return destination

    @staticmethod
    def _looks_like_windows_dll(path: Path) -> bool:
        try:
            with path.open("rb") as file:
                if file.read(2) != b"MZ":
                    return False
                file.seek(0x3C)
                pe_offset_bytes = file.read(4)
                if len(pe_offset_bytes) != 4:
                    return False
                pe_offset = int.from_bytes(pe_offset_bytes, "little")
                if pe_offset <= 0 or pe_offset > 4096:
                    return False
                file.seek(pe_offset)
                return file.read(4) == b"PE\0\0"
        except OSError:
            return False

    def _empty_state(self) -> dict:
        return {
            "version": 1,
            "created_at": now_label(),
            "mods": {},
            "order": [],
            "backups": {},
            "last_applied_targets": [],
        }

    def _load_state(self) -> dict:
        # Per-game directories are created in _activate(); here we just read state.
        if not self.state_file or not self.state_file.exists():
            return self._empty_state()
        try:
            with self.state_file.open("r", encoding="utf-8") as file:
                state = json.load(file)
        except json.JSONDecodeError as exc:
            raise ManagerError(self.t("state_read_failed", error=exc)) from exc

        state.setdefault("version", 1)
        state.setdefault("mods", {})
        state.setdefault("order", [])
        state.setdefault("backups", {})
        state.setdefault("last_applied_targets", [])
        state_changed = False
        known_ids = set(state["mods"])
        state["order"] = [mod_id for mod_id in state["order"] if mod_id in known_ids]
        for mod_id in sorted(known_ids - set(state["order"])):
            state["order"].append(mod_id)
            state_changed = True
        for mod_id, mod in state["mods"].items():
            mod.setdefault("table_sources", [])
            remaining_files = []
            seen_files: set[str] = set()
            for target_text in mod.get("files", []):
                target = PurePosixPath(target_text)
                normalized_target = normalize_asset_target(target)
                if normalized_target != target:
                    self._relocate_mod_file(mod_id, target, normalized_target)
                    target = normalized_target
                    target_text = posix_path(target)
                    state_changed = True
                if (
                    len(target.parts) >= 2
                    and target.parts[0].casefold().startswith("table_")
                    and target.name.casefold() in CUSTOM_TABLE_FILES
                ):
                    source_path = self.mod_files_root(mod_id) / Path(*target.parts)
                    mod["table_sources"].append(
                        {
                            "source": self.relative_data_path(source_path),
                            "table_name": target.name.casefold(),
                            "source_table_dir": target.parts[0].casefold(),
                        }
                    )
                    state_changed = True
                else:
                    key = normalize_key(target_text)
                    if key in seen_files:
                        state_changed = True
                        continue
                    seen_files.add(key)
                    remaining_files.append(target_text)
            if remaining_files != mod.get("files", []):
                state_changed = True
            mod["files"] = remaining_files
        if state_changed:
            self._write_state(state)
        return state

    def save(self) -> None:
        self._write_state(self.state)

    def _write_state(self, state: dict) -> None:
        if not self.state_file or not self.game_data_dir:
            return
        self.game_data_dir.mkdir(parents=True, exist_ok=True)
        temp_file = self.state_file.with_suffix(".json.tmp")
        with temp_file.open("w", encoding="utf-8") as file:
            json.dump(state, file, ensure_ascii=False, indent=2)
        temp_file.replace(self.state_file)

    def _relocate_mod_file(self, mod_id: str, old_target: PurePosixPath, new_target: PurePosixPath) -> None:
        if old_target == new_target:
            return
        files_root = self.mod_files_root(mod_id)
        old_path = files_root / Path(*old_target.parts)
        new_path = files_root / Path(*new_target.parts)
        if not old_path.exists() or new_path.exists():
            return
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_path), str(new_path))
        remove_empty_parents(old_path, files_root)

    def save_config(self) -> None:
        self.config.save()

    def set_language(self, language: str) -> None:
        self.config.language = language
        self.translator.set_language(language)
        self.save_config()

    def mod_files_root(self, mod_id: str) -> Path:
        return self.mods_dir / mod_id / "files"

    def relative_data_path(self, path: Path) -> str:
        # Paths are stored relative to the active game's data dir, so a game's
        # mods/backups stay valid regardless of the manager_data root.
        return posix_path(path.resolve().relative_to(self.game_data_dir.resolve()))

    def absolute_data_path(self, stored: str | None) -> Path | None:
        if not stored or not self.game_data_dir:
            return None
        return (self.game_data_dir / Path(*PurePosixPath(stored).parts)).resolve()

    def active_table_dir(self) -> str:
        return self.tables.active_table_dir()

    # -- import -----------------------------------------------------------

    def import_path(self, source: Path, log: Callable[[str], None] | None = None) -> str:
        source = source.resolve()
        if not source.exists():
            raise ManagerError(self.t("path_missing", path=source))
        logger = log or (lambda _message: None)
        mod_name = clean_mod_name(source, self.t("unnamed_mod"))
        mod_id = f"{slugify(mod_name)}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        staging_root = self.staging_dir / mod_id
        extracted_root = staging_root / "source"
        mod_dir = self.mods_dir / mod_id
        files_root = mod_dir / "files"

        with self._lock:
            self.tables.reset()
            if staging_root.exists():
                shutil.rmtree(staging_root)
            if mod_dir.exists():
                shutil.rmtree(mod_dir)
            extracted_root.mkdir(parents=True, exist_ok=True)

            try:
                logger(self.t("import_started", time=now_label(), path=source))
                if source.is_dir():
                    destination = extracted_root / source.name
                    shutil.copytree(source, destination)
                    logger(self.t("copied_folder_to_staging"))
                elif source.is_file() and is_archive(source):
                    self.archive_extractor.extract(source, extracted_root, logger)
                elif source.is_file():
                    destination = extracted_root / source.name
                    copy_file(source, destination)
                    logger(self.t("copied_file_to_staging"))
                else:
                    raise ManagerError(self.t("unsupported_path_type", path=source))

                self.archive_extractor.extract_nested(extracted_root, logger)
                mappings = collect_mappings(extracted_root, self.tables, logger, self.t)
                table_sources = collect_table_sources(extracted_root, self.tables, logger, self.t)
                if not mappings and not table_sources:
                    raise ManagerError(self.t("no_installable_files"))

                mod_dir.mkdir(parents=True, exist_ok=True)
                files_root.mkdir(parents=True, exist_ok=True)
                tables_root = mod_dir / "tables"
                tables_root.mkdir(parents=True, exist_ok=True)
                raw_source = self.copy_raw_source(source, mod_dir, logger)
                copied_targets: dict[str, str] = {}
                for mapping in mappings:
                    key = normalize_key(mapping.target)
                    target_text = posix_path(mapping.target)
                    destination = files_root / Path(*mapping.target.parts)
                    if key in copied_targets:
                        logger(self.t("duplicate_target_overwritten", target=target_text))
                    copy_file(mapping.source, destination)
                    copied_targets[key] = target_text
                stored_table_sources = []
                for table_source in table_sources:
                    destination = tables_root / table_source.source_table_dir / table_source.table_name
                    copy_file(table_source.source, destination)
                    stored_table_sources.append(
                        {
                            "source": self.relative_data_path(destination),
                            "table_name": table_source.table_name,
                            "source_table_dir": table_source.source_table_dir,
                        }
                    )

                preview_path = self.find_and_copy_preview(extracted_root, mod_dir, logger)
                record = {
                    "id": mod_id,
                    "name": mod_name,
                    "enabled": True,
                    "source": str(source),
                    "created_at": now_label(),
                    "files": [copied_targets[key] for key in sorted(copied_targets)],
                    "table_sources": stored_table_sources,
                    "raw_source": self.relative_data_path(raw_source),
                    "preview": self.relative_data_path(preview_path) if preview_path else None,
                }
                self.state["mods"][mod_id] = record
                self.state["order"].append(mod_id)
                self.save()
                logger(self.t("import_completed_log", name=mod_name, count=len(record["files"])))
                return mod_id
            finally:
                if staging_root.exists():
                    shutil.rmtree(staging_root, ignore_errors=True)

    def copy_raw_source(self, source: Path, mod_dir: Path, log: Callable[[str], None]) -> Path:
        raw_root = mod_dir / "raw"
        raw_root.mkdir(parents=True, exist_ok=True)
        destination = raw_root / source.name
        if destination.exists():
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            copy_file(source, destination)
        log(self.t("raw_source_saved", path=destination.relative_to(mod_dir)))
        return destination

    # -- preview ------------------------------------------------------------

    def find_and_copy_preview(
        self, root: Path, mod_dir: Path, log: Callable[[str], None]
    ) -> Path | None:
        candidates = [path for path in root.rglob("*") if path.is_file() and is_preview_image(path)]
        if not candidates:
            return None

        def score(path: Path) -> tuple[int, int, str]:
            lower = path.name.casefold()
            name_score = 0
            for word in ("preview", "thumb", "thumbnail", "cover", "image", "预览", "封面"):
                if word in lower:
                    name_score += 10
            try:
                size_score = min(path.stat().st_size // 1024, 10000)
            except OSError:
                size_score = 0
            return (name_score, size_score, str(path))

        preview = max(candidates, key=score)
        try:
            with Image.open(preview) as image:
                image.verify()
        except Exception:
            return None
        destination = mod_dir / f"preview{preview.suffix.casefold()}"
        copy_file(preview, destination)
        log(self.t("auto_preview_set", name=preview.name))
        return destination

    def set_preview(self, mod_id: str, image_path: Path) -> None:
        image_path = image_path.resolve()
        if mod_id not in self.state["mods"]:
            raise ManagerError(self.t("select_mod_required"))
        if not image_path.exists() or not image_path.is_file():
            raise ManagerError(self.t("preview_missing", path=image_path))
        if not is_preview_image(image_path):
            raise ManagerError(self.t("preview_unsupported"))
        try:
            with Image.open(image_path) as image:
                image.verify()
        except Exception as exc:
            raise ManagerError(self.t("preview_unreadable", name=image_path.name)) from exc

        self._store_preview_file(mod_id, image_path, image_path.suffix.casefold())

    def set_preview_from_url(
        self, mod_id: str, url: str, log: Callable[[str], None] | None = None
    ) -> Path:
        logger = log or (lambda _message: None)
        if mod_id not in self.state["mods"]:
            raise ManagerError(self.t("select_mod_required"))
        url = url.strip()
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ManagerError(self.t("preview_url_invalid"))

        mod_dir = self.mods_dir / mod_id
        mod_dir.mkdir(parents=True, exist_ok=True)
        temp_path = mod_dir / f"preview-download-{uuid.uuid4().hex}.tmp"

        logger(self.t("preview_download_started", url=url))
        try:
            download_url_to_file(url, temp_path, MAX_PREVIEW_DOWNLOAD_BYTES, logger, self.t)
            if temp_path.stat().st_size == 0:
                raise ManagerError(self.t("preview_url_empty_file"))

            try:
                with Image.open(temp_path) as image:
                    extension = PREVIEW_FORMAT_EXTENSIONS.get(image.format or "")
                    if extension is None:
                        raise ManagerError(self.t("preview_url_unsupported_file"))
                    image.verify()
            except ManagerError:
                raise
            except Exception as exc:
                raise ManagerError(self.t("preview_url_unreadable_file")) from exc

            destination = self._store_preview_file(
                mod_id,
                temp_path,
                extension,
                source_url=url,
                move=True,
            )
            logger(self.t("preview_cached", name=destination.name))
            return destination
        finally:
            temp_path.unlink(missing_ok=True)

    def _store_preview_file(
        self,
        mod_id: str,
        image_path: Path,
        extension: str,
        source_url: str | None = None,
        move: bool = False,
    ) -> Path:
        extension = extension.casefold()
        if extension not in IMAGE_EXTENSIONS:
            raise ManagerError(self.t("preview_unsupported"))
        mod_dir = self.mods_dir / mod_id
        mod_dir.mkdir(parents=True, exist_ok=True)
        destination = mod_dir / f"preview{extension}"
        old_preview = self.absolute_data_path(self.state["mods"][mod_id].get("preview"))
        if image_path.resolve() == destination.resolve():
            self.state["mods"][mod_id]["preview"] = self.relative_data_path(destination)
            if source_url:
                self.state["mods"][mod_id]["preview_source_url"] = source_url
            else:
                self.state["mods"][mod_id].pop("preview_source_url", None)
            self.save()
            return destination
        if old_preview and old_preview.exists() and old_preview != destination:
            old_preview.unlink(missing_ok=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if move:
            image_path.replace(destination)
        else:
            copy_file(image_path, destination)
        self.state["mods"][mod_id]["preview"] = self.relative_data_path(destination)
        if source_url:
            self.state["mods"][mod_id]["preview_source_url"] = source_url
        else:
            self.state["mods"][mod_id].pop("preview_source_url", None)
        self.save()
        return destination

    # -- ordering / conflicts ------------------------------------------------

    def compute_conflicts(self) -> list[dict]:
        buckets: dict[str, dict] = {}
        for mod_id in self.state["order"]:
            mod = self.state["mods"].get(mod_id)
            if not mod or not mod.get("enabled", True):
                continue
            for target in mod.get("files", []):
                key = normalize_key(target)
                bucket = buckets.setdefault(key, {"target": target, "mods": []})
                bucket["mods"].append(mod_id)

        conflicts = []
        for bucket in buckets.values():
            if len(bucket["mods"]) <= 1:
                continue
            winner_id = bucket["mods"][-1]
            loser_ids = bucket["mods"][:-1]
            conflicts.append(
                {
                    "target": bucket["target"],
                    "winner": winner_id,
                    "losers": loser_ids,
                    "mods": bucket["mods"],
                }
            )
        conflicts.sort(key=lambda item: normalize_key(item["target"]))
        return conflicts

    def conflict_counts_by_mod(self) -> dict[str, int]:
        counts = {mod_id: 0 for mod_id in self.state["mods"]}
        for conflict in self.compute_conflicts():
            for mod_id in conflict["mods"]:
                counts[mod_id] = counts.get(mod_id, 0) + 1
        return counts

    def set_order(self, order: list[str]) -> None:
        known = set(self.state["mods"])
        self.state["order"] = [mod_id for mod_id in order if mod_id in known]
        for mod_id in self.state["mods"]:
            if mod_id not in self.state["order"]:
                self.state["order"].append(mod_id)
        self.save()

    def toggle_enabled(self, mod_id: str) -> None:
        if mod_id not in self.state["mods"]:
            return
        mod = self.state["mods"][mod_id]
        mod["enabled"] = not mod.get("enabled", True)
        self.save()

    def delete_mod(self, mod_id: str) -> None:
        if mod_id not in self.state["mods"]:
            return
        self.state["mods"].pop(mod_id, None)
        self.state["order"] = [item for item in self.state["order"] if item != mod_id]
        mod_dir = self.mods_dir / mod_id
        if mod_dir.exists():
            shutil.rmtree(mod_dir)
        self.save()

    # -- apply / restore ------------------------------------------------------

    def apply_enabled(self, log: Callable[[str], None] | None = None) -> dict:
        logger = log or (lambda _message: None)
        with self._lock:
            self.tables.reset()
            logger(self.t("apply_started", time=now_label()))
            self.restore_applied_targets(logger)

            applied_targets: set[str] = set()
            copied_files = 0
            table_sources = []
            for mod_id in self.state["order"]:
                mod = self.state["mods"].get(mod_id)
                if not mod or not mod.get("enabled", True):
                    continue
                logger(self.t("applying_mod", name=mod["name"]))
                for source_info in mod.get("table_sources", []):
                    source_path = self.absolute_data_path(source_info.get("source"))
                    if source_path is None:
                        continue
                    table_sources.append(
                        {
                            "source": str(source_path),
                            "table_name": source_info.get("table_name"),
                            "source_table_dir": source_info.get("source_table_dir"),
                            "mod_id": mod_id,
                            "mod_name": mod.get("name", mod_id),
                        }
                    )
                files_root = self.mod_files_root(mod_id)
                for target_text in mod.get("files", []):
                    target = PurePosixPath(target_text)
                    source = files_root / Path(*target.parts)
                    if not source.exists():
                        logger(self.t("missing_file_skipped", name=mod["name"], target=target_text))
                        continue
                    self.ensure_backup(target_text, logger)
                    destination = self.game_root / Path(*target.parts)
                    copy_file(source, destination)
                    applied_targets.add(posix_path(target))
                    copied_files += 1

            table_work_root = self.generated_dir / "_work"
            table_output_root = self.generated_dir / "tables"
            if table_output_root.exists():
                shutil.rmtree(table_output_root)
            if table_work_root.exists():
                shutil.rmtree(table_work_root)
            table_mappings = build_merged_tables(
                table_sources,
                table_output_root,
                table_work_root,
                self.game_root,
                self.table_cache_dir,
                self.tools_dir,
                self.tables,
                logger,
                self.t,
            )
            build_extra_costume_catalog(
                table_sources,
                self.extra_costume_names_file,
                self.game_root,
                self.table_cache_dir,
                self.tools_dir,
                self.tables,
                logger,
                self.t,
            )
            costumes.reload_catalog()
            for mapping in table_mappings:
                target_text = posix_path(mapping.target)
                self.ensure_backup(target_text, logger)
                destination = self.game_root / Path(*mapping.target.parts)
                copy_file(mapping.source, destination)
                applied_targets.add(target_text)
                copied_files += 1

            self.state["last_applied_targets"] = sorted(applied_targets, key=normalize_key)
            self.save()
            logger(self.t("apply_completed_log", count=copied_files))
            return {
                "mods": sum(
                    1
                    for mod_id in self.state["order"]
                    if self.state["mods"].get(mod_id, {}).get("enabled", True)
                ),
                "files": copied_files,
                "conflicts": len(self.compute_conflicts()),
            }

    def ensure_backup(self, target_text: str, log: Callable[[str], None]) -> None:
        key = normalize_key(target_text)
        if key in self.state["backups"]:
            return
        target = PurePosixPath(target_text)
        game_file = self.game_root / Path(*target.parts)
        backup_file = self.backups_dir / Path(*target.parts)
        if game_file.exists():
            copy_file(game_file, backup_file)
            self.state["backups"][key] = {
                "target": posix_path(target),
                "exists": True,
                "backup": self.relative_data_path(backup_file),
            }
            log(self.t("original_file_backed_up", target=target_text))
        else:
            self.state["backups"][key] = {
                "target": posix_path(target),
                "exists": False,
                "backup": None,
            }

    def restore_applied_targets(self, log: Callable[[str], None]) -> None:
        targets = list(self.state.get("last_applied_targets", []))
        if not targets:
            return
        restored = 0
        removed = 0
        for target_text in targets:
            target = PurePosixPath(target_text)
            game_file = self.game_root / Path(*target.parts)
            backup = self.state["backups"].get(normalize_key(target_text))
            if backup and backup.get("exists"):
                backup_path = self.absolute_data_path(backup.get("backup"))
                if backup_path and backup_path.exists():
                    copy_file(backup_path, game_file)
                    restored += 1
            else:
                if game_file.exists():
                    game_file.unlink()
                    remove_empty_parents(game_file, self.game_root)
                    removed += 1
        self.state["last_applied_targets"] = []
        if restored or removed:
            log(self.t("previous_apply_restored", restored=restored, removed=removed))

    def restore_game(self, log: Callable[[str], None] | None = None) -> dict:
        logger = log or (lambda _message: None)
        with self._lock:
            targets = set(self.state.get("last_applied_targets", []))
            for backup in self.state.get("backups", {}).values():
                targets.add(backup.get("target", ""))
            restored = 0
            removed = 0
            for target_text in sorted([target for target in targets if target], key=normalize_key):
                target = PurePosixPath(target_text)
                game_file = self.game_root / Path(*target.parts)
                backup = self.state["backups"].get(normalize_key(target_text))
                if backup and backup.get("exists"):
                    backup_path = self.absolute_data_path(backup.get("backup"))
                    if backup_path and backup_path.exists():
                        copy_file(backup_path, game_file)
                        restored += 1
                else:
                    if game_file.exists():
                        game_file.unlink()
                        remove_empty_parents(game_file, self.game_root)
                        removed += 1
            self.state["last_applied_targets"] = []
            self.clear_extra_costume_catalog()
            self.save()
            logger(self.t("game_restored_log", restored=restored, removed=removed))
            return {"restored": restored, "removed": removed}

    def clear_extra_costume_catalog(self) -> None:
        self.extra_costume_names_file.parent.mkdir(parents=True, exist_ok=True)
        temp_file = self.extra_costume_names_file.with_suffix(".json.tmp")
        temp_file.write_text("{}", encoding="utf-8")
        temp_file.replace(self.extra_costume_names_file)
        costumes.reload_catalog()
