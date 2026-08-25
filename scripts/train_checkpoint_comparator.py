"""Learn the checkpoint decision from already-read H<=3 physical prefixes.

The terminal rollout stays the oracle and the label.  In production the
deadline executor has ALREADY paid for both branches' bounded physical
prefixes when it must decide; this comparator consumes exactly that
decision-time information — observed state, candidate action geometry,
and each branch's measured checkpoint vector — and predicts which branch
the terminal oracle selects.  It is a same-budget challenger to the
hand-written checkpoint Pareto rule: identical physics, different
tie-break.  No terminal outcomes, no future information, no extra reads.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_rollout_checkpoints import (  # noqa: E402
    choose_checkpoint_candidate,
)
from scripts.build_terminal_rollout_trigger_dataset import pareto_ids  # noqa: E402
from scripts.train_rollout_trigger import (  # noqa: E402
    CANDIDATE_HEADS,
    fit_allocator_member,
    group_folds,
    load_examples,
    predict_allocator,
)

CHECKPOINT_EXTRA_FEATURES = tuple(
    f"checkpoint_oriented_{name}" for name, _direction in CANDIDATE_HEADS
) + ("checkpoint_continuation_steps", "checkpoint_genuine_terminal")

GENUINE_TERMINATIONS = {
    "stream_exhausted", "no_retained_candidate", "no_safe_retained_candidate",
}


def load_checkpoint_map(
    checkpoint_root: pathlib.Path, *, cap: int,
) -> dict[str, dict[str, dict[str, Any]]]:
    """root_id -> candidate_id -> checkpoint measurement at the given cap."""
    checkpoint_map: dict[str, dict[str, dict[str, Any]]] = {}
    paths = sorted(checkpoint_root.rglob("checkpoint.json"))
    if not paths:
        raise ValueError(f"no checkpoint.json under {checkpoint_root}")
    for path in paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        for root in report.get("roots") or []:
            checkpoint = (root.get("checkpoints") or {}).get(str(cap))
            if checkpoint is None:
                raise ValueError(
                    f"{root.get('root_id')}: missing cap {cap} checkpoint"
                )
            checkpoint_map[str(root["root_id"])] = {
                str(row["root_candidate_id"]): row
                for row in checkpoint.get("candidates") or []
                if row.get("safe")
            }
    return checkpoint_map


def checkpoint_token(row: dict[str, Any]) -> list[float]:
    vector = row.get("checkpoint_vector") or {}
    values = []
    for name, direction in CANDIDATE_HEADS:
        value = vector.get(name)
        if not isinstance(value, (int, float)):
            raise ValueError(f"checkpoint vector missing head {name}")
        values.append(direction * float(value))
    values.append(float(row.get("continuation_steps") or 0))
    values.append(float(row.get("termination") in GENUINE_TERMINATIONS))
    return values


def build_comparator_examples(
    dataset_path: pathlib.Path, dataset_root: pathlib.Path,
    checkpoint_root: pathlib.Path, *, cap: int,
    features: str = "geometry_checkpoint",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if features not in {"geometry_checkpoint", "checkpoint_only"}:
        raise ValueError(f"unsupported feature set: {features}")
    base, contract = load_examples(
        dataset_path, dataset_root, candidate_feature_mode="geometry",
    )
    checkpoint_map = load_checkpoint_map(checkpoint_root, cap=cap)
    examples = []
    for row in base:
        per_candidate = checkpoint_map.get(row["root_id"])
        if per_candidate is None:
            continue
        missing = [
            candidate_id for candidate_id in row["candidate_ids"]
            if candidate_id not in per_candidate
        ]
        if missing:
            raise ValueError(
                f"{row['root_id']}: checkpoint audit lacks {missing[:2]}"
            )
        if features == "geometry_checkpoint":
            tokens = [
                list(token) + checkpoint_token(per_candidate[candidate_id])
                for token, candidate_id in zip(
                    row["candidate"], row["candidate_ids"]
                )
            ]
        else:
            tokens = [
                checkpoint_token(per_candidate[candidate_id])
                + [float(index == row["incumbent_index"])]
                for index, candidate_id in enumerate(row["candidate_ids"])
            ]
        examples.append({**row, "candidate": tokens})
    if not examples:
        raise ValueError("no roots joined between dataset and checkpoints")
    feature_names = (
        list(contract["candidate_features"])
        + list(CHECKPOINT_EXTRA_FEATURES)
        if features == "geometry_checkpoint"
        else list(CHECKPOINT_EXTRA_FEATURES) + ["is_incumbent"]
    )
    contract = {
        **contract,
        "contract": "checkpoint_comparator_set_transformer_v1",
        "target": "terminal_oracle_selected_candidate_given_checkpoints",
        "candidate_feature_mode": f"{features}_h{cap + 1}",
        "candidate_features": feature_names,
        "decision_time_note": (
            "checkpoint vectors are measured before the decision in "
            "production; consuming them adds no physics"
        ),
    }
    return examples, contract


def pareto_rule_choice(
    row: dict[str, Any], per_candidate: dict[str, dict[str, Any]],
    candidate_ids: list[str],
) -> str:
    rows = [
        {
            "root_candidate_id": candidate_id,
            "safe": True,
            "checkpoint_vector": per_candidate[candidate_id].get(
                "checkpoint_vector"
            ),
        }
        for candidate_id in candidate_ids
    ]
    frontier = pareto_ids(rows, "checkpoint_vector")
    return choose_checkpoint_candidate(
        candidate_ids,
        incumbent=row["candidate_ids"][row["incumbent_index"]],
        frontier=frontier,
    )


def decision_comparison(
    examples: list[dict[str, Any]], scores: list[list[float]],
    checkpoint_map: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    """Paired comparator-vs-Pareto decisions on identical checkpoint vectors."""
    results = {}
    for support_name in ("ranker_pair", "full_support"):
        rows = []
        for row, row_scores in zip(examples, scores):
            incumbent = row["candidate_ids"][row["incumbent_index"]]
            selected = row["candidate_ids"][row["selected_index"]]
            if support_name == "ranker_pair":
                alternates = [
                    candidate_id for candidate_id in row["candidate_ids"]
                    if candidate_id != incumbent
                ]
                if not alternates:
                    continue
                support = [incumbent, alternates[0]]
            else:
                support = list(row["candidate_ids"])
            per_candidate = checkpoint_map[row["root_id"]]
            pareto = pareto_rule_choice(row, per_candidate, support)
            learned = max(
                support,
                key=lambda candidate_id: row_scores[
                    row["candidate_ids"].index(candidate_id)
                ],
            )
            rows.append({
                "root_id": row["root_id"],
                "group": row["group"],
                "intervention": selected != incumbent,
                "available": selected in support,
                "pareto_correct": pareto == selected,
                "learned_correct": learned == selected,
            })
        interventions = [row for row in rows if row["intervention"]]
        available = [row for row in interventions if row["available"]]
        keepers = [row for row in rows if not row["intervention"]]
        results[support_name] = {
            "roots": len(rows),
            "interventions": len(interventions),
            "interventions_available": len(available),
            "pareto_conversion": sum(
                row["pareto_correct"] for row in available
            ),
            "learned_conversion": sum(
                row["learned_correct"] for row in available
            ),
            "pareto_keeper_reproduction": sum(
                row["pareto_correct"] for row in keepers
            ),
            "learned_keeper_reproduction": sum(
                row["learned_correct"] for row in keepers
            ),
            "keepers": len(keepers),
            "flips": [
                {
                    "root_id": row["root_id"],
                    "intervention": row["intervention"],
                    "pareto_correct": row["pareto_correct"],
                    "learned_correct": row["learned_correct"],
                }
                for row in rows
                if row["pareto_correct"] != row["learned_correct"]
            ],
        }
    return results


def run_comparator_oof(
    torch, examples: list[dict[str, Any]],
    checkpoint_map: dict[str, dict[str, dict[str, Any]]], *, folds: int,
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
        int(int(np.argmax(row_scores)) == row["selected_index"])
        for row, row_scores in zip(examples, scores)
    ) / len(examples)
    return {
        "contract": "checkpoint_comparator_group_oof_v1",
        "rows": len(examples),
        "groups": len(set(groups)),
        "top1_selected_action_accuracy": top1,
        "decision_gate": decision_comparison(
            examples, scores, checkpoint_map
        ),
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=pathlib.Path, required=True)
    parser.add_argument("--dataset-root", type=pathlib.Path, required=True)
    parser.add_argument("--checkpoint-root", type=pathlib.Path, required=True)
    parser.add_argument("--cap", type=int, default=2)
    parser.add_argument(
        "--features", choices=("geometry_checkpoint", "checkpoint_only"),
        default="geometry_checkpoint",
    )
    parser.add_argument("--folds", type=int, default=4)
    parser.add_argument("--ensemble-size", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--dim", type=int, default=48)
    parser.add_argument("--seed", type=int, default=20260825)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    import torch

    examples, contract = build_comparator_examples(
        args.dataset, args.dataset_root, args.checkpoint_root, cap=args.cap,
        features=args.features,
    )
    checkpoint_map = load_checkpoint_map(args.checkpoint_root, cap=args.cap)
    report = run_comparator_oof(
        torch, examples, checkpoint_map, folds=args.folds,
        ensemble_size=args.ensemble_size, epochs=args.epochs, dim=args.dim,
        seed=args.seed, repeats=args.repeats,
    )
    report["feature_contract"] = contract
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "rows": report["rows"],
        "top1": report["top1_selected_action_accuracy"],
        "gate": {
            name: {
                key: value
                for key, value in block.items() if key != "flips"
            }
            for name, block in report["decision_gate"].items()
        },
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
