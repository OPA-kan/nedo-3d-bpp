"""Value-target collection and the leave-one-cell-out scoring."""

from __future__ import annotations

import pathlib
import sys
import unittest

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.train_board_value import (  # noqa: E402
    INCUMBENT_SPEARMAN,
    feature_matrix,
    rank_by_step,
    standardise,
)


def _row(case, step, value, **features):
    return {
        "case": case, "step": step, "remaining_volume": value,
        "features": features,
    }


class TelescopedTargetTests(unittest.TestCase):
    def test_the_label_needs_no_terminal(self):
        """The whole point: an episode that ends because the generator
        ran dry labels its states exactly as well as one that packs the
        stream out. V(s_t) is the suffix sum either way."""
        rewards = [0.4, 0.3, 0.2]
        states = [{"reward": r} for r in rewards]
        tail = 0.0
        for row in reversed(states):
            tail += row["reward"]
            row["remaining_volume"] = tail
        self.assertAlmostEqual(states[0]["remaining_volume"], 0.9)
        self.assertAlmostEqual(states[1]["remaining_volume"], 0.5)
        self.assertAlmostEqual(states[2]["remaining_volume"], 0.2)

    def test_the_label_decreases_along_a_trajectory(self):
        states = [{"reward": r} for r in (0.4, 0.3, 0.2)]
        tail = 0.0
        for row in reversed(states):
            tail += row["reward"]
            row["remaining_volume"] = tail
        values = [row["remaining_volume"] for row in states]
        self.assertEqual(values, sorted(values, reverse=True))


class FeatureMatrixTests(unittest.TestCase):
    def test_columns_follow_the_name_order_not_dict_order(self):
        rows = [_row("a", 0, 1.0, b=2.0, a=1.0)]
        matrix = feature_matrix(rows, ["a", "b"])
        self.assertEqual(matrix.tolist(), [[1.0, 2.0]])

    def test_a_missing_feature_is_zero_not_an_error(self):
        rows = [_row("a", 0, 1.0, a=1.0)]
        self.assertEqual(feature_matrix(rows, ["a", "b"]).tolist(), [[1.0, 0.0]])


class StandardiseTests(unittest.TestCase):
    def test_test_data_uses_the_training_statistics(self):
        """Standardising the held-out fold by its own mean would leak
        the fold into its own normalisation."""
        train = np.asarray([[0.0], [2.0]], dtype=np.float32)
        test = np.asarray([[4.0]], dtype=np.float32)
        train_z, test_z = standardise(train, test)
        self.assertAlmostEqual(float(train_z.mean()), 0.0, places=5)
        self.assertAlmostEqual(float(test_z[0][0]), 3.0, places=5)

    def test_a_constant_column_does_not_divide_by_zero(self):
        train = np.asarray([[5.0], [5.0]], dtype=np.float32)
        (train_z,) = standardise(train)
        self.assertTrue(np.all(np.isfinite(train_z)))


class RankByStepTests(unittest.TestCase):
    def test_it_ranks_within_a_step_not_across_them(self):
        """Across steps, remaining volume falls trivially with depth, so
        a global correlation would mostly measure episode progress."""
        rows = [
            _row("a", 4, 10.0), _row("b", 4, 20.0), _row("c", 4, 30.0),
            _row("a", 8, 3.0), _row("b", 8, 2.0), _row("c", 8, 1.0),
        ]
        predictions = np.asarray([1.0, 2.0, 3.0, 3.0, 2.0, 1.0])
        out = rank_by_step(rows, predictions, [4, 8])
        self.assertAlmostEqual(out["4"]["spearman"], 1.0)
        self.assertAlmostEqual(out["8"]["spearman"], 1.0)

    def test_a_step_with_too_few_boards_is_dropped_not_scored(self):
        rows = [_row("a", 4, 1.0), _row("b", 4, 2.0)]
        self.assertEqual(rank_by_step(rows, np.asarray([1.0, 2.0]), [4]), {})

    def test_the_counts_are_reported_with_the_correlation(self):
        rows = [_row(c, 4, float(i)) for i, c in enumerate("abcd")]
        out = rank_by_step(rows, np.asarray([1.0, 2.0, 3.0, 4.0]), [4])
        self.assertEqual(out["4"]["n"], 4)


class IncumbentBaselineTests(unittest.TestCase):
    def test_the_baseline_is_the_measured_rollout_not_zero(self):
        """The bar is what the teacher's own 10-step rollout scored on
        the same ground truth, so beating zero is not the claim."""
        self.assertEqual(set(INCUMBENT_SPEARMAN), {"4", "8", "12"})
        for value in INCUMBENT_SPEARMAN.values():
            self.assertGreater(value, 0.3)


if __name__ == "__main__":
    unittest.main()


class BootstrapCompositionTests(unittest.TestCase):
    """The two silent failures the smoke run caught."""

    def test_zero_remaining_is_not_the_genuine_set(self):
        """`no_retained_candidate` means the generator ran dry, not that
        the board is full -- it is genuine (the rule may read the row)
        but its remaining value is NOT zero. Conflating the two made the
        bootstrap skip the only case it exists for."""
        from scripts.run_vector_mcts import (
            GENUINE_TERMINATIONS,
            ZERO_REMAINING_TERMINATIONS,
        )

        self.assertEqual(ZERO_REMAINING_TERMINATIONS, {"stream_exhausted"})
        self.assertIn("no_retained_candidate", GENUINE_TERMINATIONS)
        self.assertNotIn(
            "no_retained_candidate", ZERO_REMAINING_TERMINATIONS,
        )

    def test_every_head_is_emitted_so_none_can_void_the_vector(self):
        """compose_leaf_value sets any component it is not given to None,
        and a None head drops the candidate out of
        terminal_eligible_candidates -- every verdict vanishes rather
        than the tail simply reading zero."""
        from scripts.run_vector_mcts import (
            LEAF_SUFFIX_TO_COMPONENT,
            compose_leaf_value,
        )

        achieved = {
            component: 1.0 for component in LEAF_SUFFIX_TO_COMPONENT.values()
        }
        partial = compose_leaf_value(achieved, {"fill_return": {"mean": 5.0}})
        self.assertIsNone(partial["soft_violation_gain"])

        complete = {s: {"mean": 0.0} for s in LEAF_SUFFIX_TO_COMPONENT}
        complete["fill_return"] = {"mean": 5.0}
        composed = compose_leaf_value(achieved, complete)
        self.assertEqual(composed["fill_gain"], 6.0)
        self.assertEqual(composed["soft_violation_gain"], 1.0)

    def test_the_model_emits_all_of_them(self):
        from scripts.run_vector_mcts import LEAF_SUFFIX_TO_COMPONENT
        from scripts.board_value_model import BoardValue

        directory = ROOT / "reports" / "value" / "board-value-v1"
        if not (directory / "model.json").exists():
            self.skipTest("no fitted model in the tree")
        prediction = BoardValue(directory).fill_return({
            "depth_map": np.zeros((1, 4, 4)),
            "container_list": [{
                "height": 2.0, "length": 2.0, "width": 1.0,
                "packed_items": [],
            }],
            "pool_list": [],
        })
        self.assertEqual(
            set(prediction), set(LEAF_SUFFIX_TO_COMPONENT),
        )
