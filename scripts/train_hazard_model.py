#!/usr/bin/env python3
"""Train afterstate hazard models on the schema-2 selfplay corpus.

Protocol: reports/hazard/selfplay-hazard-protocol.md (committed before
any training). Four arms — linear_scalars, mlp_scalars, mlp_grid,
attention_grid — fitted on identical splits, evaluated ONLY within
(container, step) strata: `placements_after` is total-step-1 inside an
episode, so any across-step comparison measures the clock, not the
board (reports/hazard/step-confound.md). Held-out evaluation is
leave-one-container-out plus episode-disjoint blocks; single-split
numbers are not quotable.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCALAR_FEATURES = (
    "occupancy_mean",
    "occupancy_max",
    "occupancy_std",
    "roughness",
    "headroom_deficit",
    "floor_fraction_free",
    "placed",
)
GRID_SHAPE = (16, 12)
TYPE_COUNT = 7
ORIENTATION_COUNT = 6


def load_rows(paths: list[pathlib.Path]) -> list[dict[str, Any]]:
    rows = []
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if int(row.get("schema_version", 1)) < 2:
                    continue
                row["source_file"] = path.name
                rows.append(row)
    return rows


def scalar_vector(row: dict[str, Any]) -> list[float]:
    after = row["afterstate"]
    return (
        [float(after[name]) for name in SCALAR_FEATURES]
        + [
            float(row["afterstate_sealed_void"]),
            float(row["afterstate_sealed_void_by_items"]),
            float(row["afterstate_largest_free_span"]),
            float(row["options"]),
        ]
    )


def candidate_vector(row: dict[str, Any]) -> list[float]:
    candidate = row["candidate"]
    orientation = int(candidate["orientation"])
    type_index = int(row["type_index"])
    return (
        [float(v) for v in candidate["center"][:3]]
        + [float(v) for v in candidate["size"][:3]]
        + [1.0 if orientation == i else 0.0 for i in range(ORIENTATION_COUNT)]
        + [1.0 if type_index == i else 0.0 for i in range(TYPE_COUNT)]
        + [
            float(row["container"]["length"]),
            float(row["container"]["width"]),
            float(row["container"]["height"]),
        ]
    )


def grid_vector(row: dict[str, Any]) -> list[float]:
    grid = row["afterstate_grid"]
    return [float(cell) for line in grid for cell in line]


def stratum_key(row: dict[str, Any]) -> tuple:
    return (row["source_file"].split("-block")[0], int(row["step"]))


def within_stratum_spearman(
    rows: list[dict[str, Any]], predictions: np.ndarray
) -> dict[str, Any]:
    """Pooled within-(container, step) rank correlation with survival.

    Each stratum contributes its Spearman rho weighted by (n - 1);
    strata with fewer than 3 rows or a constant label are skipped.
    """
    strata: dict[tuple, list[int]] = {}
    for index, row in enumerate(rows):
        strata.setdefault(stratum_key(row), []).append(index)
    weighted = 0.0
    weight = 0.0
    used = 0
    for indices in strata.values():
        if len(indices) < 3:
            continue
        labels = np.asarray(
            [float(rows[i]["placements_after"]) for i in indices]
        )
        preds = predictions[indices]
        if np.ptp(labels) == 0 or np.ptp(preds) == 0:
            continue
        rho = _spearman(preds, labels)
        weighted += rho * (len(indices) - 1)
        weight += len(indices) - 1
        used += 1
    return {
        "pooled_rho": (weighted / weight) if weight else None,
        "strata_used": used,
    }


def within_stratum_auc(
    rows: list[dict[str, Any]], predictions: np.ndarray
) -> dict[str, Any]:
    """Pooled within-stratum AUC of -prediction against terminal_in_3."""
    strata: dict[tuple, list[int]] = {}
    for index, row in enumerate(rows):
        strata.setdefault(stratum_key(row), []).append(index)
    wins = 0.0
    pairs = 0
    for indices in strata.values():
        positives = [
            predictions[i]
            for i in indices
            if rows[i]["terminal_in_3"] > 0.5
        ]
        negatives = [
            predictions[i]
            for i in indices
            if rows[i]["terminal_in_3"] <= 0.5
        ]
        for p in positives:
            for n in negatives:
                # Lower predicted survival should mean terminal sooner.
                if p < n:
                    wins += 1.0
                elif p == n:
                    wins += 0.5
                pairs += 1
    return {
        "pooled_auc": (wins / pairs) if pairs else None,
        "pairs": pairs,
    }


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    def rank(x):
        order = np.argsort(x)
        ranks = np.empty(len(x))
        ranks[order] = np.arange(len(x), dtype=float)
        # average ties
        values, inverse, counts = np.unique(
            x, return_inverse=True, return_counts=True
        )
        cum = np.cumsum(counts) - counts
        mean_rank = cum + (counts - 1) / 2.0
        return mean_rank[inverse]

    ra, rb = rank(a), rank(b)
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    denominator = math.sqrt(float((ra**2).sum() * (rb**2).sum()))
    return float((ra * rb).sum() / denominator) if denominator else 0.0


def splits(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Leave-one-container-out plus episode-block folds."""
    containers = sorted({stratum_key(r)[0] for r in rows})
    folds = []
    for held in containers:
        folds.append(
            {
                "name": f"container:{held}",
                "test": [
                    i
                    for i, r in enumerate(rows)
                    if stratum_key(r)[0] == held
                ],
                "train": [
                    i
                    for i, r in enumerate(rows)
                    if stratum_key(r)[0] != held
                ],
            }
        )
    for block in range(3):
        test = [
            i
            for i, r in enumerate(rows)
            if int(r["episode"]) % 3 == block
        ]
        train = [
            i
            for i, r in enumerate(rows)
            if int(r["episode"]) % 3 != block
        ]
        folds.append(
            {"name": f"episodes:{block}", "test": test, "train": train}
        )
    return folds


def build_arms(torch, scalar_width, candidate_width, grid_width):
    nn = torch.nn

    class Mlp(nn.Module):
        def __init__(self, width_in, hidden=64):
            super().__init__()
            self.body = nn.Sequential(
                nn.Linear(width_in, hidden),
                nn.GELU(),
                nn.Linear(hidden, hidden),
                nn.GELU(),
            )
            self.out = nn.Linear(hidden, 2)

        def forward(self, x):
            return self.out(self.body(x))

    class Linear(nn.Module):
        def __init__(self, width_in):
            super().__init__()
            self.out = nn.Linear(width_in, 2)

        def forward(self, x):
            return self.out(x)

    class PatchAttention(nn.Module):
        """Grid patches + a scalar/candidate token, small transformer."""

        def __init__(self, dim=32, heads=4, layers=2):
            super().__init__()
            gx, gy = GRID_SHAPE
            self.px, self.py = 4, 4
            self.nx, self.ny = gx // self.px, gy // self.py
            patch_width = self.px * self.py
            self.patch_embed = nn.Linear(patch_width, dim)
            self.context_embed = nn.Linear(
                scalar_width + candidate_width, dim
            )
            self.position = nn.Parameter(
                torch.zeros(self.nx * self.ny + 1, dim)
            )
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=dim,
                nhead=heads,
                dim_feedforward=dim * 4,
                batch_first=True,
                dropout=0.0,
            )
            self.encoder = nn.TransformerEncoder(
                encoder_layer, num_layers=layers
            )
            self.out = nn.Linear(dim, 2)

        def forward(self, grid, context):
            batch = grid.shape[0]
            g = grid.reshape(batch, GRID_SHAPE[0], GRID_SHAPE[1])
            patches = (
                g.reshape(
                    batch, self.nx, self.px, self.ny, self.py
                )
                .permute(0, 1, 3, 2, 4)
                .reshape(batch, self.nx * self.ny, self.px * self.py)
            )
            tokens = torch.cat(
                [
                    self.patch_embed(patches),
                    self.context_embed(context).unsqueeze(1),
                ],
                dim=1,
            ) + self.position
            encoded = self.encoder(tokens)
            return self.out(encoded[:, -1])

    return Linear, Mlp, PatchAttention


def fit_and_evaluate(
    torch, rows, arm, fold, *, seed=0, epochs=150
) -> np.ndarray:
    torch.manual_seed(seed)
    scalars = np.asarray([scalar_vector(r) for r in rows], dtype=np.float32)
    cands = np.asarray([candidate_vector(r) for r in rows], dtype=np.float32)
    grids = np.asarray([grid_vector(r) for r in rows], dtype=np.float32)
    survival = np.asarray(
        [math.log1p(float(r["placements_after"])) for r in rows],
        dtype=np.float32,
    )
    terminal = np.asarray(
        [float(r["terminal_in_3"]) for r in rows], dtype=np.float32
    )
    train_idx = fold["train"]
    test_idx = fold["test"]

    def norm(block):
        mean = block[train_idx].mean(axis=0)
        scale = block[train_idx].std(axis=0)
        scale[scale <= 0] = 1.0
        return (block - mean) / scale

    scalars_n = norm(scalars)
    cands_n = norm(cands)
    context = np.concatenate([scalars_n, cands_n], axis=1)
    Linear, Mlp, PatchAttention = build_arms(
        torch, scalars_n.shape[1], cands_n.shape[1], grids.shape[1]
    )
    if arm == "linear_scalars":
        model = Linear(scalars_n.shape[1])
        inputs = lambda idx: (
            torch.tensor(scalars_n[idx]),
        )
    elif arm == "mlp_scalars":
        model = Mlp(scalars_n.shape[1])
        inputs = lambda idx: (torch.tensor(scalars_n[idx]),)
    elif arm == "mlp_grid":
        stacked = np.concatenate([grids, context], axis=1)
        model = Mlp(stacked.shape[1])
        inputs = lambda idx: (torch.tensor(stacked[idx]),)
    elif arm == "attention_grid":
        model = PatchAttention()
        inputs = lambda idx: (
            torch.tensor(grids[idx]),
            torch.tensor(context[idx]),
        )
    else:
        raise SystemExit(f"unknown arm {arm}")

    survival_mean = survival[train_idx].mean()
    survival_scale = survival[train_idx].std() or 1.0
    target_survival = torch.tensor(
        (survival - survival_mean) / survival_scale
    )
    target_terminal = torch.tensor(terminal)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=3e-3, weight_decay=1e-2
    )
    mse = torch.nn.MSELoss()
    bce = torch.nn.BCEWithLogitsLoss()
    batch = 4096
    train_array = np.asarray(train_idx)
    rng = np.random.default_rng(seed)
    for _epoch in range(epochs):
        model.train()
        rng.shuffle(train_array)
        for start in range(0, len(train_array), batch):
            chunk = train_array[start:start + batch]
            optimizer.zero_grad()
            out = model(*inputs(chunk))
            loss = mse(out[:, 0], target_survival[chunk]) + bce(
                out[:, 1], target_terminal[chunk]
            )
            loss.backward()
            optimizer.step()
    model.eval()
    predictions = np.zeros(len(rows), dtype=np.float64)
    with torch.no_grad():
        for start in range(0, len(test_idx), batch):
            chunk = test_idx[start:start + batch]
            predictions[chunk] = (
                model(*inputs(chunk))[:, 0].numpy().astype(np.float64)
            )
    return predictions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=pathlib.Path, required=True,
                        help="directory of schema-2 jsonl blocks")
    parser.add_argument("--arms", nargs="+", default=[
        "linear_scalars", "mlp_scalars", "mlp_grid", "attention_grid",
    ])
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    import torch

    paths = sorted(args.corpus.rglob("*.jsonl"))
    rows = load_rows(paths)
    if not rows:
        raise SystemExit("no schema-2 rows loaded")
    folds = splits(rows)
    report = {
        "protocol": "reports/hazard/selfplay-hazard-protocol.md",
        "rows": len(rows),
        "files": len(paths),
        "folds": [f["name"] for f in folds],
        "arms": {},
    }
    for arm in args.arms:
        fold_metrics = []
        for fold in folds:
            predictions = fit_and_evaluate(
                torch, rows, arm, fold,
                seed=args.seed, epochs=args.epochs,
            )
            test_rows = [rows[i] for i in fold["test"]]
            test_preds = predictions[fold["test"]]
            fold_metrics.append(
                {
                    "fold": fold["name"],
                    "spearman": within_stratum_spearman(
                        test_rows, test_preds
                    ),
                    "terminal_auc": within_stratum_auc(
                        test_rows, test_preds
                    ),
                }
            )
        rhos = [
            m["spearman"]["pooled_rho"]
            for m in fold_metrics
            if m["spearman"]["pooled_rho"] is not None
        ]
        aucs = [
            m["terminal_auc"]["pooled_auc"]
            for m in fold_metrics
            if m["terminal_auc"]["pooled_auc"] is not None
        ]
        report["arms"][arm] = {
            "folds": fold_metrics,
            "mean_pooled_rho": (
                round(sum(rhos) / len(rhos), 4) if rhos else None
            ),
            "mean_pooled_terminal_auc": (
                round(sum(aucs) / len(aucs), 4) if aucs else None
            ),
        }
        print(arm, report["arms"][arm]["mean_pooled_rho"],
              report["arms"][arm]["mean_pooled_terminal_auc"], flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        arm: {
            "rho": report["arms"][arm]["mean_pooled_rho"],
            "auc": report["arms"][arm]["mean_pooled_terminal_auc"],
        }
        for arm in report["arms"]
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
