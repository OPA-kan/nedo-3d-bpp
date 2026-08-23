"""Train the feasibility head F(s, a) = P(safe) (beta contract, Phase 3A).

Set Transformer state encoders plus an action branch, binary verdict,
class imbalance handled by pos-weighting. Split unit is the collection
cell; ensemble members are independently seeded with root-group
bootstrap. The checkpoint directory is loadable by
``FeasibilityEnsemble`` for proposal resampling and gate evaluation.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
from typing import Any

import numpy as np

SET_KEYS = ("container", "packed_item", "visible_item")
MODEL_SEMANTICS = "feasibility_p_safe_v1"
ALLOWED_SEMANTICS = {
    "feasibility_p_safe_v1",
    "acceptance_p_search_pareto_v1",
}


def load_rows(path: pathlib.Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    if not rows:
        raise ValueError(f"{path} contains no rows")
    return rows


def prepare_examples(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    examples = []
    for row in rows:
        state = row["features"]["state"]
        examples.append({
            "cell_id": row["cell_id"],
            "root_id": row["root_id"],
            "source": (
                (row.get("audit_only") or {}).get("provenance") or {}
            ).get("source"),
            "container": state["container_values"],
            "packed_item": state["packed_item_values"],
            "visible_item": state["visible_item_values"],
            "action": (
                list(row["features"]["action"])
                + list(row["features"]["acting_item"])
            ),
            "label": 1.0 if row["physical_safe"] else 0.0,
        })
    return examples


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
        stats[key] = (
            moments(tokens) if len(tokens)
            else (np.zeros(1), np.ones(1))
        )
    stats["action"] = moments(
        np.asarray([row["action"] for row in examples], dtype=np.float32)
    )
    return stats


def build_arrays(
    examples: list[dict[str, Any]], stats: dict[str, Any],
) -> dict[str, np.ndarray]:
    arrays: dict[str, np.ndarray] = {}
    for key in SET_KEYS:
        mean, scale = (np.asarray(part) for part in stats[key])
        width = len(mean)
        longest = max(1, max(len(row[key]) for row in examples))
        values = np.zeros((len(examples), longest, width), dtype=np.float32)
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
    action = np.asarray([row["action"] for row in examples], dtype=np.float32)
    arrays["action"] = (
        (action - stats["action"][0]) / stats["action"][1]
    ).astype(np.float32)
    arrays["label"] = np.asarray(
        [row["label"] for row in examples], dtype=np.float32
    )
    return arrays


def build_model(torch, widths: dict[str, int], *, dim: int = 64):
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

    class FeasibilityHead(nn.Module):
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
                nn.Linear(dim, 1),
            )

        def forward(self, batch):
            blocks = [
                self.encoders[key](batch[key], batch[f"{key}_mask"])
                for key in SET_KEYS
            ]
            blocks.append(self.action(batch["action"]))
            return self.trunk(torch.cat(blocks, dim=-1)).squeeze(-1)

    return FeasibilityHead()


def _torch_batch(torch, arrays, indices):
    batch = {}
    for key, value in arrays.items():
        tensor = torch.from_numpy(value[indices])
        batch[key] = tensor.bool() if value.dtype == bool else tensor.float()
    return batch


def fit_member(
    torch, arrays, widths, *, groups, seed, epochs, dim,
    batch_size=128, learning_rate=1e-3,
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
    labels = arrays["label"][indices]
    positives = max(1.0, float(labels.sum()))
    pos_weight = torch.tensor(
        max(1.0, (len(labels) - positives) / positives)
    )
    model = build_model(torch, widths, dim=dim)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    model.train()
    for _epoch in range(epochs):
        order = indices.copy()
        rng.shuffle(order)
        for start in range(0, len(order), batch_size):
            batch = _torch_batch(torch, arrays, order[start:start + batch_size])
            logits = model(batch)
            loss = loss_fn(logits, batch["label"])
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
    model.eval()
    return model


def predict_proba(torch, models, arrays) -> np.ndarray:
    outputs = []
    with torch.no_grad():
        for model in models:
            batch = _torch_batch(
                torch, arrays, np.arange(len(arrays["label"]))
            )
            outputs.append(torch.sigmoid(model(batch)).numpy())
    return np.stack(outputs).mean(axis=0)


def auc(labels: np.ndarray, scores: np.ndarray) -> float | None:
    positives = scores[labels > 0.5]
    negatives = scores[labels <= 0.5]
    if not len(positives) or not len(negatives):
        return None
    wins = ties = 0
    for p in positives:
        wins += int((negatives < p).sum())
        ties += int((negatives == p).sum())
    return (wins + 0.5 * ties) / (len(positives) * len(negatives))


class FeasibilityEnsemble:
    """CPU inference over a trained checkpoint directory."""

    def __init__(self, model_dir: pathlib.Path):
        import torch

        self.torch = torch
        self.model_dir = pathlib.Path(model_dir)
        manifest = json.loads(
            (self.model_dir / "manifest.json").read_text(encoding="utf-8")
        )
        if manifest.get("semantics") not in ALLOWED_SEMANTICS:
            raise ValueError("model dir is not a known binary-head ensemble")
        self.semantics = manifest.get("semantics")
        self.model_id = manifest.get("model_id")
        self.stats = {
            key: tuple(np.asarray(part, dtype=np.float32) for part in value)
            for key, value in manifest["stats"].items()
        }
        self.widths = manifest["widths"]
        self.members = []
        for member in manifest["members"]:
            checkpoint = torch.load(
                self.model_dir / member["path"], map_location="cpu",
                weights_only=True,
            )
            model = build_model(torch, self.widths)
            model.load_state_dict(checkpoint["state_dict"])
            model.eval()
            self.members.append(model)

    def predict(
        self, state: dict[str, Any], actions: list[dict[str, Any]],
        acting_items: list[list[float]],
    ) -> np.ndarray:
        examples = [
            {
                "cell_id": "inference", "root_id": "inference",
                "source": None,
                "container": state["container_values"],
                "packed_item": state["packed_item_values"],
                "visible_item": state["visible_item_values"],
                "action": [
                    float(command["container_idx"]),
                    float(command["orientation"]),
                    float(command["place_pos"][0]),
                    float(command["place_pos"][1]),
                    float(command["place_pos"][2]),
                ] + [float(v) for v in item],
                "label": 0.0,
            }
            for command, item in zip(actions, acting_items)
        ]
        arrays = build_arrays(examples, self.stats)
        return predict_proba(self.torch, self.members, arrays)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=pathlib.Path, required=True)
    parser.add_argument("--held-out-cell", action="append", default=[])
    parser.add_argument("--ensemble-size", type=int, default=3)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--dim", type=int, default=64)
    parser.add_argument("--seed", type=int, default=20260823)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument(
        "--semantics", default=MODEL_SEMANTICS,
        choices=sorted(ALLOWED_SEMANTICS),
    )
    args = parser.parse_args()

    import torch

    torch.set_num_threads(max(1, (torch.get_num_threads() or 4) - 1))
    examples = prepare_examples(load_rows(args.dataset))
    held_cells = set(args.held_out_cell)
    train = [row for row in examples if row["cell_id"] not in held_cells]
    held = [row for row in examples if row["cell_id"] in held_cells]
    if not train:
        raise SystemExit("no training rows after the cell split")
    stats = compute_stats(train)
    widths = {
        key: len(np.asarray(stats[key][0])) for key in SET_KEYS
    }
    widths["action"] = len(train[0]["action"])
    train_arrays = build_arrays(train, stats)
    groups = [row["root_id"] for row in train]
    models = [
        fit_member(
            torch, train_arrays, widths, groups=groups,
            seed=args.seed + member, epochs=args.epochs, dim=args.dim,
        )
        for member in range(args.ensemble_size)
    ]
    report: dict[str, Any] = {"train_rows": len(train), "held_rows": len(held)}
    train_scores = predict_proba(torch, models, train_arrays)
    report["train_auc"] = auc(train_arrays["label"], train_scores)
    if held:
        held_arrays = build_arrays(held, stats)
        held_scores = predict_proba(torch, models, held_arrays)
        report["held_auc"] = auc(held_arrays["label"], held_scores)
        by_source: dict[str, Any] = {}
        sources = np.asarray([row["source"] or "unknown" for row in held])
        for source in sorted(set(sources)):
            index = sources == source
            by_source[source] = {
                "rows": int(index.sum()),
                "auc": auc(held_arrays["label"][index], held_scores[index]),
            }
        report["held_by_source"] = by_source

    args.output_dir.mkdir(parents=True, exist_ok=True)
    members = []
    for index, model in enumerate(models):
        path = f"member-{index:02d}.pt"
        torch.save(
            {"state_dict": model.state_dict()}, args.output_dir / path
        )
        members.append({"member": index, "path": path})
    manifest = {
        "schema_version": 1,
        "semantics": args.semantics,
        "model_id": (
            f"{args.semantics}-{args.seed}-e{args.epochs}-d{args.dim}"
        ),
        "members": members,
        "widths": widths,
        "stats": {
            key: [np.asarray(part).tolist() for part in value]
            for key, value in stats.items()
        },
        "train_cells": sorted({row["cell_id"] for row in train}),
        "held_out_cells": sorted(held_cells),
        "report": report,
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
