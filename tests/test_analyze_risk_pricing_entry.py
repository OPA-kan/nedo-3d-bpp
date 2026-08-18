"""The entry gate's frozen constants and channel mapping.

The protocol pins "materially lower" to an absolute 0.10 drop and the
gate to E2 >= 0.30 with a non-fatal control that must lose. Those are
the numbers that stop the gate from becoming a judgement made after
seeing the data, so they are pinned here too: a future edit that
loosens either has to change a test and say so.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_risk_pricing_entry import (  # noqa: E402
    CHANNEL_KEY,
    E2_GATE,
    MATERIAL_DROP,
    analyze,
    measure_step,
)


def decision(step, candidates, selected_rank=0):
    return {
        "event": "decision",
        "step": step,
        "candidate_diagnostics": {
            "multi_axis_selector": {
                "selected_rank": selected_rank,
                "candidates": candidates,
            }
        },
    }


def candidate(rank, rotation, slide, score):
    return {
        "rank": rank,
        "rotation_probability": rotation,
        "slide_probability": slide,
        "adjusted_score": score,
    }


class FrozenConstantsTests(unittest.TestCase):
    def test_material_drop_and_gate_are_the_protocol_values(self):
        self.assertEqual(MATERIAL_DROP, 0.10)
        self.assertEqual(E2_GATE, 0.30)

    def test_each_death_channel_reads_its_own_probability(self):
        self.assertEqual(CHANNEL_KEY["topple"], "rotation_probability")
        self.assertEqual(CHANNEL_KEY["slide"], "slide_probability")
        self.assertNotIn("transport_invalid", CHANNEL_KEY)


class MeasureStepTests(unittest.TestCase):
    def test_reads_the_channel_named_and_not_the_other(self):
        step = decision(
            5,
            [
                candidate(0, rotation=0.60, slide=0.10, score=1.0),
                candidate(1, rotation=0.05, slide=0.90, score=0.9),
            ],
        )

        topple = measure_step(step, CHANNEL_KEY["topple"])
        slide = measure_step(step, CHANNEL_KEY["slide"])

        self.assertTrue(topple["materially_lower"])
        self.assertAlmostEqual(topple["drop"], 0.55)
        self.assertFalse(slide["lower"])

    def test_a_drop_just_under_the_threshold_is_not_material(self):
        step = decision(
            5,
            [
                candidate(0, rotation=0.50, slide=0.0, score=1.0),
                candidate(1, rotation=0.41, slide=0.0, score=1.0),
            ],
        )

        measured = measure_step(step, CHANNEL_KEY["topple"])

        self.assertTrue(measured["lower"])
        self.assertFalse(measured["materially_lower"])

    def test_records_what_the_safer_alternative_gives_up(self):
        step = decision(
            5,
            [
                candidate(0, rotation=0.90, slide=0.0, score=2.0),
                candidate(1, rotation=0.10, slide=0.0, score=1.25),
            ],
        )

        measured = measure_step(step, CHANNEL_KEY["topple"])

        self.assertAlmostEqual(measured["score_given_up"], 0.75)

    def test_a_lone_candidate_yields_nothing_to_compare(self):
        step = decision(5, [candidate(0, 0.9, 0.0, 1.0)])

        self.assertIsNone(measure_step(step, CHANNEL_KEY["topple"]))


class GateTests(unittest.TestCase):
    def _episode(self, channel, fatal_rotation_gap, steps=3):
        decisions = [
            decision(
                index,
                [
                    candidate(0, rotation=0.20, slide=0.0, score=1.0),
                    candidate(1, rotation=0.19, slide=0.0, score=1.0),
                ],
            )
            for index in range(steps - 1)
        ]
        decisions.append(
            decision(
                steps - 1,
                [
                    candidate(0, rotation=0.90, slide=0.0, score=1.0),
                    candidate(
                        1,
                        rotation=0.90 - fatal_rotation_gap,
                        slide=0.0,
                        score=1.0,
                    ),
                ],
            )
        )
        return {
            "label": f"ep-{channel}-{fatal_rotation_gap}",
            "case_id": "case",
            "channel": channel,
            "decisions": decisions,
        }

    def test_lever_exists_when_fatal_steps_beat_the_control(self):
        episodes = [self._episode("topple", 0.5) for _ in range(4)]

        result = analyze(episodes)

        self.assertEqual(result["physical_deaths_measured"], 4)
        self.assertEqual(
            result["E1_E2_fatal"]["fraction_materially_lower"], 1.0
        )
        self.assertEqual(
            result["E4_control_non_fatal"]["fraction_materially_lower"], 0.0
        )
        self.assertTrue(result["lever_exists"])

    def test_lever_is_empty_when_the_drop_is_never_material(self):
        episodes = [self._episode("topple", 0.02) for _ in range(4)]

        result = analyze(episodes)

        self.assertEqual(
            result["E1_E2_fatal"]["fraction_materially_lower"], 0.0
        )
        self.assertFalse(result["lever_exists"])

    def test_the_control_can_veto_a_passing_rate(self):
        """A signal present everywhere is not a signal about death."""
        episodes = []
        for _ in range(4):
            episode = self._episode("topple", 0.5)
            # Make the ordinary steps just as separable as the fatal one.
            for entry in episode["decisions"][:-1]:
                entry["candidate_diagnostics"]["multi_axis_selector"][
                    "candidates"
                ] = [
                    candidate(0, rotation=0.90, slide=0.0, score=1.0),
                    candidate(1, rotation=0.40, slide=0.0, score=1.0),
                ]
            episodes.append(episode)

        result = analyze(episodes)

        self.assertEqual(
            result["E1_E2_fatal"]["fraction_materially_lower"], 1.0
        )
        self.assertTrue(result["gate_rate"])
        self.assertFalse(result["gate_control"])
        self.assertFalse(result["lever_exists"])

    def test_non_physical_endings_are_not_counted_as_deaths(self):
        episodes = [self._episode("transport_invalid", 0.5)]

        result = analyze(episodes)

        self.assertEqual(result["physical_deaths_measured"], 0)


if __name__ == "__main__":
    unittest.main()
