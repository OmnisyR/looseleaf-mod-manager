from __future__ import annotations

import tempfile
import threading
import unittest
import zipfile
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

from mod_manager import ModManagerCore


class QuietSimpleHTTPRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


class CoreSmokeTests(unittest.TestCase):
    def make_core(self, temp_root: Path) -> ModManagerCore:
        game_root = temp_root / "game"
        app_dir = game_root / "__manager"
        app_dir.mkdir(parents=True)
        return ModManagerCore(app_dir=app_dir, game_root=game_root)

    def test_nested_archive_import_and_apply(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
            core = self.make_core(temp_root)
            source_dir = temp_root / "source"
            source_dir.mkdir()

            inner_zip = source_dir / "inner.zip"
            with zipfile.ZipFile(inner_zip, "w") as archive:
                archive.writestr("hero.mdl", b"model")
                archive.writestr("hero.mi", b"model-info")
                archive.writestr("body.dds", b"texture")
                archive.writestr("asset/common/model/in_asset.mdl", b"in-asset")
                archive.writestr("asset/model_info/wrong_dir.mi", b"normalized-model-info")

            outer_zip = source_dir / "outer.zip"
            with zipfile.ZipFile(outer_zip, "w") as archive:
                archive.write(inner_zip, "packed/inner.zip")

            mod_id = core.import_path(outer_zip)
            mod = core.state["mods"][mod_id]

            self.assertIn("asset/common/model/hero.mdl", mod["files"])
            self.assertIn("asset/common/model_info/hero.mi", mod["files"])
            self.assertIn("asset/common/model_info/wrong_dir.mi", mod["files"])
            self.assertNotIn("asset/model_info/wrong_dir.mi", mod["files"])
            self.assertIn("asset/dx11/image/body.dds", mod["files"])
            self.assertIn("asset/common/model/in_asset.mdl", mod["files"])
            raw_source = core.absolute_data_path(mod["raw_source"])
            self.assertIsNotNone(raw_source)
            self.assertEqual(raw_source.name, outer_zip.name)
            self.assertEqual(raw_source.read_bytes(), outer_zip.read_bytes())

            core.apply_enabled()

            self.assertEqual((core.game_root / "asset/common/model/hero.mdl").read_bytes(), b"model")
            self.assertEqual((core.game_root / "asset/common/model_info/hero.mi").read_bytes(), b"model-info")
            self.assertEqual(
                (core.game_root / "asset/common/model_info/wrong_dir.mi").read_bytes(),
                b"normalized-model-info",
            )
            self.assertFalse((core.game_root / "asset/model_info/wrong_dir.mi").exists())
            self.assertEqual((core.game_root / "asset/dx11/image/body.dds").read_bytes(), b"texture")
            core.extra_costume_names_file.write_text('{"chr9999_c77": {"base_model": "chr9999"}}', encoding="utf-8")
            core.restore_game()
            self.assertEqual(json.loads(core.extra_costume_names_file.read_text(encoding="utf-8")), {})

    def test_legacy_asset_model_info_targets_are_relocated_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
            core = self.make_core(temp_root)
            mod_id = "bad-model-info"
            old_target = "asset/model_info/chr5101.mi"
            new_target = "asset/common/model_info/chr5101.mi"
            old_source = core.mod_files_root(mod_id) / "asset" / "model_info" / "chr5101.mi"
            old_source.parent.mkdir(parents=True)
            old_source.write_bytes(b"legacy-model-info")
            old_game_file = core.game_root / "asset" / "model_info" / "chr5101.mi"
            old_game_file.parent.mkdir(parents=True)
            old_game_file.write_bytes(b"previous-wrong-apply")
            core.state_file.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "created_at": "test",
                        "mods": {
                            mod_id: {
                                "id": mod_id,
                                "name": "Bad Model Info",
                                "enabled": True,
                                "files": [old_target],
                                "table_sources": [],
                            }
                        },
                        "order": [mod_id],
                        "backups": {},
                        "last_applied_targets": [old_target],
                    }
                ),
                encoding="utf-8",
            )

            reloaded = ModManagerCore(app_dir=core.app_dir, game_root=core.game_root)

            self.assertEqual(reloaded.state["mods"][mod_id]["files"], [new_target])
            self.assertTrue((reloaded.mod_files_root(mod_id) / "asset/common/model_info/chr5101.mi").exists())
            self.assertFalse((reloaded.mod_files_root(mod_id) / "asset/model_info/chr5101.mi").exists())

            reloaded.apply_enabled()

            self.assertFalse(old_game_file.exists())
            self.assertEqual(
                (reloaded.game_root / "asset/common/model_info/chr5101.mi").read_bytes(),
                b"legacy-model-info",
            )

    def test_conflict_winner_follows_order(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
            core = self.make_core(temp_root)

            first_dir = temp_root / "first"
            second_dir = temp_root / "second"
            first_dir.mkdir()
            second_dir.mkdir()
            (first_dir / "same.mdl").write_bytes(b"first")
            (second_dir / "same.mdl").write_bytes(b"second")

            first_id = core.import_path(first_dir)
            second_id = core.import_path(second_dir)

            conflicts = core.compute_conflicts()
            self.assertEqual(len(conflicts), 1)
            self.assertEqual(conflicts[0]["winner"], second_id)

            core.set_order([second_id, first_id])
            conflicts = core.compute_conflicts()
            self.assertEqual(conflicts[0]["winner"], first_id)

            core.apply_enabled()
            self.assertEqual((core.game_root / "asset/common/model/same.mdl").read_bytes(), b"first")

    def test_table_files_are_normalized_and_language_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
            core = self.make_core(temp_root)

            mod_source = temp_root / "custom_tables"
            (mod_source / "table_en").mkdir(parents=True)
            (mod_source / "table_fr").mkdir()
            (mod_source / "table_sc").mkdir()
            (mod_source / "table_en" / "t_costume.tbl").write_bytes(b"costume-en")
            (mod_source / "table_fr" / "t_costume.tbl").write_bytes(b"costume-fr")
            (mod_source / "table_en" / "t_shop.tbl").write_bytes(b"shop-en")
            (mod_source / "table_sc" / "t_shop.tbl").write_bytes(b"shop-sc")

            mod_id = core.import_path(mod_source)
            mod = core.state["mods"][mod_id]
            raw_source = core.absolute_data_path(mod["raw_source"])
            self.assertIsNotNone(raw_source)
            self.assertTrue(raw_source.is_dir())
            self.assertEqual((raw_source / "table_en" / "t_costume.tbl").read_bytes(), b"costume-en")

            self.assertNotIn("table_sc/t_costume.tbl", mod["files"])
            self.assertNotIn("table_sc/t_shop.tbl", mod["files"])
            self.assertNotIn("table_en/t_costume.tbl", mod["files"])
            self.assertNotIn("table_fr/t_costume.tbl", mod["files"])
            self.assertEqual(
                {(item["source_table_dir"], item["table_name"]) for item in mod["table_sources"]},
                {("table_en", "t_costume.tbl"), ("table_sc", "t_shop.tbl")},
            )

            stored = core.mod_files_root(mod_id)
            self.assertFalse((stored / "table_sc/t_shop.tbl").exists())
            self.assertEqual(
                (core.mods_dir / mod_id / "tables" / "table_sc" / "t_shop.tbl").read_bytes(),
                b"shop-sc",
            )

            core.apply_enabled()
            self.assertFalse((core.game_root / "table_sc/t_costume.tbl").exists())
            self.assertFalse((core.game_root / "table_sc/t_shop.tbl").exists())

    def test_foreign_prebuilt_tables_do_not_replace_active_language(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
            core = self.make_core(temp_root)

            mod_source = temp_root / "foreign_tables"
            (mod_source / "table_en").mkdir(parents=True)
            (mod_source / "table_fr").mkdir()
            (mod_source / "asset" / "common" / "model").mkdir(parents=True)
            (mod_source / "asset" / "common" / "model" / "chr5000_c20a.mdl").write_bytes(b"model")
            (mod_source / "table_en" / "t_item.tbl").write_bytes(b"english-items")
            (mod_source / "table_fr" / "t_item.tbl").write_bytes(b"french-items")

            logs: list[str] = []
            mod_id = core.import_path(mod_source, logs.append)
            mod = core.state["mods"][mod_id]

            self.assertIn("asset/common/model/chr5000_c20a.mdl", mod["files"])
            self.assertNotIn("table_sc/t_item.tbl", mod["files"])
            self.assertEqual(len(mod["table_sources"]), 1)
            self.assertEqual(mod["table_sources"][0]["source_table_dir"], "table_en")
            self.assertTrue(any("table files" in line or "表文件" in line for line in logs))

    def test_preview_url_is_downloaded_and_cached(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
            core = self.make_core(temp_root)

            mod_source = temp_root / "mod"
            mod_source.mkdir()
            (mod_source / "hero.mdl").write_bytes(b"model")
            mod_id = core.import_path(mod_source)

            web_root = temp_root / "web"
            web_root.mkdir()
            image_path = web_root / "preview.png"
            Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(image_path)

            handler = partial(QuietSimpleHTTPRequestHandler, directory=str(web_root))
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                url = f"http://127.0.0.1:{server.server_port}/preview.png"
                destination = core.set_preview_from_url(mod_id, url)
            finally:
                server.shutdown()
                server.server_close()

            self.assertTrue(destination.exists())
            self.assertTrue(destination.is_relative_to(core.mods_dir))
            self.assertEqual(core.state["mods"][mod_id]["preview_source_url"], url)
            self.assertEqual(Path(core.state["mods"][mod_id]["preview"]).name, "preview.png")

    def test_xinput_download_is_cached_in_game_root(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
            core = self.make_core(temp_root)

            web_root = temp_root / "web"
            web_root.mkdir()
            dll_bytes = bytearray(128)
            dll_bytes[:2] = b"MZ"
            dll_bytes[0x3C:0x40] = (0x40).to_bytes(4, "little")
            dll_bytes[0x40:0x44] = b"PE\0\0"
            (web_root / "xinput1_4.dll").write_bytes(dll_bytes)

            handler = partial(QuietSimpleHTTPRequestHandler, directory=str(web_root))
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                url = f"http://127.0.0.1:{server.server_port}/xinput1_4.dll"
                destination = core.download_xinput(url)
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(destination, core.game_root / "xinput1_4.dll")
            self.assertTrue(core.xinput_ok())
            self.assertEqual(destination.read_bytes(), dll_bytes)
            self.assertEqual(core.config.xinput_download_url, url)

    def test_config_persists_language_and_window_layout(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
            core = self.make_core(temp_root)
            core.set_language("en")
            core.config.set_window_value("geometry", "1024x700+20+30")
            core.config.set_window_value("state", "zoomed")
            core.config.set_window_value("main_sash", 640)
            core.save_config()

            stored = json.loads(core.config_file.read_text(encoding="utf-8"))
            self.assertEqual(stored["language"], "en")
            self.assertEqual(stored["window"]["geometry"], "1024x700+20+30")
            self.assertEqual(stored["window"]["state"], "zoomed")
            self.assertEqual(stored["window"]["main_sash"], 640)

            reloaded = ModManagerCore(app_dir=core.app_dir, game_root=core.game_root)
            self.assertEqual(reloaded.config.language, "en")
            self.assertEqual(reloaded.config.get_window_value("main_sash"), 640)


if __name__ == "__main__":
    unittest.main()
