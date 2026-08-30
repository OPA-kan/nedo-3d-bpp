"""The flag sweep's arm construction and paired-delta arithmetic."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rule_alpha.config import DEFAULT_CONFIG  # noqa: E402
from scripts.sweep_rule_alpha_config import flipped, paired_delta  # noqa: E402


def _rows(fills, placed):
    return [
        {"fill_score_proxy": f, "placed_count": p}
        for f, p in zip(fills, placed)
    ]


class FlippedTests(unittest.TestCase):
    def test_flips_exactly_one_flag_and_leaves_the_rest(self):
        config = flipped("ground_before_growth")
        self.assertNotEqual(
            config.ground_before_growth, DEFAULT_CONFIG.ground_before_growth,
        )
        self.assertEqual(
            config.compaction_iterations, DEFAULT_CONFIG.compaction_iterations,
        )

    def test_an_unknown_flag_is_refused(self):
        with self.assertRaises(ValueError):
            flipped("no_such_flag")

    def test_a_non_boolean_setting_is_refused(self):
        """Flipping a float would silently make it True/False."""
        with self.assertRaises(ValueError):
            flipped("compaction_iterations")


class PairedDeltaTests(unittest.TestCase):
    def test_counts_direction_per_cell_not_just_the_mean(self):
        """A mean alone is what hides 'one task up, one task down' -- the
        exact reading that left these flags undecided at n=2."""
        base = _rows([10.0, 20.0], [5, 9])
        arm = _rows([14.0, 16.0], [6, 8])
        delta = paired_delta(base, arm)
        self.assertEqual(delta["fill_delta_mean"], 0.0)
        self.assertEqual(delta["fill_cells_better"], 1)
        self.assertEqual(delta["fill_cells_worse"], 1)
        self.assertEqual(delta["fill_cells_identical"], 0)

    def test_a_byte_identical_arm_reads_as_identical_not_as_a_tie(self):
        base = _rows([10.0, 20.0], [5, 9])
        delta = paired_delta(base, _rows([10.0, 20.0], [5, 9]))
        self.assertEqual(delta["fill_cells_identical"], 2)
        self.assertEqual(delta["fill_cells_better"], 0)
        self.assertEqual(delta["fill_cells_worse"], 0)
        self.assertEqual(delta["placed_delta_sum"], 0)

    def test_per_cell_deltas_survive_for_inspection(self):
        base = _rows([10.0, 20.0, 30.0], [5, 9, 11])
        arm = _rows([11.5, 20.0, 25.0], [6, 9, 10])
        delta = paired_delta(base, arm)
        self.assertEqual(delta["per_cell_fill_delta"], [1.5, 0.0, -5.0])
        self.assertEqual(delta["per_cell_placed_delta"], [1, 0, -1])
        self.assertEqual(delta["placed_delta_sum"], 0)
        self.assertEqual(delta["fill_delta_min"], -5.0)
        self.assertEqual(delta["fill_delta_max"], 1.5)


if __name__ == "__main__":
    unittest.main()
