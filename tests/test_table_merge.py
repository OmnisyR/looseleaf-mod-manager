from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

from modmanager import table_merge
from modmanager.table_merge import (
    create_merge_state,
    extra_costume_catalog_from_json,
    merge_table_json,
    merge_table_json_changes,
    _python_script_command,
)


class TableMergeTests(unittest.TestCase):
    def test_python_script_command_uses_python_in_source_mode(self) -> None:
        with mock.patch.object(table_merge.sys, "executable", "python.exe"):
            self.assertEqual(
                _python_script_command(Path("tool.py"), "arg"),
                ["python.exe", "tool.py", "arg"],
            )

    def test_python_script_command_uses_helper_in_frozen_mode(self) -> None:
        had_frozen = hasattr(sys, "frozen")
        old_frozen = getattr(sys, "frozen", None)
        try:
            setattr(sys, "frozen", True)
            with mock.patch.object(table_merge.sys, "executable", "manager.exe"):
                self.assertEqual(
                    _python_script_command(Path("tool.py"), "arg"),
                    ["manager.exe", "--looseleaf-run-python", "tool.py", "arg"],
                )
        finally:
            if had_frozen:
                setattr(sys, "frozen", old_frozen)
            else:
                delattr(sys, "frozen")

    def test_foreign_rows_are_added_without_replacing_existing_language(self) -> None:
        base = {
            "data": [
                {
                    "name": "ItemTableData",
                    "data": [
                        {"id": 1, "name": "Chinese item", "description": "Chinese description"},
                    ],
                },
                {
                    "name": "ShopItem",
                    "data": [
                        {"shop_id": 5, "item_id": 1, "unknown": 1},
                    ],
                },
                {
                    "name": "DLCTableData",
                    "data": [
                        {"int1": 1, "text1": "Chinese DLC"},
                    ],
                },
            ]
        }
        foreign = {
            "data": [
                {
                    "name": "ItemTableData",
                    "data": [
                        {"id": 1, "name": "English item", "description": "English description"},
                        {"id": 9001, "name": "English extra", "description": "Extra description"},
                    ],
                },
                {
                    "name": "ShopItem",
                    "data": [
                        {"shop_id": 5, "item_id": 1, "unknown": 1},
                        {"shop_id": 5, "item_id": 9001, "unknown": 1},
                    ],
                },
                {
                    "name": "DLCTableData",
                    "data": [
                        {"int1": 1, "text1": "English DLC"},
                        {"int1": 200, "text1": "English extra DLC"},
                    ],
                },
            ]
        }

        added = merge_table_json(base, foreign)

        self.assertEqual(added, {"ItemTableData": 1, "ShopItem": 1, "DLCTableData": 1})
        self.assertEqual(base["data"][0]["data"][0]["name"], "Chinese item")
        self.assertEqual(base["data"][0]["data"][1]["name"], "English extra")
        self.assertEqual(base["data"][1]["data"][1]["item_id"], 9001)
        self.assertEqual(base["data"][2]["data"][1]["text1"], "English extra DLC")

    def test_later_mod_replaces_previous_added_rows_but_not_official_rows(self) -> None:
        base = {
            "data": [
                {
                    "name": "ItemTableData",
                    "data": [
                        {"id": 1, "name": "Official Chinese"},
                    ],
                }
            ]
        }
        state = create_merge_state(base)

        first = {
            "data": [
                {
                    "name": "ItemTableData",
                    "data": [
                        {"id": 1, "name": "Should not replace official"},
                        {"id": 9001, "name": "First mod"},
                    ],
                }
            ]
        }
        second = {
            "data": [
                {
                    "name": "ItemTableData",
                    "data": [
                        {"id": 9001, "name": "Second mod wins"},
                    ],
                }
            ]
        }

        first_changes = merge_table_json_changes(base, first, state, replace_added=True)
        second_changes = merge_table_json_changes(base, second, state, replace_added=True)

        self.assertEqual(first_changes.added_by_section, {"ItemTableData": 1})
        self.assertEqual(second_changes.replaced_by_section, {"ItemTableData": 1})
        self.assertEqual(base["data"][0]["data"][0]["name"], "Official Chinese")
        self.assertEqual(base["data"][0]["data"][1]["name"], "Second mod wins")

    def test_extra_costume_catalog_maps_added_costume_model_to_item_name(self) -> None:
        base_costume = {
            "data": [
                {
                    "name": "CostumeParam",
                    "data": [
                        {"character_id": 0, "item_id": 2500, "name": "chr5000_c00"},
                    ],
                }
            ]
        }
        mod_costume = {
            "data": [
                {
                    "name": "CostumeParam",
                    "data": [
                        {"character_id": 0, "item_id": 2500, "name": "chr5000_c00"},
                        {"character_id": 0, "item_id": 7200, "name": "chr5000_c20a"},
                    ],
                }
            ]
        }
        mod_item = {
            "data": [
                {
                    "name": "ItemTableData",
                    "data": [
                        {"id": 7200, "name": "Custom Dress"},
                    ],
                }
            ]
        }

        catalog = extra_costume_catalog_from_json(mod_costume, mod_item, base_costume)

        self.assertNotIn("chr5000_c00", catalog)
        self.assertEqual(
            catalog["chr5000_c20a"],
            {"base_model": "chr5000", "en": "Custom Dress", "item_id": 7200},
        )


if __name__ == "__main__":
    unittest.main()
