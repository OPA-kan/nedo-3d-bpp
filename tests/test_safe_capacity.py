import json
import pathlib
import tempfile
import unittest

from scripts import measure_kappa_siblings as siblings
from scripts import measure_safe_capacity as safecap


class SurvivalWeightTests(unittest.TestCase):
    """
    The three rules are emitted together on purpose. P_fail does not exist:
    the rotation and slide models are separate, so any single combination is
    an assumption, and agreement across all three is what makes a result
    robust.
    """

    class _Agent:
        @staticmethod
        def release_rotation_risk_probability_mech(*_args):
            return 0.4

        @staticmethod
        def release_large_slide_probability(*_args):
            return 0.2

    class _Candidate:
        def __init__(self, name):
            self.name = name
            self.center = (0.0, 0.0, 0.0)
            self.size = (0.1, 0.1, 0.1)

    def test_release_options_use_all_three_rules(self):
        weights = safecap.survival_weights(
            self._Agent(), self._Candidate("release_candidate"), {}, {}, 0
        )

        self.assertAlmostEqual(weights["sum"], 0.4)
        self.assertAlmostEqual(weights["max"], 0.6)
        self.assertAlmostEqual(weights["product"], 0.48)
        self.assertTrue(weights["modelled"])

    def test_the_union_bound_rule_never_goes_negative(self):
        class Agent:
            @staticmethod
            def release_rotation_risk_probability_mech(*_args):
                return 0.8

            @staticmethod
            def release_large_slide_probability(*_args):
                return 0.7

        weights = safecap.survival_weights(
            Agent(), self._Candidate("release_candidate"), {}, {}, 0
        )

        self.assertEqual(weights["sum"], 0.0)

    def test_settled_options_are_unweighted_rather_than_invented(self):
        """Both models are release-specific; a settled weight would be made up."""
        weights = safecap.survival_weights(
            self._Agent(), self._Candidate("candidate"), {}, {}, 0
        )

        for rule in ("sum", "max", "product"):
            self.assertEqual(weights[rule], 1.0)
        self.assertFalse(weights["modelled"])


class LabelTests(unittest.TestCase):
    def _dataset(self, root, name, *, split, executed, safe, steps):
        directory = pathlib.Path(root) / name
        directory.mkdir(parents=True)
        for step in steps:
            (directory / f"step-{step:03d}-state.json").write_text("{}")
        (directory / "manifest.json").write_text(json.dumps({
            "split": split,
            "case": {
                "case_id": "b000-k20",
                "episode_steps_executed": executed,
                "final_status": {"is_valid": True, "is_placed_safe": safe},
                "steps": [
                    {
                        "step": step,
                        "status": "ok",
                        "snapshot_path": f"step-{step:03d}-state.json",
                    }
                    for step in steps
                ],
            },
        }))

    def test_final_holdout_is_skipped_and_named(self):
        with tempfile.TemporaryDirectory() as root:
            self._dataset(
                root, "dev", split="development", executed=10, safe=True,
                steps=[8],
            )
            self._dataset(
                root, "held", split="final_holdout", executed=10, safe=True,
                steps=[8],
            )

            rows, skipped = safecap.collect_snapshots(pathlib.Path(root))

            self.assertEqual(len(rows), 1)
            self.assertEqual(skipped, ["held"])

    def test_final_holdout_can_be_opened_deliberately(self):
        with tempfile.TemporaryDirectory() as root:
            self._dataset(
                root, "held", split="final_holdout", executed=10, safe=True,
                steps=[8],
            )

            rows, skipped = safecap.collect_snapshots(
                pathlib.Path(root), include_final_holdout=True
            )

            self.assertEqual(len(rows), 1)
            self.assertEqual(skipped, [])

    def test_a_safe_episode_is_negative_at_every_step(self):
        with tempfile.TemporaryDirectory() as root:
            self._dataset(
                root, "dev", split="development", executed=12, safe=True,
                steps=[8, 11],
            )

            rows, _ = safecap.collect_snapshots(pathlib.Path(root))

            for row in rows:
                self.assertEqual(row["terminal_channel"], "terminal")
                self.assertTrue(row["t_physical_censored"])
                self.assertIsNone(row["t_physical"])

    def test_a_toppling_episode_labels_by_distance_to_its_end(self):
        with tempfile.TemporaryDirectory() as root:
            self._dataset(
                root, "dev", split="development", executed=12, safe=False,
                steps=[8, 11],
            )

            rows, _ = safecap.collect_snapshots(pathlib.Path(root))
            by_step = {row["step"]: row for row in rows}

            self.assertEqual(by_step[11]["t_physical"], 1)
            self.assertEqual(by_step[8]["t_physical"], 4)
            for row in rows:
                self.assertEqual(row["terminal_channel"], "physical")
                self.assertFalse(row["t_physical_censored"])


class RankStatisticTests(unittest.TestCase):
    def test_auc_is_a_half_on_pure_ties(self):
        self.assertEqual(safecap.auc([1.0, 1.0, 1.0, 1.0], [1, 0, 1, 0]), 0.5)

    def test_auc_is_one_when_positives_rank_above(self):
        self.assertEqual(safecap.auc([3.0, 4.0, 1.0, 2.0], [1, 1, 0, 0]), 1.0)

    def test_auc_is_none_without_both_classes(self):
        self.assertIsNone(safecap.auc([1.0, 2.0], [0, 0]))

    def test_spearman_recovers_a_monotone_relation(self):
        self.assertEqual(
            safecap.spearman([1.0, 2.0, 3.0, 4.0], [10.0, 20.0, 30.0, 40.0]),
            1.0,
        )

    def test_spearman_needs_three_points(self):
        self.assertIsNone(safecap.spearman([1.0, 2.0], [1.0, 2.0]))


class SiblingSelectionTests(unittest.TestCase):
    def _row(self, candidate_id, item_index, score, safe=True):
        return {
            "candidate_id": candidate_id,
            "item_index": item_index,
            "score_immediate": score,
            "physical": {"is_placed_safe": safe},
        }

    def test_only_physically_labelled_candidates_are_eligible(self):
        rows = [
            self._row("a", 1, 5.0),
            {
                "candidate_id": "b",
                "item_index": 2,
                "score_immediate": 5.0,
                "physical": {"is_placed_safe": None},
            },
        ]

        chosen = siblings.sibling_candidates(rows, q_band=1.0, limit=4)

        self.assertEqual([row["candidate_id"] for row in chosen], ["a"])

    def test_the_band_is_relative_to_the_best_candidate(self):
        rows = [
            self._row("a", 1, 5.0),
            self._row("b", 2, 4.9),
            self._row("c", 3, 1.0),
        ]

        chosen = siblings.sibling_candidates(rows, q_band=0.15, limit=4)

        self.assertEqual({row["candidate_id"] for row in chosen}, {"a", "b"})

    def test_distinct_items_are_preferred_before_duplicates(self):
        rows = [
            self._row("a1", 1, 5.0),
            self._row("a2", 1, 4.99),
            self._row("b1", 2, 4.98),
        ]

        chosen = siblings.sibling_candidates(rows, q_band=1.0, limit=2)

        self.assertEqual({row["item_index"] for row in chosen}, {1, 2})


class SignTests(unittest.TestCase):
    def test_near_equal_values_are_ties_not_agreements(self):
        self.assertEqual(siblings.sign(1e-12), 0)
        self.assertEqual(siblings.sign(-1e-12), 0)
        self.assertEqual(siblings.sign(0.5), 1)
        self.assertEqual(siblings.sign(-0.5), -1)


if __name__ == "__main__":
    unittest.main()
