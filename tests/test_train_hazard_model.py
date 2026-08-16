from __future__ import annotations

import unittest

import numpy as np

from scripts.train_hazard_model import (
    candidate_vector,
    scalar_vector,
    splits,
    within_stratum_auc,
    within_stratum_spearman,
)


def _row(
    source: str,
    step: int,
    survival: int,
    episode: int = 0,
    terminal: float = 0.0,
) -> dict:
    return {
        "source_file": f"{source}-block0.jsonl",
        "step": step,
        "episode": episode,
        "placements_after": survival,
        "terminal_in_3": terminal,
        "afterstate": {
            "occupancy_mean": 0.1, "occupancy_max": 0.2,
            "occupancy_std": 0.05, "roughness": 0.01,
            "headroom_deficit": 0.1, "floor_fraction_free": 0.8,
            "placed": float(step + 1),
        },
        "afterstate_sealed_void": 0.02,
        "afterstate_sealed_void_by_items": 0.0,
        "afterstate_largest_free_span": 0.7,
        "options": 30,
        "type_index": 2,
        "candidate": {
            "center": [0.1, 0.2, 0.3],
            "size": [0.5, 0.4, 0.3],
            "orientation": 1,
        },
        "container": {"length": 2.0, "width": 1.4, "height": 1.6},
    }


class FeatureVectorTests(unittest.TestCase):
    def test_scalar_vector_width(self):
        self.assertEqual(len(scalar_vector(_row("c000-k1", 0, 5))), 11)

    def test_candidate_vector_width(self):
        # center 3 + size 3 + orientation 6 + type 7 + container 3
        self.assertEqual(len(candidate_vector(_row("c000-k1", 0, 5))), 22)


class StratifiedMetricTests(unittest.TestCase):
    def test_spearman_ignores_across_step_clock(self):
        # Across steps the label is a clock; these rows are all in
        # DIFFERENT strata, so no stratum reaches 3 rows and the metric
        # must abstain rather than report the trivial correlation.
        rows = [_row("c000-k1", s, 20 - s) for s in range(6)]
        result = within_stratum_spearman(rows, np.arange(6.0))
        self.assertIsNone(result["pooled_rho"])
        self.assertEqual(result["strata_used"], 0)

    def test_spearman_rewards_within_stratum_ranking(self):
        rows = [
            _row("c000-k1", 5, 2, episode=0),
            _row("c000-k1", 5, 8, episode=1),
            _row("c000-k1", 5, 15, episode=2),
        ]
        aligned = within_stratum_spearman(rows, np.array([0.1, 0.5, 0.9]))
        reversed_ = within_stratum_spearman(
            rows, np.array([0.9, 0.5, 0.1])
        )
        self.assertAlmostEqual(aligned["pooled_rho"], 1.0)
        self.assertAlmostEqual(reversed_["pooled_rho"], -1.0)

    def test_terminal_auc_is_directional(self):
        rows = [
            _row("c000-k1", 5, 1, episode=0, terminal=1.0),
            _row("c000-k1", 5, 9, episode=1, terminal=0.0),
            _row("c000-k1", 5, 12, episode=2, terminal=0.0),
        ]
        # Lower predicted survival on the terminal row = perfect.
        good = within_stratum_auc(rows, np.array([0.1, 0.8, 0.9]))
        bad = within_stratum_auc(rows, np.array([0.9, 0.1, 0.2]))
        self.assertEqual(good["pooled_auc"], 1.0)
        self.assertEqual(bad["pooled_auc"], 0.0)


class SplitTests(unittest.TestCase):
    def test_splits_are_container_and_episode_disjoint(self):
        rows = [
            _row("c000-k1", 1, 5, episode=e) for e in range(6)
        ] + [
            _row("c001-k1", 1, 5, episode=e) for e in range(6)
        ]
        folds = splits(rows)
        names = [f["name"] for f in folds]
        self.assertIn("container:c000-k1", names)
        self.assertIn("container:c001-k1", names)
        for fold in folds:
            self.assertFalse(set(fold["train"]) & set(fold["test"]))
            if fold["name"].startswith("container:"):
                held = fold["name"].split(":")[1]
                test_sources = {
                    rows[i]["source_file"].split("-block")[0]
                    for i in fold["test"]
                }
                self.assertEqual(test_sources, {held})


if __name__ == "__main__":
    unittest.main()
