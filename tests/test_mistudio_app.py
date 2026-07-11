from __future__ import annotations

import copy
import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk

from mod_manager import ModManagerCore
from modmanager.model_info import decode_model_info_json
from mistudio.binjson import encode_model_info_json
from mistudio.workspace import TWEAKS_MOD_ID

from tests.test_mistudio_core import SAMPLE_DOC, write_fake_fpac


def is_under(tree, iid: str, ancestor: str) -> bool:
    parent = tree.parent(iid)
    while parent:
        if parent == ancestor:
            return True
        parent = tree.parent(parent)
    return False


def make_core(temp_root: Path) -> ModManagerCore:
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
    core = ModManagerCore(app_dir=app_dir, game_root=game_root)
    core.config.language = "zh_CN"
    core.config.save()
    return core


def add_override_mod(core: ModManagerCore, target: str, doc: dict, mod_id: str = "override-mod", name: str = "Override Mod") -> None:
    path = core.mod_files_root(mod_id) / Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_model_info_json(doc))
    core.state["mods"][mod_id] = {
        "id": mod_id,
        "name": name,
        "enabled": True,
        "files": [target],
        "table_sources": [],
    }
    core.state["order"].append(mod_id)
    core.save()


class MiStudioAppSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:  # headless environment
            self.skipTest(f"Tk unavailable: {exc}")
        self.root.withdraw()

    def tearDown(self) -> None:
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_edit_flow_and_save(self) -> None:
        from mistudio.app import MiStudioApp

        with tempfile.TemporaryDirectory() as raw_temp:
            core = make_core(Path(raw_temp))
            app = MiStudioApp(self.root, core)
            app.wait_until_loaded()
            self.root.update()

            target = "asset/common/model_info/chr0006.mi"
            row = next(iid for iid, t in app._row_targets.items() if t == target)
            app.list_tree.selection_set(row)
            app.list_tree.focus(row)
            app._on_list_select(None)
            self.root.update()
            self.assertIsNotNone(app.current_entry)
            self.assertEqual(app.current_entry.target, target)

            leaf = next(
                iid
                for iid, path in app._leaf_paths.items()
                if path[-1] == ("key", "gravity") and ("item", "LeftBreast_Top", 1) in path
            )
            app.struct_tree.selection_set(leaf)
            app._on_struct_select(None)
            self.assertEqual(app._edit_kind, "number")
            self.assertEqual(str(app.sym_check.cget("state")), "normal")

            app.value_var.set("-0.5")
            app._commit_from_entry()
            doc = app.workspace.get_doc(target)
            self.assertEqual(doc["DynamicBone"][0]["Joint"][1]["gravity"], -0.5)
            self.assertEqual(doc["DynamicBone"][1]["Joint"][1]["gravity"], -0.5)  # symmetric
            self.assertTrue(app._dirty)
            self.assertIn("未保存调整", app.list_tree.set(row, "state"))

            app._save()
            self.assertFalse(app._dirty)
            self.assertIn("已保存调整", app.list_tree.set(row, "state"))
            self.assertEqual(core.state["order"][-1], TWEAKS_MOD_ID)
            saved = core.mod_files_root(TWEAKS_MOD_ID) / "asset" / "common" / "model_info" / "chr0006.mi"
            self.assertEqual(decode_model_info_json(saved.read_bytes()), doc)

    def test_group_scope_edit(self) -> None:
        from mistudio.app import MiStudioApp

        with tempfile.TemporaryDirectory() as raw_temp:
            core = make_core(Path(raw_temp))
            app = MiStudioApp(self.root, core)
            app.wait_until_loaded()
            self.root.update()

            targets = ["asset/common/model_info/chr0006.mi", "asset/common/model_info/chr0006_c01.mi"]
            app.workspace.add_to_group("组A", targets)
            app._refresh_group_filter()
            app._refresh_list()

            row = next(iid for iid, t in app._row_targets.items() if t == targets[0])
            app.list_tree.selection_set(row)
            app.list_tree.focus(row)
            app._on_list_select(None)

            leaf = next(
                iid
                for iid, path in app._leaf_paths.items()
                if path[-1] == ("key", "damping") and ("item", "LeftBreast", 0) in path and ("item", "LeftBreast_Top", 1) not in path
            )
            app.struct_tree.selection_set(leaf)
            app._on_struct_select(None)

            group_index = next(i for i, (label, _fn) in enumerate(app._scope_options) if label.startswith("组：组A"))
            app.scope_combo.current(group_index)
            app.value_var.set("0.8")
            app._commit_from_entry()

            for target in targets:
                doc = app.workspace.get_doc(target)
                self.assertEqual(doc["DynamicBone"][0]["Joint"][0]["damping"], 0.8)
                self.assertEqual(doc["DynamicBone"][1]["Joint"][0]["damping"], 0.8)

    def test_sections_start_collapsed(self) -> None:
        from mistudio.app import FAV_ROOT, MiStudioApp

        with tempfile.TemporaryDirectory() as raw_temp:
            core = make_core(Path(raw_temp))
            app = MiStudioApp(self.root, core)
            app.wait_until_loaded()
            self.root.update()
            row = next(iter(app._row_targets))
            app.list_tree.selection_set(row)
            app.list_tree.focus(row)
            app._on_list_select(None)

            for iid in app.struct_tree.get_children():
                opened = bool(app.struct_tree.item(iid, "open"))
                if iid == FAV_ROOT:
                    self.assertTrue(opened)
                else:
                    self.assertFalse(opened, f"section {iid} should start collapsed")

    def test_struct_selection_survives_commit(self) -> None:
        from mistudio.app import MiStudioApp

        with tempfile.TemporaryDirectory() as raw_temp:
            core = make_core(Path(raw_temp))
            app = MiStudioApp(self.root, core)
            app.wait_until_loaded()
            self.root.update()
            target = "asset/common/model_info/chr0006.mi"
            row = next(iid for iid, t in app._row_targets.items() if t == target)
            app.list_tree.selection_set(row)
            app.list_tree.focus(row)
            app._on_list_select(None)

            leaf = next(iid for iid, path in app._leaf_paths.items() if path[-1] == ("key", "gravity"))
            app.struct_tree.selection_set(leaf)
            app._on_struct_select(None)
            app.value_var.set("-0.33")
            app._commit_from_entry()

            # The bug: committing rebuilt the left list, which re-fired the
            # selection event and rebuilt the structure tree.
            self.assertTrue(app.struct_tree.exists(leaf))
            self.assertEqual(app.struct_tree.selection(), (leaf,))
            self.assertEqual(app._edit_path, app._leaf_paths[leaf])
            self.assertIn("● 未保存调整", app.list_tree.set(row, "state"))

    def test_official_baseline_ignores_mods(self) -> None:
        from mistudio.app import MiStudioApp

        with tempfile.TemporaryDirectory() as raw_temp:
            core = make_core(Path(raw_temp))
            target = "asset/common/model_info/chr0006.mi"
            mod_doc = copy.deepcopy(SAMPLE_DOC)
            mod_doc["DynamicBone"][0]["Joint"][1]["gravity"] = -0.7  # mod changes gravity
            add_override_mod(core, target, mod_doc)

            app = MiStudioApp(self.root, core)
            app.wait_until_loaded()
            self.root.update()
            row = next(iid for iid, t in app._row_targets.items() if t == target)
            app.list_tree.selection_set(row)
            app.list_tree.focus(row)
            app._on_list_select(None)

            leaf = next(
                iid
                for iid, path in app._leaf_paths.items()
                if path[-1] == ("key", "gravity") and ("item", "LeftBreast_Top", 1) in path
            )
            values = app.struct_tree.item(leaf, "values")
            self.assertEqual(values[0], "-0.7")  # current = effective mod value
            self.assertEqual(values[1], "-0.1")  # baseline = official pac value
            # Editing starts from the mod values, not from pac.
            self.assertEqual(app._effective_doc(target)["DynamicBone"][0]["Joint"][1]["gravity"], -0.7)
            self.assertEqual(app._official_doc(target)["DynamicBone"][0]["Joint"][1]["gravity"], -0.1)
            # No user edit yet: the file must not count as modified.
            self.assertFalse(app._is_modified(target))

            # Reference column: pick the mod as reference source.
            labels = list(app.ref_combo.cget("values"))
            self.assertIn("Override Mod", labels)
            app.ref_combo.current(labels.index("Override Mod"))
            app._on_ref_selected(None)
            self.assertEqual(app.struct_tree.item(leaf, "values")[2], "-0.7")

    def test_mod_new_baseline_uses_mod_preset(self) -> None:
        from mistudio.app import MiStudioApp

        with tempfile.TemporaryDirectory() as raw_temp:
            core = make_core(Path(raw_temp))
            target = "asset/common/model_info/chr9999_c99.mi"
            mod_doc = copy.deepcopy(SAMPLE_DOC)
            mod_doc["DynamicBone"][0]["Joint"][1]["gravity"] = -0.7
            add_override_mod(core, target, mod_doc, mod_id="new-costume", name="New Costume")

            app = MiStudioApp(self.root, core)
            app.wait_until_loaded()
            self.root.update()
            row = next(iid for iid, t in app._row_targets.items() if t == target)
            app.list_tree.selection_set(row)
            app.list_tree.focus(row)
            app._on_list_select(None)

            leaf = next(
                iid
                for iid, path in app._leaf_paths.items()
                if path[-1] == ("key", "gravity") and ("item", "LeftBreast_Top", 1) in path
            )
            values = app.struct_tree.item(leaf, "values")
            self.assertEqual(values[0], "-0.7")
            self.assertEqual(values[1], "-0.7")  # no pac: baseline is the mod preset
            self.assertIsNone(app._official_doc(target))
            self.assertEqual(app._baseline_doc(target)["DynamicBone"][0]["Joint"][1]["gravity"], -0.7)

            app.struct_tree.selection_set(leaf)
            app._on_struct_select(None)
            app.value_var.set("-0.2")
            app._commit_from_entry()
            self.assertEqual(app.workspace.get_doc(target)["DynamicBone"][0]["Joint"][1]["gravity"], -0.2)
            app._reset_field()
            self.assertEqual(app.workspace.get_doc(target)["DynamicBone"][0]["Joint"][1]["gravity"], -0.7)

    def test_reference_can_use_any_mod_file(self) -> None:
        from mistudio.app import MiStudioApp

        with tempfile.TemporaryDirectory() as raw_temp:
            core = make_core(Path(raw_temp))
            target = "asset/common/model_info/chr0006.mi"
            same_file_doc = copy.deepcopy(SAMPLE_DOC)
            same_file_doc["DynamicBone"][0]["Joint"][1]["gravity"] = -0.7
            add_override_mod(core, target, same_file_doc, mod_id="same-file", name="Same File Mod")

            other_target = "asset/common/model_info/chr9999_c99.mi"
            other_doc = copy.deepcopy(SAMPLE_DOC)
            other_doc["DynamicBone"][0]["Joint"][1]["gravity"] = -0.4
            add_override_mod(core, other_target, other_doc, mod_id="other-file", name="Other File Mod")

            app = MiStudioApp(self.root, core)
            app.wait_until_loaded()
            self.root.update()
            row = next(iid for iid, t in app._row_targets.items() if t == target)
            app.list_tree.selection_set(row)
            app.list_tree.focus(row)
            app._on_list_select(None)

            leaf = next(
                iid
                for iid, path in app._leaf_paths.items()
                if path[-1] == ("key", "gravity") and ("item", "LeftBreast_Top", 1) in path
            )
            self.assertEqual(app.struct_tree.item(leaf, "values")[2], "-0.7")  # default: same-file mod

            mod_labels = list(app.ref_combo.cget("values"))
            self.assertIn("Other File Mod", mod_labels)
            app.ref_combo.current(mod_labels.index("Other File Mod"))
            app._on_ref_selected(None)
            file_labels = list(app.ref_file_combo.cget("values"))
            self.assertTrue(any("chr9999_c99.mi" in label for label in file_labels))
            self.assertEqual(app.struct_tree.item(leaf, "values")[2], "-0.4")

    def test_locked_reference_survives_file_switch(self) -> None:
        from mistudio.app import MiStudioApp

        with tempfile.TemporaryDirectory() as raw_temp:
            core = make_core(Path(raw_temp))
            first = "asset/common/model_info/chr0006.mi"
            second = "asset/common/model_info/chr0006_c01.mi"
            fixed_ref = "asset/common/model_info/chr9999_c99.mi"

            ref_doc = copy.deepcopy(SAMPLE_DOC)
            ref_doc["DynamicBone"][0]["Joint"][1]["gravity"] = -0.4
            add_override_mod(core, fixed_ref, ref_doc, mod_id="fixed-ref", name="Fixed Ref Mod")

            second_doc = copy.deepcopy(SAMPLE_DOC)
            second_doc["DynamicBone"][0]["Joint"][1]["gravity"] = -0.8
            add_override_mod(core, second, second_doc, mod_id="second-default", name="Second Default Mod")

            app = MiStudioApp(self.root, core)
            app.wait_until_loaded()
            self.root.update()

            first_row = next(iid for iid, t in app._row_targets.items() if t == first)
            app.list_tree.selection_set(first_row)
            app.list_tree.focus(first_row)
            app._on_list_select(None)

            labels = list(app.ref_combo.cget("values"))
            app.ref_combo.current(labels.index("Fixed Ref Mod"))
            app._on_ref_selected(None)
            app.ref_lock_var.set(True)
            app._on_ref_lock_changed()

            second_row = next(iid for iid, t in app._row_targets.items() if t == second)
            app.list_tree.selection_set(second_row)
            app.list_tree.focus(second_row)
            app._on_list_select(None)

            leaf = next(
                iid
                for iid, path in app._leaf_paths.items()
                if path[-1] == ("key", "gravity") and ("item", "LeftBreast_Top", 1) in path
            )
            self.assertEqual(app._ref_pref_mod, "fixed-ref")
            self.assertEqual(app._ref_pref_target, fixed_ref)
            self.assertEqual(app.struct_tree.item(leaf, "values")[2], "-0.4")
            self.assertIsNone(app.workspace.reference_for(second))

    def test_favorites_pin_and_edit(self) -> None:
        from mistudio.app import FAV_ROOT, MiStudioApp

        with tempfile.TemporaryDirectory() as raw_temp:
            core = make_core(Path(raw_temp))
            app = MiStudioApp(self.root, core)
            app.wait_until_loaded()
            self.root.update()
            target = "asset/common/model_info/chr0006.mi"
            row = next(iid for iid, t in app._row_targets.items() if t == target)
            app.list_tree.selection_set(row)
            app.list_tree.focus(row)
            app._on_list_select(None)

            leaf = next(
                iid
                for iid, path in app._leaf_paths.items()
                if path[-1] == ("key", "gravity") and ("item", "LeftBreast_Top", 1) in path
            )
            path = app._leaf_paths[leaf]
            app.struct_tree.selection_set(leaf)
            app._on_struct_select(None)
            self.assertEqual(str(app.fav_button.cget("state")), "normal")
            app._toggle_favorite()
            self.assertIn(path, app.workspace.favorites)

            fav_children = app.struct_tree.get_children(FAV_ROOT)
            self.assertEqual(len(fav_children), 3)
            fav_leaf = next(iid for iid in fav_children if app._leaf_paths.get(iid) == path)
            self.assertEqual(app._leaf_paths[fav_leaf], path)

            # The pinned copy appears for OTHER files too.
            other = "asset/common/model_info/chr0006_c01.mi"
            other_row = next(iid for iid, t in app._row_targets.items() if t == other)
            app.list_tree.selection_set(other_row)
            app.list_tree.focus(other_row)
            app._on_list_select(None)
            fav_children = app.struct_tree.get_children(FAV_ROOT)
            self.assertEqual(len(fav_children), 3)

            # Editing through the pinned copy edits the real value.
            fav_leaf = next(iid for iid in fav_children if app._leaf_paths.get(iid) == path)
            app.struct_tree.selection_set(fav_leaf)
            app._on_struct_select(None)
            app.value_var.set("-0.9")
            app._commit_from_entry()
            self.assertEqual(app.workspace.get_doc(other)["DynamicBone"][0]["Joint"][1]["gravity"], -0.9)

            # Favorites persist across a workspace reload.
            from mistudio.workspace import MiWorkspace

            ws2 = MiWorkspace(core)
            self.assertIn(path, ws2.favorites)

    def test_favorite_star_column_updates(self) -> None:
        from mistudio.app import FAV_ROOT, MiStudioApp

        with tempfile.TemporaryDirectory() as raw_temp:
            core = make_core(Path(raw_temp))
            app = MiStudioApp(self.root, core)
            app.wait_until_loaded()
            self.root.update()
            target = "asset/common/model_info/chr0006.mi"
            row = next(iid for iid, t in app._row_targets.items() if t == target)
            app.list_tree.selection_set(row)
            app.list_tree.focus(row)
            app._on_list_select(None)

            leaf = next(
                iid
                for iid, path in app._leaf_paths.items()
                if path[-1] == ("key", "gravity") and not is_under(app.struct_tree, iid, FAV_ROOT)
            )
            path = app._leaf_paths[leaf]
            self.assertEqual(app.struct_tree.item(leaf, "values")[3], "☆")
            app._toggle_favorite_path(path)
            self.assertEqual(app.struct_tree.item(leaf, "values")[3], "★")

    def test_switching_file_preserves_tree_view_state(self) -> None:
        from mistudio.app import MiStudioApp

        with tempfile.TemporaryDirectory() as raw_temp:
            core = make_core(Path(raw_temp))
            app = MiStudioApp(self.root, core)
            app.wait_until_loaded()
            self.root.update()
            first = "asset/common/model_info/chr0006.mi"
            second = "asset/common/model_info/chr0006_c01.mi"
            first_row = next(iid for iid, t in app._row_targets.items() if t == first)
            app.list_tree.selection_set(first_row)
            app.list_tree.focus(first_row)
            app._on_list_select(None)

            dynamic_branch = next(iid for iid, path in app._branch_paths.items() if path == (("key", "DynamicBone"),))
            app.struct_tree.item(dynamic_branch, open=True)
            leaf = next(
                iid
                for iid, path in app._leaf_paths.items()
                if path[-1] == ("key", "gravity") and ("item", "LeftBreast_Top", 1) in path
            )
            selected_path = app._leaf_paths[leaf]
            app.struct_tree.selection_set(leaf)
            app._on_struct_select(None)

            second_row = next(iid for iid, t in app._row_targets.items() if t == second)
            app.list_tree.selection_set(second_row)
            app.list_tree.focus(second_row)
            app._on_list_select(None)

            dynamic_branch = next(iid for iid, path in app._branch_paths.items() if path == (("key", "DynamicBone"),))
            self.assertTrue(app.struct_tree.item(dynamic_branch, "open"))
            self.assertEqual(app._edit_path, selected_path)

    def test_tree_open_state_survives_intermediate_file_without_path(self) -> None:
        from mistudio.app import MiStudioApp

        with tempfile.TemporaryDirectory() as raw_temp:
            core = make_core(Path(raw_temp))
            target_without_dynamic = "asset/common/model_info/chr9998_c99.mi"
            doc_without_dynamic = copy.deepcopy(SAMPLE_DOC)
            doc_without_dynamic.pop("DynamicBone")
            add_override_mod(
                core,
                target_without_dynamic,
                doc_without_dynamic,
                mod_id="no-dynamic",
                name="No DynamicBone",
            )

            app = MiStudioApp(self.root, core)
            app.wait_until_loaded()
            self.root.update()

            first = "asset/common/model_info/chr0006.mi"
            first_row = next(iid for iid, t in app._row_targets.items() if t == first)
            app.list_tree.selection_set(first_row)
            app.list_tree.focus(first_row)
            app._on_list_select(None)

            dynamic_branch = next(iid for iid, path in app._branch_paths.items() if path == (("key", "DynamicBone"),))
            app.struct_tree.item(dynamic_branch, open=True)

            missing_row = next(iid for iid, t in app._row_targets.items() if t == target_without_dynamic)
            app.list_tree.selection_set(missing_row)
            app.list_tree.focus(missing_row)
            app._on_list_select(None)
            self.assertFalse(any(path == (("key", "DynamicBone"),) for path in app._branch_paths.values()))

            app.list_tree.selection_set(first_row)
            app.list_tree.focus(first_row)
            app._on_list_select(None)
            dynamic_branch = next(iid for iid, path in app._branch_paths.items() if path == (("key", "DynamicBone"),))
            self.assertTrue(app.struct_tree.item(dynamic_branch, "open"))

    def test_left_list_supports_extended_multiselect(self) -> None:
        from mistudio.app import MiStudioApp

        with tempfile.TemporaryDirectory() as raw_temp:
            core = make_core(Path(raw_temp))
            app = MiStudioApp(self.root, core)
            app.wait_until_loaded()
            self.root.update()
            rows = list(app._row_targets)[:2]
            self.assertEqual(str(app.list_tree.cget("selectmode")), "extended")
            app.list_tree.selection_set(*rows)
            self.assertEqual(set(app._selected_targets()), {app._row_targets[row] for row in rows})
            app._refresh_scope_options()
            self.assertTrue(any(label.startswith("左侧选中的 2 个文件") for label, _fn in app._scope_options))

    def test_multiselect_edit_defaults_to_selected_files(self) -> None:
        from mistudio.app import MiStudioApp

        with tempfile.TemporaryDirectory() as raw_temp:
            core = make_core(Path(raw_temp))
            app = MiStudioApp(self.root, core)
            app.wait_until_loaded()
            self.root.update()
            targets = ["asset/common/model_info/chr0006.mi", "asset/common/model_info/chr0006_c01.mi"]
            rows = [next(iid for iid, t in app._row_targets.items() if t == target) for target in targets]
            app.list_tree.selection_set(*rows)
            app.list_tree.focus(rows[0])
            app._on_list_select(None)

            leaf = next(
                iid
                for iid, path in app._leaf_paths.items()
                if path[-1] == ("key", "damping") and ("item", "LeftBreast", 0) in path and not is_under(app.struct_tree, iid, "fav-root")
            )
            app.struct_tree.selection_set(leaf)
            app._on_struct_select(None)
            self.assertTrue(app.scope_combo.get().startswith("左侧选中的 2 个文件"))

            app.value_var.set("0.66")
            app._commit_from_entry()
            for target in targets:
                self.assertEqual(app.workspace.get_doc(target)["DynamicBone"][0]["Joint"][0]["damping"], 0.66)

    def test_default_favorites_are_seeded_without_cache(self) -> None:
        from mistudio.workspace import DEFAULT_FAVORITES, MiWorkspace

        with tempfile.TemporaryDirectory() as raw_temp:
            core = make_core(Path(raw_temp))
            ws = MiWorkspace(core)
            for path in DEFAULT_FAVORITES:
                self.assertIn(path, ws.favorites)

    def test_reference_selection_persists_per_file(self) -> None:
        from mistudio.app import MiStudioApp

        with tempfile.TemporaryDirectory() as raw_temp:
            core = make_core(Path(raw_temp))
            target = "asset/common/model_info/chr0006.mi"
            same_file_doc = copy.deepcopy(SAMPLE_DOC)
            same_file_doc["DynamicBone"][0]["Joint"][1]["gravity"] = -0.7
            add_override_mod(core, target, same_file_doc, mod_id="same-file", name="Same File Mod")

            other_target = "asset/common/model_info/chr9999_c99.mi"
            other_doc = copy.deepcopy(SAMPLE_DOC)
            other_doc["DynamicBone"][0]["Joint"][1]["gravity"] = -0.4
            add_override_mod(core, other_target, other_doc, mod_id="other-file", name="Other File Mod")

            app = MiStudioApp(self.root, core)
            app.wait_until_loaded()
            self.root.update()
            row = next(iid for iid, t in app._row_targets.items() if t == target)
            app.list_tree.selection_set(row)
            app.list_tree.focus(row)
            app._on_list_select(None)
            labels = list(app.ref_combo.cget("values"))
            app.ref_combo.current(labels.index("Other File Mod"))
            app._on_ref_selected(None)

            app2 = MiStudioApp(self.root, core)
            app2.wait_until_loaded()
            self.root.update()
            row2 = next(iid for iid, t in app2._row_targets.items() if t == target)
            app2.list_tree.selection_set(row2)
            app2.list_tree.focus(row2)
            app2._on_list_select(None)
            self.assertEqual(app2.ref_combo.get(), "Other File Mod")
            self.assertTrue(any("chr9999_c99.mi" in label for label in list(app2.ref_file_combo.cget("values"))))

    def test_language_switch_uses_shared_config(self) -> None:
        from mistudio.app import MiStudioApp

        with tempfile.TemporaryDirectory() as raw_temp:
            core = make_core(Path(raw_temp))
            app = MiStudioApp(self.root, core)
            app.wait_until_loaded()
            self.root.update()

            app.language_combo.current(1)  # English
            app._on_language_selected(None)

            self.assertEqual(core.config.language, "en")
            self.assertEqual(app.reload_button.cget("text"), "Reload")
            self.assertEqual(app.struct_tree.heading("value")["text"], "Current")
            self.assertIn("All Categories", list(app.category_combo.cget("values")))

            target = "asset/common/model_info/chr0006.mi"
            row = next(iid for iid, t in app._row_targets.items() if t == target)
            app.list_tree.selection_set(row)
            app.list_tree.focus(row)
            app._on_list_select(None)
            leaf = next(iid for iid, path in app._leaf_paths.items() if path[-1] == ("key", "gravity"))
            self.assertIn("Gravity", app.struct_tree.item(leaf, "text"))

    def test_costume_names_follow_dynamic_catalog(self) -> None:
        from modmanager import costumes
        from mistudio.app import MiStudioApp

        with tempfile.TemporaryDirectory() as raw_temp:
            core = make_core(Path(raw_temp))
            app = MiStudioApp(self.root, core)
            app.wait_until_loaded()
            self.root.update()

            target = "asset/common/model_info/chr0006_c01.mi"
            core.extra_costume_names_file.write_text(
                json.dumps(
                    {
                        "chr0006_c01": {
                            "base_model": "chr0006",
                            "cn": "运行时服装",
                            "en": "Runtime Costume",
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            costumes.reload_catalog()
            app._refresh_character_combo()
            app._refresh_list()

            row = next(iid for iid, t in app._row_targets.items() if t == target)
            self.assertEqual(app.list_tree.set(row, "name"), "运行时服装")

            app.language_combo.current(1)  # English
            app._on_language_selected(None)
            row = next(iid for iid, t in app._row_targets.items() if t == target)
            self.assertEqual(app.list_tree.set(row, "name"), "Runtime Costume")

    def test_window_geometry_persists_for_mi_studio(self) -> None:
        from mistudio.app import MI_STUDIO_GEOMETRY_KEY, MI_STUDIO_STATE_KEY, MiStudioApp

        with tempfile.TemporaryDirectory() as raw_temp:
            core = make_core(Path(raw_temp))
            core.config.set_window_value("geometry", "980x660+1+2")
            core.config.set_window_value(MI_STUDIO_GEOMETRY_KEY, "1230x740+41+53")
            core.config.set_window_value(MI_STUDIO_STATE_KEY, "normal")
            core.config.save()

            app = MiStudioApp(self.root, core)
            app.wait_until_loaded()
            self.root.update()

            self.assertEqual(self.root.geometry(), "1230x740+41+53")
            app._last_normal_geometry = "1240x760+91+113"
            app._save_window_layout()

            self.assertEqual(core.config.get_window_value(MI_STUDIO_GEOMETRY_KEY), "1240x760+91+113")
            self.assertEqual(core.config.get_window_value(MI_STUDIO_STATE_KEY), "normal")
            self.assertEqual(core.config.get_window_value("geometry"), "980x660+1+2")

    def test_ui_surfaces_use_compact_dark_components(self) -> None:
        from mistudio.app import MiStudioApp

        with tempfile.TemporaryDirectory() as raw_temp:
            core = make_core(Path(raw_temp))
            app = MiStudioApp(self.root, core)
            app.wait_until_loaded()
            self.root.update()

            self.assertGreaterEqual(int(app.list_tree.column("state", "width")), 108)
            self.assertEqual(str(app.list_tree.cget("style")), "Rail.Treeview")
            self.assertEqual(app.colors["tree_selected_bg"], app.colors["panel"])
            rail_background_map = ttk.Style().map("Rail.Treeview", "background")
            self.assertFalse(any("selected" in item[:-1] for item in rail_background_map))
            self.assertEqual(app.list_rail.rail.cget("bg"), app.colors["selection_rail"])
            self.assertIs(app.value_entry.master, app.value_box)
            self.assertEqual(app.value_entry.cget("bg"), app.colors["input_bg"])
            self.assertEqual(app.log_panel.text.cget("bg"), app.colors["log_bg"])

            app._set_busy(True, "busy")
            self.assertTrue(app.status_bar.progress.grid_info())
            app._set_busy(False)
            self.assertFalse(app.status_bar.progress.grid_info())


if __name__ == "__main__":
    unittest.main()
