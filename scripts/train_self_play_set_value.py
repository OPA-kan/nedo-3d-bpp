"""Train a masked multi-head Set Transformer ensemble for V^pi_behavior.

The learner consumes only the observed set tensors and game features.  Its
targets are played-state suffix outcomes under the recorded behavior policy;
they are explicitly not V* and branch root-to-leaf gains are never accepted as
leaf-value labels.  Independent group-bootstrap members expose epistemic
variance per head.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import random
from typing import Any

import numpy as np


DATASET_SEMANTICS = "V^pi_behavior_observed_suffix_not_V_star"
MODEL_SEMANTICS = "V^pi_behavior_not_V_star"
GAME_FEATURES = (
    "player_to_move", "block_length", "handoff_count",
    "container_count", "packed_item_count", "visible_item_count",
)
SET_KEYS = ("container", "packed_item", "visible_item")


def validate_ensemble_size(size: int) -> None:
    if not 3 <= int(size) <= 5:
        raise ValueError("epistemic ensemble size must be between 3 and 5")


def _numeric_head_value(head: Any) -> float | None:
    if not isinstance(head, dict) or not head.get("target_eligible"):
        return None
    value = head.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def prepare_examples(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    eligible = [row for row in rows if row.get("value_target_eligible")]
    if not eligible:
        raise ValueError("no eligible played-state suffix value rows")
    if any(
        row.get("value_target_semantics") != DATASET_SEMANTICS
        for row in eligible
    ):
        raise ValueError(
            "Set value training requires explicit behavior-policy value "
            "semantics, never V* or branch-gain labels"
        )
    head_names = sorted({
        name
        for row in eligible
        for name, head in (row.get("value_heads") or {}).items()
        if _numeric_head_value(head) is not None
    })
    head_names = ["return_to_go", *head_names]
    examples = []
    feature_contract = None
    for row in eligible:
        state = row["state"]
        current_contract = {
            f"{key}_features": list(state[f"{key}_features"])
            for key in SET_KEYS
        }
        if feature_contract is None:
            feature_contract = current_contract
        elif current_contract != feature_contract:
            raise ValueError("state tensor feature contracts differ across rows")
        values = [float(row["return_to_go"])]
        mask = [True]
        heads = row.get("value_heads") or {}
        for name in head_names[1:]:
            value = _numeric_head_value(heads.get(name))
            values.append(0.0 if value is None else value)
            mask.append(value is not None)
        game = row["game_features"]
        set_values = {
            key: [
                list(map(float, token))
                for token in state[f"{key}_values"]
            ]
            for key in SET_KEYS
        }
        examples.append({
            "group": str(row.get("split_group") or row["trajectory_group"]),
            "game": [
                float(game[name]) for name in GAME_FEATURES[:3]
            ] + [float(len(set_values[key])) for key in SET_KEYS],
            **set_values,
            "targets": values,
            "target_mask": mask,
        })
    groups = sorted({example["group"] for example in examples})
    if len(groups) < 2:
        raise ValueError("group-held-out value training needs at least two groups")
    return examples, {
        "schema_version": 1,
        "semantics": MODEL_SEMANTICS,
        "source_semantics": DATASET_SEMANTICS,
        "head_names": head_names,
        "game_features": list(GAME_FEATURES),
        "set_features": feature_contract,
        "split_unit": "whole_trajectory_group",
        "groups": len(groups),
        "rows": len(examples),
    }


def group_folds(groups: list[str], folds: int, seed: int) -> list[set[str]]:
    if len(groups) < 2:
        raise ValueError("at least two groups are required")
    count = min(max(2, int(folds)), len(groups))
    shuffled = list(sorted(groups))
    random.Random(seed).shuffle(shuffled)
    result = [set() for _ in range(count)]
    for index, group in enumerate(shuffled):
        result[index % count].add(group)
    return result


def _stats(
    examples: list[dict[str, Any]], contract: dict[str, Any],
) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    game = np.asarray([row["game"] for row in examples], dtype=np.float32)
    stats["game"] = _mean_scale(game)
    for key in SET_KEYS:
        tokens = [token for row in examples for token in row[key]]
        if not tokens:
            width = len(contract["set_features"][f"{key}_features"])
            tokens = [[0.0] * width]
        stats[key] = _mean_scale(np.asarray(tokens, dtype=np.float32))
    targets = np.asarray([row["targets"] for row in examples], dtype=np.float32)
    mask = np.asarray([row["target_mask"] for row in examples], dtype=bool)
    means, scales = [], []
    for head in range(targets.shape[1]):
        observed = targets[mask[:, head], head]
        if not len(observed):
            means.append(0.0)
            scales.append(1.0)
        else:
            means.append(float(observed.mean()))
            spread = float(observed.std())
            scales.append(spread if spread > 1e-6 else 1.0)
    stats["targets"] = (np.asarray(means), np.asarray(scales))
    return stats


def _mean_scale(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mean = values.mean(axis=0)
    scale = values.std(axis=0)
    scale[scale < 1e-6] = 1.0
    return mean, scale


def _pad_set(
    examples: list[dict[str, Any]], key: str, width: int,
    mean: np.ndarray, scale: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    longest = max(1, max(len(row[key]) for row in examples))
    values = np.zeros((len(examples), longest, width), dtype=np.float32)
    mask = np.ones((len(examples), longest), dtype=bool)
    for index, row in enumerate(examples):
        tokens = np.asarray(row[key], dtype=np.float32)
        if len(tokens):
            values[index, :len(tokens)] = (tokens - mean) / scale
            mask[index, :len(tokens)] = False
        else:
            # A visible sentinel avoids all-masked attention NaNs while
            # carrying no state information after normalization.
            values[index, 0] = 0.0
            mask[index, 0] = False
    return values, mask


def _arrays(
    examples: list[dict[str, Any]], contract: dict[str, Any],
    stats: dict[str, Any],
) -> dict[str, np.ndarray]:
    result: dict[str, np.ndarray] = {}
    game = np.asarray([row["game"] for row in examples], dtype=np.float32)
    result["game"] = (game - stats["game"][0]) / stats["game"][1]
    for key in SET_KEYS:
        width = len(contract["set_features"][f"{key}_features"])
        values, mask = _pad_set(
            examples, key, width, stats[key][0], stats[key][1]
        )
        result[key] = values
        result[f"{key}_mask"] = mask
    targets = np.asarray([row["targets"] for row in examples], dtype=np.float32)
    result["targets"] = (
        targets - stats["targets"][0]
    ) / stats["targets"][1]
    result["target_mask"] = np.asarray(
        [row["target_mask"] for row in examples], dtype=bool
    )
    return result


def build_model(torch, contract: dict[str, Any], *, dim: int = 64):
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
            pooled, _ = self.pool(
                query, state, state, key_padding_mask=mask
            )
            return pooled.squeeze(1)

    class MultiHeadSetValue(nn.Module):
        def __init__(self):
            super().__init__()
            self.encoders = nn.ModuleDict({
                key: SetEncoder(len(
                    contract["set_features"][f"{key}_features"]
                ))
                for key in SET_KEYS
            })
            self.game = nn.Sequential(
                nn.Linear(len(GAME_FEATURES), dim), nn.GELU()
            )
            self.trunk = nn.Sequential(
                nn.Linear(4 * dim, 2 * dim), nn.GELU(),
                nn.Dropout(0.1), nn.Linear(2 * dim, dim), nn.GELU(),
            )
            self.heads = nn.ModuleList([
                nn.Linear(dim, 1) for _ in contract["head_names"]
            ])

        def forward(self, batch):
            blocks = [
                self.encoders[key](batch[key], batch[f"{key}_mask"])
                for key in SET_KEYS
            ]
            blocks.append(self.game(batch["game"]))
            state = self.trunk(torch.cat(blocks, dim=-1))
            return torch.cat([head(state) for head in self.heads], dim=1)

    return MultiHeadSetValue()


def _torch_batch(torch, arrays: dict[str, np.ndarray]) -> dict[str, Any]:
    result = {}
    for key, value in arrays.items():
        if key.endswith("_mask"):
            result[key] = torch.as_tensor(value, dtype=torch.bool)
        else:
            result[key] = torch.as_tensor(value, dtype=torch.float32)
    return result


def _bootstrap_groups(
    examples: list[dict[str, Any]], seed: int,
) -> list[dict[str, Any]]:
    groups = sorted({row["group"] for row in examples})
    rng = random.Random(seed)
    sampled = [rng.choice(groups) for _ in groups]
    by_group = {
        group: [row for row in examples if row["group"] == group]
        for group in groups
    }
    return [row for group in sampled for row in by_group[group]]


def fit_member(
    torch, train: list[dict[str, Any]], test: list[dict[str, Any]],
    contract: dict[str, Any], *, seed: int, epochs: int,
):
    torch.manual_seed(seed)
    bootstrap = _bootstrap_groups(train, seed)
    stats = _stats(bootstrap, contract)
    train_batch = _torch_batch(torch, _arrays(bootstrap, contract, stats))
    test_batch = _torch_batch(torch, _arrays(test, contract, stats))
    model = build_model(torch, contract)
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    model.train()
    for _ in range(epochs):
        optimizer.zero_grad()
        predicted = model(train_batch)
        mask = train_batch["target_mask"]
        loss = ((predicted - train_batch["targets"]) ** 2)[mask].mean()
        loss.backward()
        optimizer.step()
    model.eval()
    with torch.no_grad():
        normalized = model(test_batch).cpu().numpy()
    raw = normalized * stats["targets"][1] + stats["targets"][0]
    return raw, model, stats


def _metric(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    error = predicted - actual
    pearson = (
        float(np.corrcoef(actual, predicted)[0, 1])
        if len(actual) > 1 and np.std(actual) > 0 and np.std(predicted) > 0
        else 0.0
    )
    return {
        "rmse": float(math.sqrt(np.mean(error * error))),
        "mae": float(np.mean(np.abs(error))),
        "pearson": pearson,
    }


def run_grouped_audit(
    examples: list[dict[str, Any]], contract: dict[str, Any], *,
    ensemble_size: int, epochs: int, folds: int, seed: int,
    oof_output_dir: pathlib.Path | None = None,
) -> dict[str, Any]:
    import torch

    validate_ensemble_size(ensemble_size)
    torch.set_num_threads(4)
    groups = sorted({row["group"] for row in examples})
    split = group_folds(groups, folds, seed)
    predictions = np.zeros(
        (len(examples), ensemble_size, len(contract["head_names"])),
        dtype=np.float64,
    )
    constants = np.zeros((len(examples), len(contract["head_names"])))
    group_excluded_ensembles = []
    for fold_index, test_groups in enumerate(split):
        test_indexes = [
            i for i, row in enumerate(examples) if row["group"] in test_groups
        ]
        train = [row for row in examples if row["group"] not in test_groups]
        test = [examples[i] for i in test_indexes]
        train_targets = np.asarray([row["targets"] for row in train])
        train_mask = np.asarray([row["target_mask"] for row in train], dtype=bool)
        for head in range(train_targets.shape[1]):
            observed = train_targets[train_mask[:, head], head]
            constants[test_indexes, head] = observed.mean() if len(observed) else 0.0
        fold_members = []
        for member in range(ensemble_size):
            raw, model, stats_block = fit_member(
                torch, train, test, contract,
                seed=seed + 1000 * fold_index + member,
                epochs=epochs,
            )
            predictions[test_indexes, member] = raw
            if oof_output_dir is not None:
                path = (
                    oof_output_dir / "oof" / f"fold-{fold_index:02d}"
                    / f"member-{member:02d}.pt"
                )
                _save_checkpoint(torch, path, model, contract, stats_block)
                fold_members.append({
                    "member": member,
                    "path": path.relative_to(oof_output_dir).as_posix(),
                    "seed": seed + 1000 * fold_index + member,
                })
        if oof_output_dir is not None:
            group_excluded_ensembles.append({
                "fold": fold_index,
                "excluded_groups": sorted(test_groups),
                "members": fold_members,
            })
    actual = np.asarray([row["targets"] for row in examples], dtype=float)
    mask = np.asarray([row["target_mask"] for row in examples], dtype=bool)
    mean = predictions.mean(axis=1)
    variance = predictions.var(axis=1)
    heads = {}
    for index, name in enumerate(contract["head_names"]):
        observed = mask[:, index]
        heads[name] = {
            "eligible_rows": int(observed.sum()),
            "ensemble": _metric(actual[observed, index], mean[observed, index]),
            "constant": _metric(
                actual[observed, index], constants[observed, index]
            ),
            "mean_epistemic_variance": float(
                variance[observed, index].mean()
            ) if np.any(observed) else None,
        }
    return {
        "schema_version": 1,
        "contract": contract,
        "protocol": "whole_trajectory_group_k_fold",
        "folds": len(split),
        "ensemble_size": ensemble_size,
        "epochs": epochs,
        "epistemic_uncertainty": "per_head_variance_across_group_bootstrap_members",
        "group_excluded_ensembles": group_excluded_ensembles,
        "heads": heads,
        "deployment_ready": False,
    }


def _json_stats(stats: dict[str, Any]) -> dict[str, Any]:
    return {
        key: [part.tolist() for part in value]
        for key, value in stats.items()
    }


def _save_checkpoint(torch, path, model, contract, stats) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "schema_version": 1,
        "contract": contract,
        "stats": _json_stats(stats),
        "state_dict": model.state_dict(),
    }, path)


def train_final_ensemble(
    examples: list[dict[str, Any]], contract: dict[str, Any], *,
    ensemble_size: int, epochs: int, seed: int, output_dir: pathlib.Path,
) -> list[dict[str, Any]]:
    import torch

    output_dir.mkdir(parents=True, exist_ok=True)
    members = []
    for member in range(ensemble_size):
        _raw, model, stats = fit_member(
            torch, examples, examples, contract,
            seed=seed + member, epochs=epochs,
        )
        path = output_dir / f"member-{member:02d}.pt"
        _save_checkpoint(torch, path, model, contract, stats)
        members.append({"member": member, "path": path.name, "seed": seed + member})
    return members


def _load_checkpoint(torch, path: pathlib.Path) -> dict[str, Any]:
    """Load our tensor-and-primitive checkpoint without accepting code."""
    try:
        return torch.load(path, map_location="cpu", weights_only=True)
    except TypeError:  # torch < 2.0 has no weights_only argument.
        return torch.load(path, map_location="cpu")


def _restore_stats(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: tuple(np.asarray(part, dtype=np.float32) for part in value)
        for key, value in payload.items()
    }


def example_from_state(
    state: dict[str, Any], game_state: Any,
) -> dict[str, Any]:
    """Build one inference example using the exact training feature contract."""
    set_values = {
        key: [
            list(map(float, token))
            for token in state[f"{key}_values"]
        ]
        for key in SET_KEYS
    }
    aliases = {"player_to_move": "current_player"}
    if isinstance(game_state, dict):
        def read(name):
            return game_state.get(name, game_state.get(aliases.get(name, name)))
    else:
        def read(name):
            return getattr(game_state, name, getattr(
                game_state, aliases.get(name, name), None
            ))
    return {
        "group": "inference",
        "game": [
            float(read(name)) for name in GAME_FEATURES[:3]
        ] + [float(len(set_values[key])) for key in SET_KEYS],
        **set_values,
        # _arrays also prepares targets. These placeholders are never read by
        # inference, but keeping one path prevents train/serve skew.
        "targets": [],
        "target_mask": [],
    }


def select_ensemble_members(
    manifest: dict[str, Any], excluded_group: str | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    if excluded_group is None:
        return list(manifest.get("members", [])), []
    matches = [
        fold for fold in manifest.get("group_excluded_ensembles", [])
        if excluded_group in fold.get("excluded_groups", [])
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected one group-excluded ensemble for {excluded_group}, "
            f"found {len(matches)}"
        )
    return list(matches[0]["members"]), list(matches[0]["excluded_groups"])


class BehaviorValueEnsemble:
    """CPU inference for the frozen multi-head V^pi_behavior ensemble."""

    def __init__(
        self, model_dir: pathlib.Path, *, excluded_group: str | None = None,
    ):
        import torch

        self.torch = torch
        self.model_dir = pathlib.Path(model_dir)
        manifest = json.loads(
            (self.model_dir / "manifest.json").read_text(encoding="utf-8")
        )
        if manifest.get("semantics") != MODEL_SEMANTICS:
            raise ValueError("leaf model is not an explicit V^pi_behavior model")
        member_records, excluded_groups = select_ensemble_members(
            manifest, excluded_group
        )
        validate_ensemble_size(len(member_records))
        self.excluded_groups = excluded_groups
        self.members = []
        self.contract = None
        for member in member_records:
            checkpoint = _load_checkpoint(
                torch, self.model_dir / str(member["path"])
            )
            contract = checkpoint["contract"]
            if contract.get("semantics") != MODEL_SEMANTICS:
                raise ValueError("checkpoint semantics do not match V^pi_behavior")
            if self.contract is None:
                self.contract = contract
            elif contract != self.contract:
                raise ValueError("ensemble checkpoint contracts differ")
            model = build_model(torch, contract)
            model.load_state_dict(checkpoint["state_dict"])
            model.eval()
            self.members.append((model, _restore_stats(checkpoint["stats"])))
        self.head_names = list(self.contract["head_names"])

    def predict(
        self, state: dict[str, Any], game_state: Any,
    ) -> dict[str, dict[str, Any]]:
        example = example_from_state(state, game_state)
        predictions = []
        with self.torch.no_grad():
            for model, stats in self.members:
                prepared = dict(example)
                prepared["targets"] = [0.0] * len(self.head_names)
                prepared["target_mask"] = [False] * len(self.head_names)
                batch = _torch_batch(
                    self.torch,
                    _arrays([prepared], self.contract, stats),
                )
                normalized = model(batch).cpu().numpy()[0]
                raw = (
                    normalized * stats["targets"][1]
                    + stats["targets"][0]
                )
                predictions.append(raw)
        values = np.asarray(predictions, dtype=np.float64)
        return {
            name: {
                "mean": float(values[:, index].mean()),
                "variance": float(values[:, index].var()),
                "members": [float(value) for value in values[:, index]],
            }
            for index, name in enumerate(self.head_names)
        }


class PlayerZeroLeafValue:
    """Adapt player-to-move return predictions to PUCT's player-0 contract."""

    def __init__(self, ensemble: BehaviorValueEnsemble, *, value_scale: float):
        if value_scale <= 0.0:
            raise ValueError("value_scale must be positive")
        self.ensemble = ensemble
        self.value_scale = float(value_scale)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, *, env, observation, state) -> float:
        # Build the same physical snapshot/tensor used by the training dataset.
        from scripts.build_replay_dataset import policy_observation, state_snapshot
        from scripts.counterfactual_graph import state_tensor_from_snapshot

        snapshot = state_snapshot(
            env, policy_observation(env, observation),
            case_id="leaf-value-shadow", step=int(state.placements),
        )
        prediction = self.ensemble.predict(
            state_tensor_from_snapshot(snapshot), state
        )
        player_value = float(prediction["return_to_go"]["mean"])
        sign = 1.0 if int(state.current_player) == 0 else -1.0
        player_zero_raw = sign * player_value
        normalized = max(
            -1.0, min(1.0, player_zero_raw / self.value_scale)
        )
        self.calls.append({
            "player_to_move": int(state.current_player),
            "return_to_go_player_to_move": prediction["return_to_go"],
            "return_to_go_player0_mean": player_zero_raw,
            "normalized_player0_value": normalized,
            "heads": prediction,
        })
        return normalized


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=pathlib.Path, required=True)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--ensemble-size", type=int, default=3)
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260823)
    args = parser.parse_args()
    validate_ensemble_size(args.ensemble_size)
    with args.dataset.open("r", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    examples, contract = prepare_examples(rows)
    audit = run_grouped_audit(
        examples, contract, ensemble_size=args.ensemble_size,
        epochs=args.epochs, folds=args.folds, seed=args.seed,
        oof_output_dir=args.output_dir,
    )
    members = train_final_ensemble(
        examples, contract, ensemble_size=args.ensemble_size,
        epochs=args.epochs, seed=args.seed, output_dir=args.output_dir,
    )
    manifest = {
        "schema_version": 1,
        "model": "multi_head_set_transformer_ensemble",
        "semantics": MODEL_SEMANTICS,
        "members": members,
        "group_excluded_ensembles": audit["group_excluded_ensembles"],
        "audit": audit,
        "deployment_ready": False,
        "next_gate": "fixed_support_H2_plus_V_vs_H2_plus_zero",
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output_dir / "manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
