from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modmanager import games


class GameDetectionTests(unittest.TestCase):
    def _dir(self) -> Path:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        return Path(self._tmp.name)

    def test_detects_known_game_by_exe(self) -> None:
        root = self._dir()
        (root / "sora_1st.exe").write_bytes(b"\0" * 10)
        profile = games.detect_profile(root)
        self.assertEqual(profile.id, "sora_1st")
        self.assertTrue(profile.known)
        self.assertEqual(profile.costume_catalog, "sora_1st.json")

    def test_generic_profile_from_exe_stem(self) -> None:
        root = self._dir()
        (root / "MyFalcomGame.exe").write_bytes(b"\0" * 4096)
        profile = games.detect_profile(root)
        self.assertFalse(profile.known)
        self.assertEqual(profile.id, "myfalcomgame")
        self.assertEqual(profile.display_name, "MyFalcomGame")

    def test_generic_profile_from_folder_when_no_exe(self) -> None:
        root = self._dir() / "Trails Game"
        (root / "asset").mkdir(parents=True)
        self.assertEqual(games.detect_profile(root).id, games.resolve_game_id(root))
        self.assertFalse(games.detect_profile(root).known)

    def test_ignores_helper_exes_when_naming(self) -> None:
        root = self._dir()
        (root / "unins000.exe").write_bytes(b"\0" * 999999)
        (root / "sora_1st.exe").write_bytes(b"\0" * 10)
        self.assertEqual(games.detect_profile(root).id, "sora_1st")

    def test_looks_like_game_dir(self) -> None:
        asset_dir = self._dir()
        (asset_dir / "asset").mkdir()
        self.assertTrue(games.looks_like_game_dir(asset_dir))

        table_dir = self._dir()
        (table_dir / "table_sc").mkdir()
        self.assertTrue(games.looks_like_game_dir(table_dir))

        exe_dir = self._dir()
        (exe_dir / "game.exe").write_bytes(b"\0")
        self.assertTrue(games.looks_like_game_dir(exe_dir))

        empty = self._dir()
        self.assertFalse(games.looks_like_game_dir(empty))

    def test_xinput_present(self) -> None:
        root = self._dir()
        self.assertFalse(games.xinput_present(root))
        (root / "xinput1_4.dll").write_bytes(b"\0")
        self.assertTrue(games.xinput_present(root))

    def test_steam_common_dirs_from_libraryfolders_vdf(self) -> None:
        root = self._dir() / "Steam"
        extra = self._dir() / "SteamLibrary"
        (root / "steamapps" / "common").mkdir(parents=True)
        (extra / "steamapps" / "common").mkdir(parents=True)
        escaped_root = str(root).replace("\\", "\\\\")
        escaped_extra = str(extra).replace("\\", "\\\\")
        (root / "steamapps" / "libraryfolders.vdf").write_text(
            '\n'.join(
                [
                    '"libraryfolders"',
                    "{",
                    '  "0"',
                    "  {",
                    f'    "path" "{escaped_root}"',
                    "  }",
                    '  "1"',
                    "  {",
                    f'    "path" "{escaped_extra}"',
                    "  }",
                    "}",
                ]
            ),
            encoding="utf-8",
        )

        self.assertEqual(
            games.steam_common_dirs(root),
            [root / "steamapps" / "common", extra / "steamapps" / "common"],
        )


if __name__ == "__main__":
    unittest.main()
