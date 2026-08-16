from __future__ import annotations

import math
import unittest

import numpy as np

from scripts.export_state_model import numpy_forward


def _artifact() -> dict:
    # One phi feature, one candidate feature; a single linear->gelu->linear
    # stack with hand-checkable numbers.
    return {
        "normalization": {
            "phi_mean": [1.0], "phi_scale": [2.0],
            "candidate_mean": [0.0], "candidate_scale": [1.0],
        },
        "layers": [
            {"kind": "linear", "weight": [[1.0, 0.0], [0.0, 1.0]],
             "bias": [0.0, 0.0]},
            {"kind": "gelu"},
            {"kind": "linear", "weight": [[1.0, 1.0]], "bias": [0.5]},
        ],
    }


def _gelu(x: float) -> float:
    return 0.5 * x * (1.0 + math.erf(x / math.sqrt(2.0)))


class ExportStateModelTests(unittest.TestCase):
    def test_numpy_forward_matches_hand_computation(self) -> None:
        logits = numpy_forward(_artifact(), [[3.0]], [[2.0]])
        # phi normalizes to (3-1)/2 = 1.0; candidate stays 2.0.
        expected = _gelu(1.0) + _gelu(2.0) + 0.5
        self.assertAlmostEqual(float(logits[0]), expected, places=9)

    def test_normalization_is_applied_before_the_first_layer(self) -> None:
        centered = numpy_forward(_artifact(), [[1.0]], [[0.0]])
        self.assertAlmostEqual(float(centered[0]), 0.5, places=9)

    def test_batch_shape(self) -> None:
        logits = numpy_forward(
            _artifact(), [[1.0], [3.0]], [[0.0], [2.0]]
        )
        self.assertEqual(logits.shape, (2,))


if __name__ == "__main__":
    unittest.main()
