from __future__ import annotations

import tempfile
import threading
import unittest
import zipfile
import json
import struct
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from PIL import Image

from mod_manager import ModManagerCore
from modmanager.cel_shading import CelShadingPatchResult


class QuietSimpleHTTPRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def write_fake_fpac(path: Path, entries: list[tuple[str, bytes]]) -> None:
    index_size = 16 + len(entries) * 32
    name_blob = bytearray()
    name_offsets: list[int] = []
    for name, _data in entries:
        name_offsets.append(index_size + len(name_blob))
        name_blob.extend(name.encode("utf-8") + b"\0")

    data_start = index_size + len(name_blob)
    data_blob = bytearray()
    raw_entries = []
    for index, (_name, data) in enumerate(entries):
        data_offset = data_start + len(data_blob)
        raw_entries.append((0, name_offsets[index], len(data), data_offset))
        data_blob.extend(data)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as file:
        file.write(b"FPAC")
        file.write(struct.pack("<3I", len(entries), data_start, 0))
        for raw_entry in raw_entries:
            file.write(struct.pack("<4Q", *raw_entry))
        file.write(name_blob)
        file.write(data_blob)


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

    def test_cel_shading_patch_record_is_created_after_target(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
            core = self.make_core(temp_root)

            mod_source = temp_root / "cel_target"
            mod_source.mkdir()
            (mod_source / "chr5000_c20.mdl").write_bytes(b"model")
            target_id = core.import_path(mod_source)
            target_file = "asset/common/model/chr5000_c20.mdl"

            def fake_generate(**kwargs: object) -> CelShadingPatchResult:
                patch_dir = kwargs["patch_dir"]
                self.assertIsInstance(patch_dir, Path)
                output = patch_dir / "files" / "asset" / "common" / "model" / "chr5000_c20.mdl"
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"cel")
                return CelShadingPatchResult(
                    generated_files=[target_file],
                    changed_material_count=1,
                    changed_names={"body_skin": 1},
                    skipped=[],
                )

            with mock.patch("modmanager.core.generate_cel_shading_patch_files", side_effect=fake_generate) as generate:
                result = core.generate_cel_shading_patch(target_id)
                patch_id = str(result["patch_id"])

                self.assertEqual(core.state["order"], [target_id, patch_id])
                self.assertEqual(core.state["mods"][patch_id]["cel_shading_target_id"], target_id)
                self.assertEqual(core.state["mods"][patch_id]["files"], [target_file])
                self.assertTrue((core.mod_files_root(patch_id) / "asset/common/model/chr5000_c20.mdl").exists())

                second = core.generate_cel_shading_patch(target_id)
                self.assertEqual(second["patch_id"], patch_id)
                self.assertEqual(core.state["order"].count(patch_id), 1)
                self.assertEqual(len(core.state["mods"]), 2)
                self.assertEqual(generate.call_count, 2)

    def test_apply_does_not_create_game_file_backups(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
            core = self.make_core(temp_root)

            mod_source = temp_root / "loose_mod"
            mod_source.mkdir()
            (mod_source / "hero.mdl").write_bytes(b"model")
            core.import_path(mod_source)

            core.apply_enabled()

            self.assertFalse((core.game_data_dir / "backups").exists())
            state = json.loads(core.state_file.read_text(encoding="utf-8"))
            self.assertNotIn("backups", state)

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

    def test_model_info_diff_uses_original_from_pac_cache(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
            core = self.make_core(temp_root)
            original = b"JSON\0\0\0\0\0\0\0\0\0\0\0\0Root\0"
            modified = b"JSON\0\0\0\0\0\0\0\0\0\0\0\0Root\0LeftBreast\0"
            write_fake_fpac(
                core.game_root / "pac" / "steam" / "asset_common_model_info.pac",
                [("model_info/hero.mi", original)],
            )

            mod_source = temp_root / "model_info_mod"
            mod_source.mkdir()
            (mod_source / "hero.mi").write_bytes(modified)
            mod_id = core.import_path(mod_source)

            diffs = core.model_info_diffs_for_mod(mod_id)
            diff = diffs["asset/common/model_info/hero.mi"]
            self.assertEqual(diff["status"], "changed")
            self.assertEqual(diff["original_size"], len(original))
            self.assertEqual(diff["modified_size"], len(modified))
            cache_path = core.model_info_cache_dir / "asset" / "common" / "model_info" / "hero.mi"
            self.assertEqual(cache_path.read_bytes(), original)

    def test_model_info_diff_requires_original_from_pac(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
            core = self.make_core(temp_root)
            target = "asset/common/model_info/new_costume.mi"
            modified = b"JSON\0\0\0\0\0\0\0\0\0\0\0\0Root\0AddedModelInfo\0"

            game_file = core.game_root / "asset" / "common" / "model_info" / "new_costume.mi"
            game_file.parent.mkdir(parents=True)
            game_file.write_bytes(modified)
            cache_path = core.model_info_cache_dir / "asset" / "common" / "model_info" / "new_costume.mi"
            cache_path.parent.mkdir(parents=True)
            cache_path.write_bytes(modified)

            mod_source = temp_root / "added_model_info_mod"
            mod_source.mkdir()
            (mod_source / "new_costume.mi").write_bytes(modified)
            mod_id = core.import_path(mod_source)

            diff = core.model_info_diff_for_target(mod_id, target)
            self.assertIsNotNone(diff)
            self.assertEqual(diff["status"], "missing_original")
            self.assertTrue(cache_path.exists())

    def test_model_info_diff_uses_prior_mod_for_added_model_info(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
            core = self.make_core(temp_root)
            target = "asset/common/model_info/new_costume.mi"
            base = b"JSON\0\0\0\0\0\0\0\0\0\0\0\0Root\0AddedModelInfo\0Base\0"
            modified = b"JSON\0\0\0\0\0\0\0\0\0\0\0\0Root\0AddedModelInfo\0Modified\0"

            base_source = temp_root / "base_added_model_info"
            base_source.mkdir()
            (base_source / "new_costume.mi").write_bytes(base)
            base_id = core.import_path(base_source)

            override_source = temp_root / "override_added_model_info"
            override_source.mkdir()
            (override_source / "new_costume.mi").write_bytes(modified)
            override_id = core.import_path(override_source)

            base_diff = core.model_info_diff_for_target(base_id, target)
            self.assertIsNotNone(base_diff)
            self.assertEqual(base_diff["status"], "missing_original")

            override_diff = core.model_info_diff_for_target(override_id, target)
            self.assertIsNotNone(override_diff)
            self.assertEqual(override_diff["status"], "changed")
            self.assertEqual(override_diff["original_size"], len(base))
            self.assertEqual(override_diff["modified_size"], len(modified))

    def test_config_persists_language_and_window_layout(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
            core = self.make_core(temp_root)
            core.set_language("en")
            core.set_model_info_diff_enabled(True)
            core.config.set_window_value("geometry", "1024x700+20+30")
            core.config.set_window_value("state", "zoomed")
            core.config.set_window_value("main_sash", 640)
            core.save_config()

            stored = json.loads(core.config_file.read_text(encoding="utf-8"))
            self.assertEqual(stored["language"], "en")
            self.assertTrue(stored["advanced"]["model_info_diff"])
            self.assertEqual(stored["window"]["geometry"], "1024x700+20+30")
            self.assertEqual(stored["window"]["state"], "zoomed")
            self.assertEqual(stored["window"]["main_sash"], 640)

            reloaded = ModManagerCore(app_dir=core.app_dir, game_root=core.game_root)
            self.assertEqual(reloaded.config.language, "en")
            self.assertTrue(reloaded.config.model_info_diff_enabled)
            self.assertEqual(reloaded.config.get_window_value("main_sash"), 640)


if __name__ == "__main__":
    unittest.main()
