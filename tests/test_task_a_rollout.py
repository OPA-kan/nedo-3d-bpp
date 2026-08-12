import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.build_task_a_config import build_task_a_config
from scripts.run_task_a_rollout import configure_task_a_arm, summarize

AGENT_PATH = Path(__file__).parents[1] / "agent" / "agent.py"
SPEC = importlib.util.spec_from_file_location("task_a_agent", AGENT_PATH)
agent = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = agent
SPEC.loader.exec_module(agent)


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
        self.assertEqual(base["OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM"], "0")
        self.assertEqual(base["OFFLINE_PAIR_MACRO_BUDGET_SECONDS"], "0.0")

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

    def test_base_arm_does_not_inherit_the_adopted_default(self):
        """
        The regression this guards: once bounded128 became the shipped
        default, an arm that merely unsets the variables measures the
        treatment, not the control. A leaked value must not survive either.
        """
        base = dict(
            OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM="256",
            OFFLINE_PAIR_MACRO_BUDGET_SECONDS="9.0",
        )
        configure_task_a_arm(
            base, "base", offline_seconds=150.0, macro_seconds=0.5
        )

        self.assertEqual(base["OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM"], "0")
        self.assertEqual(base["OFFLINE_PAIR_MACRO_BUDGET_SECONDS"], "0.0")
        self.assertNotEqual(
            base["OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM"],
            str(agent.OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM),
            "the shipped default has reverted to the legacy scan, so the "
            "base arm no longer contrasts with anything -- retire the arm "
            "or re-point it before running another comparison",
        )

    def test_default_arm_measures_the_shipped_submission(self):
        env = dict(
            OFFLINE_SEARCH_BUDGET_SECONDS="30.0",
            OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM="0",
            OFFLINE_PAIR_MACRO_BUDGET_SECONDS="0.0",
        )
        configure_task_a_arm(
            env, "default", offline_seconds=30.0, macro_seconds=0.5
        )

        self.assertEqual(env, {})

    def test_risk_on_arm_changes_only_the_proposal_oracle_ranking(self):
        env = dict(OFFLINE_RISK_RERANK="stale")
        configure_task_a_arm(
            env, "risk_on", offline_seconds=150.0, macro_seconds=0.5
        )

        self.assertEqual(env, {"OFFLINE_RISK_RERANK": "1"})

    def test_unknown_arm_is_rejected(self):
        for arm in ("bounded0", "bounded-8", "shipped"):
            with self.subTest(arm=arm), self.assertRaises(ValueError):
                configure_task_a_arm(
                    {}, arm, offline_seconds=30.0, macro_seconds=0.5
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
