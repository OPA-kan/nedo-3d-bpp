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
LABEL_FAMILIES = (
    "continuation_labels",
    "distributional_continuation_labels",
)
METRICS = (
    "placed_count",
    "fill_score_proxy",
    "com_z",
    "surface_total_variation",
    "priority_misrouted",
    "soft_covered_by_other",
)


def load_run(
    path: pathlib.Path, *, label_family: str = "continuation_labels",
) -> dict[str, Any]:
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if int(manifest.get("schema_version", 0)) < 4:
        raise ValueError(f"afterstate tensors require schema v4: {path}")
    if label_family not in LABEL_FAMILIES:
        raise ValueError(f"unsupported label family: {label_family}")
    if label_family == "distributional_continuation_labels":
        if int(manifest.get("schema_version", 0)) < 5:
            raise ValueError(f"distributional splits require schema v5: {path}")
        discovery_name = "distributional_discovery.jsonl"
        late_name = "distributional_late_holdout.jsonl"
    else:
        discovery_name = "discovery.jsonl"
        late_name = "late_holdout.jsonl"
    discovery = _read_jsonl(path / discovery_name)
    late = _read_jsonl(path / late_name)
    for row in discovery + late:
        for metric, label in row.get("continuation_labels", {}).items():
            if metric in (
                "placed_count", "priority_misrouted",
                "soft_covered_by_other",
            ):
                continue
            if not {
                "lower_best_continuation", "higher_best_continuation"
            }.issubset(label):
                continue
            if math.isclose(
                float(label["lower_best_continuation"]),
                float(label["higher_best_continuation"]),
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                label["relation"] = "equal"
    return {
        "run_id": str(manifest["source_run_id"]),
        "discovery": discovery,
        "late": late,
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


def _state_block_delta(row: dict[str, Any], block: str) -> list[float]:
    lower = row["lower_afterstate_tensor"]
    higher = row["higher_afterstate_tensor"]

    def block_summary(state: dict[str, Any], prefix: str) -> list[float]:
        names = state[f"{prefix}_features"]
        values = [
            [float(value) for value in item]
            for item in state[f"{prefix}_values"]
        ]
        summary = [float(len(values))]
        if values:
            columns = list(zip(*values))
            summary.extend(statistics.fmean(column) for column in columns)
            summary.extend(statistics.pstdev(column) for column in columns)
            summary.extend(min(column) for column in columns)
            summary.extend(max(column) for column in columns)
        else:
            summary.extend([0.0] * (4 * len(names)))
        return summary

    prefixes = {
        "packed": ("packed_item",),
        "packed_visible": ("packed_item", "visible_item"),
    }[block]
    lower_values = [
        value for prefix in prefixes for value in block_summary(lower, prefix)
    ]
    higher_values = [
        value for prefix in prefixes for value in block_summary(higher, prefix)
    ]
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


def _eligible(
    rows: list[dict[str, Any]], metric: str, *,
    label_family: str = "continuation_labels",
) -> list[dict[str, Any]]:
    return [
        row for row in rows
        if row.get(label_family, {}).get(metric, {}).get("relation")
        in DIRECTIONAL
    ]


def fit_ridge_model(
    train: list[dict[str, Any]], metric: str,
    features: Callable[[dict[str, Any]], list[float]],
    *, label_family: str = "continuation_labels",
) -> dict[str, Any]:
    eligible = _eligible(train, metric, label_family=label_family)
    if not eligible:
        raise ValueError(f"no directional training rows for {metric}")
    train_values = [features(row) for row in eligible]
    scales = [statistics.pstdev(column) or 1.0 for column in zip(*train_values)]
    design = np.asarray([
        [value / scales[index] for index, value in enumerate(row)]
        for row in train_values
    ])
    target = np.asarray([
        1.0
        if row[label_family][metric]["relation"]
        == "higher_afterstate_better"
        else -1.0
        for row in eligible
    ])
    weights = np.linalg.solve(
        design.T @ design + np.eye(design.shape[1]), design.T @ target
    )
    return {
        "model": "fixed_l2_no_intercept_ridge",
        "l2": 1.0,
        "metric": metric,
        "label_family": label_family,
        "training_rows": len(eligible),
        "feature_count": len(scales),
        "scales": [float(value) for value in scales],
        "weights": [float(value) for value in weights],
    }


def predict_ridge_model(
    model: dict[str, Any], rows: list[dict[str, Any]],
    features: Callable[[dict[str, Any]], list[float]],
) -> dict[str, str]:
    scales = [float(value) for value in model["scales"]]
    weights = np.asarray(model["weights"], dtype=float)
    values = [features(row) for row in rows]
    if any(len(row) != len(scales) for row in values):
        raise ValueError("ridge feature count does not match model artifact")
    design = np.asarray([
        [value / scales[index] for index, value in enumerate(row)]
        for row in values
    ])
    return {
        row["teacher_id"]: (
            "higher_afterstate_better"
            if float(np.dot(values, weights)) >= 0.0
            else "lower_afterstate_better"
        )
        for row, values in zip(rows, design)
    }


def _predict_ridge(
    train: list[dict[str, Any]], test: list[dict[str, Any]], metric: str,
    features: Callable[[dict[str, Any]], list[float]],
    *, label_family: str = "continuation_labels",
) -> dict[str, str]:
    if not _eligible(train, metric, label_family=label_family):
        return {}
    model = fit_ridge_model(
        train, metric, features, label_family=label_family
    )
    return predict_ridge_model(model, test, features)


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


def evaluate(
    runs: list[dict[str, Any]], *,
    label_family: str = "continuation_labels",
    target_run_ids: set[str] | None = None,
) -> dict[str, Any]:
    if label_family not in LABEL_FAMILIES:
        raise ValueError(f"unsupported label family: {label_family}")
    if len(runs) < 2:
        raise ValueError("cross-run evaluation requires at least two runs")
    run_ids = [run["run_id"] for run in runs]
    if len(set(run_ids)) != len(run_ids):
        raise ValueError("source run IDs must be unique")
    selected_target_ids = set(run_ids) if target_run_ids is None else target_run_ids
    unknown_target_ids = selected_target_ids - set(run_ids)
    if unknown_target_ids:
        raise ValueError(
            "target run IDs are not loaded: "
            + ", ".join(sorted(unknown_target_ids))
        )
    if not selected_target_ids:
        raise ValueError("at least one target run ID is required")
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
    immediate_score_abstentions = {metric: 0 for metric in METRICS}
    targets = []
    fill_selective = {
        "discovery_retrospective": {"correct": 0, "covered": 0, "total": 0},
        "late_retrospective": {"correct": 0, "covered": 0, "total": 0},
    }
    for target_run in (
        run for run in runs if run["run_id"] in selected_target_ids
    ):
        train = [
            row for run in runs if run is not target_run
            for row in run["discovery"]
        ]
        axes = {}
        for metric in METRICS:
            test = _eligible(
                target_run["late"], metric, label_family=label_family
            )
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
                name: _predict_ridge(
                    train, test, metric, features,
                    label_family=label_family,
                )
                for name, features in feature_sets.items()
            }
            correct = {
                "immediate_score": sum(
                    not row.get("equal_immediate_score", False)
                    and row[label_family][metric]["relation"]
                    == "higher_afterstate_better"
                    for row in test
                )
            }
            abstained = sum(
                row.get("equal_immediate_score", False) for row in test
            )
            immediate_score_abstentions[metric] += abstained
            correct.update({
                name: sum(
                    prediction.get(row["teacher_id"])
                    == row[label_family][metric]["relation"]
                    for row in test
                )
                for name, prediction in predictions.items()
            })
            row_correct = {}
            for row in test:
                teacher_id = row["teacher_id"]
                actual = row[label_family][metric]["relation"]
                row_correct[teacher_id] = {
                    "immediate_score": (
                        not row.get("equal_immediate_score", False)
                        and actual == "higher_afterstate_better"
                    ),
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
                    label_family=label_family,
                )
                value = sum(
                    prediction.get(row["teacher_id"])
                    == row[label_family][metric]["relation"]
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
                "immediate_score_abstained": abstained,
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
        for split, report_key in (
            ("discovery", "discovery_retrospective"),
            ("late", "late_retrospective"),
        ):
            test = _eligible(
                target_run[split], "fill_score_proxy",
                label_family=label_family,
            )
            packed = _predict_ridge(
                train, test, "fill_score_proxy",
                lambda row: _state_block_delta(row, "packed"),
                label_family=label_family,
            )
            packed_visible = _predict_ridge(
                train, test, "fill_score_proxy",
                lambda row: _state_block_delta(row, "packed_visible"),
                label_family=label_family,
            )
            for row in test:
                left = packed[row["teacher_id"]]
                right = packed_visible[row["teacher_id"]]
                fill_selective[report_key]["total"] += 1
                if left != right:
                    continue
                fill_selective[report_key]["covered"] += 1
                fill_selective[report_key]["correct"] += (
                    left
                    == row[label_family]["fill_score_proxy"][
                        "relation"
                    ]
                )
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
        "label_family": label_family,
        "protocol": "train_other_runs_discovery_test_whole_target_run_late",
        "target": (
            "uniform-searched-action pessimistic continuation relation (q25/q75, "
            "physical-failure rate, then mean) from each physical afterstate"
            if label_family == "distributional_continuation_labels"
            else "best bounded-H3 continuation gain from each physical "
            "afterstate; the first action's H0 outcome is subtracted per axis"
        ),
        "run_ids": run_ids,
        "evaluated_target_run_ids": [
            run_id for run_id in run_ids if run_id in selected_target_ids
        ],
        "targets": targets,
        "pooled_exact_counts": totals,
        "immediate_score_abstentions": immediate_score_abstentions,
        "paired_exact_comparisons": paired_comparisons,
        "permuted_afterstate_negative_control": permutation_summary,
        "fill_selective_consensus": {
            "contract": (
                "predict only when fixed-L2 packed-only and packed+visible "
                "afterstate models agree"
            ),
            "selection_warning": (
                "This consensus was designed after inspecting the five-run "
                "late errors. Both existing splits are retrospective; only a "
                "subsequent physical run can confirm it."
            ),
            **fill_selective,
        },
        "claim": (
            "Synthetic run-held-out diagnostic. It tests learnable continuation "
            "value in H3 states, not episode-level policy improvement."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Cross-run physical afterstate-value audit", "",
        report["target"] + ". Outcome axes remain separate.", "",
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
    if any(report.get("immediate_score_abstentions", {}).values()):
        lines.extend([
            "", "Immediate-score ties are abstentions, not higher-side "
            "predictions. They remain in the row denominator; abstentions by "
            "axis: " + ", ".join(
                f"{metric}={count}" for metric, count in
                report["immediate_score_abstentions"].items() if count
            ) + ".",
        ])
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
        "", "## Fill-only selective consensus", "",
    ])
    selective = report["fill_selective_consensus"]
    for name in ("discovery_retrospective", "late_retrospective"):
        row = selective[name]
        lines.append(
            f"- {name}: {row['correct']}/{row['covered']} correct at "
            f"{row['covered']}/{row['total']} coverage"
        )
    lines.extend([
        "", f"> {selective['selection_warning']}",
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
    parser.add_argument(
        "--label-family", choices=LABEL_FAMILIES,
        default="continuation_labels",
    )
    parser.add_argument(
        "--target-run-id", action="append",
        help="Evaluate only this loaded run as holdout; may be repeated.",
    )
    args = parser.parse_args()
    report = evaluate(
        [
            load_run(path, label_family=args.label_family)
            for path in args.teacher_dir
        ],
        label_family=args.label_family,
        target_run_ids=(
            set(args.target_run_id) if args.target_run_id else None
        ),
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
