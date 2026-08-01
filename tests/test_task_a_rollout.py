import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_task_a_config import build_task_a_config
from scripts.run_task_a_rollout import configure_task_a_arm, summarize


class TaskARolloutTests(unittest.TestCase):
    def test_builder_forces_task_a_contract_without_mutating_source(self):
        source = {
            "000": {
                "agent": {
                    "optimize": False,
                    "optimization_timeout": 180.0,
                    "policy_timeout": 10.0,
                },
                "item_stream": {
                    "look_ahead": 40,
                    "max_space": 40,
                    "visible_pool": [1],
                    "item_list": [],
                },
            }
        }
        built = build_task_a_config(
            source, "000", optimization_timeout=35.0
        )

        self.assertFalse(source["000"]["agent"]["optimize"])
        case = built["a000"]
        self.assertTrue(case["agent"]["optimize"])
        self.assertEqual(case["agent"]["optimization_timeout"], 35.0)
        self.assertEqual(case["item_stream"]["look_ahead"], 1)
        self.assertEqual(case["item_stream"]["max_space"], 1)
        self.assertEqual(case["item_stream"]["visible_pool"], [])

    def test_arm_environment_preserves_legacy_and_enables_bounded(self):
        base = {}
        configure_task_a_arm(
            base, "base", offline_seconds=30.0, macro_seconds=0.5
        )
        self.assertEqual(base["OFFLINE_SEARCH_BUDGET_SECONDS"], "30.0")
        self.assertNotIn("OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM", base)

        bounded = {}
        configure_task_a_arm(
            bounded,
            "bounded64",
            offline_seconds=30.0,
            macro_seconds=0.5,
        )
        self.assertEqual(
            bounded["OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM"], "64"
        )
        self.assertEqual(
            bounded["OFFLINE_PAIR_MACRO_BUDGET_SECONDS"], "0.5"
        )

    def test_summary_reads_isolated_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for repeat, placed in enumerate((10, 12)):
                path = root / str(repeat) / "row.json"
                path.parent.mkdir()
                path.write_text(
                    json.dumps(
                        {
                            "source_case": "000",
                            "arm": "bounded64",
                            "repeat": repeat,
                            "process_returncode": 0,
                            "optimization_seconds": 30.0,
                            "case": {
                                "placed_count": placed,
                                "fill_score": 20,
                            },
                            "offline": {
                                "evaluations": 4,
                                "best_result": {"placed_count": 15},
                            },
                        }
                    ),
                    encoding="utf-8",
                )

            result = summarize(root)["results"][0]

        self.assertEqual(result["placed"]["mean"], 11.0)
        self.assertEqual(result["offline_evaluations"]["mean"], 4.0)


if __name__ == "__main__":
    unittest.main()
