"""The PCT learning signal, applied to logged episodes.

What these pin is the arithmetic that makes an episode teachable without
a terminal: the telescoped return, the per-(cell, step) baseline, and the
exponential advantage weight whose degenerate case is behaviour cloning.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_advantage_policy_dataset as builder  # noqa: E402
from scripts import train_rollout_trigger as trainer  # noqa: E402


def _candidate(candidate_id: str) -> dict:
    return {
        "root_candidate_id": candidate_id,
        "safe": True,
        "stable_item_index": 0,
        "command_action": {
            "container_idx": 0, "place_pos": [0.0, 0.0, 0.0],
            "orientation": 0, "item_idx": 0,
        },
    }


def _manifest(steps: list[tuple[float, str, int]], final: float) -> dict:
    return {
        "episodes": [{
            "final_metrics": {"fill_score_proxy": final},
            "records": [
                {
                    "step": index,
                    "root_id": f"r{index}",
                    "board_fingerprint": f"b{index}",
                    "snapshot_path": f"step-{index:03d}-state.json",
                    "metrics_before": {"fill_score_proxy": before},
                    "selection": {"selected_candidate_id": selected},
                    "search": {"root_candidates": [
                        _candidate(f"c{n}") for n in range(candidates)
                    ]},
                }
                for index, (before, selected, candidates) in enumerate(steps)
            ],
        }]
    }


class ReturnTests(unittest.TestCase):
    def _rows(self, manifest: dict, *, snapshots: int = 4):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "cup-cell-x" / "horse" / "rollout"
            (root / "episode-000").mkdir(parents=True)
            for index in range(snapshots):
                (root / "episode-000" / f"step-{index:03d}-state.json").write_text(
                    "{}", encoding="utf-8"
                )
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            return builder.episode_rows(path, cell="cell-x", horse="horse")

    def test_the_return_telescopes_from_the_final_fill(self):
        rows = self._rows(_manifest(
            [(0.0, "c0", 3), (4.0, "c1", 3), (9.0, "c0", 3)], final=12.0
        ))
        self.assertEqual([row["return"] for row in rows], [12.0, 8.0, 3.0])

    def test_an_episode_that_ran_dry_still_labels_its_prefix(self):
        """No terminal is required -- that is the whole point.

        The episode below stops with the board far from full; its states
        are labelled by what it did achieve, exactly as a stream-
        exhausting episode would be.
        """
        rows = self._rows(_manifest(
            [(0.0, "c0", 2), (2.0, "c1", 2)], final=3.0
        ))
        self.assertEqual([row["return"] for row in rows], [3.0, 1.0])

    def test_a_state_with_one_candidate_is_not_a_decision(self):
        rows = self._rows(_manifest(
            [(0.0, "c0", 1), (1.0, "c1", 2)], final=5.0
        ))
        self.assertEqual([row["step"] for row in rows], [1])

    def test_an_action_outside_its_own_safe_support_is_skipped(self):
        """The Cup 008 mismatch: not trainable, and not silently mislabelled."""
        rows = self._rows(_manifest(
            [(0.0, "elsewhere", 3), (1.0, "c1", 3)], final=5.0
        ))
        self.assertEqual([row["step"] for row in rows], [1])


class BaselineTests(unittest.TestCase):
    def test_the_baseline_is_the_mean_over_horses_at_that_step(self):
        rows = [
            {"cell": "a", "step": 0, "return": 10.0},
            {"cell": "a", "step": 0, "return": 4.0},
            {"cell": "a", "step": 1, "return": 3.0},
            {"cell": "b", "step": 0, "return": 100.0},
        ]
        builder.add_advantages(rows)
        self.assertEqual([row["advantage"] for row in rows],
                         [3.0, -3.0, 0.0, 0.0])

    def test_a_step_only_one_horse_reached_gets_zero_advantage(self):
        """Neutral, not excluded: weight 1, so it teaches like plain BC."""
        rows = [{"cell": "a", "step": 0, "return": 7.0},
                {"cell": "a", "step": 1, "return": 2.0}]
        stats = builder.add_advantages(rows)
        self.assertEqual(stats["singleton_baselines"], 2)
        self.assertEqual([row["advantage"] for row in rows], [0.0, 0.0])


class WeightTests(unittest.TestCase):
    def test_build_arrays_defaults_the_weight_so_old_corpora_are_unchanged(self):
        import numpy as np

        examples = [{
            "container": [[1.0]], "packed_item": [[1.0]],
            "visible_item": [[1.0]], "candidate": [[1.0], [2.0]],
            "label": 0.0, "selected_index": 0,
        }]
        stats = trainer.compute_stats(examples)
        arrays = trainer.build_arrays(examples, stats)
        self.assertTrue(np.allclose(arrays["advantage_weight"], 1.0))

    def test_uniform_weights_reduce_to_behaviour_cloning(self):
        from scripts.train_advantage_policy import attach_weights

        examples = [{"advantage": 0.0}, {"advantage": 0.0}]
        attach_weights(examples, beta=1.0, clip=20.0)
        self.assertEqual(
            [row["advantage_weight"] for row in examples], [1.0, 1.0]
        )

    def test_a_negative_advantage_shrinks_rather_than_reverses(self):
        """Offline soundness: never push mass onto an unobserved action."""
        from scripts.train_advantage_policy import attach_weights

        examples = [{"advantage": -5.0}, {"advantage": 5.0}]
        attach_weights(examples, beta=1.0, clip=20.0)
        weights = [row["advantage_weight"] for row in examples]
        self.assertGreater(weights[0], 0.0)
        self.assertLess(weights[0], 1.0)
        self.assertEqual(weights[1], 20.0)


class ObjectiveTests(unittest.TestCase):
    def test_the_ensemble_format_admits_the_advantage_objective(self):
        import inspect

        source = inspect.getsource(trainer.save_allocator_ensemble)
        self.assertIn('"advantage": fit_advantage_member', source)

    def test_the_runtime_can_load_an_advantage_model(self):
        import inspect

        from scripts import learned_allocator_policy

        source = inspect.getsource(learned_allocator_policy)
        self.assertIn(
            '{"allocator", "preference", "advantage"}', source
        )


class SharedBoardPairTests(unittest.TestCase):
    def _row(self, fingerprint, ids, selected, value):
        return {
            "board_fingerprint": fingerprint, "candidate_ids": ids,
            "selected_index": selected, "return": value,
        }

    def test_a_pair_needs_the_same_board_and_different_actions(self):
        from scripts.train_advantage_policy import shared_board_pairs

        rows = [
            self._row("b", ["c0", "c1"], 0, 10.0),
            self._row("b", ["c0", "c1"], 1, 4.0),
            self._row("b", ["c0", "c1"], 0, 9.0),   # same action, no pair
            self._row("other", ["c0", "c1"], 1, 1.0),
        ]
        pairs = shared_board_pairs(rows)
        self.assertEqual(len(pairs), 2)
        for left, right in pairs:
            self.assertNotEqual(left["selected_index"], right["selected_index"])

    def test_a_differing_candidate_set_is_not_a_comparison(self):
        from scripts.train_advantage_policy import shared_board_pairs

        rows = [
            self._row("b", ["c0", "c1"], 0, 10.0),
            self._row("b", ["c0", "c2"], 1, 4.0),
        ]
        self.assertEqual(shared_board_pairs(rows), [])


if __name__ == "__main__":
    unittest.main()
