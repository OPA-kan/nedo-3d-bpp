"""Train a group-held-out Set Transformer rollout-trigger classifier.

This model does not predict packing value.  It predicts whether the expensive
terminal physics oracle will change the incumbent action.  Inputs are limited
to the observed state sets and H1 candidate vectors; terminal outcomes, future
actions and step indices are excluded.  OOF scores are evaluated as a compute
allocation policy against the observed wall-clock budget.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import random
import sys
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.counterfactual_graph import state_tensor_from_snapshot

SET_KEYS = ("container", "packed_item", "visible_item", "candidate")
CANDIDATE_HEADS = (
    ("fill_gain", +1.0),
    ("soft_violation_gain", -1.0),
    ("priority_covered_gain", -1.0),
    ("priority_misrouted_gain", -1.0),
    ("surface_total_variation_delta", -1.0),
)
CANDIDATE_FEATURES = tuple(
    f"oriented_{name}" for name, _direction in CANDIDATE_HEADS
) + ("is_incumbent",)


def load_examples(
    dataset_path: pathlib.Path, dataset_root: pathlib.Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    if dataset.get("contract") != "terminal_rollout_trigger_dataset_v1":
        raise ValueError("unsupported trigger dataset contract")
    examples = []
    state_contract = None
    for row in dataset.get("rows") or []:
        snapshot = json.loads(
            (dataset_root / row["snapshot_path"]).read_text(encoding="utf-8")
        )
        state = state_tensor_from_snapshot(snapshot)
        current_contract = {
            "container": list(state["container_features"]),
            "packed_item": list(state["packed_item_features"]),
            "visible_item": list(state["visible_item_features"]),
        }
        if state_contract is None:
            state_contract = current_contract
        elif state_contract != current_contract:
            raise ValueError("state tensor contracts differ")
        incumbent = row.get("incumbent_candidate_id")
        candidate_tokens = []
        for candidate in row.get("candidates") or []:
            if not candidate.get("safe"):
                continue
            vector = candidate.get("one_step_vector") or {}
            if not all(
                isinstance(vector.get(name), (int, float))
                for name, _direction in CANDIDATE_HEADS
            ):
                continue
            candidate_tokens.append([
                direction * float(vector[name])
                for name, direction in CANDIDATE_HEADS
            ] + [float(candidate.get("root_candidate_id") == incumbent)])
        if not candidate_tokens:
            raise ValueError(f"{row.get('root_id')}: no complete safe H1 candidates")
        full = (row.get("decision_timing") or {}).get(
            "decision_total_seconds"
        )
        shallow = row.get("estimated_no_terminal_decision_seconds")
        if not isinstance(full, (int, float)) or not isinstance(
            shallow, (int, float)
        ):
            raise ValueError(f"{row.get('root_id')}: wall-clock timing missing")
        examples.append({
            "group": str(row["cell"]),
            "root_id": str(row["root_id"]),
            "container": state["container_values"],
            "packed_item": state["packed_item_values"],
            "visible_item": state["visible_item_values"],
            "candidate": candidate_tokens,
            "label": float(bool(row["terminal_intervention"])),
            "full_seconds": float(full),
            "shallow_seconds": float(shallow),
        })
    if not examples:
        raise ValueError("trigger dataset contains no rows")
    if len({row["group"] for row in examples}) < 2:
        raise ValueError("group-held-out trigger training needs >=2 groups")
    return examples, {
        "contract": "rollout_trigger_set_transformer_v1",
        "target": "terminal_oracle_changes_incumbent_action",
        "state_features": state_contract,
        "candidate_features": list(CANDIDATE_FEATURES),
        "forbidden_inputs": [
            "step", "terminal_vector", "terminal_pareto_candidates",
            "terminal_continuation_actions",
        ],
        "split_unit": "whole_collection_cell",
    }


def group_folds(groups: list[str], folds: int, seed: int) -> list[set[str]]:
    unique = sorted(set(groups))
    if len(unique) < 2:
        raise ValueError("at least two groups required")
    count = min(max(2, int(folds)), len(unique))
    random.Random(seed).shuffle(unique)
    result = [set() for _ in range(count)]
    for index, group in enumerate(unique):
        result[index % count].add(group)
    return result


def _moments(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mean = values.mean(axis=0)
    scale = values.std(axis=0)
    scale[scale < 1e-6] = 1.0
    return mean, scale


def compute_stats(examples: list[dict[str, Any]]) -> dict[str, Any]:
    stats = {}
    for key in SET_KEYS:
        tokens = np.asarray(
            [token for row in examples for token in row[key]],
            dtype=np.float32,
        )
        if not len(tokens):
            raise ValueError(f"no {key} tokens")
        stats[key] = _moments(tokens)
    return stats


def build_arrays(
    examples: list[dict[str, Any]], stats: dict[str, Any],
) -> dict[str, np.ndarray]:
    arrays = {}
    for key in SET_KEYS:
        mean, scale = stats[key]
        longest = max(1, max(len(row[key]) for row in examples))
        values = np.zeros(
            (len(examples), longest, len(mean)), dtype=np.float32
        )
        mask = np.ones((len(examples), longest), dtype=bool)
        for index, row in enumerate(examples):
            tokens = np.asarray(row[key], dtype=np.float32)
            if len(tokens):
                values[index, :len(tokens)] = (tokens - mean) / scale
                mask[index, :len(tokens)] = False
            else:
                mask[index, 0] = False
        arrays[key] = values
        arrays[f"{key}_mask"] = mask
    arrays["label"] = np.asarray(
        [row["label"] for row in examples], dtype=np.float32
    )
    return arrays


def build_model(torch, widths: dict[str, int], *, dim: int = 48):
    nn = torch.nn

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

    class RolloutTrigger(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoders = nn.ModuleDict({
                key: SetEncoder(widths[key]) for key in SET_KEYS
            })
            self.head = nn.Sequential(
                nn.Linear(len(SET_KEYS) * dim, 2 * dim), nn.GELU(),
                nn.Dropout(0.1), nn.Linear(2 * dim, dim), nn.GELU(),
                nn.Linear(dim, 1),
            )

        def forward(self, batch):
            blocks = [
                self.encoders[key](batch[key], batch[f"{key}_mask"])
                for key in SET_KEYS
            ]
            return self.head(torch.cat(blocks, dim=-1)).squeeze(-1)

    return RolloutTrigger()


def _torch_batch(torch, arrays, indices):
    batch = {}
    for key, value in arrays.items():
        tensor = torch.from_numpy(value[indices])
        batch[key] = tensor.bool() if value.dtype == bool else tensor.float()
    return batch


def fit_member(
    torch, examples: list[dict[str, Any]], *, seed: int, epochs: int,
    dim: int,
):
    torch.manual_seed(seed)
    rng = random.Random(seed)
    groups = sorted({row["group"] for row in examples})
    sampled = collections.Counter(rng.choice(groups) for _ in groups)
    bootstrap = [
        row for row in examples for _ in range(sampled[row["group"]])
    ]
    if not any(row["label"] for row in bootstrap):
        bootstrap = list(examples)
    stats = compute_stats(bootstrap)
    arrays = build_arrays(bootstrap, stats)
    widths = {key: len(stats[key][0]) for key in SET_KEYS}
    labels = arrays["label"]
    positives = max(1.0, float(labels.sum()))
    pos_weight = torch.tensor(max(1.0, (len(labels) - positives) / positives))
    model = build_model(torch, widths, dim=dim)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    indices = np.arange(len(bootstrap))
    model.train()
    for _epoch in range(epochs):
        rng.shuffle(indices)
        for start in range(0, len(indices), 64):
            batch = _torch_batch(torch, arrays, indices[start:start + 64])
            loss = loss_fn(model(batch), batch["label"])
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
    model.eval()
    return model, stats


def predict(torch, members, examples: list[dict[str, Any]]) -> np.ndarray:
    outputs = []
    with torch.no_grad():
        for model, stats in members:
            arrays = build_arrays(examples, stats)
            batch = _torch_batch(torch, arrays, np.arange(len(examples)))
            outputs.append(torch.sigmoid(model(batch)).cpu().numpy())
    return np.stack(outputs).mean(axis=0)


def auc(labels: np.ndarray, scores: np.ndarray) -> float | None:
    positives = scores[labels > 0.5]
    negatives = scores[labels <= 0.5]
    if not len(positives) or not len(negatives):
        return None
    wins = sum(int((negatives < value).sum()) for value in positives)
    ties = sum(int((negatives == value).sum()) for value in positives)
    return (wins + 0.5 * ties) / (len(positives) * len(negatives))


def average_precision(labels: np.ndarray, scores: np.ndarray) -> float | None:
    positives = int((labels > 0.5).sum())
    if not positives:
        return None
    order = np.argsort(-scores)
    found = 0
    total = 0.0
    for rank, index in enumerate(order, 1):
        if labels[index] > 0.5:
            found += 1
            total += found / rank
    return total / positives


def _percentile(values: list[float], fraction: float) -> float:
    return float(np.quantile(np.asarray(values), fraction))


def budget_curve(
    labels: np.ndarray, scores: np.ndarray, full: np.ndarray,
    shallow: np.ndarray,
) -> list[dict[str, Any]]:
    thresholds = [math.inf, *sorted(set(map(float, scores)), reverse=True)]
    positives = int((labels > 0.5).sum())
    full_total = float(full.sum())
    points = []
    for threshold in thresholds:
        trigger = scores >= threshold
        true_positive = int(((labels > 0.5) & trigger).sum())
        times = np.where(trigger, full, shallow)
        predicted = int(trigger.sum())
        points.append({
            "threshold": threshold if math.isfinite(threshold) else None,
            "triggered_roots": predicted,
            "intervention_recall": (
                true_positive / positives if positives else None
            ),
            "precision": true_positive / predicted if predicted else None,
            "estimated_mean_seconds": float(times.mean()),
            "estimated_p95_seconds": _percentile(list(times), 0.95),
            "estimated_max_seconds": float(times.max()),
            "estimated_within_10s_rate": float((times <= 10.0).mean()),
            "estimated_speedup_vs_full": full_total / float(times.sum()),
        })
    return points


def select_operating_points(points: list[dict[str, Any]]) -> dict[str, Any]:
    under_sla = [p for p in points if p["estimated_p95_seconds"] <= 10.0]
    recall_80 = [
        p for p in points
        if (p["intervention_recall"] or 0.0) >= 0.8
    ]
    return {
        "best_recall_with_p95_le_10": max(
            under_sla,
            key=lambda p: (p["intervention_recall"] or 0.0,
                           p["estimated_speedup_vs_full"]),
            default=None,
        ),
        "fastest_with_recall_ge_0_8": max(
            recall_80,
            key=lambda p: p["estimated_speedup_vs_full"],
            default=None,
        ),
    }


def run_oof(
    torch, examples: list[dict[str, Any]], *, folds: int,
    ensemble_size: int, epochs: int, dim: int, seed: int,
) -> dict[str, Any]:
    fold_groups = group_folds(
        [row["group"] for row in examples], folds, seed
    )
    scores = np.zeros(len(examples), dtype=np.float32)
    fold_reports = []
    for fold, held_groups in enumerate(fold_groups):
        train = [row for row in examples if row["group"] not in held_groups]
        held_indices = [
            index for index, row in enumerate(examples)
            if row["group"] in held_groups
        ]
        held = [examples[index] for index in held_indices]
        members = [
            fit_member(
                torch, train, seed=seed + fold * 100 + member,
                epochs=epochs, dim=dim,
            )
            for member in range(ensemble_size)
        ]
        scores[held_indices] = predict(torch, members, held)
        fold_reports.append({
            "fold": fold,
            "held_groups": sorted(held_groups),
            "rows": len(held),
            "positives": int(sum(row["label"] for row in held)),
        })
    labels = np.asarray([row["label"] for row in examples])
    full = np.asarray([row["full_seconds"] for row in examples])
    shallow = np.asarray([row["shallow_seconds"] for row in examples])
    curve = budget_curve(labels, scores, full, shallow)
    return {
        "contract": "rollout_trigger_group_oof_v1",
        "rows": len(examples),
        "groups": len(set(row["group"] for row in examples)),
        "positives": int(labels.sum()),
        "positive_prevalence": float(labels.mean()),
        "auc": auc(labels, scores),
        "average_precision": average_precision(labels, scores),
        "folds": fold_reports,
        "operating_points": select_operating_points(curve),
        "oof_rows": [
            {
                "root_id": row["root_id"], "group": row["group"],
                "label": row["label"], "score": float(scores[index]),
                "full_seconds": row["full_seconds"],
                "shallow_seconds": row["shallow_seconds"],
            }
            for index, row in enumerate(examples)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=pathlib.Path, required=True)
    parser.add_argument("--dataset-root", type=pathlib.Path, required=True)
    parser.add_argument("--folds", type=int, default=4)
    parser.add_argument("--ensemble-size", type=int, default=3)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--dim", type=int, default=48)
    parser.add_argument("--seed", type=int, default=20260825)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    import torch

    torch.set_num_threads(4)
    examples, feature_contract = load_examples(
        args.dataset, args.dataset_root
    )
    result = run_oof(
        torch, examples, folds=args.folds,
        ensemble_size=args.ensemble_size, epochs=args.epochs,
        dim=args.dim, seed=args.seed,
    )
    result["feature_contract"] = feature_contract
    result["evaluation_scope"] = (
        "development group-OOF; threshold still needs a fresh cohort gate"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        key: result[key] for key in (
            "rows", "groups", "positives", "auc", "average_precision",
            "operating_points",
        )
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
