from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Iterable

from .constants import (
    MAX_TOOL_DOWNLOAD_BYTES,
    SEVEN_ZIP_BOOTSTRAP_FALLBACK_URL,
    SEVEN_ZIP_DOWNLOAD_PAGE,
    SEVEN_ZIP_FALLBACK_URLS,
)
from .errors import ManagerError
from .i18n import DEFAULT_LANGUAGE, translate
from .network import download_url_to_file


def _t(tr: Callable[..., str] | None, key: str, **kwargs: object) -> str:
    if tr is not None:
        return tr(key, **kwargs)
    return translate(DEFAULT_LANGUAGE, key, **kwargs)


def windows_arch() -> str:
    machine = platform.machine().casefold()
    if "arm" in machine and "64" in machine:
        return "arm64"
    if sys.maxsize > 2**32:
        return "x64"
    return "x86"


def find_7z(extra_dirs: Iterable[Path] | None = None) -> Path | None:
    candidates: list[str | Path | None] = []
    for directory in extra_dirs or []:
        candidates.extend(
            [
                directory / "7z.exe",
                directory / "x64" / "7z.exe",
                directory / "arm64" / "7z.exe",
            ]
        )
    candidates.extend(
        [
            shutil.which("7z"),
            shutil.which("7za"),
            r"C:\Program Files\7-Zip\7z.exe",
            r"C:\Program Files (x86)\7-Zip\7z.exe",
        ]
    )
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


def find_7z_in_dirs(directories: Iterable[Path]) -> Path | None:
    for directory in directories:
        candidates = [
            directory / "7z.exe",
            directory / "x64" / "7z.exe",
            directory / "arm64" / "7z.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
    return None


def find_bsdtar() -> Path | None:
    candidates = [
        shutil.which("bsdtar"),
        shutil.which("tar"),
        r"C:\Windows\System32\tar.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


def resolve_7zip_download_url() -> str:
    arch = windows_arch()
    fallback = SEVEN_ZIP_FALLBACK_URLS[arch]
    try:
        with urllib.request.urlopen(SEVEN_ZIP_DOWNLOAD_PAGE, timeout=25) as response:
            html = response.read().decode("utf-8", "replace")
    except Exception:
        return fallback

    urls = []
    for href in re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE):
        url = urllib.parse.urljoin(SEVEN_ZIP_DOWNLOAD_PAGE, href)
        filename = Path(urllib.parse.urlparse(url).path).name.casefold()
        if arch == "x64" and re.fullmatch(r"7z\d+-x64\.exe", filename):
            urls.append(url)
        elif arch == "arm64" and re.fullmatch(r"7z\d+-arm64\.exe", filename):
            urls.append(url)
        elif arch == "x86" and re.fullmatch(r"7z\d+\.exe", filename):
            urls.append(url)
    return urls[0] if urls else fallback


def resolve_7zr_download_url() -> str:
    try:
        with urllib.request.urlopen(SEVEN_ZIP_DOWNLOAD_PAGE, timeout=25) as response:
            html = response.read().decode("utf-8", "replace")
    except Exception:
        return SEVEN_ZIP_BOOTSTRAP_FALLBACK_URL

    for href in re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE):
        url = urllib.parse.urljoin(SEVEN_ZIP_DOWNLOAD_PAGE, href)
        filename = Path(urllib.parse.urlparse(url).path).name.casefold()
        if filename == "7zr.exe":
            return url
    return SEVEN_ZIP_BOOTSTRAP_FALLBACK_URL


class SevenZipManager:
    def __init__(self, tools_dir: Path, tr: Callable[..., str] | None = None) -> None:
        self.tools_dir = tools_dir
        self.seven_zip_dir = tools_dir / "7zip"
        self.tr = tr

    def ensure(
        self,
        log: Callable[[str], None] | None = None,
        tr: Callable[..., str] | None = None,
    ) -> Path:
        logger = log or (lambda _message: None)
        translator = tr or self.tr
        bundled = find_7z_in_dirs([self.seven_zip_dir])
        if bundled:
            return bundled

        if os.name != "nt":
            system_7z = find_7z()
            if system_7z:
                return system_7z
            raise ManagerError(_t(translator, "sevenzip_auto_download_unsupported"))

        bootstrap_dir = self.tools_dir / "7zip-bootstrap"
        bootstrap_dir.mkdir(parents=True, exist_ok=True)
        seven_zr = bootstrap_dir / "7zr.exe"
        if not seven_zr.exists():
            logger(_t(translator, "sevenzip_bootstrap_downloading"))
            download_url_to_file(
                resolve_7zr_download_url(),
                seven_zr,
                MAX_TOOL_DOWNLOAD_BYTES,
                logger,
                translator,
            )

        installer_url = resolve_7zip_download_url()
        installer = bootstrap_dir / Path(urllib.parse.urlparse(installer_url).path).name
        if not installer.exists():
            logger(_t(translator, "sevenzip_backend_downloading"))
            download_url_to_file(
                installer_url,
                installer,
                MAX_TOOL_DOWNLOAD_BYTES,
                logger,
                translator,
            )

        extract_dir = self.tools_dir / "7zip-extracting"
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            [str(seven_zr), "x", "-y", f"-o{extract_dir}", str(installer)],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            details = result.stderr.strip() or result.stdout.strip()
            raise ManagerError(_t(translator, "sevenzip_backend_extract_failed", details=details))

        extracted_7z = extract_dir / "7z.exe"
        extracted_dll = extract_dir / "7z.dll"
        if not extracted_7z.exists() or not extracted_dll.exists():
            raise ManagerError(_t(translator, "sevenzip_backend_missing_files"))

        if self.seven_zip_dir.exists():
            shutil.rmtree(self.seven_zip_dir)
        shutil.move(str(extract_dir), str(self.seven_zip_dir))
        logger(_t(translator, "sevenzip_backend_cached"))

        bundled = find_7z_in_dirs([self.seven_zip_dir])
        if not bundled:
            raise ManagerError(_t(translator, "sevenzip_backend_cache_failed"))
        return bundled
