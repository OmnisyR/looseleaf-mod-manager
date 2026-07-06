from __future__ import annotations

import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path
from typing import Callable

from .errors import ManagerError
from .i18n import DEFAULT_LANGUAGE, translate
from .pathutils import archive_stem, is_archive, safe_destination, unique_child
from .sevenzip import SevenZipManager, find_7z

STDLIB_TAR_EXTENSIONS = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")


class ArchiveExtractor:
    def __init__(self, seven_zip: SevenZipManager, tr: Callable[..., str] | None = None) -> None:
        self.seven_zip = seven_zip
        self.tr = tr

    def t(self, key: str, **kwargs: object) -> str:
        if self.tr is not None:
            return self.tr(key, **kwargs)
        return translate(DEFAULT_LANGUAGE, key, **kwargs)

    def extract(self, archive: Path, destination: Path, log: Callable[[str], None]) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        lower = archive.name.casefold()
        log(self.t("archive_extracting", name=archive.name))

        if lower.endswith(".zip"):
            self._extract_zip(archive, destination)
            return
        if lower.endswith(STDLIB_TAR_EXTENSIONS):
            self._extract_tar(archive, destination)
            return

        # RAR/7z/Zstandard tar and any future archive type are handled by the
        # bundled 7-Zip backend, avoiding optional Python package drift.
        self._extract_with_preferred_7z(archive, destination, log)

    def _extract_zip(self, archive: Path, destination: Path) -> None:
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                target = safe_destination(destination, info.filename, self.t)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)

    def _extract_tar(self, archive: Path, destination: Path) -> None:
        try:
            members = None
            with tarfile.open(archive) as tf:
                members = tf.getmembers()
                for member in members:
                    target = safe_destination(destination, member.name, self.t)
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    if not member.isfile():
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    extracted = tf.extractfile(member)
                    if extracted is None:
                        continue
                    with extracted, target.open("wb") as dst:
                        shutil.copyfileobj(extracted, dst)
        except tarfile.TarError as exc:
            raise ManagerError(self.t("archive_tar_failed", error=exc)) from exc

    def _extract_with_preferred_7z(
        self, archive: Path, destination: Path, log: Callable[[str], None]
    ) -> None:
        errors = []
        try:
            self._extract_with_7z(self.seven_zip.ensure(log, self.t), archive, destination)
            return
        except Exception as exc:
            errors.append(f"{self.t('archive_7z_manager_label')}: {exc}")

        system_7z = find_7z()
        if system_7z:
            try:
                self._extract_with_7z(system_7z, archive, destination)
                return
            except Exception as exc:
                errors.append(f"{self.t('archive_7z_system_label')}: {exc}")

        raise ManagerError(
            self.t(
                "archive_extract_failed_backends",
                name=archive.name,
                errors="; ".join(errors),
            )
        )

    def _extract_with_7z(self, seven_zip: Path, archive: Path, destination: Path) -> None:
        result = subprocess.run(
            [str(seven_zip), "x", "-y", f"-o{destination}", str(archive)],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            details = result.stderr.strip() or result.stdout.strip()
            raise ManagerError(self.t("archive_7z_failed", details=details))

    def extract_nested(
        self, root: Path, log: Callable[[str], None], max_rounds: int = 12
    ) -> None:
        processed: set[Path] = set()
        for round_index in range(max_rounds):
            archives = [
                path
                for path in root.rglob("*")
                if path.is_file() and is_archive(path) and path.resolve() not in processed
            ]
            if not archives:
                return
            for archive in archives:
                processed.add(archive.resolve())
                destination = unique_child(
                    archive.parent,
                    f"{archive_stem(archive)}__unpacked",
                    self.t,
                )
                destination.mkdir(parents=True, exist_ok=True)
                log(self.t("nested_archive_found", name=archive.name))
                self.extract(archive, destination, log)
            if round_index == max_rounds - 1:
                log(self.t("nested_archive_depth_limit"))
