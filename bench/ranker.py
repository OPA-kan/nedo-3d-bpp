"""A learned ranker over the ladder's survivors.

Trained on ``bench.rollouts`` labels: for each decision, the sampled
candidates' continuation outcomes are centred within the decision, so the
model predicts *how much better than the alternatives* a candidate is, not
the absolute count (which mostly depends on how far into the episode the
decision is).  Inference is numpy only, so the same file runs inside the
submission without a learning framework.

Selection: score every survivor, take the best; keep the ladder's own pick
whenever its score is within ``margin`` of the best, so the ranker only
overrides when it has something to say.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

import numpy as np

SURFACES = ("floor", "shelf", "item")
CLASSES = ("normal-hard", "soft", "priority", "soft+priority")
CONTEXT_KEYS = ("items_left", "n_survivors", "step")


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------
class FeatureSpec:
    def __init__(self, numeric_keys, roles, families, mean=None, std=None):
        self.numeric_keys = list(numeric_keys)
        self.roles = list(roles)
        self.families = list(families)
        self.mean = mean
        self.std = std

    @classmethod
    def from_records(cls, records) -> "FeatureSpec":
        keys, roles, families = set(), set(), set()
        for r in records:
            keys.update(r["candidate"]["features"].keys())
            roles.add(r["candidate"]["role"])
            families.add(r["candidate"]["family"])
        return cls(sorted(keys), sorted(roles), sorted(families))

    @property
    def size(self) -> int:
        return (len(self.numeric_keys) + 6 + len(CONTEXT_KEYS) + 1
                + len(SURFACES) + len(self.roles) + len(self.families) + 6 + len(CLASSES) + 2)

    def raw(self, candidate: dict, context: dict, is_ladder: bool) -> np.ndarray:
        feats = candidate["features"]
        x = [float(feats.get(k, 0.0)) for k in self.numeric_keys]
        dx, dy, dz = float(candidate["dx"]), float(candidate["dy"]), float(candidate["dz"])
        x += [dx, dy, dz, dx * dy, dx * dy * dz, float(candidate["tipping_ratio"])]
        x += [float(context.get(k, 0.0)) for k in CONTEXT_KEYS]
        x += [1.0 if is_ladder else 0.0]
        x += [1.0 if candidate["surface"] == s else 0.0 for s in SURFACES]
        x += [1.0 if candidate["role"] == r else 0.0 for r in self.roles]
        x += [1.0 if candidate["family"] == f else 0.0 for f in self.families]
        x += [1.0 if int(candidate["orientation"]) == i else 0.0 for i in range(6)]
        item = candidate["item"]
        x += [1.0 if item["class"] == c else 0.0 for c in CLASSES]
        x += [float(item["mass"]), float(item["volume"])]
        return np.asarray(x, dtype=np.float64)

    def fit_scaler(self, X: np.ndarray) -> None:
        self.mean = X.mean(axis=0)
        std = X.std(axis=0)
        std[std < 1e-9] = 1.0
        self.std = std

    def transform(self, X: np.ndarray) -> np.ndarray:
        return (X - self.mean) / self.std

    def to_dict(self) -> dict:
        return {"numeric_keys": self.numeric_keys, "roles": self.roles, "families": self.families}


def records_to_matrix(records, spec: FeatureSpec):
    X = np.stack([
        spec.raw(r["candidate"], {"items_left": r["items_left"], "n_survivors": r["n_survivors"],
                                  "step": r["step"]}, bool(r["is_ladder"]))
        for r in records
    ])
    return X


def advantages(records, target: str = "placed_h") -> np.ndarray:
    """Outcome centred within each (scene, step) decision."""
    groups: dict = {}
    for i, r in enumerate(records):
        groups.setdefault((r["scene"], r["step"]), []).append(i)
    y = np.zeros(len(records))
    for idx in groups.values():
        vals = np.array([_target(records[i]["outcome"], target) for i in idx])
        y[idx] = vals - vals.mean()
    return y


def _target(outcome: dict, target: str) -> float:
    if target.startswith("placed_at:"):
        return float(outcome["placed_at"][target.split(":")[1]])
    return float(outcome[target])


# ---------------------------------------------------------------------------
# Model: a small MLP in numpy
# ---------------------------------------------------------------------------
class MLP:
    def __init__(self, sizes, seed: int = 0):
        rng = np.random.default_rng(seed)
        self.W = [rng.normal(0, np.sqrt(2.0 / a), size=(a, b)) for a, b in zip(sizes[:-1], sizes[1:])]
        self.b = [np.zeros(b) for b in sizes[1:]]

    def forward(self, X):
        acts = [X]
        h = X
        for i, (W, b) in enumerate(zip(self.W, self.b)):
            h = h @ W + b
            if i < len(self.W) - 1:
                h = np.maximum(h, 0.0)
            acts.append(h)
        return acts

    def predict(self, X) -> np.ndarray:
        return self.forward(X)[-1][:, 0]

    def train(self, X, y, X_val=None, y_val=None, epochs: int = 200, lr: float = 1e-3,
              batch: int = 256, weight_decay: float = 1e-4, seed: int = 0, patience: int = 20,
              log=None) -> dict:
        rng = np.random.default_rng(seed)
        m = [np.zeros_like(w) for w in self.W]; v = [np.zeros_like(w) for w in self.W]
        mb = [np.zeros_like(b) for b in self.b]; vb = [np.zeros_like(b) for b in self.b]
        beta1, beta2, eps = 0.9, 0.999, 1e-8
        t = 0
        best = (float("inf"), None)
        bad = 0
        history = []
        for epoch in range(epochs):
            order = rng.permutation(len(X))
            for start in range(0, len(X), batch):
                idx = order[start:start + batch]
                acts = self.forward(X[idx])
                pred = acts[-1][:, 0]
                grad_out = (2.0 / len(idx)) * (pred - y[idx])[:, None]
                grads_W, grads_b = [], []
                g = grad_out
                for i in range(len(self.W) - 1, -1, -1):
                    a_prev = acts[i]
                    grads_W.insert(0, a_prev.T @ g + weight_decay * self.W[i])
                    grads_b.insert(0, g.sum(axis=0))
                    if i > 0:
                        g = (g @ self.W[i].T) * (acts[i] > 0)
                t += 1
                for i in range(len(self.W)):
                    m[i] = beta1 * m[i] + (1 - beta1) * grads_W[i]
                    v[i] = beta2 * v[i] + (1 - beta2) * grads_W[i] ** 2
                    mb[i] = beta1 * mb[i] + (1 - beta1) * grads_b[i]
                    vb[i] = beta2 * vb[i] + (1 - beta2) * grads_b[i] ** 2
                    mhat = m[i] / (1 - beta1 ** t); vhat = v[i] / (1 - beta2 ** t)
                    self.W[i] -= lr * mhat / (np.sqrt(vhat) + eps)
                    mhat = mb[i] / (1 - beta1 ** t); vhat = vb[i] / (1 - beta2 ** t)
                    self.b[i] -= lr * mhat / (np.sqrt(vhat) + eps)
            train_loss = float(np.mean((self.predict(X) - y) ** 2))
            row = {"epoch": epoch, "train_mse": train_loss}
            if X_val is not None and len(X_val):
                val_loss = float(np.mean((self.predict(X_val) - y_val) ** 2))
                row["val_mse"] = val_loss
                if val_loss < best[0] - 1e-6:
                    best = (val_loss, [w.copy() for w in self.W] + [b.copy() for b in self.b])
                    bad = 0
                else:
                    bad += 1
            history.append(row)
            if log is not None and (epoch % 10 == 0 or epoch == epochs - 1):
                log(row)
            if bad >= patience:
                break
        if best[1] is not None:
            n = len(self.W)
            self.W = best[1][:n]; self.b = best[1][n:]
        return {"history": history, "best_val_mse": best[0] if best[1] is not None else None}


# ---------------------------------------------------------------------------
# Save / load / selector
# ---------------------------------------------------------------------------
def save_model(path: pathlib.Path, model: MLP, spec: FeatureSpec, meta: dict) -> None:
    arrays = {f"W{i}": w for i, w in enumerate(model.W)}
    arrays.update({f"b{i}": b for i, b in enumerate(model.b)})
    arrays["mean"] = spec.mean; arrays["std"] = spec.std
    arrays["spec"] = np.array(json.dumps(spec.to_dict()))
    arrays["meta"] = np.array(json.dumps(meta))
    np.savez(path, **arrays)


def load_model(path: pathlib.Path):
    data = np.load(path, allow_pickle=False)
    spec_dict = json.loads(str(data["spec"]))
    spec = FeatureSpec(spec_dict["numeric_keys"], spec_dict["roles"], spec_dict["families"],
                       mean=data["mean"], std=data["std"])
    n = sum(1 for k in data.files if k.startswith("W"))
    model = MLP([1, 1])
    model.W = [data[f"W{i}"] for i in range(n)]
    model.b = [data[f"b{i}"] for i in range(n)]
    meta = json.loads(str(data["meta"]))
    return model, spec, meta


def file_sha(path: pathlib.Path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()[:12]


class LearnedSelector:
    """``layer1.choose_for_item`` selector backed by a saved MLP."""

    def __init__(self, path, margin: float = 0.0):
        self.path = str(path)
        self.model, self.spec, self.meta = load_model(pathlib.Path(path))
        self.margin = float(margin)
        self.overrides = 0
        self.calls = 0

    def candidate_dict(self, candidate, profile) -> dict:
        from .rollouts import _candidate_record
        return _candidate_record(candidate, profile)

    def __call__(self, survivors, chosen, chosen_archetype, board, container_idx, profile):
        self.calls += 1
        if len(survivors) < 2:
            return None
        items_left = None  # not known inside the planner; use 0 as trained-neutral value
        context = {"items_left": 0.0, "n_survivors": float(len(survivors)), "step": 0.0}
        rows = np.stack([
            self.spec.raw(self.candidate_dict(c, profile), context, c is chosen) for c in survivors
        ])
        scores = self.model.predict(self.spec.transform(rows))
        best = int(np.argmax(scores))
        ladder = next(i for i, c in enumerate(survivors) if c is chosen)
        if scores[best] <= scores[ladder] + self.margin:
            return None
        self.overrides += 1
        pick = survivors[best]
        label = sorted(pick.archetypes)[0] if pick.archetypes else "alternative"
        return pick, f"nn/{label}"


# ---------------------------------------------------------------------------
# Training entry point
# ---------------------------------------------------------------------------
def train_from_jsonl(paths, out_path: pathlib.Path, target: str = "placed_h",
                     hidden=(64, 64), epochs: int = 300, val_fraction: float = 0.2,
                     seed: int = 0, log=print, drop_context: bool = True) -> dict:
    from .rollouts import read_jsonl

    records = read_jsonl(paths)
    if not records:
        raise ValueError("no rollout records")
    spec = FeatureSpec.from_records(records)
    X = records_to_matrix(records, spec)
    if drop_context:
        # the planner does not know items_left/step at inference; train
        # without them so the model never depends on them
        n_num = len(spec.numeric_keys)
        ctx_start = n_num + 6
        X[:, ctx_start:ctx_start + len(CONTEXT_KEYS)] = 0.0
    y = advantages(records, target)
    scenes = sorted({r["scene"] for r in records})
    rng = np.random.default_rng(seed)
    val_scenes = set(rng.choice(scenes, size=max(1, int(len(scenes) * val_fraction)), replace=False).tolist())
    is_val = np.array([r["scene"] in val_scenes for r in records])
    spec.fit_scaler(X[~is_val])
    Xs = spec.transform(X)
    model = MLP([spec.size, *hidden, 1], seed=seed)
    fit = model.train(Xs[~is_val], y[~is_val], Xs[is_val], y[is_val], epochs=epochs, seed=seed, log=log)
    # how often does argmax-by-model agree with argmax-by-label, per decision?
    agree = _decision_agreement(records, model.predict(Xs), y, is_val)
    meta = {
        "target": target, "records": len(records), "scenes": len(scenes),
        "val_scenes": sorted(val_scenes), "hidden": list(hidden),
        "best_val_mse": fit["best_val_mse"], "val_top1_agreement": agree["val"],
        "train_top1_agreement": agree["train"], "ladder_top1_agreement_val": agree["ladder_val"],
        "drop_context": drop_context,
    }
    save_model(out_path, model, spec, meta)
    return meta


def _decision_agreement(records, pred, y, is_val) -> dict:
    groups: dict = {}
    for i, r in enumerate(records):
        groups.setdefault((r["scene"], r["step"]), []).append(i)
    hits = {"train": [0, 0], "val": [0, 0], "ladder_val": [0, 0]}
    for idx in groups.values():
        idx = np.array(idx)
        if len(idx) < 2 or np.ptp(y[idx]) < 1e-9:
            continue  # nothing to get right when every candidate ties
        best_label = y[idx].max()
        split = "val" if is_val[idx[0]] else "train"
        model_pick = idx[int(np.argmax(pred[idx]))]
        hits[split][0] += int(y[model_pick] >= best_label - 1e-9); hits[split][1] += 1
        if split == "val":
            ladder = [i for i in idx if records[i]["is_ladder"]]
            if ladder:
                hits["ladder_val"][0] += int(y[ladder[0]] >= best_label - 1e-9); hits["ladder_val"][1] += 1
    return {k: (v[0] / v[1] if v[1] else None) for k, v in hits.items()}
