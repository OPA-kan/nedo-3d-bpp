import json
import pathlib
import tempfile
import unittest

from scripts.train_checkpoint_comparator import (
    checkpoint_token,
    decision_comparison,
    load_checkpoint_map,
)


def _vector(fill):
    return {
        "fill_gain": fill,
        "soft_violation_gain": 0.0,
        "priority_covered_gain": 0.0,
        "priority_misrouted_gain": 0.0,
        "surface_total_variation_delta": 0.0,
    }


class CheckpointComparatorTests(unittest.TestCase):
    def test_checkpoint_token_orients_heads_and_flags_terminals(self):
        token = checkpoint_token({
            "checkpoint_vector": {
                "fill_gain": 2.0,
                "soft_violation_gain": 1.0,
                "priority_covered_gain": 0.0,
                "priority_misrouted_gain": 0.0,
                "surface_total_variation_delta": 0.5,
            },
            "continuation_steps": 2,
            "termination": "stream_exhausted",
        })
        self.assertEqual(token, [2.0, -1.0, 0.0, 0.0, -0.5, 2.0, 1.0])

    def test_load_checkpoint_map_indexes_safe_candidates_at_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "cell" / "checkpoint.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "roots": [{
                    "root_id": "r1",
                    "checkpoints": {"2": {"candidates": [
                        {"root_candidate_id": "a", "safe": True,
                         "checkpoint_vector": _vector(1.0)},
                        {"root_candidate_id": "b", "safe": False,
                         "checkpoint_vector": _vector(9.0)},
                    ]}},
                }],
            }), encoding="utf-8")
            checkpoint_map = load_checkpoint_map(pathlib.Path(tmp), cap=2)
        self.assertEqual(set(checkpoint_map), {"r1"})
        self.assertEqual(set(checkpoint_map["r1"]), {"a"})

    def test_decision_gate_pairs_pareto_and_learned_on_same_vectors(self):
        # Intervention root: terminal picks b; the Pareto rule keeps the
        # incumbent (tie on the frontier) while the comparator switches.
        examples = [{
            "root_id": "r1", "group": "g",
            "candidate_ids": ["a", "b"],
            "incumbent_index": 0, "selected_index": 1,
        }]
        checkpoint_map = {"r1": {
            "a": {"checkpoint_vector": _vector(1.0)},
            "b": {"checkpoint_vector": _vector(1.0)},
        }}
        scores = [[0.2, 0.8]]
        gate = decision_comparison(examples, scores, checkpoint_map)
        pair = gate["ranker_pair"]
        self.assertEqual(pair["interventions_available"], 1)
        self.assertEqual(pair["pareto_conversion"], 0)
        self.assertEqual(pair["learned_conversion"], 1)
        self.assertEqual(len(pair["flips"]), 1)
        self.assertEqual(gate["full_support"]["learned_conversion"], 1)


if __name__ == "__main__":
    unittest.main()
