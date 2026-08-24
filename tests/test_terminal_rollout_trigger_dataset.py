import json
import pathlib
import tempfile
import unittest

from scripts.build_terminal_rollout_trigger_dataset import (
    audit_rules,
    build_dataset,
    pareto_ids,
)


def vector(fill, soft=0.0):
    return {
        "fill_gain": fill,
        "soft_violation_gain": soft,
        "priority_covered_gain": 0.0,
        "priority_misrouted_gain": 0.0,
        "surface_total_variation_delta": 0.0,
    }


class TerminalRolloutTriggerDatasetTests(unittest.TestCase):
    def test_pareto_ids_uses_declared_head_directions(self):
        rows = [
            {"root_candidate_id": "a", "safe": True,
             "one_step_vector": vector(1.0, 0.0)},
            {"root_candidate_id": "b", "safe": True,
             "one_step_vector": vector(2.0, 1.0)},
            {"root_candidate_id": "c", "safe": True,
             "one_step_vector": vector(0.5, 2.0)},
        ]
        self.assertEqual(pareto_ids(rows, "one_step_vector"), ["a", "b"])

    def test_builds_action_change_label_and_resurrection(self):
        candidates = [
            {"root_candidate_id": "a", "safe": True,
             "one_step_vector": vector(2.0),
             "terminal_vector": vector(2.0)},
            {"root_candidate_id": "b", "safe": True,
             "one_step_vector": vector(1.0),
             "terminal_vector": vector(3.0)},
        ]
        payload = {
            "case_id": "case", "environment_seed": 42,
            "episodes": [{"records": [{
                "step": 0, "root_id": "root", "snapshot_path": "state.json",
                "selection": {
                    "switched": True, "incumbent_candidate_id": "a",
                    "selected_candidate_id": "b",
                },
                "search": {
                    "terminal_truth_complete": True,
                    "terminal_pareto_candidates": ["b"],
                    "terminal_rollout_physical_step_equivalents": 20,
                    "root_candidates": candidates,
                    "timing": {"terminal_rollout_total_seconds": 8.0},
                },
                "timing": {"decision_total_seconds": 10.0},
            }]}],
        }
        with tempfile.TemporaryDirectory() as directory:
            cell = pathlib.Path(directory) / "cell"
            cell.mkdir()
            (cell / "rollout.json").write_text(json.dumps(payload))
            dataset = build_dataset(pathlib.Path(directory))
        row = dataset["rows"][0]
        self.assertEqual(dataset["manifest_count"], 1)
        self.assertTrue(row["terminal_intervention"])
        self.assertEqual(row["h1_pareto_candidates"], ["a"])
        self.assertEqual(row["terminal_resurrection_candidates"], ["b"])
        self.assertFalse(pathlib.Path(row["snapshot_path"]).is_absolute())
        self.assertEqual(
            row["snapshot_path"], "cell/rollout/episode-000/state.json"
        )
        self.assertEqual(row["estimated_no_terminal_decision_seconds"], 2.0)

    def test_rule_audit_reports_compute_upper_bound(self):
        rows = [
            {"terminal_intervention": True, "h1_incumbent_pareto": True,
             "h1_frontier_size": 2, "h1_all_safe_candidates_pareto": True,
             "safe_candidate_count": 2, "h1_distinct_vector_count": 2,
             "terminal_rollout_physical_step_equivalents": 30,
             "decision_timing": {"decision_total_seconds": 12.0},
             "estimated_no_terminal_decision_seconds": 2.0},
            {"terminal_intervention": False, "h1_incumbent_pareto": True,
             "h1_frontier_size": 1, "h1_all_safe_candidates_pareto": False,
             "safe_candidate_count": 3, "h1_distinct_vector_count": 3,
             "terminal_rollout_physical_step_equivalents": 70,
             "decision_timing": {"decision_total_seconds": 8.0},
             "estimated_no_terminal_decision_seconds": 3.0},
        ]
        results = {row["rule"]: row for row in audit_rules(rows)}
        ambiguous = results["h1_frontier_ambiguous"]
        self.assertEqual(ambiguous["intervention_recall"], 1.0)
        self.assertEqual(ambiguous["retained_compute_rate"], 0.3)
        self.assertEqual(
            ambiguous["saved_physical_step_equivalents_upper_bound"], 70
        )
        self.assertEqual(ambiguous["estimated_p95_seconds"], 11.55)
        self.assertEqual(ambiguous["estimated_within_10s_count"], 1)


if __name__ == "__main__":
    unittest.main()
