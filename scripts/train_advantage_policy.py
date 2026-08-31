"""Distil a policy from logged episodes with the PCT learning signal.

The architecture is unchanged -- the same set transformer over the same
geometry candidate tokens the incumbent champion uses -- and so is the
saved artifact format. **Only the loss changes**, from "which of these
two candidates strictly dominates on four heads" to "how good was the
return this action actually led to, against what the other horses got
from the same step".

Why that is the whole point: Cup 009 distilled 156 strict pairs out of
episodes holding about 1500 decisions, because a pair needs two genuine
terminals and a strict 4-head dominance. Under an advantage signal every
decision teaches, and a rollout that stopped early is not a problem --
its return is simply the fill it did achieve.

Evaluation is leave-one-cell-out, and the metric is deliberately NOT
agreement with the logged action (that would reward copying the
behaviour policies, which is what we are trying to beat). It is the
**shared-board comparison**: within a held-out cell, group decisions by
`board_fingerprint`; where two horses took different actions from the
identical board, the better model is the one that scores the action
with the higher realised return above the other. That is a genuine
preference test computed entirely from logged returns, and the
incumbent champion is scored on exactly the same comparisons.
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

from scripts.counterfactual_graph import (  # noqa: E402
    ITEM_TENSOR_FEATURES,
    state_tensor_from_snapshot,
)
from scripts.train_rollout_trigger import (  # noqa: E402
    SET_KEYS,
    build_arrays,
    candidate_features,
    candidate_token,
    compute_stats,
    fit_advantage_member,
    predict_allocator,
    save_allocator_ensemble,
)

FEATURE_MODE = "geometry"


def _example(row: dict[str, Any]) -> dict[str, Any] | None:
    snapshot = json.loads(
        pathlib.Path(row["snapshot_path"]).read_text(encoding="utf-8")
    )
    state = state_tensor_from_snapshot(snapshot)
    visible = dict(zip(
        state["visible_item_indices"], state["visible_item_values"]
    ))
    tokens = []
    ids = []
    for candidate in row["candidates"]:
        item_values = visible.get(
            int(candidate.get("stable_item_index", -1)),
            [0.0] * len(ITEM_TENSOR_FEATURES),
        )
        token = candidate_token(
            FEATURE_MODE, snapshot, candidate, list(item_values),
            incumbent=False,
        )
        if token is None:
            continue
        tokens.append(token)
        ids.append(str(candidate["root_candidate_id"]))
    if len(tokens) < 2 or row["selected_candidate_id"] not in ids:
        return None
    return {
        "group": str(row["cell"]),
        "root_id": str(row["root_id"]),
        "board_fingerprint": row.get("board_fingerprint"),
        "horse": row["horse"],
        "step": int(row["step"]),
        "container": state["container_values"],
        "packed_item": state["packed_item_values"],
        "visible_item": state["visible_item_values"],
        "candidate": tokens,
        "candidate_ids": ids,
        "selected_index": ids.index(row["selected_candidate_id"]),
        "incumbent_index": 0,
        "label": 0.0,
        "advantage": float(row["advantage"]),
        "return": float(row["return"]),
    }


def load_examples(dataset_path: pathlib.Path) -> list[dict[str, Any]]:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    if dataset.get("contract") != "advantage_policy_dataset_v1":
        raise ValueError("unsupported advantage dataset contract")
    examples = [example for row in dataset["rows"]
                if (example := _example(row)) is not None]
    if len({row["group"] for row in examples}) < 2:
        raise ValueError("leave-one-cell-out needs at least two cells")
    return examples


def attach_weights(
    examples: list[dict[str, Any]], *, beta: float | None, clip: float,
) -> float:
    """w = clip(exp(A / beta)), beta defaulting to the corpus advantage std.

    Normalising by the corpus spread keeps the weights scale-free, so the
    same clip means the same thing whether the fills are 3 points apart
    or 30.
    """
    advantages = np.asarray(
        [row["advantage"] for row in examples], dtype=np.float64
    )
    scale = beta if beta else float(advantages.std()) or 1.0
    for row, advantage in zip(examples, advantages):
        row["advantage_weight"] = float(
            min(clip, math.exp(advantage / scale))
        )
    return scale


def shared_board_pairs(
    examples: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Decisions from an identical board where two horses differed.

    Same board, same candidate set, different chosen action, different
    realised return: the one comparison in this corpus where a logged
    return says which of two available actions was better.
    """
    by_board: dict[Any, list[dict[str, Any]]] = {}
    for row in examples:
        by_board.setdefault(row["board_fingerprint"], []).append(row)
    pairs = []
    for rows in by_board.values():
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                left, right = rows[i], rows[j]
                if left["selected_index"] == right["selected_index"]:
                    continue
                if left["candidate_ids"] != right["candidate_ids"]:
                    continue
                if math.isclose(left["return"], right["return"]):
                    continue
                pairs.append((left, right))
    return pairs


def _scores(torch, members, rows: list[dict[str, Any]]) -> np.ndarray:
    return predict_allocator(torch, members, rows)


def evaluate_pairs(torch, members, pairs) -> dict[str, Any]:
    if not pairs:
        return {"pairs": 0, "accuracy": None}
    correct = 0
    for left, right in pairs:
        scores = _scores(torch, members, [left])[0]
        better, worse = (
            (left, right) if left["return"] > right["return"]
            else (right, left)
        )
        if scores[better["selected_index"]] > scores[worse["selected_index"]]:
            correct += 1
    return {
        "pairs": len(pairs),
        "accuracy": correct / len(pairs),
        "correct": correct,
    }


def leave_one_cell_out(
    torch, examples: list[dict[str, Any]], *, epochs: int, dim: int,
    seed: int, members_per_fold: int,
) -> dict[str, Any]:
    cells = sorted({row["group"] for row in examples})
    folds = []
    for index, cell in enumerate(cells):
        train = [row for row in examples if row["group"] != cell]
        held = [row for row in examples if row["group"] == cell]
        pairs = shared_board_pairs(held)
        if not pairs:
            folds.append({"cell": cell, "pairs": 0, "accuracy": None})
            continue
        members = [
            fit_advantage_member(
                torch, train, seed=seed + 1000 * index + member,
                epochs=epochs, dim=dim,
            )
            for member in range(members_per_fold)
        ]
        result = evaluate_pairs(torch, members, pairs)
        result["cell"] = cell
        folds.append(result)
    scored = [fold for fold in folds if fold.get("pairs")]
    total = sum(fold["pairs"] for fold in scored)
    correct = sum(fold.get("correct", 0) for fold in scored)
    return {
        "folds": folds,
        "cells_with_pairs": len(scored),
        "pairs": total,
        "accuracy": correct / total if total else None,
    }


def evaluate_incumbent(
    torch, model_dir: pathlib.Path, examples: list[dict[str, Any]],
) -> dict[str, Any]:
    """The shipped champion on exactly the same comparisons.

    It never trained on a return, so this is not an unfair test of it --
    it is the question of whether the corpus it did train on taught it
    the same ordering.
    """
    from scripts.train_rollout_trigger import load_allocator_ensemble

    members, metadata = load_allocator_ensemble(torch, model_dir)
    if (metadata.get("feature_contract") or {}).get(
        "candidate_feature_mode"
    ) != FEATURE_MODE:
        raise ValueError(
            "incumbent champion uses a different candidate feature mode;"
            " the two models would not be scored on the same inputs"
        )
    result = evaluate_pairs(torch, members, shared_board_pairs(examples))
    result["model_dir"] = str(model_dir)
    result["objective"] = metadata.get("objective")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=pathlib.Path, required=True)
    parser.add_argument("--report", type=pathlib.Path, required=True)
    parser.add_argument("--model-dir", type=pathlib.Path, default=None)
    parser.add_argument(
        "--incumbent-model-dir", type=pathlib.Path, default=None,
        help="score the shipped champion on the same shared-board pairs",
    )
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--dim", type=int, default=48)
    parser.add_argument("--seed", type=int, default=20260831)
    parser.add_argument("--ensemble-size", type=int, default=3)
    parser.add_argument("--fold-members", type=int, default=1)
    parser.add_argument(
        "--beta", type=float, default=None,
        help="advantage temperature; default is the corpus advantage std",
    )
    parser.add_argument("--weight-clip", type=float, default=20.0)
    parser.add_argument(
        "--uniform-weights", action="store_true",
        help="ablation: w = 1 everywhere, i.e. plain behaviour cloning",
    )
    args = parser.parse_args()

    import torch

    torch.set_num_threads(4)
    examples = load_examples(args.dataset)
    if args.uniform_weights:
        for row in examples:
            row["advantage_weight"] = 1.0
        beta = None
    else:
        beta = attach_weights(
            examples, beta=args.beta, clip=args.weight_clip,
        )
    weights = [row["advantage_weight"] for row in examples]
    report: dict[str, Any] = {
        "contract": "advantage_policy_distillation_v1",
        "examples": len(examples),
        "cells": len({row["group"] for row in examples}),
        "horses": sorted({row["horse"] for row in examples}),
        "uniform_weights": bool(args.uniform_weights),
        "beta": beta,
        "weight_clip": args.weight_clip,
        "weight_mean": float(np.mean(weights)),
        "weight_max": float(np.max(weights)),
        "shared_board_pairs": len(shared_board_pairs(examples)),
        "candidate_features": list(candidate_features(FEATURE_MODE)),
    }
    report["leave_one_cell_out"] = leave_one_cell_out(
        torch, examples, epochs=args.epochs, dim=args.dim, seed=args.seed,
        members_per_fold=args.fold_members,
    )
    if args.incumbent_model_dir is not None:
        report["incumbent"] = evaluate_incumbent(
            torch, args.incumbent_model_dir, examples
        )
    if args.model_dir is not None:
        report["model"] = save_allocator_ensemble(
            torch, examples,
            {
                "contract": "rollout_trigger_set_transformer_v2_candidate_modes",
                "target": "advantage_weighted_logged_action",
                "candidate_feature_mode": FEATURE_MODE,
                "candidate_features": list(candidate_features(FEATURE_MODE)),
                "split_unit": "whole_collection_cell",
            },
            args.model_dir, ensemble_size=args.ensemble_size,
            epochs=args.epochs, dim=args.dim, seed=args.seed,
            objective="advantage",
        )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = {
        key: report[key]
        for key in ("examples", "cells", "shared_board_pairs", "beta",
                    "weight_mean", "weight_max")
    }
    summary["loco"] = {
        key: report["leave_one_cell_out"][key]
        for key in ("cells_with_pairs", "pairs", "accuracy")
    }
    if "incumbent" in report:
        summary["incumbent"] = report["incumbent"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
