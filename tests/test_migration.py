from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modmanager.config import ManagerConfig
from modmanager.migration import migrate_legacy_layout, repair_nested_game_data


class LegacyMigrationTests(unittest.TestCase):
    def _build_flat_layout(self, data_home: Path) -> None:
        (data_home / "mods" / "somemod" / "files").mkdir(parents=True)
        (data_home / "mods" / "somemod" / "files" / "x.mdl").write_bytes(b"model")
        (data_home / "backups" / "asset").mkdir(parents=True)
        (data_home / "table_cache").mkdir()
        (data_home / "tools").mkdir()  # global — must NOT move
        (data_home / "state.json").write_text('{"mods":{},"order":[]}', encoding="utf-8")
        (data_home / "extra_costume_names.json").write_text("{}", encoding="utf-8")

    def test_migrates_and_registers_detected_game(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            data_home = tmp / "manager_data"
            data_home.mkdir()
            self._build_flat_layout(data_home)
            game_root = tmp / "game"
            (game_root / "asset").mkdir(parents=True)
            (game_root / "sora_1st.exe").write_bytes(b"\0" * 10)

            config = ManagerConfig(data_home / "config.json")
            game_id = migrate_legacy_layout(data_home, game_root, config)

            self.assertEqual(game_id, "sora_1st")
            game_dir = data_home / "games" / "sora_1st"
            self.assertTrue((game_dir / "mods" / "somemod" / "files" / "x.mdl").exists())
            self.assertTrue((game_dir / "backups" / "asset").exists())
            self.assertTrue((game_dir / "state.json").exists())
            self.assertFalse((data_home / "state.json").exists())
            # tools stays global
            self.assertTrue((data_home / "tools").exists())
            self.assertFalse((game_dir / "tools").exists())
            # registered + active
            self.assertEqual(config.active_game_id, "sora_1st")
            self.assertEqual(config.get_game("sora_1st")["path"], str(game_root))

    def test_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            data_home = tmp / "manager_data"
            data_home.mkdir()
            self._build_flat_layout(data_home)
            game_root = tmp / "game"
            (game_root / "asset").mkdir(parents=True)

            config = ManagerConfig(data_home / "config.json")
            first = migrate_legacy_layout(data_home, game_root, config)
            second = migrate_legacy_layout(data_home, game_root, config)
            self.assertIsNotNone(first)
            self.assertIsNone(second)

    def test_completes_when_games_dir_pre_exists_empty(self) -> None:
        # Reproduces a half-migrated folder: core pre-creates games/<id> (and may
        # have registered the game) but the file move never ran. Migration must
        # still finish because the flat state.json is the trigger, not games/.
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            data_home = tmp / "manager_data"
            data_home.mkdir()
            self._build_flat_layout(data_home)
            (data_home / "games" / "sora_1st").mkdir(parents=True)  # empty, pre-existing
            game_root = tmp / "game"
            (game_root / "asset").mkdir(parents=True)
            (game_root / "sora_1st.exe").write_bytes(b"\0" * 10)

            config = ManagerConfig(data_home / "config.json")
            game_id = migrate_legacy_layout(data_home, game_root, config)

            self.assertEqual(game_id, "sora_1st")
            self.assertTrue(
                (data_home / "games" / "sora_1st" / "mods" / "somemod" / "files" / "x.mdl").exists()
            )
            self.assertFalse((data_home / "state.json").exists())

    def test_no_op_on_fresh_install(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            data_home = Path(raw) / "manager_data"
            data_home.mkdir()
            config = ManagerConfig(data_home / "config.json")
            self.assertIsNone(migrate_legacy_layout(data_home, Path(raw), config))

    def test_migration_does_not_nest_into_pre_created_dirs(self) -> None:
        # If per-game subdirs already exist (created by a prior activation), the
        # move must merge, not produce mods/mods/... .
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            data_home = tmp / "manager_data"
            data_home.mkdir()
            self._build_flat_layout(data_home)
            game_root = tmp / "game"
            (game_root / "asset").mkdir(parents=True)
            (game_root / "sora_1st.exe").write_bytes(b"\0" * 10)
            # pre-create the destination subdir (the bug trigger)
            (data_home / "games" / "sora_1st" / "mods").mkdir(parents=True)

            config = ManagerConfig(data_home / "config.json")
            migrate_legacy_layout(data_home, game_root, config)

            mods = data_home / "games" / "sora_1st" / "mods"
            self.assertFalse((mods / "mods").exists(), "data was nested one level too deep")
            self.assertTrue((mods / "somemod" / "files" / "x.mdl").exists())

    def test_repair_unnests_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            game_dir = Path(raw) / "games" / "sora_1st"
            nested = game_dir / "mods" / "mods" / "mymod" / "files"
            nested.mkdir(parents=True)
            (nested / "x.mdl").write_bytes(b"M")
            (game_dir / "backups" / "backups" / "a").mkdir(parents=True)

            self.assertTrue(repair_nested_game_data(game_dir))
            self.assertTrue((game_dir / "mods" / "mymod" / "files" / "x.mdl").exists())
            self.assertFalse((game_dir / "mods" / "mods").exists())
            self.assertFalse((game_dir / "backups" / "backups").exists())
            # second run is a no-op
            self.assertFalse(repair_nested_game_data(game_dir))


if __name__ == "__main__":
    unittest.main()
