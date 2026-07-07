from __future__ import annotations

import itertools
import queue
import threading
import unittest

from modmanager.ui.app import ModManagerApp


class FakeConfig:
    model_info_diff_enabled = True


class FakeCore:
    game_id = "sora_1st"

    def __init__(self) -> None:
        self.config = FakeConfig()
        self.state = {
            "mods": {
                "mod-a": {
                    "files": [
                        "asset/common/model_info/first.mi",
                        "asset/common/model_info/second.mi",
                        "asset/common/model_info/third.mi",
                        "asset/common/model/not-model-info.mdl",
                    ]
                }
            }
        }


class FakeModList:
    def get_selected_mod_id(self) -> str:
        return "mod-a"


class AppModelInfoLazyTests(unittest.TestCase):
    def make_app(self) -> ModManagerApp:
        app = ModManagerApp.__new__(ModManagerApp)
        app.core = FakeCore()
        app.mod_list = FakeModList()
        app._model_info_diff_cache = {}
        app._model_info_diff_pending = set()
        app._model_info_diff_queue = queue.PriorityQueue()
        app._model_info_diff_counter = itertools.count()
        app._model_info_diff_lock = threading.Lock()
        return app

    def test_unscheduled_targets_skip_cached_and_pending_entries(self) -> None:
        app = self.make_app()
        cached_key = app._model_info_diff_cache_key("sora_1st", "mod-a", "asset/common/model_info/first.mi")
        pending_key = app._model_info_diff_cache_key("sora_1st", "mod-a", "asset/common/model_info/second.mi")
        app._model_info_diff_cache[cached_key] = {"status": "identical"}
        app._model_info_diff_pending.add(pending_key)

        self.assertEqual(
            app._next_unscheduled_model_info_targets("mod-a", 8),
            ["asset/common/model_info/third.mi"],
        )

    def test_active_entries_only_include_cached_and_pending_entries(self) -> None:
        app = self.make_app()
        cached_key = app._model_info_diff_cache_key("sora_1st", "mod-a", "asset/common/model_info/first.mi")
        pending_key = app._model_info_diff_cache_key("sora_1st", "mod-a", "asset/common/model_info/second.mi")
        app._model_info_diff_cache[cached_key] = {"status": "identical"}
        app._model_info_diff_pending.add(pending_key)

        self.assertEqual(
            app._model_info_active_entries_for_mod("mod-a"),
            {
                "asset/common/model_info/first.mi": {"status": "identical"},
                "asset/common/model_info/second.mi": {"status": "loading"},
            },
        )

    def test_scheduling_marks_targets_pending_without_duplicates(self) -> None:
        app = self.make_app()

        first = app._schedule_model_info_diffs("mod-a", ["asset/common/model_info/first.mi"])
        second = app._schedule_model_info_diffs("mod-a", ["asset/common/model_info/first.mi"])

        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        self.assertEqual(app._model_info_diff_queue.qsize(), 1)

    def test_tooltip_diff_lookup_uses_single_target_and_schedules_hover(self) -> None:
        app = self.make_app()

        entry = app.model_info_diff_for_tooltip("asset/common/model_info/first.mi")

        self.assertEqual(entry, {"status": "loading"})
        self.assertEqual(app._model_info_diff_queue.qsize(), 1)
        queued = app._model_info_diff_queue.get_nowait()
        self.assertEqual(queued[0], 0)
        self.assertEqual(queued[4], "asset/common/model_info/first.mi")

    def test_tooltip_diff_lookup_returns_cached_result_without_scheduling(self) -> None:
        app = self.make_app()
        key = app._model_info_diff_cache_key("sora_1st", "mod-a", "asset/common/model_info/first.mi")
        app._model_info_diff_cache[key] = {"status": "changed", "semantic_change_count": 1}

        entry = app.model_info_diff_for_tooltip("asset/common/model_info/first.mi")

        self.assertEqual(entry, {"status": "changed", "semantic_change_count": 1})
        self.assertEqual(app._model_info_diff_queue.qsize(), 0)


if __name__ == "__main__":
    unittest.main()
