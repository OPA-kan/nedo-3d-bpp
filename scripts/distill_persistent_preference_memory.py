"""Distil verified Cup forks into a champion's persistent head memory.

This is the long-timescale counterpart of ``OnlineAdapterPolicy``.  The
champion backbone and original preference head are the initial policy; only a
trust-region delta on the final scoring head learns from strict physical A/B
verdicts.  A leave-one-course-cell-out report measures whether the memory
generalises before a frozen model artifact is emitted.  No league match or
promotion is performed here.
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

from scripts.learned_allocator_policy import OnlineAdapterPolicy
from scripts.train_rollout_trigger import auc, average_precision, load_examples


def alternate(example: dict[str, Any]) -> tuple[str, bool]:
    incumbent = int(example["incumbent_index"])
    positions = [
        index for index in range(len(example["candidate_ids"]))
        if index != incumbent and example["pair_labels"][index] >= 0.0
    ]
    if len(positions) != 1:
        raise ValueError(
            f"{example['root_id']}: expected exactly one labelled alternate"
        )
    position = positions[0]
    return (
        str(example["candidate_ids"][position]),
        bool(example["pair_labels"][position] > 0.5),
    )


def probability(
    policy: OnlineAdapterPolicy, example: dict[str, Any], alternate_id: str,
) -> float:
    index = example["candidate_ids"].index(alternate_id)
    return policy._pair_probability(example, index)


def train_memory(
    policy: OnlineAdapterPolicy, examples: list[dict[str, Any]], *, passes: int,
) -> list[dict[str, Any]]:
    events = []
    ordered = sorted(examples, key=lambda row: (row["group"], row["root_id"]))
    for pass_index in range(passes):
        for example in ordered:
            alternate_id, alternate_wins = alternate(example)
            event = policy.update_from_example(
                example, alternate_id=alternate_id,
                alternate_wins=alternate_wins,
            )
            if event is None:
                raise ValueError(f"{example['root_id']}: memory update failed")
            events.append({
                "pass": pass_index,
                "group": example["group"],
                "root_id": example["root_id"],
                "alternate_id": alternate_id,
                **event,
            })
    return events


def score_examples(
    policy: OnlineAdapterPolicy, examples: list[dict[str, Any]],
) -> tuple[list[float], list[float]]:
    labels = []
    scores = []
    for example in examples:
        alternate_id, alternate_wins = alternate(example)
        labels.append(float(alternate_wins))
        scores.append(probability(policy, example, alternate_id))
    return labels, scores


def metrics(labels: list[float], scores: list[float]) -> dict[str, Any]:
    truth = np.asarray(labels, dtype=np.float32)
    prediction = np.asarray(scores, dtype=np.float32)
    clipped = np.clip(prediction, 1e-7, 1.0 - 1e-7)
    loss = -np.mean(
        truth * np.log(clipped) + (1.0 - truth) * np.log(1.0 - clipped)
    )
    return {
        "pairs": len(labels),
        "positive_pairs": int(truth.sum()),
        "auc": auc(truth, prediction),
        "average_precision": average_precision(truth, prediction),
        "accuracy_at_0_5": float(
            ((prediction > 0.5) == (truth > 0.5)).mean()
        ),
        "log_loss": float(loss),
        "mean_probability": float(prediction.mean()),
    }


def held_out_report(
    model_dir: pathlib.Path, examples: list[dict[str, Any]], *, passes: int,
    learning_rate: float, update_steps: int, trust_radius: float,
) -> dict[str, Any]:
    labels = []
    before = []
    after = []
    folds = []
    for group in sorted({row["group"] for row in examples}):
        train = [row for row in examples if row["group"] != group]
        held = [row for row in examples if row["group"] == group]
        policy = OnlineAdapterPolicy(
            model_dir, learning_rate=learning_rate,
            update_steps=update_steps, trust_radius=trust_radius,
        )
        held_labels, held_before = score_examples(policy, held)
        train_memory(policy, train, passes=passes)
        _labels, held_after = score_examples(policy, held)
        labels.extend(held_labels)
        before.extend(held_before)
        after.extend(held_after)
        folds.append({
            "held_group": group,
            "train_pairs": len(train),
            "held_pairs": len(held),
            "before": metrics(held_labels, held_before),
            "after": metrics(held_labels, held_after),
            "adapter_norms": policy.adapter_norms(),
        })
    return {
        "contract": "cup_memory_leave_one_course_cell_out_v1",
        "split_unit": "whole_cup_course_cell",
        "groups": len(folds),
        "before": metrics(labels, before),
        "after": metrics(labels, after),
        "folds": folds,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=pathlib.Path, required=True)
    parser.add_argument("--dataset-root", type=pathlib.Path, required=True)
    parser.add_argument("--base-model-dir", type=pathlib.Path, required=True)
    parser.add_argument("--output-model-dir", type=pathlib.Path, required=True)
    parser.add_argument("--report", type=pathlib.Path, required=True)
    parser.add_argument("--cup-run-id", required=True)
    parser.add_argument("--base-model-run-id", required=True)
    parser.add_argument("--cup-id", required=True)
    parser.add_argument("--passes", type=int, default=1)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--update-steps", type=int, default=2)
    parser.add_argument("--trust-radius", type=float, default=1.0)
    args = parser.parse_args()
    if args.passes < 1:
        raise ValueError("passes must be positive")
    examples, feature_contract = load_examples(
        args.dataset, args.dataset_root, candidate_feature_mode="geometry"
    )
    oof = held_out_report(
        args.base_model_dir, examples, passes=args.passes,
        learning_rate=args.learning_rate, update_steps=args.update_steps,
        trust_radius=args.trust_radius,
    )
    policy = OnlineAdapterPolicy(
        args.base_model_dir, learning_rate=args.learning_rate,
        update_steps=args.update_steps, trust_radius=args.trust_radius,
    )
    labels, before = score_examples(policy, examples)
    events = train_memory(policy, examples, passes=args.passes)
    _labels, after = score_examples(policy, examples)
    memory = {
        "lineage": "shun-long",
        "base_model_run_id": str(args.base_model_run_id),
        "cup_run_ids": [str(args.cup_run_id)],
        "cup_ids": [str(args.cup_id)],
        "training_pairs": len(examples),
        "training_groups": sorted({row["group"] for row in examples}),
        "passes": args.passes,
        "learning_rate": args.learning_rate,
        "update_steps": args.update_steps,
        "trust_radius": args.trust_radius,
        "teacher": "strict_genuine_terminal_4_head_dominance",
        "feature_contract": feature_contract,
    }
    model_metadata = policy.materialize(args.output_model_dir, memory=memory)
    report = {
        "contract": "persistent_preference_memory_distillation_v1",
        "status": "capability_only_not_league_evidence",
        "lineage": "shun-long",
        "memory": memory,
        "same_corpus": {
            "before": metrics(labels, before),
            "after": metrics(labels, after),
        },
        "leave_one_course_cell_out": oof,
        "updates": len(events),
        "final_adapter_norms": policy.adapter_norms(),
        "model_memory": model_metadata["memory"],
        "next_gate": (
            "preregistered frozen challenge against the unchanged base "
            "champion; no race-time forks in the first causal test"
        ),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "pairs": len(examples),
        "groups": len({row['group'] for row in examples}),
        "oof_before": oof["before"],
        "oof_after": oof["after"],
        "adapter_norms": policy.adapter_norms(),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
