"""Stage 0 probe: perturbation generation, spanning, and verdicts."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.probe_perturbation_novelty import (  # noqa: E402
    perturbation_candidate,
    perturbations,
    pick_spanning,
    summarize,
    verdicts,
)

BASE = {
    "item_idx": 2,
    "container_idx": 0,
    "place_pos": [1.0, 2.0, 0.5],
    "orientation": 0,
}
OBSERVATION = {"pool_list": [{"index": 5}, {"index": 6}, {"index": 7}]}


def _row(candidate_id, genuine, fill, soft=0.0, covered=0.0, misrouted=0.0):
    return {
        "root_candidate_id": candidate_id,
        "terminal_genuine": genuine,
        "terminal_vector": {
            "fill_gain": fill,
            "soft_violation_gain": soft,
            "priority_covered_gain": covered,
            "priority_misrouted_gain": misrouted,
        },
    }


class PerturbationTests(unittest.TestCase):
    def test_translations_move_only_the_plane_and_keep_the_item(self):
        rows = perturbations(BASE, magnitudes=[0.05], orientation_swaps=0)
        self.assertEqual(len(rows), 4)  # +-x, +-y
        for row in rows:
            action = row["action"]
            self.assertEqual(action["item_idx"], BASE["item_idx"])
            self.assertEqual(action["orientation"], BASE["orientation"])
            self.assertEqual(action["place_pos"][2], BASE["place_pos"][2])
            moved = [
                abs(action["place_pos"][i] - BASE["place_pos"][i])
                for i in range(2)
            ]
            self.assertAlmostEqual(max(moved), 0.05)

    def test_orientation_swaps_never_repeat_the_base_pose(self):
        rows = perturbations(BASE, magnitudes=[], orientation_swaps=3)
        self.assertEqual(len(rows), 3)
        poses = {row["action"]["orientation"] for row in rows}
        self.assertNotIn(BASE["orientation"], poses)
        for row in rows:
            self.assertEqual(row["action"]["place_pos"], BASE["place_pos"])

    def test_every_magnitude_is_generated_in_both_signs(self):
        rows = perturbations(
            BASE, magnitudes=[0.02, 0.10], orientation_swaps=0,
        )
        self.assertEqual({row["magnitude"] for row in rows}, {0.02, 0.10})
        self.assertEqual(len(rows), 8)

    def test_a_perturbation_gets_a_different_id_from_the_base(self):
        base = perturbation_candidate(BASE, OBSERVATION, label="base", rank=0)
        moved = perturbations(BASE, magnitudes=[0.05], orientation_swaps=0)[0]
        other = perturbation_candidate(
            moved["action"], OBSERVATION, label=moved["label"], rank=1,
        )
        self.assertNotEqual(base.candidate_id, other.candidate_id)
        self.assertEqual(base.selection["stable_item_index"], 7)


class PickSpanningTests(unittest.TestCase):
    def _rows(self):
        return [
            {"kind": "translate", "magnitude": 0.02, "label": f"a{i}"}
            for i in range(4)
        ] + [
            {"kind": "translate", "magnitude": 0.10, "label": f"b{i}"}
            for i in range(4)
        ] + [
            {"kind": "orientation", "magnitude": 0.0, "label": "o0"},
        ]

    def test_each_bucket_gets_a_slot_before_any_gets_a_second(self):
        picked = pick_spanning(self._rows(), 3)
        self.assertEqual(len(picked), 3)
        self.assertEqual(
            len({(r["kind"], r["magnitude"]) for r in picked}), 3,
        )

    def test_taking_the_head_of_one_bucket_is_what_this_avoids(self):
        picked = pick_spanning(self._rows(), 2)
        self.assertNotEqual(
            picked[0]["magnitude"], picked[1]["magnitude"],
        )

    def test_width_above_supply_returns_everything_once(self):
        rows = self._rows()
        picked = pick_spanning(rows, 99)
        self.assertEqual(len(picked), len(rows))
        self.assertEqual(
            len({r["label"] for r in picked}), len(rows),
        )


class VerdictTests(unittest.TestCase):
    def test_a_strictly_better_fill_beats_the_base(self):
        fork = {"root_candidates": [
            _row("base", True, 10.0), _row("p1", True, 12.0),
        ]}
        out = verdicts(fork, "base")
        self.assertTrue(out["base_genuine"])
        self.assertEqual(
            out["per_candidate"]["p1"]["verdict"], "beats_base",
        )

    def test_a_worse_fill_loses(self):
        fork = {"root_candidates": [
            _row("base", True, 10.0), _row("p1", True, 8.0),
        ]}
        self.assertEqual(
            verdicts(fork, "base")["per_candidate"]["p1"]["verdict"],
            "loses_to_base",
        )

    def test_an_identical_terminal_is_not_reported_as_a_tradeoff(self):
        """The distinction the v1 probe could not make afterwards: a
        perturbation whose terminal is the same is evidence the episode
        absorbed it, not evidence of a trade-off the rule declines."""
        fork = {"root_candidates": [
            _row("base", True, 10.0), _row("p1", True, 10.0),
        ]}
        entry = verdicts(fork, "base")["per_candidate"]["p1"]
        self.assertEqual(entry["verdict"], "identical")

    def test_the_raw_vectors_survive_into_the_record(self):
        fork = {"root_candidates": [
            _row("base", True, 10.0), _row("p1", True, 12.0),
        ]}
        out = verdicts(fork, "base")
        self.assertEqual(out["base_terminal_vector"]["fill_gain"], 10.0)
        self.assertEqual(
            out["per_candidate"]["p1"]["terminal_vector"]["fill_gain"], 12.0,
        )

    def test_more_fill_but_a_new_violation_is_incomparable(self):
        fork = {"root_candidates": [
            _row("base", True, 10.0),
            _row("p1", True, 12.0, soft=1.0),
        ]}
        self.assertEqual(
            verdicts(fork, "base")["per_candidate"]["p1"]["verdict"],
            "incomparable",
        )

    def test_a_non_genuine_perturbation_is_not_counted_as_a_loss(self):
        fork = {"root_candidates": [
            _row("base", True, 10.0), _row("p1", False, 99.0),
        ]}
        self.assertEqual(
            verdicts(fork, "base")["per_candidate"]["p1"]["verdict"],
            "not_genuine",
        )

    def test_a_non_genuine_base_yields_no_verdicts_at_all(self):
        """Censor rather than guess: without the base's own terminal there
        is nothing to compare against, and a missing comparison must not
        read as evidence the rule was not beaten."""
        fork = {"root_candidates": [
            _row("base", False, 10.0), _row("p1", True, 12.0),
        ]}
        out = verdicts(fork, "base")
        self.assertFalse(out["base_genuine"])
        self.assertEqual(out["per_candidate"], {})


class SummaryTests(unittest.TestCase):
    def test_counts_steps_not_just_comparisons(self):
        episode = {"records": [
            {"forked": True, "generated": 10, "feasible": 4,
             "base_genuine": True, "verdicts": [
                 {"label": "a", "kind": "translate", "magnitude": 0.02,
                  "verdict": "beats_base"},
                 {"label": "b", "kind": "translate", "magnitude": 0.02,
                  "verdict": "incomparable"},
             ]},
            {"forked": True, "generated": 10, "feasible": 2,
             "base_genuine": True, "verdicts": [
                 {"label": "c", "kind": "orientation", "magnitude": 0.0,
                  "verdict": "loses_to_base"},
             ]},
            {"generated": 10, "feasible": 0},
        ]}
        summary = summarize(episode)
        self.assertEqual(summary["forked_steps"], 2)
        self.assertEqual(summary["steps_with_a_winning_perturbation"], 1)
        self.assertEqual(summary["comparisons"], 3)
        self.assertEqual(summary["verdict_tally"]["beats_base"], 1)
        self.assertEqual(summary["perturbations_generated"], 30)
        self.assertEqual(summary["perturbations_feasible"], 6)
        self.assertEqual(summary["feasible_rate"], 0.2)


if __name__ == "__main__":
    unittest.main()
