"""Board tensors and the value network: numpy inference must match torch."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

import numpy as np

from bench import valuenet
from bench.arms import make_arm
from bench.scenes import make_scene
from bench.tensor import CHANNELS, board_tensor, summary_vector
from bench.rollouts import EpisodeState


def _boards(n_steps=4):
    scene = make_scene(101, "c1s", "C", items_per_container=8)
    arm = make_arm("ladder-stable")
    state = EpisodeState(scene, arm)
    out = []
    for _ in range(n_steps):
        X, s = board_tensor(state.board, 0, arm.config)
        out.append((X, summary_vector(s)))
        action, decision = state.decide()
        if action is None:
            break
        state.apply_placement(decision.placement, int(action["item_idx"]))
    return out


class TensorTests(unittest.TestCase):
    def test_channels_shape_and_ranges(self):
        boards = _boards(2)
        X, aux = boards[-1]
        self.assertEqual(X.shape[0], len(CHANNELS))
        self.assertTrue(np.all(X >= 0.0) and np.all(X <= 1.5))
        self.assertEqual(aux.shape[0], 9)
        # occupied grows as items are placed
        self.assertGreater(boards[-1][0][1].sum(), boards[0][0][1].sum())


class NumpyInferenceTests(unittest.TestCase):
    def test_numpy_matches_torch(self):
        try:
            import torch
        except ImportError:  # pragma: no cover
            self.skipTest("torch not installed")
        boards = _boards(3)
        X = np.stack([b[0] for b in boards]); aux = np.stack([b[1] for b in boards])
        model = valuenet.build_torch_model(X.shape[1], aux.shape[1], width=8)
        model.eval()
        spec = {"channels": list(CHANNELS), "summary_keys": [], "width": 8,
                "aux_mean": aux.mean(axis=0).tolist(), "aux_std": [1.0] * aux.shape[1],
                "y_mean": 3.0, "y_std": 2.0}
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "v.npz"
            arrays = {k: v.detach().numpy().astype(np.float32) for k, v in model.state_dict().items()
                      if not k.startswith("aux.")}
            arrays["spec"] = np.array(json.dumps(spec))
            np.savez(path, **arrays)
            net = valuenet.load_numpy(path)
            A = torch.tensor((aux - np.asarray(spec["aux_mean"])) / np.asarray(spec["aux_std"]), dtype=torch.float32)
            with torch.no_grad():
                ref = model(torch.tensor(X), A)[0].numpy() * 2.0 + 3.0
            for i in range(len(boards)):
                self.assertAlmostEqual(net.value(X[i], aux[i]), float(ref[i]), places=4)


if __name__ == "__main__":
    unittest.main()
