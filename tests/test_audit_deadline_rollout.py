import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

from scripts.audit_deadline_rollout import (
    choose_from_checkpoint,
    main,
    ranker_order_candidates,
)
from scripts.deadline_rollout_summary import summarize


def candidate(candidate_id, fill):
    return {
        "root_candidate_id": candidate_id,
        "safe": True,
        "checkpoint_vector": {
            "fill_gain": fill,
            "soft_violation_gain": 0.0,
            "priority_covered_gain": 0.0,
            "priority_misrouted_gain": 0.0,
            "surface_total_variation_delta": 0.0,
        },
    }


class AuditDeadlineRolloutTests(unittest.TestCase):
    def test_physics_switches_only_when_incumbent_is_dominated(self):
        selected, frontier = choose_from_checkpoint(
            ["a", "b"], incumbent="a",
            candidates=[candidate("a", 1.0), candidate("b", 2.0)],
        )
        self.assertEqual(selected, "b")
        self.assertEqual(frontier, ["b"])

    def test_ranker_next_ignores_scores_and_keeps_rank_order(self):
        oof_row = {
            "candidate_ids": ["a", "b", "c"],
            "candidate_scores": [0.1, 0.2, 0.9],
            "incumbent_index": 0,
        }
        self.assertEqual(
            ranker_order_candidates(oof_row, budget=2), ["a", "b"]
        )
        self.assertEqual(
            ranker_order_candidates(oof_row, budget=1), ["a"]
        )
        self.assertEqual(
            ranker_order_candidates(oof_row, budget=3), ["a", "b", "c"]
        )

    def test_cli_alternate_mode_reaches_audit(self):
        # Regression: run 32802783183 silently ran in allocator mode because
        # main() dropped the parsed --alternate-mode on the floor.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "manifest.json").write_text(
                json.dumps({"case_id": "case"}), encoding="utf-8"
            )
            (root / "dataset.json").write_text("{}", encoding="utf-8")
            (root / "oof.json").write_text("{}", encoding="utf-8")
            (root / "config.json").write_text(
                json.dumps({"case": {}}), encoding="utf-8"
            )
            argv = [
                "audit_deadline_rollout.py",
                "--manifest", str(root / "manifest.json"),
                "--trigger-dataset", str(root / "dataset.json"),
                "--oof-report", str(root / "oof.json"),
                "--task-config", str(root / "config.json"),
                "--cell", "cell",
                "--alternate-mode", "ranker_next",
                "--contested-extra-steps", "5",
                "--output", str(root / "out.json"),
            ]
            with mock.patch(
                "scripts.audit_deadline_rollout.audit",
                return_value={"summary": {}},
            ) as audit_call, mock.patch.object(sys, "argv", argv):
                self.assertEqual(main(), 0)
            self.assertEqual(
                audit_call.call_args.kwargs["alternate_mode"], "ranker_next"
            )
            self.assertEqual(
                audit_call.call_args.kwargs["contested_extra_steps"], 5
            )

    def test_summary_reports_actual_budget_compliance(self):
        rows = [
            {
                "incumbent_candidate_id": "a",
                "terminal_selected_candidate_id": "b",
                "terminal_selected_available": True,
                "matches_terminal_action": True,
                "decision_seconds": 9.0,
                "search": {"deadline_met": True, "common_total_depth": 3},
            },
            {
                "incumbent_candidate_id": "a",
                "terminal_selected_candidate_id": "a",
                "terminal_selected_available": True,
                "matches_terminal_action": True,
                "decision_seconds": 11.0,
                "search": {"deadline_met": False, "common_total_depth": 1},
            },
        ]
        result = summarize(rows)
        self.assertEqual(result["terminal_action_recall"], 1.0)
        self.assertEqual(result["intervention_action_recall"], 1.0)
        self.assertEqual(result["within_10s_rate"], 0.5)
        self.assertEqual(result["depth_counts"], {"1": 1, "3": 1})


if __name__ == "__main__":
    unittest.main()
