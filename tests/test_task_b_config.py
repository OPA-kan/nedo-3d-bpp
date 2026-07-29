from __future__ import annotations

import copy
import json
import pathlib
import unittest

from scripts.build_task_b_config import build_task_b_config


ROOT = pathlib.Path(__file__).resolve().parents[1]
SAMPLE_CONFIG = ROOT / "simulator" / "configs" / "sample_config.json"


class TaskBConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = json.loads(SAMPLE_CONFIG.read_text(encoding="utf-8"))

    def test_builds_online_pool_case_without_mutating_source(self) -> None:
        original = copy.deepcopy(self.source)

        generated = build_task_b_config(
            self.source,
            source_case="001",
            task_id="task-b-k3",
            look_ahead=3,
            policy_timeout=8.0,
        )

        self.assertEqual(self.source, original)
        self.assertEqual(list(generated), ["task-b-k3"])
        task = generated["task-b-k3"]
        self.assertFalse(task["agent"]["optimize"])
        self.assertEqual(task["agent"]["policy_timeout"], 8.0)
        self.assertEqual(task["item_stream"]["look_ahead"], 3)
        self.assertEqual(task["item_stream"]["max_space"], 1)
        self.assertEqual(task["item_stream"]["visible_pool"], [])
        self.assertEqual(len(task["item_stream"]["item_list"]), 42)

    def test_supports_largest_planned_pool(self) -> None:
        generated = build_task_b_config(
            self.source,
            source_case="001",
            task_id="task-b-k40",
            look_ahead=40,
            policy_timeout=8.0,
        )
        self.assertEqual(
            generated["task-b-k40"]["item_stream"]["look_ahead"],
            40,
        )

    def test_rejects_pool_larger_than_item_stream(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot exceed item count"):
            build_task_b_config(
                self.source,
                source_case="001",
                task_id="task-b-k43",
                look_ahead=43,
                policy_timeout=8.0,
            )


if __name__ == "__main__":
    unittest.main()
