from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from scripts import analyze_ranker_divergence as analysis


class DivergenceTests(unittest.TestCase):
    def test_first_divergence_compares_the_action_not_diagnostics(self):
        left = [
            {
                "step": 0,
                "selected_item_index": 4,
                "container_index": 0,
                "orientation": 3,
                "place_pos": [0.1, 0.2, 0.3],
                "policy_seconds": 1.0,
            },
            {
                "step": 1,
                "selected_item_index": 17,
                "container_index": 0,
                "orientation": 3,
                "place_pos": [0.6, 0.2, 0.4],
            },
        ]
        right = [
            {
                "step": 0,
                "selected_item_index": 4,
                "container_index": 0,
                "orientation": 3,
                "place_pos": [0.1, 0.2, 0.3],
                "policy_seconds": 2.0,
            },
            {
                "step": 1,
                "selected_item_index": 28,
                "container_index": 0,
                "orientation": 3,
                "place_pos": [0.5, -0.2, 0.4],
            },
        ]

        result = analysis.first_action_divergence(left, right)

        self.assertEqual(result["step"], 1)
        self.assertEqual(result["left"]["item_index"], 17)
        self.assertEqual(result["right"]["item_index"], 28)


class DecompositionTests(unittest.TestCase):
    class Geometry:
        @staticmethod
        def support_ratio(_candidate, _container):
            return 0.75

    class Agent:
        Geometry = None

        @staticmethod
        def release_rotation_risk_probability_mech(*_args):
            return 0.2

        @staticmethod
        def release_large_slide_probability(*_args):
            return 0.4

    Agent.Geometry = Geometry

    def test_decomposition_sums_to_old_and_active_scores(self):
        candidate = analysis.SimpleCandidate(
            center=(0.5, 0.4, 0.3),
            size=(0.2, 0.3, 0.4),
            name="release_candidate",
        )
        item = {"mass": 2.0, "is_prioritized": False}
        container = {"is_prioritized": False}

        result = analysis.decompose_score(
            self.Agent,
            candidate,
            item,
            container,
            orientation=0,
            has_priority_container=False,
            rotation_lambda=1.0,
            slide_lambda=0.5,
        )

        expected_old = (
            12.0 * 0.2 * 0.3 * 0.4
            + 2.0 * 0.75
            + 0.35 * 0.4
            - 0.12 * 0.5
            - 0.18 * 0.3 * 2.0
        )
        self.assertAlmostEqual(result["q_old"], expected_old)
        self.assertAlmostEqual(
            result["q_active"], expected_old - 0.2 - 0.5 * 0.4
        )
        self.assertAlmostEqual(
            sum(
                result[key]
                for key in (
                    "term_12v",
                    "term_2r",
                    "term_depth",
                    "term_x",
                    "term_z_mass",
                    "term_route",
                )
            ),
            result["q_old"],
        )

    def test_settled_candidate_has_no_release_penalty(self):
        candidate = analysis.SimpleCandidate(
            center=(0.0, 0.0, 0.1),
            size=(1.0, 1.0, 0.2),
            name="candidate",
        )
        result = analysis.decompose_score(
            self.Agent,
            candidate,
            {"mass": 1.0},
            {"is_prioritized": False},
            orientation=0,
            has_priority_container=False,
            rotation_lambda=1.0,
            slide_lambda=0.5,
        )
        self.assertIsNone(result["p_rot"])
        self.assertIsNone(result["p_slide"])
        self.assertEqual(result["q_old"], result["q_active"])


class RankingTests(unittest.TestCase):
    def test_selected_action_overrides_a_fresh_audit_miss(self):
        audit = analysis.SearchMembership(
            reached_ids=frozenset({"other"}),
            observed_ids=None,
            source="fresh rerun",
        )

        combined = analysis.add_selected_evidence(audit, "selected", "right")

        self.assertTrue(combined.verdict("selected"))
        self.assertIn("selected", combined.forced_selected_ids)
        self.assertFalse(combined.verdict("not-reached"))

    def test_stratified_jsonl_only_knows_membership_for_sampled_rows(self):
        records = [
            {"candidate_id": "reached", "found_by_anytime": True},
            {"candidate_id": "missed", "found_by_anytime": False},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "candidates.jsonl"
            path.write_text(
                "\n".join(json.dumps(record) for record in records),
                encoding="utf-8",
            )
            membership = analysis.load_search_membership(path)

        self.assertIsNotNone(membership)
        self.assertTrue(membership.verdict("reached"))
        self.assertFalse(membership.verdict("missed"))
        self.assertIsNone(membership.verdict("not-sampled"))

    def test_ranks_membership_and_selected_margins(self):
        rows = [
            {"candidate_id": "a", "item_index": 1, "q_old": 4.0, "q_active": 5.0},
            {"candidate_id": "b", "item_index": 1, "q_old": 5.0, "q_active": 3.0},
            {"candidate_id": "c", "item_index": 2, "q_old": 3.0, "q_active": 4.0},
        ]

        analysis.annotate_ranks_and_membership(
            rows,
            left_membership=analysis.SearchMembership(
                frozenset({"a", "b"}), None, "left"
            ),
            right_membership=analysis.SearchMembership(
                frozenset({"a", "c"}), None, "right"
            ),
            left_selected_id="a",
            right_selected_id="c",
        )

        by_id = {row["candidate_id"]: row for row in rows}
        self.assertEqual(by_id["a"]["across_candidate_rank"], 1)
        self.assertEqual(by_id["c"]["across_candidate_rank"], 2)
        self.assertEqual(by_id["a"]["item_rank"], 1)
        self.assertEqual(by_id["b"]["item_rank"], 1)
        self.assertEqual(by_id["c"]["item_rank"], 2)
        self.assertEqual(by_id["b"]["within_item_rank"], 2)
        self.assertEqual(by_id["b"]["old_across_candidate_rank"], 1)
        self.assertEqual(by_id["b"]["old_within_item_rank"], 1)
        self.assertFalse(by_id["a"]["new_search_only"])
        self.assertTrue(by_id["c"]["new_search_only"])
        self.assertAlmostEqual(by_id["b"]["margin_to_left_selected"], 2.0)
        self.assertAlmostEqual(by_id["a"]["margin_to_right_selected"], -1.0)

    def test_sample_absence_is_unknown_not_new_search_only(self):
        rows = [
            {
                "candidate_id": "sampled-out",
                "item_index": 1,
                "q_old": 5.0,
                "q_active": 5.0,
            },
            {
                "candidate_id": "known-old-miss",
                "item_index": 2,
                "q_old": 4.0,
                "q_active": 4.0,
            },
        ]
        left = analysis.SearchMembership(
            reached_ids=frozenset(),
            observed_ids=frozenset({"known-old-miss"}),
            source="stratified sample",
        )
        right = analysis.SearchMembership(
            reached_ids=frozenset({"sampled-out", "known-old-miss"}),
            observed_ids=None,
            source="complete current audit",
        )

        analysis.annotate_ranks_and_membership(
            rows,
            left_membership=left,
            right_membership=right,
            left_selected_id=None,
            right_selected_id=None,
        )

        by_id = {row["candidate_id"]: row for row in rows}
        self.assertIsNone(by_id["sampled-out"]["left_search_reached"])
        self.assertIsNone(by_id["sampled-out"]["new_search_only"])
        self.assertFalse(by_id["known-old-miss"]["left_search_reached"])
        self.assertTrue(by_id["known-old-miss"]["new_search_only"])


if __name__ == "__main__":
    unittest.main()
