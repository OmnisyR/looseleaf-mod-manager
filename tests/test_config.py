from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modmanager.config import ManagerConfig


class ConfigTests(unittest.TestCase):
    def _config(self) -> ManagerConfig:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        return ManagerConfig(Path(self._tmp.name) / "config.json")

    def test_default_language_uses_simplified_chinese_locale(self) -> None:
        with mock.patch("modmanager.config._locale_candidates", return_value=["zh-CN"]):
            self.assertEqual(self._config().language, "zh_CN")

    def test_default_language_uses_traditional_chinese_locale(self) -> None:
        with mock.patch("modmanager.config._locale_candidates", return_value=["zh-TW"]):
            self.assertEqual(self._config().language, "zh_CN")

    def test_default_language_uses_english_for_other_locales(self) -> None:
        with mock.patch("modmanager.config._locale_candidates", return_value=["ja-JP"]):
            self.assertEqual(self._config().language, "en")


if __name__ == "__main__":
    unittest.main()
