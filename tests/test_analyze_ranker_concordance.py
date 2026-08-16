from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from scripts.analyze_ranker_concordance import (
    _exact_two_sided_binomial_p,
    analyze,
)


def _branch(q: float, placed: float, fill: float, volume: float) -> dict:
    return {
        "q": q,
        "is_control": False,
        "q_components": {
            "volume": volume, "support": 0.0, "depth": 0.0, "lateral": 0.0,
            "lift": 0.0, "routing": 0.0, "zone": 0.0, "unattributed": 0.0,
            "immediate_total": q, "risk_penalty": 0.0,
        },
        "runs": [{
            "repeat": 0,
            "steps": 20,
            "evaluation": {"num_placed_items": placed, "fill_score": fill},
            "parent_state_matches": True,
            "forced_action_accepted": True,
            "prefix_reproduced": True,
        }],
        "reproducibility": {
            "repeats": 1,
            "placed_identical": True,
            "fill_identical": True,
            "placed_sd": None,
            "fill_sd": None,
            "parent_state_matches_all": True,
            "prefix_reproduced_all": True,
        },
    }


def _dataset(task_id: str, states: list[list[dict]]) -> dict:
    return {
        "schema_version": 2,
        "task_id": task_id,
        "states": [
            {"step": 4 + 2 * index, "branches": branches}
            for index, branches in enumerate(states)
        ],
    }


class AnalyzeRankerConcordanceTests(unittest.TestCase):
    def test_exact_binomial_matches_known_values(self) -> None:
        self.assertAlmostEqual(_exact_two_sided_binomial_p(6, 6), 0.03125)
        self.assertAlmostEqual(_exact_two_sided_binomial_p(2, 3), 1.0)

    def test_discordant_ordering_is_counted_against_live_q(self) -> None:
        # Higher q reaches the WORSE final outcome in both states.
        data = _dataset("b-test", [
            [_branch(2.0, 0.4, 20.0, 1.0), _branch(1.0, 0.6, 25.0, -1.0)],
            [_branch(3.0, 0.3, 15.0, 1.0), _branch(1.5, 0.5, 22.0, -1.0)],
        ])
        with tempfile.TemporaryDirectory() as scratch:
            root = pathlib.Path(scratch)
            (root / "branch-labels.json").write_text(json.dumps(data))
            result = analyze([root])
        placed = result["per_outcome"]["placed"]
        self.assertEqual(placed["live_q"]["decided_pairs"], 2)
        self.assertEqual(placed["live_q"]["concordant"], 0)
        self.assertEqual(placed["top_pick"]["states"], 2)
        self.assertEqual(placed["top_pick"]["top_q_reaches_best_outcome"], 0)

    def test_reweighting_learns_a_component_that_tracks_outcome(self) -> None:
        # volume delta always points at the better final outcome; the fit is
        # evaluated held-out across two configs.
        states = [
            [_branch(2.0, 0.4, 20.0, -1.0), _branch(1.0, 0.6, 25.0, 1.0)],
            [_branch(3.0, 0.3, 15.0, -1.0), _branch(1.5, 0.5, 22.0, 1.0)],
        ]
        with tempfile.TemporaryDirectory() as scratch:
            roots = []
            for name in ("cfg-a", "cfg-b"):
                root = pathlib.Path(scratch) / name
                root.mkdir()
                (root / "branch-labels.json").write_text(
                    json.dumps(_dataset(name, states))
                )
                roots.append(root)
            result = analyze(roots)
        held = result["per_outcome"]["placed"]["held_out_reweighting"]
        self.assertEqual(held["decided_pairs"], 4)
        self.assertEqual(held["concordant"], 4)


if __name__ == "__main__":
    unittest.main()
