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

from scripts.build_terminal_rollout_trigger_dataset import (
    _dominates,
    _oriented,
)
from scripts.counterfactual_graph import (
    CONTAINER_TENSOR_FEATURES,
    ITEM_TENSOR_FEATURES,
    state_tensor_from_snapshot,
)

SET_KEYS = ("container", "packed_item", "visible_item", "candidate")
CANDIDATE_HEADS = (
    ("fill_gain", +1.0),
    ("soft_violation_gain", -1.0),
    ("priority_covered_gain", -1.0),
    ("priority_misrouted_gain", -1.0),
    ("surface_total_variation_delta", -1.0),
)
CANDIDATE_H1_FEATURES = tuple(
    f"oriented_{name}" for name, _direction in CANDIDATE_HEADS
) + tuple(f"item_{name}" for name in ITEM_TENSOR_FEATURES) + ("is_incumbent",)
CANDIDATE_GEOMETRY_FEATURES = (
    "action_local_x", "action_local_y", "action_local_z",
    "action_normalized_x", "action_normalized_y", "action_normalized_z",
) + tuple(f"orientation_{index}" for index in range(6)) + tuple(
    f"target_container_{name}" for name in CONTAINER_TENSOR_FEATURES
) + tuple(f"item_{name}" for name in ITEM_TENSOR_FEATURES) + ("is_incumbent",)


def candidate_features(mode: str) -> tuple[str, ...]:
    if mode == "h1":
        return CANDIDATE_H1_FEATURES
    if mode == "geometry":
        return CANDIDATE_GEOMETRY_FEATURES
    raise ValueError(f"unsupported candidate feature mode: {mode}")


def _geometry_candidate_token(
    snapshot: dict[str, Any], candidate: dict[str, Any],
    item_values: list[float], *, incumbent: bool,
) -> list[float]:
    action = candidate.get("command_action")
    if not isinstance(action, dict):
        raise ValueError("geometry candidate is missing command_action")
    container_index = int(action["container_idx"])
    containers = {
        int(row.get("index", -1)): row
        for row in snapshot.get("observation", {}).get("container_list", [])
    }
    container = containers.get(container_index)
    if container is None:
        raise ValueError(f"candidate targets unknown container {container_index}")
    center = [float(value) for value in container.get("center", [0, 0, 0])]
    position = [float(value) for value in action["place_pos"]]
    local = [position[index] - center[index] for index in range(3)]
    dimensions = [
        float(container.get("length", 0.0) or 0.0),
        float(container.get("width", 0.0) or 0.0),
        float(container.get("height", 0.0) or 0.0),
    ]
    scales = [max(dimensions[0] / 2.0, 1e-6),
              max(dimensions[1] / 2.0, 1e-6),
              max(dimensions[2], 1e-6)]
    normalized = [local[index] / scales[index] for index in range(3)]
    orientation = int(action["orientation"])
    orientation_one_hot = [
        float(index == orientation) for index in range(6)
    ]
    container_values = [
        float(container.get("length", 0.0) or 0.0),
        float(container.get("width", 0.0) or 0.0),
        float(container.get("height", 0.0) or 0.0),
        float(container.get("cut_x", 0.0) or 0.0),
        float(container.get("cut_y", 0.0) or 0.0),
        float(container.get("thickness", 0.0) or 0.0),
        float(container.get("buffer", 0.0) or 0.0),
        float(bool(container.get("shelf"))),
        float(bool(container.get("is_prioritized"))),
    ]
    return (
        local + normalized + orientation_one_hot + container_values
        + list(item_values) + [float(incumbent)]
    )


def candidate_token(
    mode: str, snapshot: dict[str, Any], candidate: dict[str, Any],
    item_values: list[float], *, incumbent: bool,
) -> list[float] | None:
    """Build one candidate token; None when required inputs are missing."""
    if mode == "h1":
        vector = candidate.get("one_step_vector") or {}
        if not all(
            isinstance(vector.get(name), (int, float))
            for name, _direction in CANDIDATE_HEADS
        ):
            return None
        return [
            direction * float(vector[name])
            for name, direction in CANDIDATE_HEADS
        ] + list(item_values) + [float(incumbent)]
    return _geometry_candidate_token(
        snapshot, candidate, list(item_values), incumbent=incumbent,
    )


def load_examples(
    dataset_path: pathlib.Path, dataset_root: pathlib.Path,
    *, candidate_feature_mode: str = "h1",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    if dataset.get("contract") not in {
        "terminal_rollout_trigger_dataset_v1",
        "terminal_rollout_trigger_dataset_with_actions_v1",
    }:
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
        selected = row.get("selected_candidate_id")
        visible_items = dict(zip(
            state["visible_item_indices"], state["visible_item_values"]
        ))
        candidate_tokens = []
        candidate_ids = []
        candidate_work = []
        for candidate in row.get("candidates") or []:
            if not candidate.get("safe"):
                continue
            item_values = visible_items.get(
                int(candidate.get("stable_item_index", -1)),
                [0.0] * len(ITEM_TENSOR_FEATURES),
            )
            token = candidate_token(
                candidate_feature_mode, snapshot, candidate,
                list(item_values),
                incumbent=candidate.get("root_candidate_id") == incumbent,
            )
            if token is None:
                continue
            candidate_tokens.append(token)
            candidate_ids.append(str(candidate["root_candidate_id"]))
            candidate_work.append(float(
                candidate.get("terminal_physical_step_equivalents", 1.0)
                or 1.0
            ))
        if not candidate_tokens:
            raise ValueError(f"{row.get('root_id')}: no complete safe H1 candidates")
        if incumbent not in candidate_ids or selected not in candidate_ids:
            raise ValueError(
                f"{row.get('root_id')}: selected/incumbent candidate missing"
            )
        # pairwise preference labels vs the incumbent, derived from the
        # SAME 4-head terminal dominance rule the search executes with
        # (never a synthesized scalar): 1 = this alternate's genuine
        # terminal outcome strictly dominates the incumbent's, 0 = it
        # does not, -1 = masked (the incumbent itself, or a censored
        # terminal on either side)
        terminal_by_id = {
            str(candidate["root_candidate_id"]): oriented
            for candidate in row.get("candidates") or []
            if candidate.get("safe") and candidate.get("terminal_genuine")
            and (oriented := _oriented(candidate.get("terminal_vector")))
            is not None
        }
        incumbent_terminal = terminal_by_id.get(incumbent)
        pair_labels = []
        for candidate_id in candidate_ids:
            alternate_terminal = terminal_by_id.get(candidate_id)
            if (
                candidate_id == incumbent
                or incumbent_terminal is None
                or alternate_terminal is None
            ):
                pair_labels.append(-1.0)
            else:
                pair_labels.append(float(_dominates(
                    alternate_terminal, incumbent_terminal
                )))
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
            "candidate_ids": candidate_ids,
            "candidate_work": candidate_work,
            "incumbent_index": candidate_ids.index(incumbent),
            "selected_index": candidate_ids.index(selected),
            "pair_labels": pair_labels,
            "label": float(bool(row["terminal_intervention"])),
            "full_seconds": float(full),
            "shallow_seconds": float(shallow),
        })
    if not examples:
        raise ValueError("trigger dataset contains no rows")
    if len({row["group"] for row in examples}) < 2:
        raise ValueError("group-held-out trigger training needs >=2 groups")
    return examples, {
        "contract": "rollout_trigger_set_transformer_v2_candidate_modes",
        "target": "terminal_oracle_changes_incumbent_action",
        "state_features": state_contract,
        "candidate_feature_mode": candidate_feature_mode,
        "candidate_features": list(candidate_features(candidate_feature_mode)),
        "forbidden_inputs": [
            "step", "terminal_vector", "terminal_pareto_candidates",
            "terminal_continuation_actions",
        ],
        "split_unit": "whole_collection_cell",
    }


def group_folds(
    groups: list[str], folds: int, seed: int,
    labels: list[float] | None = None,
) -> list[set[str]]:
    unique = sorted(set(groups))
    if len(unique) < 2:
        raise ValueError("at least two groups required")
    count = min(max(2, int(folds)), len(unique))
    rng = random.Random(seed)
    rng.shuffle(unique)
    group_rows = collections.Counter(groups)
    group_positives = collections.Counter()
    if labels is not None:
        if len(labels) != len(groups):
            raise ValueError("labels must align with groups")
        for group, label in zip(groups, labels):
            group_positives[group] += int(label > 0.5)
    unique.sort(
        key=lambda group: (-group_positives[group], -group_rows[group])
    )
    result = [set() for _ in range(count)]
    fold_positives = [0] * count
    fold_rows = [0] * count
    for group in unique:
        index = min(
            range(count),
            key=lambda fold: (
                fold_positives[fold], fold_rows[fold], len(result[fold]), fold
            ),
        )
        result[index].add(group)
        fold_positives[index] += group_positives[group]
        fold_rows[index] += group_rows[group]
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
    arrays["selected_index"] = np.asarray(
        [row["selected_index"] for row in examples], dtype=np.int64
    )
    arrays["incumbent_index"] = np.asarray(
        [int(row.get("incumbent_index", 0)) for row in examples],
        dtype=np.int64,
    )
    width = arrays["candidate"].shape[1]
    pair_label = np.zeros((len(examples), width), dtype=np.float32)
    pair_valid = np.zeros((len(examples), width), dtype=np.float32)
    for index, row in enumerate(examples):
        for position, value in enumerate(row.get("pair_labels") or []):
            if value >= 0.0:
                pair_label[index, position] = float(value)
                pair_valid[index, position] = 1.0
    arrays["pair_label"] = pair_label
    arrays["pair_valid"] = pair_valid
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
        if value.dtype == bool:
            batch[key] = tensor.bool()
        elif np.issubdtype(value.dtype, np.integer):
            batch[key] = tensor.long()
        else:
            batch[key] = tensor.float()
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


def build_allocator_model(torch, widths: dict[str, int], *, dim: int = 48):
    """Score candidates for rollout allocation without predicting their value."""
    nn = torch.nn

    class SetEncoder(nn.Module):
        def __init__(self, width: int):
            super().__init__()
            self.input = nn.Linear(width, dim)
            self.attention = nn.MultiheadAttention(
                dim, 4, dropout=0.1, batch_first=True
            )
            self.norm = nn.LayerNorm(dim)
            self.seed = nn.Parameter(torch.zeros(1, 1, dim))
            nn.init.normal_(self.seed, std=0.02)
            self.pool = nn.MultiheadAttention(dim, 4, batch_first=True)

        def forward(self, values, mask):
            state = self.input(values)
            attended, _ = self.attention(
                state, state, state, key_padding_mask=mask
            )
            state = self.norm(state + attended)
            query = self.seed.expand(state.shape[0], -1, -1)
            pooled, _ = self.pool(query, state, state, key_padding_mask=mask)
            return pooled.squeeze(1)

    class CandidateEncoder(nn.Module):
        def __init__(self, width: int):
            super().__init__()
            self.input = nn.Linear(width, dim)
            self.attention = nn.MultiheadAttention(
                dim, 4, dropout=0.1, batch_first=True
            )
            self.norm = nn.LayerNorm(dim)

        def forward(self, values, mask):
            state = self.input(values)
            attended, _ = self.attention(
                state, state, state, key_padding_mask=mask
            )
            return self.norm(state + attended)

    class RolloutAllocator(nn.Module):
        def __init__(self):
            super().__init__()
            self.state_encoders = nn.ModuleDict({
                key: SetEncoder(widths[key])
                for key in ("container", "packed_item", "visible_item")
            })
            self.candidates = CandidateEncoder(widths["candidate"])
            self.context = nn.Sequential(
                nn.Linear(3 * dim, dim), nn.GELU()
            )
            self.score = nn.Sequential(
                nn.Linear(2 * dim, dim), nn.GELU(), nn.Linear(dim, 1)
            )

        def forward(self, batch):
            context = self.context(torch.cat([
                self.state_encoders[key](
                    batch[key], batch[f"{key}_mask"]
                )
                for key in ("container", "packed_item", "visible_item")
            ], dim=-1))
            candidates = self.candidates(
                batch["candidate"], batch["candidate_mask"]
            )
            expanded = context.unsqueeze(1).expand(
                -1, candidates.shape[1], -1
            )
            logits = self.score(
                torch.cat([candidates, expanded], dim=-1)
            ).squeeze(-1)
            return logits.masked_fill(batch["candidate_mask"], -1e9)

    return RolloutAllocator()


def fit_allocator_member(
    torch, examples: list[dict[str, Any]], *, seed: int, epochs: int,
    dim: int,
):
    torch.manual_seed(seed)
    rng = random.Random(seed)
    groups = sorted({row["group"] for row in examples})
    sampled = collections.Counter(rng.choice(groups) for _ in groups)
    bootstrap = [
        row for row in examples for _ in range(sampled[row["group"]])
    ] or list(examples)
    stats = compute_stats(bootstrap)
    arrays = build_arrays(bootstrap, stats)
    widths = {key: len(stats[key][0]) for key in SET_KEYS}
    model = build_allocator_model(torch, widths, dim=dim)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    indices = np.arange(len(bootstrap))
    model.train()
    for _epoch in range(epochs):
        rng.shuffle(indices)
        for start in range(0, len(indices), 64):
            batch = _torch_batch(torch, arrays, indices[start:start + 64])
            loss = torch.nn.functional.cross_entropy(
                model(batch), batch["selected_index"]
            )
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
    model.eval()
    return model, stats


def fit_preference_member(
    torch, examples: list[dict[str, Any]], *, seed: int, epochs: int,
    dim: int,
):
    """Learn P(alternate beats incumbent | state) via antisymmetric deltas.

    The model scores every candidate; the pairwise logistic loss is
    applied to score differences against the incumbent, so
    sigmoid(score_j - score_incumbent) IS the preference probability and
    the incumbent's own probability is 0.5 by construction.  Labels come
    only from genuine-terminal dominance; masked pairs carry no loss.
    """
    torch.manual_seed(seed)
    rng = random.Random(seed)
    groups = sorted({row["group"] for row in examples})
    sampled = collections.Counter(rng.choice(groups) for _ in groups)
    bootstrap = [
        row for row in examples for _ in range(sampled[row["group"]])
    ] or list(examples)
    stats = compute_stats(bootstrap)
    arrays = build_arrays(bootstrap, stats)
    widths = {key: len(stats[key][0]) for key in SET_KEYS}
    positives = float((arrays["pair_label"] * arrays["pair_valid"]).sum())
    negatives = float(arrays["pair_valid"].sum()) - positives
    pos_weight = torch.tensor(
        max(1.0, negatives / max(1.0, positives))
    )
    model = build_allocator_model(torch, widths, dim=dim)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    indices = np.arange(len(bootstrap))
    model.train()
    for _epoch in range(epochs):
        rng.shuffle(indices)
        for start in range(0, len(indices), 64):
            batch = _torch_batch(torch, arrays, indices[start:start + 64])
            logits = model(batch)
            incumbent = logits.gather(
                1, batch["incumbent_index"].unsqueeze(1)
            )
            delta = logits - incumbent
            raw = torch.nn.functional.binary_cross_entropy_with_logits(
                delta, batch["pair_label"], pos_weight=pos_weight,
                reduction="none",
            )
            loss = (raw * batch["pair_valid"]).sum() / batch[
                "pair_valid"
            ].sum().clamp(min=1.0)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
    model.eval()
    return model, stats


def predict_preference(torch, members, examples: list[dict[str, Any]]):
    """Ensemble-mean P(candidate beats incumbent); incumbent gets 0.5."""
    member_outputs = []
    with torch.no_grad():
        for model, stats in members:
            arrays = build_arrays(examples, stats)
            batch = _torch_batch(torch, arrays, np.arange(len(examples)))
            logits = model(batch)
            incumbent = logits.gather(
                1, batch["incumbent_index"].unsqueeze(1)
            )
            member_outputs.append(
                torch.sigmoid(logits - incumbent).cpu().numpy()
            )
    mean = np.stack(member_outputs).mean(axis=0)
    return [
        list(map(float, mean[index, :len(row["candidate_ids"])]))
        for index, row in enumerate(examples)
    ]


def predict_allocator(torch, members, examples: list[dict[str, Any]]):
    member_outputs = []
    with torch.no_grad():
        for model, stats in members:
            arrays = build_arrays(examples, stats)
            batch = _torch_batch(torch, arrays, np.arange(len(examples)))
            member_outputs.append(
                torch.softmax(model(batch), dim=-1).cpu().numpy()
            )
    mean = np.stack(member_outputs).mean(axis=0)
    return [
        list(map(float, mean[index, :len(row["candidate_ids"])]))
        for index, row in enumerate(examples)
    ]


POLICY_MODEL_CONTRACT = "rollout_allocator_policy_ensemble_v1"


def save_allocator_ensemble(
    torch, examples: list[dict[str, Any]], feature_contract: dict[str, Any],
    output_dir: pathlib.Path, *, ensemble_size: int, epochs: int, dim: int,
    seed: int, objective: str = "allocator",
) -> dict[str, Any]:
    """Fit the final allocator ensemble on every example and freeze it.

    Unlike the OOF gates this trains on the whole corpus: the saved model
    is the deployable policy head, not an evaluation artifact, and its
    honest report card is the league match it must win on frozen streams.
    """
    if objective not in {"allocator", "preference"}:
        raise ValueError(f"unsupported objective: {objective}")
    fit = fit_preference_member if objective == "preference" \
        else fit_allocator_member
    output_dir.mkdir(parents=True, exist_ok=True)
    member_meta = []
    widths = None
    for member in range(ensemble_size):
        model, stats = fit(
            torch, examples, seed=seed + 90_000 + member,
            epochs=epochs, dim=dim,
        )
        widths = {key: len(stats[key][0]) for key in SET_KEYS}
        weights_name = f"member-{member:02d}.pt"
        torch.save(model.state_dict(), output_dir / weights_name)
        member_meta.append({
            "weights": weights_name,
            "seed": seed + 90_000 + member,
            "stats": {
                key: {
                    "mean": [float(v) for v in stats[key][0]],
                    "scale": [float(v) for v in stats[key][1]],
                }
                for key in SET_KEYS
            },
        })
    metadata = {
        "contract": POLICY_MODEL_CONTRACT,
        "objective": objective,
        "switch_threshold": 0.5 if objective == "preference" else None,
        "dim": dim,
        "ensemble_size": ensemble_size,
        "epochs": epochs,
        "seed": seed,
        "widths": widths,
        "training_rows": len(examples),
        "training_groups": sorted({row["group"] for row in examples}),
        "feature_contract": feature_contract,
        "members": member_meta,
    }
    (output_dir / "model.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return metadata


def load_allocator_ensemble(
    torch, model_dir: pathlib.Path,
) -> tuple[list[tuple[Any, dict[str, Any]]], dict[str, Any]]:
    metadata = json.loads(
        (model_dir / "model.json").read_text(encoding="utf-8")
    )
    if metadata.get("contract") != POLICY_MODEL_CONTRACT:
        raise ValueError(
            f"unsupported policy model contract: {metadata.get('contract')}"
        )
    widths = {key: int(metadata["widths"][key]) for key in SET_KEYS}
    members = []
    for member in metadata.get("members") or []:
        model = build_allocator_model(
            torch, widths, dim=int(metadata["dim"])
        )
        model.load_state_dict(torch.load(
            model_dir / member["weights"], map_location="cpu",
            weights_only=True,
        ))
        model.eval()
        stats = {
            key: (
                np.asarray(member["stats"][key]["mean"], dtype=np.float32),
                np.asarray(member["stats"][key]["scale"], dtype=np.float32),
            )
            for key in SET_KEYS
        }
        members.append((model, stats))
    if not members:
        raise ValueError("policy model directory contains no ensemble members")
    return members, metadata


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


def allocator_budget_curve(
    examples: list[dict[str, Any]], scores: list[list[float]],
) -> list[dict[str, Any]]:
    """Audit incumbent-plus-ranked-candidate terminal rollout budgets."""
    max_candidates = max(len(row["candidate_ids"]) for row in examples)
    intervention_total = sum(
        row["selected_index"] != row["incumbent_index"] for row in examples
    )
    points = []
    for budget in range(1, max_candidates + 1):
        selected_found = 0
        intervention_found = 0
        uniform_intervention_recall = 0.0
        times = []
        fractions = []
        for row, row_scores in zip(examples, scores):
            incumbent = row["incumbent_index"]
            alternatives = sorted(
                (
                    index for index in range(len(row_scores))
                    if index != incumbent
                ),
                key=lambda index: row_scores[index],
                reverse=True,
            )
            chosen = [incumbent] + alternatives[:max(0, budget - 1)]
            found = row["selected_index"] in chosen
            selected_found += int(found)
            is_intervention = row["selected_index"] != incumbent
            intervention_found += int(is_intervention and found)
            if is_intervention:
                uniform_intervention_recall += min(
                    1.0,
                    max(0, budget - 1) / max(1, len(alternatives)),
                )
            total_work = max(1e-9, sum(row["candidate_work"]))
            fraction = sum(row["candidate_work"][i] for i in chosen) / total_work
            fractions.append(fraction)
            terminal_seconds = max(
                0.0, row["full_seconds"] - row["shallow_seconds"]
            )
            times.append(row["shallow_seconds"] + terminal_seconds * fraction)
        points.append({
            "candidate_budget": budget,
            "selected_action_recall": selected_found / len(examples),
            "intervention_action_recall": (
                intervention_found / intervention_total
                if intervention_total else None
            ),
            "uniform_expected_intervention_recall": (
                uniform_intervention_recall / intervention_total
                if intervention_total else None
            ),
            "mean_terminal_branch_fraction": float(np.mean(fractions)),
            "estimated_mean_seconds": float(np.mean(times)),
            "estimated_p95_seconds": _percentile(times, 0.95),
            "estimated_max_seconds": float(max(times)),
            "estimated_within_10s_rate": float(
                np.mean(np.asarray(times) <= 10.0)
            ),
        })
    return points


def run_allocator_oof(
    torch, examples: list[dict[str, Any]], *, folds: int,
    ensemble_size: int, epochs: int, dim: int, seed: int, repeats: int,
) -> dict[str, Any]:
    groups = [row["group"] for row in examples]
    labels = [row["label"] for row in examples]
    accumulated = [
        np.zeros(len(row["candidate_ids"]), dtype=np.float32)
        for row in examples
    ]
    for repeat in range(repeats):
        repeat_seed = seed + 50_000 + repeat * 10_000
        fold_groups = group_folds(
            groups, folds, repeat_seed, labels=labels
        )
        for fold, held_groups in enumerate(fold_groups):
            train = [
                row for row in examples if row["group"] not in held_groups
            ]
            held_indices = [
                index for index, row in enumerate(examples)
                if row["group"] in held_groups
            ]
            held = [examples[index] for index in held_indices]
            members = [
                fit_allocator_member(
                    torch, train,
                    seed=repeat_seed + fold * 100 + member,
                    epochs=epochs, dim=dim,
                )
                for member in range(ensemble_size)
            ]
            predictions = predict_allocator(torch, members, held)
            for index, prediction in zip(held_indices, predictions):
                accumulated[index] += np.asarray(prediction, dtype=np.float32)
    scores = [list(map(float, values / repeats)) for values in accumulated]
    top1 = sum(
        int(np.argmax(row_scores) == row["selected_index"])
        for row, row_scores in zip(examples, scores)
    ) / len(examples)
    intervention_rows = [
        index for index, row in enumerate(examples)
        if row["selected_index"] != row["incumbent_index"]
    ]
    alternative_top1 = sum(
        int(max(
            (
                candidate for candidate in range(len(scores[index]))
                if candidate != examples[index]["incumbent_index"]
            ),
            key=lambda candidate: scores[index][candidate],
        ) == examples[index]["selected_index"])
        for index in intervention_rows
    ) / max(1, len(intervention_rows))
    return {
        "contract": "rollout_candidate_allocator_group_oof_v1",
        "target": "terminal_oracle_selected_candidate",
        "top1_selected_action_accuracy": top1,
        "intervention_alternative_top1_recall": alternative_top1,
        "budget_curve": allocator_budget_curve(examples, scores),
        "oof_rows": [
            {
                "root_id": row["root_id"],
                "group": row["group"],
                "candidate_ids": row["candidate_ids"],
                "candidate_scores": row_scores,
                "incumbent_index": row["incumbent_index"],
                "selected_index": row["selected_index"],
            }
            for row, row_scores in zip(examples, scores)
        ],
    }


def preference_decisions(
    examples: list[dict[str, Any]], probabilities: list[list[float]],
    *, threshold: float = 0.5,
) -> dict[str, Any]:
    """Score the executable rule: keep incumbent unless a clear winner."""
    executed_agreement = 0
    intervention_rows = 0
    intervention_hits = 0
    quiet_rows = 0
    false_switches = 0
    for row, probs in zip(examples, probabilities):
        incumbent = row["incumbent_index"]
        alternates = [
            position for position in range(len(probs))
            if position != incumbent
        ]
        best = max(alternates, key=lambda p: probs[p]) if alternates \
            else incumbent
        chosen = best if alternates and probs[best] > threshold \
            else incumbent
        if chosen == row["selected_index"]:
            executed_agreement += 1
        if row["selected_index"] != incumbent:
            intervention_rows += 1
            intervention_hits += int(chosen == row["selected_index"])
        else:
            quiet_rows += 1
            false_switches += int(chosen != incumbent)
    return {
        "threshold": threshold,
        "executed_selection_agreement": executed_agreement / len(examples),
        "intervention_rows": intervention_rows,
        "intervention_action_recall": (
            intervention_hits / intervention_rows
            if intervention_rows else None
        ),
        "quiet_rows": quiet_rows,
        "false_switch_rate": (
            false_switches / quiet_rows if quiet_rows else None
        ),
    }


def run_preference_oof(
    torch, examples: list[dict[str, Any]], *, folds: int,
    ensemble_size: int, epochs: int, dim: int, seed: int, repeats: int,
) -> dict[str, Any]:
    groups = [row["group"] for row in examples]
    labels = [row["label"] for row in examples]
    accumulated = [
        np.zeros(len(row["candidate_ids"]), dtype=np.float32)
        for row in examples
    ]
    for repeat in range(repeats):
        repeat_seed = seed + 70_000 + repeat * 10_000
        fold_groups = group_folds(groups, folds, repeat_seed, labels=labels)
        for fold, held_groups in enumerate(fold_groups):
            train = [
                row for row in examples if row["group"] not in held_groups
            ]
            held_indices = [
                index for index, row in enumerate(examples)
                if row["group"] in held_groups
            ]
            held = [examples[index] for index in held_indices]
            members = [
                fit_preference_member(
                    torch, train,
                    seed=repeat_seed + fold * 100 + member,
                    epochs=epochs, dim=dim,
                )
                for member in range(ensemble_size)
            ]
            predictions = predict_preference(torch, members, held)
            for index, prediction in zip(held_indices, predictions):
                accumulated[index] += np.asarray(
                    prediction, dtype=np.float32
                )
    probabilities = [
        list(map(float, values / repeats)) for values in accumulated
    ]
    pair_truth = []
    pair_scores = []
    for row, probs in zip(examples, probabilities):
        for position, value in enumerate(row["pair_labels"]):
            if value >= 0.0:
                pair_truth.append(float(value))
                pair_scores.append(probs[position])
    pair_truth_array = np.asarray(pair_truth, dtype=np.float32)
    pair_scores_array = np.asarray(pair_scores, dtype=np.float32)
    return {
        "contract": "rollout_preference_group_oof_v1",
        "target": "alternate_terminal_dominates_incumbent_terminal",
        "rows": len(examples),
        "groups": len(set(groups)),
        "pairs": len(pair_truth),
        "positive_pairs": int(pair_truth_array.sum()),
        "pair_auc": auc(pair_truth_array, pair_scores_array),
        "pair_average_precision": average_precision(
            pair_truth_array, pair_scores_array
        ),
        "decision_rule": preference_decisions(examples, probabilities),
        "oof_rows": [
            {
                "root_id": row["root_id"],
                "group": row["group"],
                "candidate_ids": row["candidate_ids"],
                "incumbent_index": row["incumbent_index"],
                "selected_index": row["selected_index"],
                "pair_labels": row["pair_labels"],
                "preference_probabilities": probs,
            }
            for row, probs in zip(examples, probabilities)
        ],
    }


def run_oof(
    torch, examples: list[dict[str, Any]], *, folds: int,
    ensemble_size: int, epochs: int, dim: int, seed: int, repeats: int = 1,
) -> dict[str, Any]:
    if repeats < 1:
        raise ValueError("repeats must be positive")
    groups = [row["group"] for row in examples]
    labels_list = [row["label"] for row in examples]
    repeated_scores = np.zeros((repeats, len(examples)), dtype=np.float32)
    fold_reports = []
    for repeat in range(repeats):
        repeat_seed = seed + repeat * 10_000
        fold_groups = group_folds(
            groups, folds, repeat_seed, labels=labels_list
        )
        for fold, held_groups in enumerate(fold_groups):
            train = [
                row for row in examples if row["group"] not in held_groups
            ]
            held_indices = [
                index for index, row in enumerate(examples)
                if row["group"] in held_groups
            ]
            held = [examples[index] for index in held_indices]
            members = [
                fit_member(
                    torch, train,
                    seed=repeat_seed + fold * 100 + member,
                    epochs=epochs, dim=dim,
                )
                for member in range(ensemble_size)
            ]
            held_scores = predict(torch, members, held)
            repeated_scores[repeat, held_indices] = held_scores
            held_labels = np.asarray([row["label"] for row in held])
            fold_reports.append({
                "repeat": repeat,
                "fold": fold,
                "held_groups": sorted(held_groups),
                "rows": len(held),
                "positives": int(held_labels.sum()),
                "auc": auc(held_labels, held_scores),
                "average_precision": average_precision(
                    held_labels, held_scores
                ),
            })
    scores = repeated_scores.mean(axis=0)
    score_std = repeated_scores.std(axis=0)
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
        "repeated_group_cv": repeats,
        "auc": auc(labels, scores),
        "average_precision": average_precision(labels, scores),
        "folds": fold_reports,
        "operating_points": select_operating_points(curve),
        "oof_rows": [
            {
                "root_id": row["root_id"], "group": row["group"],
                "label": row["label"], "score": float(scores[index]),
                "score_repeat_std": float(score_std[index]),
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
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--dim", type=int, default=48)
    parser.add_argument("--seed", type=int, default=20260825)
    parser.add_argument(
        "--candidate-feature-mode", choices=("h1", "geometry"),
        default="h1",
    )
    parser.add_argument(
        "--objective", choices=("allocator", "preference"),
        default="allocator",
        help=(
            "allocator: imitate the search's selected action;"
            " preference: learn P(alternate beats incumbent) from"
            " terminal dominance and keep the incumbent by default"
        ),
    )
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument(
        "--save-model-dir", type=pathlib.Path, default=None,
        help=(
            "freeze the deployable allocator ensemble (trained on all"
            " examples) into this directory"
        ),
    )
    args = parser.parse_args()
    import torch

    torch.set_num_threads(4)
    examples, feature_contract = load_examples(
        args.dataset, args.dataset_root,
        candidate_feature_mode=args.candidate_feature_mode,
    )
    if args.objective == "preference":
        result = run_preference_oof(
            torch, examples, folds=args.folds,
            ensemble_size=args.ensemble_size, epochs=args.epochs,
            dim=args.dim, seed=args.seed, repeats=args.repeats,
        )
    else:
        result = run_oof(
            torch, examples, folds=args.folds,
            ensemble_size=args.ensemble_size, epochs=args.epochs,
            dim=args.dim, seed=args.seed, repeats=args.repeats,
        )
        result["candidate_allocator"] = run_allocator_oof(
            torch, examples, folds=args.folds,
            ensemble_size=args.ensemble_size, epochs=args.epochs,
            dim=args.dim, seed=args.seed, repeats=args.repeats,
        )
    result["feature_contract"] = feature_contract
    result["evaluation_scope"] = (
        "development group-OOF; threshold still needs a fresh cohort gate"
    )
    if args.save_model_dir is not None:
        result["policy_model"] = save_allocator_ensemble(
            torch, examples, feature_contract, args.save_model_dir,
            ensemble_size=args.ensemble_size, epochs=args.epochs,
            dim=args.dim, seed=args.seed, objective=args.objective,
        )
        result["policy_model"]["saved_to"] = str(args.save_model_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.objective == "preference":
        print(json.dumps({
            key: result[key] for key in (
                "rows", "groups", "pairs", "positive_pairs", "pair_auc",
                "pair_average_precision", "decision_rule",
            )
        }, ensure_ascii=False))
    else:
        print(json.dumps({
            key: result[key] for key in (
                "rows", "groups", "positives", "auc", "average_precision",
                "operating_points",
            )
        } | {
            "candidate_allocator": {
                key: result["candidate_allocator"][key]
                for key in (
                    "top1_selected_action_accuracy",
                    "intervention_alternative_top1_recall",
                    "budget_curve",
                )
            }
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
