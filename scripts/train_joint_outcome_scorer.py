"""Train and evaluate the joint outcome scorer F(s, a) for PoC-2.

The model predicts the bounded joint physical outcome vector of
JointOutcomeSample v2 from the searched root's state set tensors and the
commanded root action, as fixed in
``reports/self-play-packing/joint-outcome-scorer-contract.md``. The output
is a joint Gaussian (mean plus full Cholesky factor) so dominance
estimates keep across-head structure instead of head-independent means.

Held-out evaluation asks the PoC-2 question directly: on roots the model
never saw, does predicted candidate ordering, pairwise dominance and
Pareto membership agree with the paired physical measurements?
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import random
from typing import Any

import numpy as np

try:
    from scripts.audit_paired_physical_contract import PARETO_OBJECTIVES
    from scripts.build_paired_joint_outcome_dataset import (
        ACTION_FEATURES,
        TARGET_HEADS,
    )
except ModuleNotFoundError:
    from audit_paired_physical_contract import PARETO_OBJECTIVES
    from build_paired_joint_outcome_dataset import (
        ACTION_FEATURES,
        TARGET_HEADS,
    )

SET_KEYS = ("container", "packed_item", "visible_item")
DOMINANCE_HEADS = tuple(PARETO_OBJECTIVES)
DOMINANCE_SIGNS = {
    head: 1.0 if direction == "maximize" else -1.0
    for head, direction in PARETO_OBJECTIVES.items()
}


def load_rows(path: pathlib.Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        raise ValueError(f"{path} contains no rows")
    return rows


def prepare_examples(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    examples = []
    for row in rows:
        mask = [bool(row["target_mask"][head]) for head in TARGET_HEADS]
        if not any(mask):
            continue
        state = row["features"]["state"]
        examples.append({
            "cell_id": row["cell_id"],
            "root_id": row["root_id"],
            "root_candidate_id": row["root_candidate_id"],
            "exogenous_world_id": row["exogenous_world_id"],
            "container": state["container_values"],
            "packed_item": state["packed_item_values"],
            "visible_item": state["visible_item_values"],
            "action": (
                list(row["features"]["action"])
                + list(row["features"]["acting_item"])
            ),
            "targets": [
                float(row["targets"][head]) if row["target_mask"][head] else 0.0
                for head in TARGET_HEADS
            ],
            "target_mask": mask,
        })
    if not examples:
        raise ValueError("no supervised examples after masking")
    return examples


def split_by_cell(
    examples: list[dict[str, Any]], held_out_cells: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train = [row for row in examples if row["cell_id"] not in held_out_cells]
    held = [row for row in examples if row["cell_id"] in held_out_cells]
    if not train or not held:
        raise ValueError(
            f"cell split is degenerate: {len(train)} train / {len(held)} held"
        )
    # Empty-board fingerprints collide across scenarios, so the same
    # root_id can appear in a training and a held-out cell. Those roots
    # are not held out in any meaningful sense; drop them from evaluation.
    train_roots = {row["root_id"] for row in train}
    held = [row for row in held if row["root_id"] not in train_roots]
    if not held:
        raise ValueError("every held-out root also appears in training cells")
    return train, held


def compute_stats(examples: list[dict[str, Any]]) -> dict[str, Any]:
    def moments(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        mean = values.mean(axis=0)
        scale = values.std(axis=0)
        scale[scale < 1e-6] = 1.0
        return mean, scale

    stats: dict[str, Any] = {}
    for key in SET_KEYS:
        tokens = np.asarray(
            [token for row in examples for token in row[key]],
            dtype=np.float32,
        )
        if not len(tokens):
            width = 1
            stats[key] = (np.zeros(width), np.ones(width))
        else:
            stats[key] = moments(tokens)
    stats["action"] = moments(
        np.asarray([row["action"] for row in examples], dtype=np.float32)
    )
    target_values = np.asarray(
        [row["targets"] for row in examples], dtype=np.float32
    )
    target_mask = np.asarray(
        [row["target_mask"] for row in examples], dtype=bool
    )
    mean = np.zeros(len(TARGET_HEADS))
    scale = np.ones(len(TARGET_HEADS))
    for column in range(len(TARGET_HEADS)):
        eligible = target_values[target_mask[:, column], column]
        if len(eligible):
            mean[column] = eligible.mean()
            deviation = eligible.std()
            scale[column] = deviation if deviation > 1e-6 else 1.0
    stats["targets"] = (mean, scale)
    return stats


def _pad_set(
    examples: list[dict[str, Any]], key: str,
    mean: np.ndarray, scale: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    width = len(mean)
    longest = max(
        1, max(len(row[key]) for row in examples)
    )
    values = np.zeros((len(examples), longest, width), dtype=np.float32)
    mask = np.ones((len(examples), longest), dtype=bool)
    for index, row in enumerate(examples):
        tokens = np.asarray(row[key], dtype=np.float32)
        if len(tokens):
            values[index, :len(tokens)] = (tokens - mean) / scale
            mask[index, :len(tokens)] = False
        else:
            values[index, 0] = 0.0
            mask[index, 0] = False
    return values, mask


def build_arrays(
    examples: list[dict[str, Any]], stats: dict[str, Any],
) -> dict[str, np.ndarray]:
    arrays: dict[str, np.ndarray] = {}
    for key in SET_KEYS:
        mean, scale = stats[key]
        arrays[key], arrays[f"{key}_mask"] = _pad_set(
            examples, key, np.asarray(mean), np.asarray(scale)
        )
    action = np.asarray([row["action"] for row in examples], dtype=np.float32)
    arrays["action"] = (
        (action - stats["action"][0]) / stats["action"][1]
    ).astype(np.float32)
    targets = np.asarray([row["targets"] for row in examples], dtype=np.float32)
    arrays["targets"] = (
        (targets - stats["targets"][0]) / stats["targets"][1]
    ).astype(np.float32)
    arrays["target_mask"] = np.asarray(
        [row["target_mask"] for row in examples], dtype=bool
    )
    return arrays


def build_model(torch, widths: dict[str, int], *, dim: int = 64):
    nn = torch.nn
    heads = len(TARGET_HEADS)
    tril = heads * (heads + 1) // 2

    class SetEncoder(nn.Module):
        def __init__(self, width: int):
            super().__init__()
            self.input = nn.Linear(width, dim)
            self.attention = nn.MultiheadAttention(
                dim, 4, dropout=0.1, batch_first=True
            )
            self.norm1 = nn.LayerNorm(dim)
            self.ff = nn.Sequential(
                nn.Linear(dim, 2 * dim), nn.GELU(), nn.Linear(2 * dim, dim)
            )
            self.norm2 = nn.LayerNorm(dim)
            self.seed = nn.Parameter(torch.zeros(1, 1, dim))
            nn.init.normal_(self.seed, std=0.02)
            self.pool = nn.MultiheadAttention(dim, 4, batch_first=True)

        def forward(self, values, mask):
            state = self.input(values)
            attended, _ = self.attention(
                state, state, state, key_padding_mask=mask
            )
            state = self.norm1(state + attended)
            state = self.norm2(state + self.ff(state))
            query = self.seed.expand(state.shape[0], -1, -1)
            pooled, _ = self.pool(query, state, state, key_padding_mask=mask)
            return pooled.squeeze(1)

    class JointOutcomeScorer(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoders = nn.ModuleDict({
                key: SetEncoder(widths[key]) for key in SET_KEYS
            })
            self.action = nn.Sequential(
                nn.Linear(widths["action"], dim), nn.GELU(),
                nn.Linear(dim, dim), nn.GELU(),
            )
            self.trunk = nn.Sequential(
                nn.Linear(4 * dim, 2 * dim), nn.GELU(),
                nn.Dropout(0.1), nn.Linear(2 * dim, dim), nn.GELU(),
            )
            self.mean = nn.Linear(dim, heads)
            self.cholesky = nn.Linear(dim, tril)

        def forward(self, batch):
            blocks = [
                self.encoders[key](batch[key], batch[f"{key}_mask"])
                for key in SET_KEYS
            ]
            blocks.append(self.action(batch["action"]))
            state = self.trunk(torch.cat(blocks, dim=-1))
            mean = self.mean(state)
            raw = self.cholesky(state)
            rows, cols = torch.tril_indices(heads, heads)
            factor = torch.zeros(
                state.shape[0], heads, heads, device=state.device
            )
            factor[:, rows, cols] = raw
            diagonal = torch.arange(heads, device=state.device)
            factor[:, diagonal, diagonal] = (
                torch.nn.functional.softplus(
                    factor[:, diagonal, diagonal]
                ) + 1e-3
            )
            return mean, factor

    return JointOutcomeScorer()


def joint_nll(torch, mean, factor, targets, target_mask):
    """Masked Gaussian NLL: joint on fully eligible rows, diagonal otherwise."""
    residual = targets - mean
    full = target_mask.all(dim=1)
    losses = []
    if full.any():
        solved = torch.linalg.solve_triangular(
            factor[full], residual[full].unsqueeze(-1), upper=False
        ).squeeze(-1)
        log_det = torch.log(
            torch.diagonal(factor[full], dim1=-2, dim2=-1)
        ).sum(dim=1)
        losses.append(0.5 * (solved ** 2).sum(dim=1) + log_det)
    partial = target_mask.any(dim=1) & ~full
    if partial.any():
        variance = (
            torch.diagonal(factor[partial], dim1=-2, dim2=-1) ** 2
        )
        element = 0.5 * (
            residual[partial] ** 2 / variance + torch.log(variance)
        )
        masked = torch.where(
            target_mask[partial], element, torch.zeros_like(element)
        )
        losses.append(masked.sum(dim=1))
    if not losses:
        raise ValueError("batch has no eligible targets")
    return torch.cat(losses).mean()


def _torch_batch(torch, arrays: dict[str, np.ndarray], indices) -> dict:
    batch = {}
    for key, value in arrays.items():
        tensor = torch.from_numpy(value[indices])
        batch[key] = tensor.bool() if value.dtype == bool else tensor.float()
    return batch


def fit_member(
    torch, arrays: dict[str, np.ndarray], widths: dict[str, int], *,
    groups: list[str], seed: int, epochs: int, dim: int,
    batch_size: int = 64, learning_rate: float = 1e-3,
):
    torch.manual_seed(seed)
    rng = random.Random(seed)
    unique_groups = sorted(set(groups))
    chosen = collections.Counter(
        rng.choice(unique_groups) for _ in unique_groups
    )
    indices = np.asarray([
        index for index, group in enumerate(groups)
        for _ in range(chosen[group])
    ])
    model = build_model(torch, widths, dim=dim)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    model.train()
    for _epoch in range(epochs):
        order = indices.copy()
        rng.shuffle(order)
        for start in range(0, len(order), batch_size):
            batch = _torch_batch(
                torch, arrays, order[start:start + batch_size]
            )
            mean, factor = model(batch)
            loss = joint_nll(
                torch, mean, factor, batch["targets"], batch["target_mask"]
            )
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
    model.eval()
    return model


def predict(
    torch, models, arrays: dict[str, np.ndarray], stats: dict[str, Any],
) -> dict[str, np.ndarray]:
    """Ensemble predictions denormalized to head units."""
    target_mean = np.asarray(stats["targets"][0], dtype=np.float64)
    target_scale = np.asarray(stats["targets"][1], dtype=np.float64)
    means, factors = [], []
    with torch.no_grad():
        for model in models:
            batch = _torch_batch(
                torch, arrays, np.arange(len(arrays["targets"]))
            )
            mean, factor = model(batch)
            means.append(
                mean.numpy() * target_scale + target_mean
            )
            factors.append(factor.numpy() * target_scale[None, :, None])
    stacked = np.stack(means)
    return {
        "member_means": stacked,
        "mean": stacked.mean(axis=0),
        "epistemic_variance": stacked.var(axis=0),
        "member_factors": np.stack(factors),
    }


def _dominance_probability(
    rng: np.random.Generator,
    prediction: dict[str, np.ndarray],
    left: list[int], right: list[int],
    head_indices: list[int], signs: np.ndarray,
    draws: int,
) -> float:
    """P(left jointly strictly dominates right) by independent sampling."""
    def draw(indices: list[int]) -> np.ndarray:
        members = prediction["member_means"].shape[0]
        rows = rng.choice(indices, size=draws)
        member = rng.integers(members, size=draws)
        noise = rng.standard_normal((draws, len(TARGET_HEADS)))
        factor = prediction["member_factors"][member, rows]
        return (
            prediction["member_means"][member, rows]
            + np.einsum("bij,bj->bi", factor, noise)
        )

    left_draws = draw(left)[:, head_indices] * signs
    right_draws = draw(right)[:, head_indices] * signs
    nonworse = (left_draws >= right_draws).all(axis=1)
    strict = (left_draws > right_draws).any(axis=1)
    return float((nonworse & strict).mean())


def _kendall_tau(left: list[float], right: list[float]) -> float | None:
    pairs = [
        (i, j)
        for i in range(len(left)) for j in range(i + 1, len(left))
        if left[i] != left[j] and right[i] != right[j]
    ]
    if not pairs:
        return None
    agree = sum(
        1 for i, j in pairs
        if (left[i] - left[j]) * (right[i] - right[j]) > 0
    )
    return (2.0 * agree - len(pairs)) / len(pairs)


def evaluate_held_out(
    examples: list[dict[str, Any]], prediction: dict[str, np.ndarray], *,
    seed: int = 0, draws: int = 512,
    dominance_threshold: float = 0.75,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    head_indices = [TARGET_HEADS.index(head) for head in DOMINANCE_HEADS]
    signs = np.asarray(
        [DOMINANCE_SIGNS[head] for head in DOMINANCE_HEADS]
    )
    by_root: dict[str, dict[str, list[int]]] = collections.defaultdict(
        lambda: collections.defaultdict(list)
    )
    for index, row in enumerate(examples):
        by_root[row["root_id"]][row["root_candidate_id"]].append(index)

    tau_by_head: dict[str, list[float]] = collections.defaultdict(list)
    dominance_records = []
    regret_by_head: dict[str, list[float]] = collections.defaultdict(list)
    pareto_counts = collections.Counter()
    for root_id, candidates in sorted(by_root.items()):
        names = sorted(candidates)
        if len(names) < 2:
            continue
        measured = {
            name: np.asarray(
                [examples[i]["targets"] for i in candidates[name]]
            ).mean(axis=0)
            for name in names
        }
        predicted = {
            name: prediction["mean"][candidates[name]].mean(axis=0)
            for name in names
        }
        for head_index, head in enumerate(TARGET_HEADS):
            tau = _kendall_tau(
                [float(measured[name][head_index]) for name in names],
                [float(predicted[name][head_index]) for name in names],
            )
            if tau is not None:
                tau_by_head[head].append(tau)
        for head in ("game_reward", "fill_gain"):
            head_index = TARGET_HEADS.index(head)
            best = max(names, key=lambda name: measured[name][head_index])
            picked = max(names, key=lambda name: predicted[name][head_index])
            regret_by_head[head].append(float(
                measured[best][head_index] - measured[picked][head_index]
            ))

        measured_dominated = set()
        model_dominated = set()
        for target in names:
            for challenger in names:
                if challenger == target:
                    continue
                paired = _measured_dominance(
                    examples, candidates, challenger, target,
                    head_indices, signs,
                )
                model = _dominance_probability(
                    rng, prediction,
                    candidates[challenger], candidates[target],
                    head_indices, signs, draws,
                )
                dominance_records.append({
                    "root_id": root_id,
                    "challenger": challenger,
                    "target": target,
                    "measured": paired,
                    "model": model,
                })
                if paired is not None and paired >= dominance_threshold:
                    measured_dominated.add(target)
                if model >= dominance_threshold:
                    model_dominated.add(target)
        for name in names:
            in_measured = name in measured_dominated
            in_model = name in model_dominated
            pareto_counts[(in_measured, in_model)] += 1

    confident = [
        row for row in dominance_records
        if row["measured"] is not None
        and (row["measured"] >= 0.75 or row["measured"] <= 0.25)
    ]
    agreement = (
        sum(
            1 for row in confident
            if (row["measured"] >= 0.75) == (row["model"] >= 0.5)
        ) / len(confident)
        if confident else None
    )
    true_dominated = (
        pareto_counts[(True, True)] + pareto_counts[(True, False)]
    )
    flagged = pareto_counts[(True, True)] + pareto_counts[(False, True)]
    return {
        "roots": len(by_root),
        "ordering_kendall_tau": {
            head: {
                "mean": float(np.mean(values)),
                "count": len(values),
            }
            for head, values in sorted(tau_by_head.items())
        },
        "dominance": {
            "records": len(dominance_records),
            "confident_measured": len(confident),
            "direction_agreement": agreement,
        },
        "pareto": {
            "measured_dominated": true_dominated,
            "model_flagged": flagged,
            "recall": (
                pareto_counts[(True, True)] / true_dominated
                if true_dominated else None
            ),
            "precision": (
                pareto_counts[(True, True)] / flagged if flagged else None
            ),
            "threshold": dominance_threshold,
        },
        "top_pick_regret": {
            head: {
                "mean": float(np.mean(values)),
                "max": float(np.max(values)),
                "zero_share": float(np.mean([v == 0.0 for v in values])),
            }
            for head, values in sorted(regret_by_head.items())
        },
        "dominance_records": dominance_records,
    }


def _measured_dominance(
    examples, candidates, challenger, target, head_indices, signs,
) -> float | None:
    """Same-world joint strict dominance share from measured samples."""
    def by_world(name):
        return {
            examples[i]["exogenous_world_id"]:
                np.asarray(examples[i]["targets"])[head_indices] * signs
            for i in candidates[name]
        }

    left, right = by_world(challenger), by_world(target)
    shared = sorted(set(left) & set(right))
    if not shared:
        return None
    wins = 0
    for world in shared:
        nonworse = bool((left[world] >= right[world]).all())
        strict = bool((left[world] > right[world]).any())
        wins += int(nonworse and strict)
    return wins / len(shared)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=pathlib.Path, required=True)
    parser.add_argument(
        "--held-out-cell", action="append", required=True,
        help="cell_id excluded from training and used for evaluation",
    )
    parser.add_argument("--ensemble-size", type=int, default=3)
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--dim", type=int, default=64)
    parser.add_argument("--seed", type=int, default=20260823)
    parser.add_argument("--dominance-draws", type=int, default=512)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    import torch

    torch.set_num_threads(max(1, (torch.get_num_threads() or 4) - 1))
    rows = load_rows(args.dataset)
    examples = prepare_examples(rows)
    train, held = split_by_cell(examples, set(args.held_out_cell))
    stats = compute_stats(train)
    widths = {
        key: len(np.asarray(stats[key][0])) for key in SET_KEYS
    }
    widths["action"] = len(train[0]["action"])
    train_arrays = build_arrays(train, stats)
    held_arrays = build_arrays(held, stats)
    groups = [row["root_id"] for row in train]
    models = [
        fit_member(
            torch, train_arrays, widths, groups=groups,
            seed=args.seed + member, epochs=args.epochs, dim=args.dim,
        )
        for member in range(args.ensemble_size)
    ]
    held_prediction = predict(torch, models, held_arrays, stats)
    train_prediction = predict(torch, models, train_arrays, stats)
    report = {
        "schema_version": 1,
        "contract": "joint_outcome_scorer_poc2_v1",
        "dataset": str(args.dataset),
        "target_heads": list(TARGET_HEADS),
        "dominance_heads": list(DOMINANCE_HEADS),
        "train_rows": len(train),
        "held_rows": len(held),
        "train_cells": sorted({row["cell_id"] for row in train}),
        "held_out_cells": sorted({row["cell_id"] for row in held}),
        "ensemble_size": args.ensemble_size,
        "epochs": args.epochs,
        "dim": args.dim,
        "held_out": evaluate_held_out(
            held, held_prediction,
            seed=args.seed, draws=args.dominance_draws,
        ),
        "train_fit": evaluate_held_out(
            train, train_prediction,
            seed=args.seed, draws=args.dominance_draws,
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    held_summary = report["held_out"]
    print(
        f"train_rows={len(train)} held_rows={len(held)} "
        f"held_roots={held_summary['roots']} "
        f"dominance_agreement={held_summary['dominance']['direction_agreement']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
