"""A value network over board tensors: V^{pi_0}(board) = items pi_0 still places.

Trained with torch (CPU), run with numpy so the same weights work inside the
agent.  Convolutions see local structure; the geometric channels carry what
convolutions cannot; a few scalar summaries ride along.  Auxiliary heads
predict the board summaries so the representation is shaped by what the
structures are, but only the value head is used to rank candidates.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np

from .tensor import CHANNELS, SUMMARY_KEYS


# ---------------------------------------------------------------------------
# numpy inference
# ---------------------------------------------------------------------------
def _conv2d(x, w, b, pad=1):
    """x (C,H,W), w (O,C,k,k), b (O,) -> (O,H,W), stride 1, zero padding."""
    C, H, W = x.shape
    O, _, k, _ = w.shape
    xp = np.pad(x, ((0, 0), (pad, pad), (pad, pad)))
    cols = np.empty((C * k * k, H * W), dtype=x.dtype)
    idx = 0
    for c in range(C):
        for i in range(k):
            for j in range(k):
                cols[idx] = xp[c, i:i + H, j:j + W].reshape(-1)
                idx += 1
    out = w.reshape(O, -1) @ cols + b[:, None]
    return out.reshape(O, H, W)


def _maxpool2(x):
    C, H, W = x.shape
    H2, W2 = H // 2, W // 2
    x = x[:, :H2 * 2, :W2 * 2].reshape(C, H2, 2, W2, 2)
    return x.max(axis=(2, 4))


class NumpyValueNet:
    def __init__(self, params: dict, spec: dict):
        self.p = params
        self.spec = spec
        self.aux_mean = np.asarray(spec["aux_mean"], dtype=np.float32)
        self.aux_std = np.asarray(spec["aux_std"], dtype=np.float32)

    def value(self, X: np.ndarray, aux: np.ndarray) -> float:
        h = X.astype(np.float32)
        p = self.p
        h = np.maximum(_conv2d(h, p["conv1.weight"], p["conv1.bias"]), 0.0)
        h = np.maximum(_conv2d(h, p["conv2.weight"], p["conv2.bias"]), 0.0)
        h = _maxpool2(h)
        h = np.maximum(_conv2d(h, p["conv3.weight"], p["conv3.bias"]), 0.0)
        pooled = np.concatenate([h.mean(axis=(1, 2)), h.max(axis=(1, 2))])
        a = (aux.astype(np.float32) - self.aux_mean) / self.aux_std
        z = np.concatenate([pooled, a])
        z = np.maximum(z @ p["fc1.weight"].T + p["fc1.bias"], 0.0)
        v = z @ p["value.weight"].T + p["value.bias"]
        return float(v[0]) * float(self.spec["y_std"]) + float(self.spec["y_mean"])


def load_numpy(path) -> NumpyValueNet:
    data = np.load(path, allow_pickle=False)
    spec = json.loads(str(data["spec"]))
    params = {k: data[k] for k in data.files if k != "spec"}
    return NumpyValueNet(params, spec)


# ---------------------------------------------------------------------------
# torch training
# ---------------------------------------------------------------------------
def build_torch_model(in_channels: int, aux_size: int, width: int = 32):
    import torch
    from torch import nn

    class ValueNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = nn.Conv2d(in_channels, width, 3, padding=1)
            self.conv2 = nn.Conv2d(width, width, 3, padding=1)
            self.conv3 = nn.Conv2d(width, 2 * width, 3, padding=1)
            self.fc1 = nn.Linear(4 * width + aux_size, 64)
            self.value = nn.Linear(64, 1)
            self.aux = nn.Linear(64, aux_size)

        def forward(self, x, a):
            h = torch.relu(self.conv1(x))
            h = torch.relu(self.conv2(h))
            h = torch.nn.functional.max_pool2d(h, 2)
            h = torch.relu(self.conv3(h))
            pooled = torch.cat([h.mean(dim=(2, 3)), h.amax(dim=(2, 3))], dim=1)
            z = torch.relu(self.fc1(torch.cat([pooled, a], dim=1)))
            return self.value(z)[:, 0], self.aux(z)

    return ValueNet()


def train(paths, out_path: pathlib.Path, epochs: int = 40, batch: int = 64, lr: float = 1e-3,
          width: int = 32, aux_weight: float = 0.1, val_fraction: float = 0.2, seed: int = 0,
          log=print) -> dict:
    import torch

    from .boards import load_boards

    torch.manual_seed(seed)
    X, y, aux, kind, names = load_boards(paths)
    scenes = sorted(set(names.tolist()))
    rng = np.random.default_rng(seed)
    val_scenes = set(rng.choice(scenes, size=max(1, int(len(scenes) * val_fraction)), replace=False).tolist())
    is_val = np.array([n in val_scenes for n in names])
    aux_mean = aux[~is_val].mean(axis=0); aux_std = aux[~is_val].std(axis=0); aux_std[aux_std < 1e-6] = 1.0
    y_mean = float(y[~is_val].mean()); y_std = float(y[~is_val].std() or 1.0)
    A = (aux - aux_mean) / aux_std
    Y = (y - y_mean) / y_std

    model = build_torch_model(X.shape[1], aux.shape[1], width)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    Xt = torch.tensor(X); At = torch.tensor(A, dtype=torch.float32); Yt = torch.tensor(Y, dtype=torch.float32)
    tr = np.where(~is_val)[0]; va = np.where(is_val)[0]
    best = (float("inf"), None); history = []
    for epoch in range(epochs):
        model.train()
        perm = rng.permutation(tr)
        for start in range(0, len(perm), batch):
            idx = torch.tensor(perm[start:start + batch])
            v, a_pred = model(Xt[idx], At[idx])
            loss = torch.mean((v - Yt[idx]) ** 2) + aux_weight * torch.mean((a_pred - At[idx]) ** 2)
            opt.zero_grad(); loss.backward(); opt.step()
        model.eval()
        with torch.no_grad():
            v_tr, _ = model(Xt[tr], At[tr]); v_va, _ = model(Xt[va], At[va]) if len(va) else (torch.zeros(0), None)
            mse_tr = float(torch.mean((v_tr - Yt[tr]) ** 2)) * y_std ** 2
            mse_va = float(torch.mean((v_va - Yt[va]) ** 2)) * y_std ** 2 if len(va) else float("nan")
        history.append({"epoch": epoch, "train_mse": mse_tr, "val_mse": mse_va})
        if log is not None:
            log(history[-1])
        if len(va) and mse_va < best[0]:
            best = (mse_va, {k: v.detach().clone() for k, v in model.state_dict().items()})
    if best[1] is not None:
        model.load_state_dict(best[1])
    # held-out ranking quality: within each (scene, step) group of branch boards, does the
    # model's argmax hit the best true return?
    with torch.no_grad():
        pred = model(Xt, At)[0].numpy() * y_std + y_mean
    agree = _rank_agreement(paths, pred, y, names, is_val)
    spec = {"channels": list(CHANNELS), "summary_keys": list(SUMMARY_KEYS), "width": width,
            "aux_mean": aux_mean.tolist(), "aux_std": aux_std.tolist(), "y_mean": y_mean, "y_std": y_std,
            "val_scenes": sorted(val_scenes), "best_val_mse": best[0], "boards": int(len(y)),
            "scenes": len(scenes), "rank_agreement": agree}
    arrays = {k: v.detach().numpy().astype(np.float32) for k, v in model.state_dict().items()
              if not k.startswith("aux.")}
    arrays["spec"] = np.array(json.dumps(spec))
    np.savez(out_path, **arrays)
    return spec


def _rank_agreement(paths, pred, y, names, is_val) -> dict:
    """Group branch boards by (scene, step) using the per-file step arrays."""
    groups: dict = {}
    ladder_of: dict = {}
    offset = 0
    for p in paths:
        d = np.load(p)
        n = len(d["y"])
        if n == 0:
            continue
        for i in range(n):
            kind = int(d["kind"][i])
            if kind >= 1:
                key = (str(d["scene"]), int(d["step"][i]))
                groups.setdefault(key, []).append(offset + i)
                if kind == 2:
                    ladder_of[key] = offset + i
        offset += n
    hits = {"train": [0, 0], "val": [0, 0], "ladder_val": [0, 0], "ladder_train": [0, 0]}
    for key, idx in groups.items():
        idx = np.asarray(idx)
        if len(idx) < 2 or np.ptp(y[idx]) < 1e-9:
            continue
        split = "val" if is_val[idx[0]] else "train"
        best = y[idx].max() - 1e-9
        pick = idx[int(np.argmax(pred[idx]))]
        hits[split][0] += int(y[pick] >= best); hits[split][1] += 1
        if key in ladder_of:
            hits["ladder_" + split][0] += int(y[ladder_of[key]] >= best); hits["ladder_" + split][1] += 1
    return {k: (v[0] / v[1] if v[1] else None, v[1]) for k, v in hits.items()}


# ---------------------------------------------------------------------------
# selector: rank survivors by the value of the board they leave
# ---------------------------------------------------------------------------
class ValueSelector:
    def __init__(self, path, margin: float = 0.0):
        from rule_alpha import layer1
        self._layer1 = layer1
        self.net = load_numpy(path)
        self.margin = float(margin)
        self.calls = 0
        self.overrides = 0

    def __call__(self, survivors, chosen, chosen_archetype, board, container_idx, profile):
        import copy

        from .tensor import board_tensor, summary_vector

        self.calls += 1
        if len(survivors) < 2:
            return None
        config = board.config
        scores = []
        for c in survivors:
            archetype = chosen_archetype if c is chosen else (
                sorted(c.archetypes)[0] if c.archetypes else "alternative")
            placement = self._layer1.build_placement(c, archetype, board, container_idx, profile, config)
            after = self._layer1.Board(copy.deepcopy(board.containers), config)
            after.apply(placement)
            X, summary = board_tensor(after, container_idx, config)
            scores.append(self.net.value(X, summary_vector(summary)))
        scores = np.asarray(scores)
        best = int(np.argmax(scores))
        ladder = next(i for i, c in enumerate(survivors) if c is chosen)
        if scores[best] <= scores[ladder] + self.margin:
            return None
        self.overrides += 1
        pick = survivors[best]
        label = sorted(pick.archetypes)[0] if pick.archetypes else "alternative"
        return pick, f"vnet/{label}"
