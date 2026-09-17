"""The trained stack/wedge policy in numpy: the same forward pass as
``ppo.Policy`` without torch, for the submission.

``export(policy_dir)`` writes ``policy.npz`` next to ``policy.pt`` (needs
torch); ``NumpyPolicy.load(policy_dir)`` reads it back (numpy only).  The
two agree to float32 precision (``tests/test_wedge.py``).
"""

from __future__ import annotations

import pathlib

import numpy as np


def _conv2d(x: np.ndarray, w: np.ndarray, b: np.ndarray) -> np.ndarray:
    """x (C, H, W), w (O, C, 3, 3), b (O,); stride 1, zero padding 1."""
    C, H, W = x.shape
    O = w.shape[0]
    xp = np.pad(x, ((0, 0), (1, 1), (1, 1)))
    cols = np.empty((C * 9, H * W), dtype=np.float32)
    k = 0
    for c in range(C):
        for i in range(3):
            for j in range(3):
                cols[k] = xp[c, i:i + H, j:j + W].reshape(-1)
                k += 1
    return (w.reshape(O, -1) @ cols + b[:, None]).reshape(O, H, W)


class NumpyPolicy:
    def __init__(self, params: dict):
        self.p = {k: np.asarray(v, dtype=np.float32) for k, v in params.items()}

    @classmethod
    def load(cls, policy_dir) -> "NumpyPolicy":
        data = np.load(pathlib.Path(policy_dir) / "policy.npz", allow_pickle=False)
        return cls({k: data[k] for k in data.files})

    def embed(self, obs: dict) -> np.ndarray:
        h = np.asarray(obs["heightmap"], dtype=np.float32)
        ch = np.broadcast_to(np.asarray(obs["profile"], dtype=np.float32)[:, None], h.shape)
        x = np.stack([h, ch])
        p = self.p
        z = np.maximum(_conv2d(x, p["conv1.weight"], p["conv1.bias"]), 0.0)
        z = np.maximum(_conv2d(z, p["conv2.weight"], p["conv2.bias"]), 0.0)
        pooled = np.concatenate([z.mean(axis=(1, 2)), z.max(axis=(1, 2))])
        vec = np.concatenate([pooled, np.asarray(obs["item"], dtype=np.float32),
                              np.asarray([obs["remaining"]], dtype=np.float32)])
        return np.maximum(vec @ p["state_fc.weight"].T + p["state_fc.bias"], 0.0)

    def logits(self, emb: np.ndarray, feats: np.ndarray) -> np.ndarray:
        p = self.p
        pass_logit = emb @ p["pass_fc.weight"].T + p["pass_fc.bias"]
        if feats.shape[0] == 0:
            return pass_logit
        f = np.asarray(feats, dtype=np.float32)
        x = np.concatenate([np.broadcast_to(emb, (f.shape[0], emb.shape[0])), f], axis=1)
        h = np.maximum(x @ p["cand_fc.0.weight"].T + p["cand_fc.0.bias"], 0.0)
        cand = (h @ p["cand_fc.2.weight"].T + p["cand_fc.2.bias"])[:, 0]
        return np.concatenate([cand, pass_logit])

    def value(self, emb: np.ndarray) -> float:
        p = self.p
        h = np.maximum(emb @ p["value_fc.0.weight"].T + p["value_fc.0.bias"], 0.0)
        return float((h @ p["value_fc.2.weight"].T + p["value_fc.2.bias"])[0])


def export(policy_dir) -> pathlib.Path:
    """``policy.pt`` -> ``policy.npz`` (float32 arrays keyed as the state dict)."""
    import torch

    policy_dir = pathlib.Path(policy_dir)
    state = torch.load(policy_dir / "policy.pt", map_location="cpu")
    arrays = {k: v.detach().cpu().numpy().astype(np.float32) for k, v in state.items()}
    out = policy_dir / "policy.npz"
    np.savez(out, **arrays)
    return out
