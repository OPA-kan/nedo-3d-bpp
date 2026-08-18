"""Branch labels must carry all five official axes, not two.

`build_branch_labels.py` runs each forced sibling to the end of the
episode, which is the only label shape this project has left standing --
its own docstring records that every short-horizon label was measured
and found unusable for a board-value question. But the record it kept
was `fill_score` and `num_placed_items` (plus `shake_response`), and
`step_metrics` was dropped for size, taking the attribute-placement
counts and the centre of mass with it. A value function trained on that
can only learn two of the five axes.

These tests pin the terminal vector: what it extracts, that it takes the
LAST step, and that a missing key is omitted rather than defaulted, so a
contract change surfaces instead of reading as a clean board.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_branch_labels import (  # noqa: E402
    TERMINAL_AXIS_KEYS,
    terminal_axis_vector,
)


class TerminalAxisVectorTests(unittest.TestCase):
    def test_covers_both_attribute_axes_and_the_centre_of_mass(self):
        for key in (
            "soft_clean_ratio",
            "soft_covered_by_other",
            "priority_clean_ratio",
            "priority_covered_by_other",
            "priority_misrouted",
        ):
            self.assertIn(key, TERMINAL_AXIS_KEYS)
        self.assertTrue(
            any("com" in key for key in TERMINAL_AXIS_KEYS),
            "no centre-of-mass key: cog cannot be learned from this label",
        )

    def test_reads_the_last_step_not_the_first(self):
        evaluation = {
            "step_metrics": [
                {"soft_clean_ratio": 1.0, "priority_clean_ratio": 1.0},
                {"soft_clean_ratio": 0.5, "priority_clean_ratio": 0.75},
            ]
        }

        vector = terminal_axis_vector(evaluation)

        self.assertEqual(vector["soft_clean_ratio"], 0.5)
        self.assertEqual(vector["priority_clean_ratio"], 0.75)

    def test_a_missing_key_is_omitted_rather_than_defaulted(self):
        """A silent zero would read as a perfectly clean board."""
        evaluation = {"step_metrics": [{"soft_clean_ratio": 0.5}]}

        vector = terminal_axis_vector(evaluation)

        self.assertEqual(vector, {"soft_clean_ratio": 0.5})
        self.assertNotIn("priority_clean_ratio", vector)

    def test_an_episode_with_no_steps_yields_an_empty_vector(self):
        self.assertEqual(terminal_axis_vector({}), {})
        self.assertEqual(terminal_axis_vector({"step_metrics": []}), {})

    def test_unrelated_step_fields_are_not_carried(self):
        evaluation = {
            "step_metrics": [
                {
                    "soft_clean_ratio": 1.0,
                    "settle_final_position": [0.0, 0.0, 0.0],
                    "depth_occupancy_profile": [1, 2, 3],
                }
            ]
        }

        vector = terminal_axis_vector(evaluation)

        self.assertEqual(vector, {"soft_clean_ratio": 1.0})


if __name__ == "__main__":
    unittest.main()
