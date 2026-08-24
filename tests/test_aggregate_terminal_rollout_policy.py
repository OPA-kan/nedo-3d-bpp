import json
import pathlib
import tempfile
import unittest

from scripts.aggregate_terminal_rollout_policy import (
    aggregate,
    compare_pair,
    render_markdown,
)


def manifest(policy, *, fill, soft, steps, switches=0):
    return {
        "behavior_contract": "single_agent_terminal_rollout_policy_v1",
        "case_id": "case",
        "environment_seed": 42,
        "policy": policy,
        "value_model": None,
        "episodes": [{
            "policy": policy,
            "steps": steps,
            "termination": "stream_exhausted",
            "genuine_termination": True,
            "final_metrics": {
                "fill_score_proxy": fill,
                "placed_count": steps,
                "soft_covered_by_other": soft,
                "priority_covered_by_other": 0,
                "priority_misrouted": 0,
                "surface_total_variation": 1.0,
                "post_shake_max_shift": 0.1,
            },
            "terminal_dominance_switches": switches,
            "terminal_truth_complete_roots": steps,
            "terminal_truth_censored_roots": 0,
            "search_physical_steps": steps * 3,
            "terminal_rollout_physical_steps": steps * 10,
        }],
    }


class TerminalRolloutPolicyAggregateTests(unittest.TestCase):
    def test_pair_reports_vector_relation_without_scalar_score(self):
        baseline = manifest("legacy", fill=10.0, soft=1, steps=5)
        rollout = manifest(
            "terminal-rollout", fill=12.0, soft=0, steps=6, switches=2
        )

        result = compare_pair(baseline, rollout, cell="x")

        self.assertEqual(result["terminal_vector_relation"], "rollout_dominates")
        self.assertEqual(result["metric_deltas"]["fill_score_proxy"], 2.0)
        self.assertEqual(result["metric_deltas"]["soft_covered_by_other"], -1.0)
        self.assertEqual(result["rollout"]["switches"], 2)
        self.assertNotIn("score", result)

    def test_aggregate_keeps_incomparable_outcomes_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            cell = root / "cell"
            cell.mkdir()
            (cell / "baseline.json").write_text(
                json.dumps(manifest("legacy", fill=10.0, soft=0, steps=5)),
                encoding="utf-8",
            )
            (cell / "rollout.json").write_text(
                json.dumps(manifest(
                    "terminal-rollout", fill=12.0, soft=1, steps=6, switches=1
                )),
                encoding="utf-8",
            )
            result = aggregate(root)

        self.assertEqual(result["relation_counts"]["incomparable"], 1)
        self.assertEqual(result["total_switches"], 1)
        self.assertIn("No scalar utility", render_markdown(result))


if __name__ == "__main__":
    unittest.main()
