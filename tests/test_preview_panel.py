from __future__ import annotations

import unittest

from modmanager.ui.preview_panel import PreviewPanel


class FakeTranslator:
    language = "zh_CN"

    def t(self, key: str, **kwargs: object) -> str:
        templates = {
            "model_info_diff_missing_tip": "missing original",
            "model_info_no_semantic_changes": "no changes",
            "model_info_decode_unavailable": "decode unavailable",
            "model_info_semantic_changes_more": "  ...and {count} more changes",
        }
        return templates[key].format(**kwargs)


class PreviewPanelFormattingTests(unittest.TestCase):
    def test_model_info_missing_original_uses_muted_tag_not_error_tag(self) -> None:
        panel = PreviewPanel.__new__(PreviewPanel)

        self.assertEqual(panel._model_info_diff_tag({"status": "missing_original"}), "model-info-missing")
        self.assertEqual(panel._model_info_diff_tag({"status": "error"}), "model-info-error")

    def test_model_info_missing_original_tooltip_is_single_line(self) -> None:
        panel = PreviewPanel.__new__(PreviewPanel)
        panel.translator = FakeTranslator()

        text = panel._model_info_diff_tooltip_text(
            {
                "status": "missing_original",
                "impact_keys": ["physics", "collision"],
                "notable_identifiers": ["Head", "Hips"],
            }
        )

        self.assertEqual(text, "missing original")
        self.assertNotIn("\n", text)

    def test_model_info_changes_are_grouped_by_repeated_parameter_sets(self) -> None:
        panel = PreviewPanel.__new__(PreviewPanel)
        panel.translator = FakeTranslator()
        diff = {
            "decoded_json": True,
            "semantic_change_count": 8,
            "semantic_changes": [
                {
                    "path": "$.DynamicBone[0].Joint[0].damping_min",
                    "before": 0.1,
                    "after": 0.01,
                    "context": "LeftBreast",
                },
                {
                    "path": "$.DynamicBone[0].Joint[0].gravity",
                    "before": -0.98,
                    "after": -0.5,
                    "context": "LeftBreast",
                },
                {
                    "path": "$.DynamicBone[0].Joint[0].damping",
                    "before": 0.1,
                    "after": 0.01,
                    "context": "LeftBreast",
                },
                {
                    "path": "$.DynamicBone[0].Joint[0].damping_max",
                    "before": 0.1,
                    "after": 0.01,
                    "context": "LeftBreast",
                },
                {
                    "path": "$.DynamicBone[1].Joint[0].damping_min",
                    "before": 0.1,
                    "after": 0.01,
                    "context": "RightBreast",
                },
                {
                    "path": "$.DynamicBone[1].Joint[0].gravity",
                    "before": -0.98,
                    "after": -0.5,
                    "context": "RightBreast",
                },
                {
                    "path": "$.DynamicBone[1].Joint[0].damping",
                    "before": 0.1,
                    "after": 0.01,
                    "context": "RightBreast",
                },
                {
                    "path": "$.DynamicBone[1].Joint[0].damping_max",
                    "before": 0.1,
                    "after": 0.01,
                    "context": "RightBreast",
                },
            ],
        }

        text = panel._format_model_info_semantic_changes(diff)

        self.assertIn("[动态骨骼] LeftBreast, RightBreast", text)
        self.assertIn("最小阻尼: 0.1 -> 0.01", text)
        self.assertIn("重力: -0.98 -> -0.5", text)
        self.assertIn("阻尼: 0.1 -> 0.01", text)
        self.assertIn("最大阻尼: 0.1 -> 0.01", text)
        self.assertNotIn("DynamicBone / LeftBreast / damping_min", text)


if __name__ == "__main__":
    unittest.main()
