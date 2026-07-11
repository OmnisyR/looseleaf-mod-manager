from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from mod_manager import ModManagerCore
from modmanager.model_info import decode_model_info_json
from mistudio.binjson import encode_model_info_json
from mistudio.catalog import build_catalog, category_of
from mistudio.fields import FIELD_HELPS_EN, FIELD_INFO, field_help, field_range, mirror_name
from mistudio.workspace import (
    TWEAKS_MOD_ID,
    MiWorkspace,
    get_value,
    item_label,
    mirrored_path,
    set_value,
)


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


SAMPLE_DOC = {
    "Bounding": {"size": {"x": 1.0, "y": 1.5, "z": 0.5}, "type": 1, "offset": {"x": 0, "y": 0.8, "z": 0}},
    "DynamicBone": [
        {
            "Joint": [
                {"node": "LeftBreast", "damping": 0.1, "gravity": -0.98, "is_disable": False},
                {"node": "LeftBreast_Top", "damping": 0.3, "gravity": -0.1, "is_disable": False},
            ],
            "NeighborBones": [],
            "SpecificCollider": [],
            "ignore_collision": False,
        },
        {
            "Joint": [
                {"node": "RightBreast", "damping": 0.1, "gravity": -0.98, "is_disable": False},
                {"node": "RightBreast_Top", "damping": 0.3, "gravity": -0.1, "is_disable": False},
            ],
            "NeighborBones": [],
            "SpecificCollider": [],
            "ignore_collision": False,
        },
    ],
    "Locators": [{"name": "Head_Point", "node": "Head", "off_x": 0, "off_y": 0.1, "off_z": 0}],
    "Extra": {"door_type": 0},
    "Occluder": {"is_valid": False},
    "Empty": [],
    "Text": "中文字符串",
    "Null": None,
}


class BinJsonTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        data = encode_model_info_json(SAMPLE_DOC)
        self.assertTrue(data.startswith(b"JSON"))
        decoded = decode_model_info_json(data)
        self.assertEqual(decoded, SAMPLE_DOC)

    def test_header_layout(self) -> None:
        data = encode_model_info_json({"a": 1})
        data_start = struct.unpack_from("<I", data, 8)[0]
        self.assertEqual(data[data_start], 0x04)  # named object root
        # Dictionary begins with the empty root name (~crc32("") == 0xFFFFFFFF).
        self.assertEqual(data[16:20], b"\xff\xff\xff\xff")


class SymmetryTests(unittest.TestCase):
    def test_mirror_name(self) -> None:
        self.assertEqual(mirror_name("LeftBreast_Top"), "RightBreast_Top")
        self.assertEqual(mirror_name("RightUpLeg_atari"), "LeftUpLeg_atari")
        self.assertEqual(mirror_name("L_Skirt01"), "R_Skirt01")
        self.assertEqual(mirror_name("Skirt_l"), "Skirt_r")
        self.assertIsNone(mirror_name("Spine2_atari"))

    def test_mirrored_path(self) -> None:
        path = (("key", "DynamicBone"), ("item", "LeftBreast", 0), ("key", "Joint"), ("item", "LeftBreast_Top", 1), ("key", "damping"))
        mirrored = mirrored_path(path)
        self.assertEqual(mirrored[1], ("item", "RightBreast", 0))
        self.assertEqual(mirrored[3], ("item", "RightBreast_Top", 1))
        self.assertIsNone(mirrored_path((("key", "Bounding"), ("key", "type"))))

    def test_item_label_chain(self) -> None:
        self.assertEqual(item_label(SAMPLE_DOC["DynamicBone"][0]), "LeftBreast")
        self.assertEqual(item_label(SAMPLE_DOC["Locators"][0]), "Head_Point")


class SemanticPathTests(unittest.TestCase):
    def test_get_set_by_label(self) -> None:
        import copy

        doc = copy.deepcopy(SAMPLE_DOC)
        path = (("key", "DynamicBone"), ("item", "LeftBreast", 0), ("key", "Joint"), ("item", "LeftBreast_Top", 1), ("key", "damping"))
        self.assertEqual(get_value(doc, path), 0.3)
        self.assertTrue(set_value(doc, path, 0.7))
        self.assertEqual(doc["DynamicBone"][0]["Joint"][1]["damping"], 0.7)
        # Label matching must survive list reordering.
        doc["DynamicBone"].reverse()
        self.assertEqual(get_value(doc, path), 0.7)

    def test_field_range_widen(self) -> None:
        low, high = field_range("damping", 3.0)
        self.assertLessEqual(low, 0.0)
        self.assertGreaterEqual(high, 3.0)

    def test_english_help_covers_chinese_fields(self) -> None:
        missing = [name for name in FIELD_INFO if not FIELD_HELPS_EN.get(name)]
        self.assertEqual(missing, [])
        self.assertIn("damp", field_help("damping", "en").casefold())


class WorkspaceTests(unittest.TestCase):
    def make_core(self, temp_root: Path) -> ModManagerCore:
        game_root = temp_root / "game"
        app_dir = game_root / "__manager"
        app_dir.mkdir(parents=True)
        mi = encode_model_info_json(SAMPLE_DOC)
        write_fake_fpac(
            game_root / "pac" / "steam" / "asset_common_model_info.pac",
            [
                ("asset/common/model_info/chr0006.mi", mi),
                ("asset/common/model_info/chr0006_c01.mi", mi),
            ],
        )
        return ModManagerCore(app_dir=app_dir, game_root=game_root)

    def test_edit_symmetric_and_save(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            core = self.make_core(Path(raw_temp))
            catalog = build_catalog(core.game_root, core.state, core.mod_files_root, TWEAKS_MOD_ID)
            self.assertEqual(len(catalog), 2)
            entry = catalog["asset/common/model_info/chr0006.mi"]
            self.assertEqual(entry.origin, "official")
            baseline = entry.decode_baseline()
            self.assertEqual(baseline, SAMPLE_DOC)

            ws = MiWorkspace(core)
            path = (("key", "DynamicBone"), ("item", "LeftBreast", 0), ("key", "Joint"), ("item", "LeftBreast_Top", 1), ("key", "gravity"))
            result = ws.apply_edit([(entry.target, baseline)], path, -0.5, symmetric=True)
            self.assertEqual(result.applied, 1)
            self.assertEqual(result.mirrored, 1)
            doc = ws.get_doc(entry.target)
            self.assertEqual(doc["DynamicBone"][0]["Joint"][1]["gravity"], -0.5)
            self.assertEqual(doc["DynamicBone"][1]["Joint"][1]["gravity"], -0.5)
            self.assertTrue(ws.is_modified(entry.target, baseline))

            written, removed = ws.save_tweaks_mod(lambda target: baseline)
            self.assertEqual((written, removed), (1, 0))
            self.assertIn(TWEAKS_MOD_ID, core.state["mods"])
            self.assertEqual(core.state["order"][-1], TWEAKS_MOD_ID)
            saved = core.mod_files_root(TWEAKS_MOD_ID) / "asset" / "common" / "model_info" / "chr0006.mi"
            self.assertEqual(decode_model_info_json(saved.read_bytes()), doc)

            # A fresh workspace picks the saved tweak back up.
            ws2 = MiWorkspace(core)
            self.assertTrue(ws2.has_doc(entry.target))

            # Reverting removes the file and unregisters the mod.
            ws2.drop_doc(entry.target)
            written, removed = ws2.save_tweaks_mod(lambda target: baseline)
            self.assertEqual((written, removed), (0, 1))
            self.assertNotIn(TWEAKS_MOD_ID, core.state["mods"])

    def test_tweaks_mod_stays_last_and_wins(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            core = self.make_core(Path(raw_temp))
            ws = MiWorkspace(core)
            entry_target = "asset/common/model_info/chr0006.mi"
            ws.open_doc(entry_target, SAMPLE_DOC)
            doc = ws.get_doc(entry_target)
            doc["Extra"]["door_type"] = 5
            ws.save_tweaks_mod(lambda target: SAMPLE_DOC)

            # Another mod registered later must not displace the tweaks mod.
            core.state["mods"]["other-mod"] = {
                "id": "other-mod",
                "name": "Other",
                "enabled": True,
                "files": [entry_target],
                "table_sources": [],
            }
            core.state["order"].append("other-mod")
            core.save()
            ws.save_tweaks_mod(lambda target: SAMPLE_DOC)
            self.assertEqual(core.state["order"][-1], TWEAKS_MOD_ID)

            conflicts = core.compute_conflicts()
            self.assertEqual(len(conflicts), 1)
            self.assertEqual(conflicts[0]["winner"], TWEAKS_MOD_ID)

    def test_groups_and_import_sections(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            core = self.make_core(Path(raw_temp))
            ws = MiWorkspace(core)
            targets = ["asset/common/model_info/chr0006.mi", "asset/common/model_info/chr0006_c01.mi"]
            ws.add_to_group("测试组", targets)
            self.assertEqual(ws.group_names(), ["测试组"])
            self.assertEqual(ws.group_of(targets[0]), ["测试组"])

            source = {
                "DynamicBone": [
                    {
                        "Joint": [
                            {"node": "Hair", "damping": 0.9, "is_disable": "not-a-bool", "source_only": 1},
                            {"node": "Hair_Top", "gravity": -0.25},
                        ],
                        "ignore_collision": True,
                        "source_only": {"value": 1},
                    }
                ]
            }
            result = ws.import_sections(source, ["DynamicBone"], [(t, SAMPLE_DOC) for t in targets])
            self.assertEqual(result.applied, 2)
            self.assertEqual(result.changed_targets, targets)
            for target in targets:
                imported = ws.get_doc(target)
                self.assertEqual(len(imported["DynamicBone"]), 2)
                self.assertEqual(len(imported["DynamicBone"][0]["Joint"]), 2)
                self.assertEqual(imported["DynamicBone"][0]["Joint"][0]["node"], "Hair")
                self.assertEqual(imported["DynamicBone"][0]["Joint"][0]["damping"], 0.9)
                self.assertFalse(imported["DynamicBone"][0]["Joint"][0]["is_disable"])
                self.assertNotIn("source_only", imported["DynamicBone"][0]["Joint"][0])
                self.assertEqual(imported["DynamicBone"][0]["Joint"][1]["node"], "Hair_Top")
                self.assertEqual(imported["DynamicBone"][0]["Joint"][1]["gravity"], -0.25)
                self.assertTrue(imported["DynamicBone"][0]["ignore_collision"])
                self.assertNotIn("source_only", imported["DynamicBone"][0])
                self.assertEqual(imported["DynamicBone"][1], SAMPLE_DOC["DynamicBone"][1])
                self.assertEqual(imported["Bounding"], SAMPLE_DOC["Bounding"])

            untouched = "asset/common/model_info/chr0006.mi"
            ws.drop_doc(untouched)
            result = ws.import_sections({"Missing": {"value": 1}}, ["Missing"], [(untouched, SAMPLE_DOC)])
            self.assertEqual(result.applied, 0)
            self.assertEqual(result.skipped, [untouched])
            self.assertFalse(ws.has_doc(untouched))

            ws.remove_from_group("测试组", [targets[0]])
            self.assertEqual(ws.group_of(targets[0]), [])
            ws.delete_group("测试组")
            self.assertEqual(ws.group_names(), [])

            # Groups survive a workspace reload via mi_studio.json.
            ws.add_to_group("持久组", targets[:1])
            ws2 = MiWorkspace(core)
            self.assertEqual(ws2.group_names(), ["持久组"])


class CatalogTests(unittest.TestCase):
    def test_origin_classification(self) -> None:
        with tempfile.TemporaryDirectory() as raw_temp:
            temp_root = Path(raw_temp)
            game_root = temp_root / "game"
            app_dir = game_root / "__manager"
            app_dir.mkdir(parents=True)
            mi = encode_model_info_json(SAMPLE_DOC)
            write_fake_fpac(
                game_root / "pac" / "steam" / "asset_common_model_info.pac",
                [("asset/common/model_info/chr0006.mi", mi)],
            )
            core = ModManagerCore(app_dir=app_dir, game_root=game_root)

            override_target = "asset/common/model_info/chr0006.mi"
            new_target = "asset/common/model_info/chr9999_c99.mi"
            mod_root = core.mod_files_root("some-mod")
            for target in (override_target, new_target):
                path = mod_root / Path(target)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(mi)
            core.state["mods"]["some-mod"] = {
                "id": "some-mod",
                "name": "Some Mod",
                "enabled": True,
                "files": [override_target, new_target],
                "table_sources": [],
            }
            core.state["order"].append("some-mod")
            core.save()

            catalog = build_catalog(core.game_root, core.state, core.mod_files_root, TWEAKS_MOD_ID)
            self.assertEqual(catalog[override_target].origin, "mod_override")
            self.assertEqual(catalog[override_target].baseline.kind, "mod")
            self.assertEqual(catalog[new_target].origin, "mod_new")
            self.assertEqual(catalog[new_target].character_id, "chr9999")

    def test_category_of(self) -> None:
        self.assertEqual(category_of("chr0006_c01"), "角色")
        self.assertEqual(category_of("ob4061isu01"), "物件")
        self.assertEqual(category_of("mon123"), "怪物")
        self.assertEqual(category_of("equ001"), "装备")
        self.assertEqual(category_of("xipha01"), "其他")


if __name__ == "__main__":
    unittest.main()


class ScreenGeometryTests(unittest.TestCase):
    BOUNDS = (0, 0, 1920, 1080)

    def test_offscreen_position_is_dropped(self) -> None:
        from modmanager.ui.screen import sanitize_geometry

        # The exact geometry that produced the "black window": saved on a
        # disconnected monitor to the left of the primary display.
        self.assertEqual(sanitize_geometry("1500x920+-2076+322", self.BOUNDS, "1500x920"), "1500x920")
        self.assertEqual(sanitize_geometry("1180x800+-2249+431", self.BOUNDS, "1180x800"), "1180x800")

    def test_valid_position_is_kept(self) -> None:
        from modmanager.ui.screen import sanitize_geometry

        self.assertEqual(sanitize_geometry("1500x920+100+50", self.BOUNDS, "1500x920"), "1500x920+100+50")
        # Multi-monitor: negative coordinates are fine when that area exists.
        # Tk syntax requires "+-2076" (a bare "-2076" would mean "from the
        # right edge" and place the window somewhere unrelated).
        wide = (-2560, 0, 4480, 1440)
        self.assertEqual(sanitize_geometry("1500x920+-2076+322", wide, "1500x920"), "1500x920+-2076+322")

    def test_edge_relative_position_is_dropped(self) -> None:
        from modmanager.ui.screen import sanitize_geometry

        # "-100+50" is right-edge-relative; we cannot validate it, so keep size only.
        self.assertEqual(sanitize_geometry("1500x920-100+50", self.BOUNDS, "1500x920"), "1500x920")

    def test_oversized_window_is_clamped(self) -> None:
        from modmanager.ui.screen import sanitize_geometry

        self.assertEqual(sanitize_geometry("2560x1417+100+50", self.BOUNDS, "1500x920"), "1920x1080+100+50")

    def test_garbage_falls_back_to_default(self) -> None:
        from modmanager.ui.screen import sanitize_geometry

        self.assertEqual(sanitize_geometry("", self.BOUNDS, "1500x920"), "1500x920")
        self.assertEqual(sanitize_geometry("banana", self.BOUNDS, "1500x920"), "1500x920")
