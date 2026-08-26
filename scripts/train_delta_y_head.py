"""Train and shadow-evaluate the paired-difference head DeltaY(s, a, a').

Beta-contract Phase 3B: the pairwise primitive is the component
difference vector with **architectural antisymmetry** —
``N(s,a,a') - N(s,a',a)`` — never a dominance probability. The head is
shadow-only: it must not touch proposal weights before Vector MCTS
exists. Its PoC metrics are per-head sign accuracy, within-root Kendall
tau, same-world dominance classification, and incomparability
recognition, all against measured sibling pairs on held-out cells.
"""

from __future__ import annotations

import argparse
import collections
import itertools
import json
import pathlib
import random
import sys
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.counterfactual_graph import (  # noqa: E402
    state_tensor_from_snapshot,
)

SET_KEYS = ("container", "packed_item", "visible_item")
COMPONENT_HEADS = (
    "fill_gain", "placed_gain", "soft_violation_gain",
    "priority_covered_gain", "priority_misrouted_gain",
    "center_of_mass_z_delta", "surface_total_variation_delta",
)
# The model still regresses surface_total_variation_delta (see
# COMPONENT_HEADS) as a diagnostic auxiliary target, but it stays out
# of DOMINANCE_HEADS: shadow_metrics()'s verdict() zeroes any head
# missing from this dict (`DOMINANCE_HEADS.get(head, 0.0)`), so the
# ground-truth/predicted a_dominates/b_dominates confusion matrix no
# longer lets an unvalidated proxy axis decide or block a verdict, in
# line with DOMINANCE_HEADS in run_vector_mcts.py.
DOMINANCE_HEADS = {
    "fill_gain": +1.0,
    "soft_violation_gain": -1.0,
    "priority_covered_gain": -1.0,
    "priority_misrouted_gain": -1.0,
}
MODEL_SEMANTICS = "paired_difference_delta_y_v1"


def build_pairs(run_dir: pathlib.Path, *, cell_id: str) -> list[dict[str, Any]]:
    manifest = json.loads((run_dir / "manifest.json").read_text())
    pairs = []
    for episode_index, episode in enumerate(manifest.get("episodes") or []):
        episode_dir = run_dir / f"episode-{episode_index:03d}"
        for record in episode.get("records") or []:
            snapshot = json.loads(
                (episode_dir / record["snapshot_path"]).read_text()
            )
            state = state_tensor_from_snapshot(snapshot)
            visible = list(state["visible_item_indices"])
            safe = [
                sample for sample in record.get("measurement_samples") or []
                if sample.get("physical_safe")
                and sample.get("command_action") is not None
                and sample.get("stable_item_index") in visible
                and sample.get("raw_outcome_vector")
            ]
            for a, b in itertools.combinations(safe, 2):
                delta = {}
                eligible = {}
                for head in COMPONENT_HEADS:
                    ya = a["raw_outcome_vector"].get(head)
                    yb = b["raw_outcome_vector"].get(head)
                    ok = (
                        a["head_eligibility"].get(head) is True
                        and b["head_eligibility"].get(head) is True
                        and ya is not None and yb is not None
                    )
                    delta[head] = (float(yb) - float(ya)) if ok else 0.0
                    eligible[head] = bool(ok)
                if not any(eligible.values()):
                    continue

                def action_features(sample):
                    command = sample["command_action"]
                    item = [
                        float(v)
                        for v in state["visible_item_values"][
                            visible.index(sample["stable_item_index"])
                        ]
                    ]
                    return [
                        float(command["container_idx"]),
                        float(command["orientation"]),
                        float(command["place_pos"][0]),
                        float(command["place_pos"][1]),
                        float(command["place_pos"][2]),
                    ] + item

                pairs.append({
                    "cell_id": cell_id,
                    "root_id": a["root_id"],
                    "candidate_a": a["root_candidate_id"],
                    "candidate_b": b["root_candidate_id"],
                    "container": state["container_values"],
                    "packed_item": state["packed_item_values"],
                    "visible_item": state["visible_item_values"],
                    "action_a": action_features(a),
                    "action_b": action_features(b),
                    "delta": [delta[head] for head in COMPONENT_HEADS],
                    "delta_mask": [eligible[head] for head in COMPONENT_HEADS],
                })
    return pairs


def compute_stats(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    def moments(values):
        values = np.asarray(values, dtype=np.float32)
        mean = values.mean(axis=0)
        scale = values.std(axis=0)
        scale[scale < 1e-6] = 1.0
        return mean, scale

    stats: dict[str, Any] = {}
    for key in SET_KEYS:
        tokens = [token for row in pairs for token in row[key]]
        stats[key] = moments(tokens) if tokens else (np.zeros(1), np.ones(1))
    stats["action"] = moments(
        [row["action_a"] for row in pairs] + [row["action_b"] for row in pairs]
    )
    deltas = np.asarray([row["delta"] for row in pairs], dtype=np.float32)
    masks = np.asarray([row["delta_mask"] for row in pairs], dtype=bool)
    mean = np.zeros(len(COMPONENT_HEADS))
    scale = np.ones(len(COMPONENT_HEADS))
    for column in range(len(COMPONENT_HEADS)):
        observed = deltas[masks[:, column], column]
        if len(observed):
            scale[column] = max(float(observed.std()), 1e-3)
    stats["delta"] = (mean, scale)  # differences stay zero-centered
    return stats


def build_arrays(pairs, stats):
    arrays = {}
    for key in SET_KEYS:
        mean, scale = (np.asarray(part) for part in stats[key])
        width = len(mean)
        longest = max(1, max(len(row[key]) for row in pairs))
        values = np.zeros((len(pairs), longest, width), dtype=np.float32)
        mask = np.ones((len(pairs), longest), dtype=bool)
        for index, row in enumerate(pairs):
            tokens = np.asarray(row[key], dtype=np.float32)
            if len(tokens):
                values[index, :len(tokens)] = (tokens - mean) / scale
                mask[index, :len(tokens)] = False
            else:
                mask[index, 0] = False
        arrays[key] = values
        arrays[f"{key}_mask"] = mask
    for side in ("action_a", "action_b"):
        action = np.asarray([row[side] for row in pairs], dtype=np.float32)
        arrays[side] = (
            (action - stats["action"][0]) / stats["action"][1]
        ).astype(np.float32)
    delta = np.asarray([row["delta"] for row in pairs], dtype=np.float32)
    arrays["delta"] = (delta / stats["delta"][1]).astype(np.float32)
    arrays["delta_mask"] = np.asarray(
        [row["delta_mask"] for row in pairs], dtype=bool
    )
    return arrays


def build_model(torch, widths, *, dim: int = 64):
    nn = torch.nn

    class SetEncoder(nn.Module):
        def __init__(self, width):
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

    class DeltaYHead(nn.Module):
        """Architecturally antisymmetric: N(s,a,b) - N(s,b,a)."""

        def __init__(self):
            super().__init__()
            self.encoders = nn.ModuleDict({
                key: SetEncoder(widths[key]) for key in SET_KEYS
            })
            self.action = nn.Sequential(
                nn.Linear(widths["action"], dim), nn.GELU(),
                nn.Linear(dim, dim),
            )
            self.pair = nn.Sequential(
                nn.Linear(5 * dim, 2 * dim), nn.GELU(),
                nn.Dropout(0.1), nn.Linear(2 * dim, dim), nn.GELU(),
                nn.Linear(dim, len(COMPONENT_HEADS)),
            )

        def _ordered(self, state, ea, eb):
            return self.pair(torch.cat([state, ea, eb], dim=-1))

        def forward(self, batch):
            blocks = [
                self.encoders[key](batch[key], batch[f"{key}_mask"])
                for key in SET_KEYS
            ]
            state = torch.cat(blocks, dim=-1)
            ea = self.action(batch["action_a"])
            eb = self.action(batch["action_b"])
            return self._ordered(state, ea, eb) - self._ordered(state, eb, ea)

    return DeltaYHead()


def _torch_batch(torch, arrays, indices):
    batch = {}
    for key, value in arrays.items():
        tensor = torch.from_numpy(value[indices])
        batch[key] = tensor.bool() if value.dtype == bool else tensor.float()
    return batch


def fit_member(torch, arrays, widths, *, groups, seed, epochs, dim):
    torch.manual_seed(seed)
    rng = random.Random(seed)
    unique = sorted(set(groups))
    chosen = collections.Counter(rng.choice(unique) for _ in unique)
    indices = np.asarray([
        index for index, group in enumerate(groups)
        for _ in range(chosen[group])
    ])
    model = build_model(torch, widths, dim=dim)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    model.train()
    for _epoch in range(epochs):
        order = indices.copy()
        rng.shuffle(order)
        for start in range(0, len(order), 64):
            batch = _torch_batch(torch, arrays, order[start:start + 64])
            predicted = model(batch)
            error = (predicted - batch["delta"]) ** 2
            masked = torch.where(
                batch["delta_mask"], error, torch.zeros_like(error)
            )
            loss = masked.sum() / batch["delta_mask"].sum().clamp(min=1)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
    model.eval()
    return model


def predict_delta(torch, models, arrays, stats) -> np.ndarray:
    outputs = []
    with torch.no_grad():
        for model in models:
            batch = _torch_batch(
                torch, arrays, np.arange(len(arrays["delta"]))
            )
            outputs.append(model(batch).numpy() * np.asarray(stats["delta"][1]))
    return np.stack(outputs).mean(axis=0)


def shadow_metrics(
    pairs: list[dict[str, Any]], predicted: np.ndarray, *,
    sign_tolerance: float = 1e-6,
) -> dict[str, Any]:
    actual = np.asarray([row["delta"] for row in pairs])
    mask = np.asarray([row["delta_mask"] for row in pairs], dtype=bool)
    per_head = {}
    for column, head in enumerate(COMPONENT_HEADS):
        rows = mask[:, column] & (np.abs(actual[:, column]) > sign_tolerance)
        if not rows.any():
            per_head[head] = {"sign_accuracy": None, "count": 0}
            continue
        agree = (
            np.sign(predicted[rows, column]) == np.sign(actual[rows, column])
        )
        per_head[head] = {
            "sign_accuracy": float(agree.mean()),
            "count": int(rows.sum()),
        }

    heads = list(COMPONENT_HEADS)
    directions = np.asarray([
        DOMINANCE_HEADS.get(head, 0.0) for head in heads
    ])
    active = directions != 0.0

    def verdict(vector, row_mask):
        signed = vector[active] * directions[active]
        usable = row_mask[active]
        if not usable.any():
            return None
        signed = signed[usable]
        if (signed >= -sign_tolerance).all() and (signed > sign_tolerance).any():
            return "b_dominates"
        if (signed <= sign_tolerance).all() and (signed < -sign_tolerance).any():
            return "a_dominates"
        return "incomparable"

    confusion = collections.Counter()
    for index, row in enumerate(pairs):
        truth = verdict(actual[index], mask[index])
        guess = verdict(predicted[index], mask[index])
        if truth is not None and guess is not None:
            confusion[(truth, guess)] += 1
    total = sum(confusion.values())
    correct = sum(
        count for (truth, guess), count in confusion.items() if truth == guess
    )
    incomparable_truth = sum(
        count for (truth, _guess), count in confusion.items()
        if truth == "incomparable"
    )
    incomparable_hit = confusion[("incomparable", "incomparable")]

    tau_values = []
    by_root: dict[str, list[int]] = collections.defaultdict(list)
    for index, row in enumerate(pairs):
        by_root[row["root_id"]].append(index)
    fill = heads.index("fill_gain")
    for root, indices in by_root.items():
        scores_pred: dict[str, float] = collections.defaultdict(float)
        scores_true: dict[str, float] = collections.defaultdict(float)
        for index in indices:
            if not mask[index][fill]:
                continue
            a = pairs[index]["candidate_a"]
            b = pairs[index]["candidate_b"]
            scores_pred[b] += predicted[index][fill]
            scores_pred[a] -= predicted[index][fill]
            scores_true[b] += actual[index][fill]
            scores_true[a] -= actual[index][fill]
        names = sorted(set(scores_pred) & set(scores_true))
        concordant = discordant = 0
        for i, x in enumerate(names):
            for y in names[i + 1:]:
                dp = scores_pred[x] - scores_pred[y]
                dt = scores_true[x] - scores_true[y]
                if dp * dt > 0:
                    concordant += 1
                elif dp * dt < 0:
                    discordant += 1
        if concordant + discordant:
            tau_values.append(
                (concordant - discordant) / (concordant + discordant)
            )
    return {
        "pairs": len(pairs),
        "sign_accuracy": per_head,
        "dominance_classification": {
            "total": total,
            "accuracy": correct / total if total else None,
            "incomparable_recall": (
                incomparable_hit / incomparable_truth
                if incomparable_truth else None
            ),
            "confusion": {
                f"{truth}->{guess}": count
                for (truth, guess), count in sorted(confusion.items())
            },
        },
        "within_root_fill_tau": {
            "mean": (
                sum(tau_values) / len(tau_values) if tau_values else None
            ),
            "count": len(tau_values),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", action="append", required=True, metavar="CELL=RUN_DIR",
    )
    parser.add_argument("--held-out-cell", action="append", default=[])
    parser.add_argument("--ensemble-size", type=int, default=3)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--dim", type=int, default=64)
    parser.add_argument("--seed", type=int, default=20260823)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()

    import torch

    torch.set_num_threads(max(1, (torch.get_num_threads() or 4) - 1))
    pairs = []
    for spec in args.run:
        cell, _, run_dir = spec.partition("=")
        pairs.extend(build_pairs(pathlib.Path(run_dir), cell_id=cell))
    held_cells = set(args.held_out_cell)
    train = [row for row in pairs if row["cell_id"] not in held_cells]
    held = [row for row in pairs if row["cell_id"] in held_cells]
    if not train or not held:
        raise SystemExit(
            f"degenerate split: {len(train)} train / {len(held)} held pairs"
        )
    stats = compute_stats(train)
    widths = {key: len(np.asarray(stats[key][0])) for key in SET_KEYS}
    widths["action"] = len(train[0]["action_a"])
    train_arrays = build_arrays(train, stats)
    held_arrays = build_arrays(held, stats)
    models = [
        fit_member(
            torch, train_arrays, widths,
            groups=[row["root_id"] for row in train],
            seed=args.seed + member, epochs=args.epochs, dim=args.dim,
        )
        for member in range(args.ensemble_size)
    ]
    report = {
        "train_pairs": len(train),
        "held_pairs": len(held),
        "held_out_cells": sorted(held_cells),
        "shadow_only": True,
        "held_metrics": shadow_metrics(
            held, predict_delta(torch, models, held_arrays, stats)
        ),
        "train_metrics": shadow_metrics(
            train, predict_delta(torch, models, train_arrays, stats)
        ),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    members = []
    for index, model in enumerate(models):
        path = f"member-{index:02d}.pt"
        torch.save({"state_dict": model.state_dict()}, args.output_dir / path)
        members.append({"member": index, "path": path})
    (args.output_dir / "manifest.json").write_text(
        json.dumps({
            "schema_version": 1,
            "semantics": MODEL_SEMANTICS,
            "antisymmetry": "architectural_N(s,a,b)-N(s,b,a)",
            "members": members,
            "widths": widths,
            "stats": {
                key: [np.asarray(part).tolist() for part in value]
                for key, value in stats.items()
            },
            "report": report,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["held_metrics"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
