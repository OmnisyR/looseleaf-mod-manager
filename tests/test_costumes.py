from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modmanager import costumes


class CostumeLookupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._extra_dir = tempfile.TemporaryDirectory()
        self._original_extra_path = costumes.EXTRA_DATA_PATH
        # Pin the base catalog to the shipped Sora 1st file: other tests instantiate
        # ModManagerCore, which repoints these module globals via configure_paths().
        self._original_base_path = costumes.BASE_DATA_PATH
        costumes.BASE_DATA_PATH = costumes.COSTUMES_DIR / "sora_1st.json"
        costumes.EXTRA_DATA_PATH = Path(self._extra_dir.name) / "extra_costume_names.json"
        costumes.reload_catalog()

    def tearDown(self) -> None:
        costumes.EXTRA_DATA_PATH = self._original_extra_path
        costumes.BASE_DATA_PATH = self._original_base_path
        costumes.reload_catalog()
        self._extra_dir.cleanup()

    def test_known_costume_resolves_both_languages(self) -> None:
        info = costumes.lookup("chr5000_c01")
        self.assertIsNotNone(info)
        self.assertEqual(info.base_model, "chr5000")
        self.assertTrue(info.en)
        self.assertTrue(info.cn)

    def test_describe_target_matches_model_and_texture_paths(self) -> None:
        model_desc = costumes.describe_target("asset/common/model/chr5000_c01.mdl")
        texture_desc = costumes.describe_target("asset/dx11/image/CHR5000_C01.dds")
        self.assertIsNotNone(model_desc)
        self.assertEqual(model_desc, texture_desc)

    def test_unknown_target_returns_none(self) -> None:
        self.assertIsNone(costumes.describe_target("table_sc/t_shop.tbl"))
        self.assertIsNone(costumes.describe_target("asset/common/model/not_a_costume.mdl"))

    def test_modified_costumes_includes_unknown_models_last(self) -> None:
        changes = costumes.modified_costumes(
            [
                "asset/common/model/chr9999_c77.mdl",
                "asset/common/model/chr5000_c01.mdl",
                "asset/common/model/chr5000_face.mdl",
                "asset/common/model/equ0310.mdl",
                "asset/dx11/image/chr5000_c01.dds",
            ],
            "en",
        )

        self.assertEqual([change.file_name for change in changes], ["chr5000_c01.mdl", "chr9999_c77.mdl"])
        self.assertTrue(changes[0].recognized)
        self.assertEqual(changes[0].character_id, "chr5000")
        self.assertEqual(changes[0].character_name, "Estelle")
        self.assertFalse(changes[1].recognized)
        self.assertEqual(changes[1].display_name, "chr9999_c77.mdl")
        self.assertEqual(changes[1].character_id, "chr9999")
        self.assertEqual(changes[1].character_name, "chr9999")

    def test_modified_assets_filter_by_kind_and_sort_all_by_filename(self) -> None:
        files = [
            "asset/dx11/image/z_texture.dds",
            "asset/common/model_info/b_model.mi",
            "asset/common/model/chr5000_c01.mdl",
            "asset/common/model/equ0310.mdl",
            "asset/dx11/image/chr5000_c01.dds",
            "asset/common/model_info/a_model.mi",
        ]

        costumes_only = costumes.modified_assets(files, "costumes", "en")
        self.assertEqual([asset.file_name for asset in costumes_only], ["chr5000_c01.mdl"])
        self.assertEqual(costumes_only[0].kind, "costume")

        model_info = costumes.modified_assets(files, "model_info", "en")
        self.assertEqual([asset.file_name for asset in model_info], ["a_model.mi", "b_model.mi"])
        self.assertTrue(all(asset.kind == "model_info" for asset in model_info))

        textures = costumes.modified_assets(files, "textures", "en")
        self.assertEqual([asset.file_name for asset in textures], ["chr5000_c01.dds", "z_texture.dds"])
        self.assertTrue(all(asset.kind == "texture" for asset in textures))

        all_assets = costumes.modified_assets(files, "all", "en")
        self.assertEqual(
            [asset.file_name for asset in all_assets],
            ["a_model.mi", "b_model.mi", "chr5000_c01.dds", "chr5000_c01.mdl", "z_texture.dds"],
        )

    def test_costume_characters_groups_known_and_unknown_models(self) -> None:
        characters = costumes.costume_characters(
            [
                "asset/common/model/chr9999_c77.mdl",
                "asset/common/model/chr5000_c01.mdl",
                "asset/common/model/chr5000_c02.mdl",
                "asset/common/model/chr0001_c01.mdl",
            ],
            "en",
        )

        self.assertIn(("chr5000", "Estelle"), characters)
        self.assertIn(("chr0001", "Joshua"), characters)
        self.assertIn(("chr9999", "chr9999"), characters)
        self.assertEqual(len(characters), 3)
        self.assertEqual([key for key, _name in characters], ["chr0001", "chr5000", "chr9999"])

    def test_extra_catalog_extends_unknown_costume_lookup(self) -> None:
        costumes.EXTRA_DATA_PATH.write_text(
            json.dumps(
                {
                    "chr9999_c77": {
                        "base_model": "chr9999",
                        "en": "Custom Table Costume",
                    }
                }
            ),
            encoding="utf-8",
        )
        costumes.reload_catalog()

        info = costumes.lookup("chr9999_c77")
        self.assertIsNotNone(info)
        self.assertEqual(info.en, "Custom Table Costume")

        changes = costumes.modified_costumes(["asset/common/model/chr9999_c77.mdl"], "en")
        self.assertEqual(changes[0].display_name, "Custom Table Costume")
        self.assertTrue(changes[0].recognized)

    def test_test_name_artifacts_are_filtered_out(self) -> None:
        info = costumes.lookup("chr5000_c02")
        self.assertIsNotNone(info)
        self.assertNotIn("Test", info.en or "")


if __name__ == "__main__":
    unittest.main()
