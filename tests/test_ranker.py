"""The learned ranker: features, training, persistence, and the selector."""

from __future__ import annotations

import json
import pathlib
import random
import tempfile
import unittest

import numpy as np

from bench import ranker


def _record(scene, step, cand, surface, y_back, placed, is_ladder):
    return {
        "scene": scene, "step": step, "cand": cand, "is_ladder": is_ladder,
        "ladder_archetype": "max-footprint", "n_survivors": 4, "n_sampled": 3,
        "items_left": 20 - step,
        "candidate": {
            "surface": surface, "role": "none", "family": "floor", "orientation": cand % 6,
            "dx": 0.55, "dy": 0.4, "dz": 0.24, "tipping_ratio": 0.6,
            "archetypes": ["max-footprint"], "center": [0.0, y_back - 0.2, 0.17],
            "container_idx": 0,
            "features": {"y_back": y_back, "footprint": 0.22, "top_z": 0.29},
            "item": {"class": "normal-hard", "is_soft": False, "is_prioritized": False,
                     "mass": 8.0, "volume": 0.05, "elongation": 1.3},
        },
        "outcome": {"placed_h": placed, "placed_at": {"3": min(3, placed), "5": min(5, placed), "10": min(10, placed)},
                    "declined": False, "stream_empty": True, "horizon": 999, "fill_gain": 1.0,
                    "com_z_ratio": 0.3, "priority_covered_delta": 0, "soft_covered_delta": 0,
                    "reach_free_after": 1.0, "largest_hard_plateau_after": 0.2},
        "seconds": 0.1,
    }


def _synthetic(n_scenes=6, steps=12, seed=0):
    """Deeper y_back is worth one more item; the ladder picks at random."""
    rng = random.Random(seed)
    out = []
    for s in range(n_scenes):
        for step in range(steps):
            ladder = rng.randrange(3)
            for cand in range(3):
                y_back = 0.2 + 0.2 * cand + rng.uniform(-0.02, 0.02)
                placed = 10 + cand + (1 if rng.random() < 0.1 else 0)
                out.append(_record(f"s{s}", step, cand, "floor", y_back, placed, cand == ladder))
    return out


class RankerTests(unittest.TestCase):
    def test_advantages_are_centred_per_decision(self):
        records = _synthetic(n_scenes=1, steps=2)
        y = ranker.advantages(records)
        for step in (0, 1):
            idx = [i for i, r in enumerate(records) if r["step"] == step]
            self.assertAlmostEqual(float(y[idx].sum()), 0.0)

    def test_train_save_load_and_select(self):
        records = _synthetic(n_scenes=12, steps=15)
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "rollouts.jsonl"
            with path.open("w") as fh:
                for r in records:
                    fh.write(json.dumps(r) + "\n")
            model_path = pathlib.Path(tmp) / "model.npz"
            meta = ranker.train_from_jsonl([path], model_path, epochs=300, hidden=(16,), log=None)
            # labels carry 10 % noise, so perfect agreement is not reachable
            self.assertGreater(meta["val_top1_agreement"], 0.75)
            self.assertGreater(meta["val_top1_agreement"], meta["ladder_top1_agreement_val"])
            model, spec, meta2 = ranker.load_model(model_path)
            self.assertEqual(meta2["target"], "placed_h")
            X = spec.transform(ranker.records_to_matrix(records[:3], spec))
            pred = model.predict(X)
            # deeper candidate (cand 2) must score highest
            self.assertEqual(int(np.argmax(pred)), 2)

    def test_feature_size_matches_vector(self):
        records = _synthetic(n_scenes=1, steps=1)
        spec = ranker.FeatureSpec.from_records(records)
        X = ranker.records_to_matrix(records, spec)
        self.assertEqual(X.shape[1], spec.size)


if __name__ == "__main__":
    unittest.main()
