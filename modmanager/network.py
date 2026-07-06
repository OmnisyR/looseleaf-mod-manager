from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Callable

from .errors import ManagerError
from .i18n import DEFAULT_LANGUAGE, translate


def _t(tr: Callable[..., str] | None, key: str, **kwargs: object) -> str:
    if tr is not None:
        return tr(key, **kwargs)
    return translate(DEFAULT_LANGUAGE, key, **kwargs)


def download_url_to_file(
    url: str,
    destination: Path,
    max_bytes: int,
    log: Callable[[str], None] | None = None,
    tr: Callable[..., str] | None = None,
) -> None:
    logger = log or (lambda _message: None)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_destination = destination.with_name(f"{destination.name}.download")
    temp_destination.unlink(missing_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "LooseleafModManager/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > max_bytes:
                        raise ManagerError(_t(tr, "download_size_exceeded"))
                except ValueError:
                    pass

            downloaded = 0
            with temp_destination.open("wb") as file:
                while True:
                    chunk = response.read(512 * 1024)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        raise ManagerError(_t(tr, "download_size_exceeded"))
                    file.write(chunk)
        temp_destination.replace(destination)
    finally:
        temp_destination.unlink(missing_ok=True)
    logger(_t(tr, "download_done", name=destination.name))
