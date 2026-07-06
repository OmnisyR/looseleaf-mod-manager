from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


APP_DIR = _app_dir()
GAME_ROOT = APP_DIR.parent
DATA_DIR_NAME = "manager_data"
MODEL_TARGET = PurePosixPath("asset/common/model")
MODEL_INFO_TARGET = PurePosixPath("asset/common/model_info")
IMAGE_TARGET = PurePosixPath("asset/dx11/image")
DEFAULT_TABLE_TARGET = "table_sc"

ARCHIVE_EXTENSIONS = (
    ".zip",
    ".7z",
    ".rar",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".tar.bz2",
    ".tbz2",
    ".tar.xz",
    ".txz",
    ".tar.zst",
    ".tzst",
)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
MOD_FILE_EXTENSIONS = {".mdl", ".mi", ".dds"}
CUSTOM_TABLE_FILES = {"t_costume.tbl", "t_dlc.tbl", "t_item.tbl", "t_shop.tbl"}
TABLE_LANGUAGE_PRIORITY = (
    "en",
    "sc",
    "tc",
    "kr",
    "jp",
    "ja",
    "fr",
    "de",
    "es",
    "it",
    "pt",
    "ru",
)
PREVIEW_FORMAT_EXTENSIONS = {
    "PNG": ".png",
    "JPEG": ".jpg",
    "WEBP": ".webp",
    "GIF": ".gif",
    "BMP": ".bmp",
    "TIFF": ".tiff",
}
MAX_PREVIEW_DOWNLOAD_BYTES = 50 * 1024 * 1024
MAX_XINPUT_DOWNLOAD_BYTES = 10 * 1024 * 1024
XINPUT_DOWNLOAD_URL = "https://github.com/Hinkiii/sora1looseload/releases/latest/download/xinput1_4.dll"
XINPUT_PROJECT_URL = "https://github.com/Hinkiii/sora1looseload"
SEVEN_ZIP_DOWNLOAD_PAGE = "https://www.7-zip.org/download.html"
SEVEN_ZIP_FALLBACK_URLS = {
    "x64": "https://github.com/ip7z/7zip/releases/download/26.02/7z2602-x64.exe",
    "x86": "https://github.com/ip7z/7zip/releases/download/26.02/7z2602.exe",
    "arm64": "https://github.com/ip7z/7zip/releases/download/26.02/7z2602-arm64.exe",
}
SEVEN_ZIP_BOOTSTRAP_FALLBACK_URL = "https://github.com/ip7z/7zip/releases/download/26.02/7zr.exe"
MAX_TOOL_DOWNLOAD_BYTES = 100 * 1024 * 1024
