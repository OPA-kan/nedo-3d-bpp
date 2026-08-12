"""Evaluate physical afterstate continuation value across independent H3 runs."""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import statistics
from typing import Any, Callable

import numpy as np

try:
    from scripts.evaluate_counterfactual_teacher_baseline import (
        _read_jsonl,
        _set_summary,
    )
    from scripts.evaluate_counterfactual_teacher_cross_run import (
        _action_delta,
    )
except ModuleNotFoundError:  # direct script execution
    from evaluate_counterfactual_teacher_baseline import _read_jsonl, _set_summary
    from evaluate_counterfactual_teacher_cross_run import _action_delta


DIRECTIONAL = ("lower_afterstate_better", "higher_afterstate_better")
METRICS = (
    "placed_count",
    "fill_score_proxy",
    "com_z",
    "surface_total_variation",
    "priority_misrouted",
    "soft_covered_by_other",
)


def load_run(path: pathlib.Path) -> dict[str, Any]:
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if int(manifest.get("schema_version", 0)) < 4:
        raise ValueError(f"afterstate tensors require schema v4: {path}")
    return {
        "run_id": str(manifest["source_run_id"]),
        "discovery": _read_jsonl(path / "discovery.jsonl"),
        "late": _read_jsonl(path / "late_holdout.jsonl"),
    }


def _state_delta(
    row: dict[str, Any],
    pair: tuple[dict[str, Any], dict[str, Any]] | None = None,
) -> list[float]:
    lower, higher = pair or (
        row["lower_afterstate_tensor"], row["higher_afterstate_tensor"]
    )
    lower_values = _set_summary(lower)
    higher_values = _set_summary(higher)
    if len(lower_values) != len(higher_values):
        raise ValueError(f"afterstate shape mismatch in {row['teacher_id']}")
    return [right - left for left, right in zip(lower_values, higher_values)]


def _features(
    row: dict[str, Any], *, include_action: bool, include_afterstate: bool,
    pair: tuple[dict[str, Any], dict[str, Any]] | None = None,
) -> list[float]:
    values = []
    if include_action:
        values.extend(_action_delta(row, include_score=False))
    if include_afterstate:
        values.extend(_state_delta(row, pair))
    return values


def _eligible(rows: list[dict[str, Any]], metric: str) -> list[dict[str, Any]]:
    return [
        row for row in rows
        if row.get("continuation_labels", {}).get(metric, {}).get("relation")
        in DIRECTIONAL
    ]


def _predict_ridge(
    train: list[dict[str, Any]], test: list[dict[str, Any]], metric: str,
    features: Callable[[dict[str, Any]], list[float]],
) -> dict[str, str]:
    eligible = _eligible(train, metric)
    if not eligible:
        return {}
    train_values = [features(row) for row in eligible]
    test_values = [features(row) for row in test]
    scales = [statistics.pstdev(column) or 1.0 for column in zip(*train_values)]
    design = np.asarray([
        [value / scales[index] for index, value in enumerate(row)]
        for row in train_values
    ])
    test_design = np.asarray([
        [value / scales[index] for index, value in enumerate(row)]
        for row in test_values
    ])
    target = np.asarray([
        1.0
        if row["continuation_labels"][metric]["relation"]
        == "higher_afterstate_better"
        else -1.0
        for row in eligible
    ])
    weights = np.linalg.solve(
        design.T @ design + np.eye(design.shape[1]), design.T @ target
    )
    return {
        row["teacher_id"]: (
            "higher_afterstate_better"
            if float(np.dot(values, weights)) >= 0.0
            else "lower_afterstate_better"
        )
        for row, values in zip(test, test_design)
    }


def _rotated_afterstates(
    rows: list[dict[str, Any]], shift: int,
) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    ordered = sorted(rows, key=lambda row: row["teacher_id"])
    pairs = [
        (row["lower_afterstate_tensor"], row["higher_afterstate_tensor"])
        for row in ordered
    ]
    return {
        row["teacher_id"]: pairs[(index + shift) % len(pairs)]
        for index, row in enumerate(ordered)
    }


def _exact_two_sided_sign_p(wins: int, losses: int) -> float:
    discordant = wins + losses
    if not discordant:
        return 1.0
    tail = sum(
        math.comb(discordant, value)
        for value in range(min(wins, losses) + 1)
    ) / (2 ** discordant)
    return min(1.0, 2.0 * tail)


def evaluate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if len(runs) < 2:
        raise ValueError("cross-run evaluation requires at least two runs")
    run_ids = [run["run_id"] for run in runs]
    if len(set(run_ids)) != len(run_ids):
        raise ValueError("source run IDs must be unique")
    totals = {
        metric: {
            name: {"correct": 0, "total": 0}
            for name in (
                "immediate_score", "action_geometry", "afterstate",
                "action_plus_afterstate",
            )
        }
        for metric in METRICS
    }
    permutation_totals = {
        metric: [{"correct": 0, "total": 0} for _ in range(7)]
        for metric in METRICS
    }
    paired_totals = {
        metric: {
            name: {"wins": 0, "ties": 0, "losses": 0}
            for name in (
                "afterstate_vs_action_geometry",
                "action_plus_afterstate_vs_action_geometry",
                "afterstate_vs_immediate_score",
            )
        }
        for metric in METRICS
    }
    targets = []
    for target_run in runs:
        train = [
            row for run in runs if run is not target_run
            for row in run["discovery"]
        ]
        axes = {}
        for metric in METRICS:
            test = _eligible(target_run["late"], metric)
            feature_sets = {
                "action_geometry": lambda row: _features(
                    row, include_action=True, include_afterstate=False
                ),
                "afterstate": lambda row: _features(
                    row, include_action=False, include_afterstate=True
                ),
                "action_plus_afterstate": lambda row: _features(
                    row, include_action=True, include_afterstate=True
                ),
            }
            predictions = {
                name: _predict_ridge(train, test, metric, features)
                for name, features in feature_sets.items()
            }
            correct = {
                "immediate_score": sum(
                    row["continuation_labels"][metric]["relation"]
                    == "higher_afterstate_better"
                    for row in test
                )
            }
            correct.update({
                name: sum(
                    prediction.get(row["teacher_id"])
                    == row["continuation_labels"][metric]["relation"]
                    for row in test
                )
                for name, prediction in predictions.items()
            })
            row_correct = {}
            for row in test:
                teacher_id = row["teacher_id"]
                actual = row["continuation_labels"][metric]["relation"]
                row_correct[teacher_id] = {
                    "immediate_score": actual == "higher_afterstate_better",
                    **{
                        name: prediction.get(teacher_id) == actual
                        for name, prediction in predictions.items()
                    },
                }
            comparisons = {
                "afterstate_vs_action_geometry": (
                    "afterstate", "action_geometry"
                ),
                "action_plus_afterstate_vs_action_geometry": (
                    "action_plus_afterstate", "action_geometry"
                ),
                "afterstate_vs_immediate_score": (
                    "afterstate", "immediate_score"
                ),
            }
            for name, (left, right) in comparisons.items():
                for values in row_correct.values():
                    outcome = (
                        "wins" if values[left] and not values[right]
                        else "losses" if values[right] and not values[left]
                        else "ties"
                    )
                    paired_totals[metric][name][outcome] += 1
            permutation_correct = []
            for shift in range(1, 8):
                state_map = _rotated_afterstates(train, shift)
                prediction = _predict_ridge(
                    train, test, metric,
                    lambda row, state_map=state_map: _features(
                        row, include_action=False, include_afterstate=True,
                        pair=state_map.get(row["teacher_id"]),
                    ),
                )
                value = sum(
                    prediction.get(row["teacher_id"])
                    == row["continuation_labels"][metric]["relation"]
                    for row in test
                )
                permutation_correct.append(value)
                permutation_totals[metric][shift - 1]["correct"] += value
                permutation_totals[metric][shift - 1]["total"] += len(test)
            for name, value in correct.items():
                totals[metric][name]["correct"] += value
                totals[metric][name]["total"] += len(test)
            axes[metric] = {
                "directional_rows": len(test),
                "correct": correct,
                "permuted_afterstate_correct": permutation_correct,
            }
        targets.append({
            "target_run_id": target_run["run_id"],
            "training_run_ids": [
                run["run_id"] for run in runs if run is not target_run
            ],
            "training_discovery_rows": len(train),
            "target_late_rows": len(target_run["late"]),
            "axes": axes,
        })
    permutation_summary = {}
    for metric, values in permutation_totals.items():
        correct = [value["correct"] for value in values]
        permutation_summary[metric] = {
            "correct_by_shift": correct,
            "total": values[0]["total"],
            "minimum": min(correct),
            "median": statistics.median(correct),
            "maximum": max(correct),
        }
    paired_comparisons = {}
    for metric, comparisons in paired_totals.items():
        paired_comparisons[metric] = {}
        for name, counts in comparisons.items():
            paired_comparisons[metric][name] = {
                **counts,
                "exact_two_sided_sign_p": _exact_two_sided_sign_p(
                    counts["wins"], counts["losses"]
                ),
            }
    return {
        "schema_version": 1,
        "protocol": "train_other_runs_discovery_test_whole_target_run_late",
        "target": (
            "best bounded-H3 continuation gain from each physical afterstate; "
            "the first action's H0 outcome is subtracted per axis"
        ),
        "run_ids": run_ids,
        "targets": targets,
        "pooled_exact_counts": totals,
        "paired_exact_comparisons": paired_comparisons,
        "permuted_afterstate_negative_control": permutation_summary,
        "claim": (
            "Synthetic run-held-out diagnostic. It tests learnable continuation "
            "value in H3 states, not episode-level policy improvement."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Cross-run physical afterstate-value audit", "",
        "Targets are best remaining H3 gains after subtracting each child "
        "state's immediate H0 outcome. Outcome axes remain separate.", "",
        "| Axis | Rows | Immediate | Action geometry | Afterstate | "
        "Action + afterstate | Permuted afterstate min/median/max |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for metric in METRICS:
        models = report["pooled_exact_counts"][metric]
        total = models["afterstate"]["total"]
        permuted = report["permuted_afterstate_negative_control"][metric]
        lines.append(
            f"| {metric} | {total} | "
            f"{models['immediate_score']['correct']}/{total} | "
            f"{models['action_geometry']['correct']}/{total} | "
            f"{models['afterstate']['correct']}/{total} | "
            f"{models['action_plus_afterstate']['correct']}/{total} | "
            f"{permuted['minimum']}/{permuted['median']:g}/"
            f"{permuted['maximum']} |"
        )
    lines.extend([
        "", "## Paired exact comparisons", "",
        "Each `W/T/L` is for the model named first. The exact two-sided sign "
        "test uses only discordant held-out rows.", "",
        "| Axis | Afterstate vs action | p | Action+state vs action | p | "
        "Afterstate vs immediate | p |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for metric in METRICS:
        comparisons = report["paired_exact_comparisons"][metric]
        cells = []
        for name in (
            "afterstate_vs_action_geometry",
            "action_plus_afterstate_vs_action_geometry",
            "afterstate_vs_immediate_score",
        ):
            row = comparisons[name]
            cells.extend([
                f"{row['wins']}/{row['ties']}/{row['losses']}",
                f"{row['exact_two_sided_sign_p']:.4g}",
            ])
        lines.append(f"| {metric} | " + " | ".join(cells) + " |")
    lines.extend([
        "", "The afterstate model is a fixed-L2 no-intercept ridge over the "
        "difference of permutation-invariant physical child-state summaries. "
        "Each target run is excluded in full from training. Seven deterministic "
        "training-state rotations are reported as a negative control.", "",
        f"> {report['claim']}", "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teacher-dir", action="append", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    report = evaluate([load_run(path) for path in args.teacher_dir])
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
