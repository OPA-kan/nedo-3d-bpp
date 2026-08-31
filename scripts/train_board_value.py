"""Fit V_theta(s) to replace the bootstrap term the teacher pins to zero.

`scripts/collect_value_targets.py` labels every prefix state with the
volume its behaviour policy goes on to place. This fits a small model to
that and scores it the only way a value function used inside a search
needs to be scored: **by ranking, within a step index, on cells it never
trained on.**

Three things this deliberately does not do.

It does not chase absolute accuracy. A predictor that is wrong by a
constant factor but orders boards correctly is worth exactly as much
inside a search, so Spearman is the headline and the regression loss is
diagnostic only.

It does not pool across step indices when scoring. Later boards trivially
have less left to place, so a global correlation mostly measures how far
into an episode a state is, and `placed_count` would win it while saying
nothing. Boards are ranked against other boards at the same depth, which
is the comparison a search actually makes.

It does not hold out at random. Splits are by CELL, so a fold's training
set never contains another state from the same board -- states within one
episode are near-duplicates of each other and a random split would score
memorisation.

The baseline to beat is the incumbent teacher itself, whose rollout
scored Spearman +0.365 / +0.477 / +0.399 at steps 4 / 8 / 12 against the
same ground truth (reports/candidate-support/, value rankability probe).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import torch  # noqa: E402
from torch import nn  # noqa: E402

from scripts.probe_value_rankability import spearman  # noqa: E402

CONTRACT = "board_value_model_v1"
# The incumbent: what the teacher's own 10-step rollout scored against
# this ground truth, measured in the value rankability probe.
INCUMBENT_SPEARMAN = {"4": 0.365, "8": 0.477, "12": 0.399}


def feature_matrix(rows, names):
    return np.asarray(
        [[float(r["features"].get(n, 0.0)) for n in names] for r in rows],
        dtype=np.float32,
    )


class ValueHead(nn.Module):
    def __init__(self, width: int, hidden: int = 64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(width, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, 1),
        )

    def forward(self, x):
        return self.net(x).squeeze(-1)


def fit(train_x, train_y, *, epochs, seed, learning_rate=1e-3):
    torch.manual_seed(seed)
    model = ValueHead(train_x.shape[1])
    optimiser = torch.optim.Adam(model.parameters(), lr=learning_rate)
    x = torch.from_numpy(train_x)
    y = torch.from_numpy(train_y)
    for _ in range(epochs):
        optimiser.zero_grad()
        loss = nn.functional.mse_loss(model(x), y)
        loss.backward()
        optimiser.step()
    return model, float(loss.item())


def standardise(train_x, *arrays):
    mean = train_x.mean(axis=0, keepdims=True)
    std = train_x.std(axis=0, keepdims=True)
    std[std < 1e-8] = 1.0
    return [(a - mean) / std for a in (train_x, *arrays)]


def rank_by_step(rows, predictions, steps):
    """Spearman within each step index, against the telescoped return."""
    out = {}
    for step in steps:
        index = [i for i, r in enumerate(rows) if int(r["step"]) == step]
        if len(index) < 3:
            continue
        out[str(step)] = {
            "n": len(index),
            "spearman": spearman(
                [float(predictions[i]) for i in index],
                [float(rows[i]["remaining_volume"]) for i in index],
            ),
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", type=pathlib.Path, required=True)
    parser.add_argument("--epochs", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--steps", type=int, nargs="+", default=[4, 8, 12],
        help="step indices to rank within; the incumbent rollout was"
             " measured at these",
    )
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument(
        "--model-dir", type=pathlib.Path, default=None,
        help="also fit on ALL cells and save the weights there, for use"
             " as a rollout bootstrap. The held-out numbers above come"
             " from the leave-one-cell-out folds, never from this fit",
    )
    args = parser.parse_args()

    payload = json.loads(args.targets.read_text(encoding="utf-8"))
    rows = payload["rows"]
    names = sorted({n for r in rows for n in r["features"]})
    cases = sorted({r["case"] for r in rows})
    print(
        f"{len(rows)} states, {len(cases)} cells, {len(names)} features",
        flush=True,
    )

    # Leave one CELL out: states inside one episode are near-duplicates,
    # so a random split would score memorisation rather than transfer.
    held_predictions = np.zeros(len(rows), dtype=np.float32)
    folds = []
    for case in cases:
        test_index = [i for i, r in enumerate(rows) if r["case"] == case]
        train_index = [i for i, r in enumerate(rows) if r["case"] != case]
        if not test_index or not train_index:
            continue
        train_x = feature_matrix([rows[i] for i in train_index], names)
        test_x = feature_matrix([rows[i] for i in test_index], names)
        train_x, test_x = standardise(train_x, test_x)
        train_y = np.asarray(
            [float(rows[i]["remaining_volume"]) for i in train_index],
            dtype=np.float32,
        )
        model, loss = fit(
            train_x, train_y, epochs=args.epochs, seed=args.seed,
        )
        with torch.no_grad():
            prediction = model(torch.from_numpy(test_x)).numpy()
        for slot, i in enumerate(test_index):
            held_predictions[i] = prediction[slot]
        folds.append({
            "held_cell": case, "train_states": len(train_index),
            "held_states": len(test_index), "train_mse": round(loss, 6),
        })

    learned = rank_by_step(rows, held_predictions, args.steps)
    # Every single feature, scored the same way, so "the model beat the
    # rollout" cannot hide "one raw feature would have too".
    singles = {}
    for position, name in enumerate(names):
        column = feature_matrix(rows, names)[:, position]
        singles[name] = rank_by_step(rows, column, args.steps)

    truth = np.asarray(
        [float(r["remaining_volume"]) for r in rows], dtype=np.float32
    )
    report = {
        "held_out_spearman_by_step": learned,
        "incumbent_rollout_spearman_by_step": INCUMBENT_SPEARMAN,
        "single_feature_spearman_by_step": singles,
        "held_out_mse": float(np.mean((held_predictions - truth) ** 2)),
        "target_mean": float(truth.mean()),
        "target_std": float(truth.std()),
        "folds": folds,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({
            "schema_version": 1, "contract": CONTRACT,
            "split": "leave_one_course_cell_out",
            "scored_by": "spearman within step index, not calibration",
            "report": report,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if args.model_dir is not None:
        # A separate fit on every cell, for deployment only. Reporting a
        # number from this model would be reporting training accuracy;
        # the folds above are what the claims rest on.
        all_x = feature_matrix(rows, names)
        mean = all_x.mean(axis=0, keepdims=True)
        std = all_x.std(axis=0, keepdims=True)
        std[std < 1e-8] = 1.0
        model, loss = fit(
            (all_x - mean) / std,
            np.asarray(
                [float(r["remaining_volume"]) for r in rows],
                dtype=np.float32,
            ),
            epochs=args.epochs, seed=args.seed,
        )
        args.model_dir.mkdir(parents=True, exist_ok=True)
        torch.save(model.state_dict(), args.model_dir / "value.pt")
        (args.model_dir / "model.json").write_text(
            json.dumps({
                "contract": CONTRACT,
                "feature_names": names,
                "feature_mean": mean.reshape(-1).tolist(),
                "feature_std": std.reshape(-1).tolist(),
                "hidden": 64,
                "target": (
                    "remaining placed volume under the behaviour policy"
                    " (gamma=1); V^behaviour, not V*"
                ),
                "train_states": len(rows),
                "train_cells": len(cases),
                "train_mse": round(loss, 6),
                "held_out_spearman_by_step": learned,
                "incumbent_rollout_spearman_by_step": INCUMBENT_SPEARMAN,
            }, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"saved model -> {args.model_dir}", flush=True)

    print("\n=== held-out Spearman within step index ===", flush=True)
    print(
        f"{'step':>5s} {'n':>4s} {'learned V':>10s} {'incumbent':>10s}"
        "   best single feature", flush=True,
    )
    for step in args.steps:
        key = str(step)
        if key not in learned:
            continue
        entry = learned[key]
        best_name, best_value = None, None
        for name, table in singles.items():
            value = (table.get(key) or {}).get("spearman")
            if value is None:
                continue
            if best_value is None or abs(value) > abs(best_value):
                best_name, best_value = name, value
        incumbent = INCUMBENT_SPEARMAN.get(key)
        print(
            f"{step:5d} {entry['n']:4d} "
            f"{entry['spearman']:+10.3f} "
            f"{incumbent:+10.3f}   {best_name} {best_value:+.3f}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
