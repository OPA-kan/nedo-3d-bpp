"""Evaluate action-only teachers across independent physical matrix runs."""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
from typing import Any

import numpy as np

try:
    from scripts.evaluate_counterfactual_teacher_baseline import (
        DIRECTIONAL,
        _action_pair,
        _read_jsonl,
    )
    from scripts.evaluate_counterfactual_teacher_discovery import (
        _predict_ridge_fold,
    )
except ModuleNotFoundError:  # direct `python scripts/...py` execution
    from evaluate_counterfactual_teacher_baseline import (
        DIRECTIONAL,
        _action_pair,
        _read_jsonl,
    )
    from evaluate_counterfactual_teacher_discovery import _predict_ridge_fold


def load_run(path: pathlib.Path) -> dict[str, Any]:
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    return {
        "run_id": str(manifest["source_run_id"]),
        "discovery": _read_jsonl(path / "discovery.jsonl"),
        "late": _read_jsonl(path / "late_holdout.jsonl"),
    }


def _directional(rows: list[dict[str, Any]], metric: str) -> list[dict[str, Any]]:
    return [
        row for row in rows
        if row["labels"][metric]["relation"] in DIRECTIONAL
    ]


def _action_geometry_pair(row: dict[str, Any]) -> list[float]:
    lower_tensor = row["lower_action_tensor"]
    higher_tensor = row["higher_action_tensor"]
    names = lower_tensor["feature_names"]
    indices = [
        index for index, name in enumerate(names)
        if name != "immediate_score"
    ]
    lower = [float(lower_tensor["values"][index]) for index in indices]
    higher = [float(higher_tensor["values"][index]) for index in indices]
    return lower + higher + [right - left for left, right in zip(lower, higher)]


def _score_gap_pair(row: dict[str, Any]) -> list[float]:
    names = row["lower_action_tensor"]["feature_names"]
    index = names.index("immediate_score")
    lower = float(row["lower_action_tensor"]["values"][index])
    higher = float(row["higher_action_tensor"]["values"][index])
    return [lower, higher, higher - lower]


def _action_delta(row: dict[str, Any], *, include_score: bool) -> list[float]:
    lower_tensor = row["lower_action_tensor"]
    higher_tensor = row["higher_action_tensor"]
    indices = [
        index for index, name in enumerate(lower_tensor["feature_names"])
        if include_score or name != "immediate_score"
    ]
    return [
        float(higher_tensor["values"][index])
        - float(lower_tensor["values"][index])
        for index in indices
    ]


def _predict_utility_delta_fold(
    train: list[dict[str, Any]], test: list[dict[str, Any]], metric: str,
    *, include_score: bool,
) -> dict[str, str]:
    """No-intercept ridge so swapping the candidates negates the prediction."""
    eligible = _directional(train, metric)
    if not eligible:
        return {}
    train_values = [
        _action_delta(row, include_score=include_score) for row in eligible
    ]
    test_values = [
        _action_delta(row, include_score=include_score) for row in test
    ]
    scales = [
        statistics.pstdev(column) or 1.0 for column in zip(*train_values)
    ]
    train_values = [
        [value / scales[index] for index, value in enumerate(row)]
        for row in train_values
    ]
    test_values = [
        [value / scales[index] for index, value in enumerate(row)]
        for row in test_values
    ]
    design = np.asarray(train_values, dtype=float)
    target = np.asarray([
        1.0
        if row["labels"][metric]["relation"]
        == "higher_immediate_score_better"
        else -1.0
        for row in eligible
    ])
    weights = np.linalg.solve(
        design.T @ design + np.eye(design.shape[1], dtype=float),
        design.T @ target,
    )
    return {
        row["teacher_id"]: (
            "higher_immediate_score_better"
            if float(np.dot(np.asarray(values), weights)) >= 0.0
            else "lower_immediate_score_better"
        )
        for row, values in zip(test, test_values)
    }
def evaluate_cross_run(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if len(runs) < 2:
        raise ValueError("cross-run evaluation requires at least two runs")
    run_ids = [run["run_id"] for run in runs]
    if len(set(run_ids)) != len(run_ids):
        raise ValueError("source run IDs must be unique")
    metrics = ("fill_score_proxy", "com_z", "surface_total_variation")
    targets = []
    pooled_pareto = {
        name: {"pairs": 0, "proposals": 0, "non_contradicted": 0, "contradicted": 0}
        for name in ("immediate_higher", "geometry_delta_consensus")
    }
    pooled_joint_dominance = {
        "immediate_score": {"correct": 0, "total": 0},
        "geometry_utility_delta": {"correct": 0, "total": 0},
    }
    totals = {
        metric: {
            "immediate_score": {"correct": 0, "total": 0},
            "cross_run_action_ridge": {"correct": 0, "total": 0},
            "cross_run_geometry_ridge": {"correct": 0, "total": 0},
            "cross_run_score_gap_ridge": {"correct": 0, "total": 0},
            "cross_run_action_delta_ridge": {"correct": 0, "total": 0},
            "cross_run_geometry_delta_ridge": {"correct": 0, "total": 0},
        }
        for metric in metrics
    }
    for target in runs:
        train = [
            row for run in runs if run is not target
            for row in run["discovery"]
        ]
        joint_train = []
        for row in train:
            relation = row.get("joint_pareto", {}).get("relation")
            if relation not in (
                "lower_reachable_set_dominates",
                "higher_reachable_set_dominates",
            ):
                continue
            converted = dict(row)
            converted["labels"] = dict(row["labels"])
            converted["labels"]["joint_pareto_dominance"] = {
                "relation": (
                    "lower_immediate_score_better"
                    if relation == "lower_reachable_set_dominates"
                    else "higher_immediate_score_better"
                )
            }
            joint_train.append(converted)
        axes = {}
        for metric in metrics:
            test = _directional(target["late"], metric)
            predictions = _predict_ridge_fold(
                train, test, metric, _action_pair
            )
            geometry_predictions = _predict_ridge_fold(
                train, test, metric, _action_geometry_pair
            )
            score_predictions = _predict_ridge_fold(
                train, test, metric, _score_gap_pair
            )
            delta_predictions = _predict_utility_delta_fold(
                train, test, metric, include_score=True,
            )
            geometry_delta_predictions = _predict_utility_delta_fold(
                train, test, metric, include_score=False,
            )
            action_correct = sum(
                predictions.get(row["teacher_id"])
                == row["labels"][metric]["relation"]
                for row in test
            )
            immediate_correct = sum(
                row["labels"][metric]["relation"]
                == "higher_immediate_score_better"
                for row in test
            )
            geometry_correct = sum(
                geometry_predictions.get(row["teacher_id"])
                == row["labels"][metric]["relation"]
                for row in test
            )
            score_correct = sum(
                score_predictions.get(row["teacher_id"])
                == row["labels"][metric]["relation"]
                for row in test
            )
            delta_correct = sum(
                delta_predictions.get(row["teacher_id"])
                == row["labels"][metric]["relation"]
                for row in test
            )
            geometry_delta_correct = sum(
                geometry_delta_predictions.get(row["teacher_id"])
                == row["labels"][metric]["relation"]
                for row in test
            )
            axes[metric] = {
                "directional_rows": len(test),
                "immediate_score_correct": immediate_correct,
                "cross_run_action_ridge_correct": action_correct,
                "cross_run_geometry_ridge_correct": geometry_correct,
                "cross_run_score_gap_ridge_correct": score_correct,
                "cross_run_action_delta_ridge_correct": delta_correct,
                "cross_run_geometry_delta_ridge_correct": geometry_delta_correct,
            }
            totals[metric]["immediate_score"]["correct"] += immediate_correct
            totals[metric]["immediate_score"]["total"] += len(test)
            totals[metric]["cross_run_action_ridge"]["correct"] += action_correct
            totals[metric]["cross_run_action_ridge"]["total"] += len(test)
            totals[metric]["cross_run_geometry_ridge"]["correct"] += geometry_correct
            totals[metric]["cross_run_geometry_ridge"]["total"] += len(test)
            totals[metric]["cross_run_score_gap_ridge"]["correct"] += score_correct
            totals[metric]["cross_run_score_gap_ridge"]["total"] += len(test)
            totals[metric]["cross_run_action_delta_ridge"]["correct"] += delta_correct
            totals[metric]["cross_run_action_delta_ridge"]["total"] += len(test)
            totals[metric]["cross_run_geometry_delta_ridge"]["correct"] += geometry_delta_correct
            totals[metric]["cross_run_geometry_delta_ridge"]["total"] += len(test)
        joint_test = []
        for row in target["late"]:
            relation = row.get("joint_pareto", {}).get("relation")
            if relation not in (
                "lower_reachable_set_dominates",
                "higher_reachable_set_dominates",
            ):
                continue
            converted = dict(row)
            converted["labels"] = dict(row["labels"])
            converted["labels"]["joint_pareto_dominance"] = {
                "relation": (
                    "lower_immediate_score_better"
                    if relation == "lower_reachable_set_dominates"
                    else "higher_immediate_score_better"
                )
            }
            joint_test.append(converted)
        joint_predictions = _predict_utility_delta_fold(
            joint_train, joint_test, "joint_pareto_dominance",
            include_score=False,
        )
        joint_immediate_correct = sum(
            row["labels"]["joint_pareto_dominance"]["relation"]
            == "higher_immediate_score_better"
            for row in joint_test
        )
        joint_geometry_correct = sum(
            joint_predictions.get(row["teacher_id"])
            == row["labels"]["joint_pareto_dominance"]["relation"]
            for row in joint_test
        )
        joint_dominance = {
            "directional_rows": len(joint_test),
            "immediate_score_correct": joint_immediate_correct,
            "geometry_utility_delta_correct": joint_geometry_correct,
            "training_dominance_rows": len(joint_train),
        }
        pooled_joint_dominance["immediate_score"]["correct"] += joint_immediate_correct
        pooled_joint_dominance["immediate_score"]["total"] += len(joint_test)
        pooled_joint_dominance["geometry_utility_delta"]["correct"] += joint_geometry_correct
        pooled_joint_dominance["geometry_utility_delta"]["total"] += len(joint_test)
        all_late = target["late"]
        fill_predictions = _predict_utility_delta_fold(
            train, all_late, "fill_score_proxy", include_score=False
        )
        surface_predictions = _predict_utility_delta_fold(
            train, all_late, "surface_total_variation", include_score=False
        )
        pareto = {
            name: {"pairs": len(all_late), "proposals": 0, "non_contradicted": 0, "contradicted": 0}
            for name in pooled_pareto
        }
        for row in all_late:
            predictions = {
                "immediate_higher": "higher_immediate_score_better",
                "geometry_delta_consensus": (
                    fill_predictions.get(row["teacher_id"])
                    if fill_predictions.get(row["teacher_id"])
                    == surface_predictions.get(row["teacher_id"])
                    else None
                ),
            }
            actual = [
                row["labels"][metric]["relation"]
                for metric in ("fill_score_proxy", "surface_total_variation")
            ]
            for name, prediction in predictions.items():
                if prediction is None:
                    continue
                pareto[name]["proposals"] += 1
                contradicted = any(
                    relation in DIRECTIONAL and relation != prediction
                    for relation in actual
                )
                key = "contradicted" if contradicted else "non_contradicted"
                pareto[name][key] += 1
        for name in pooled_pareto:
            for key in pooled_pareto[name]:
                pooled_pareto[name][key] += pareto[name][key]
        targets.append({
            "target_run_id": target["run_id"],
            "training_run_ids": [run["run_id"] for run in runs if run is not target],
            "training_discovery_rows": len(train),
            "target_late_rows": len(target["late"]),
            "axes": axes,
            "pareto_shadow": pareto,
            "joint_pareto_dominance": joint_dominance,
        })
    return {
        "schema_version": 1,
        "protocol": "train_other_runs_discovery_test_whole_target_run_late",
        "run_ids": run_ids,
        "model": "fixed_l2_action_only_ridge",
        "targets": targets,
        "pooled_exact_counts": totals,
        "pooled_pareto_shadow": pooled_pareto,
        "pooled_joint_pareto_dominance": pooled_joint_dominance,
        "claim": (
            "Run-held-out synthetic diagnostic; repeated scenarios and small "
            "late denominators do not establish official-policy gain."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Cross-run action-only teacher audit",
        "",
        "Each row trains on discovery roots from the other runs and tests the complete target run's late roots.",
        "",
        "| Target run | Axis | Rows | Immediate | Full pair | Geometry pair | Score only | Action delta | Geometry delta |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for target in report["targets"]:
        for metric, axis in target["axes"].items():
            total = axis["directional_rows"]
            lines.append(
                f"| {target['target_run_id']} | {metric} | {total} | "
                f"{axis['immediate_score_correct']}/{total} | "
                f"{axis['cross_run_action_ridge_correct']}/{total} | "
                f"{axis['cross_run_geometry_ridge_correct']}/{total} | "
                f"{axis['cross_run_score_gap_ridge_correct']}/{total} | "
                f"{axis['cross_run_action_delta_ridge_correct']}/{total} | "
                f"{axis['cross_run_geometry_delta_ridge_correct']}/{total} |"
            )
    lines.extend(["", "## Pooled exact counts", ""])
    for metric, models in report["pooled_exact_counts"].items():
        immediate = models["immediate_score"]
        ridge = models["cross_run_action_ridge"]
        geometry = models["cross_run_geometry_ridge"]
        score = models["cross_run_score_gap_ridge"]
        delta = models["cross_run_action_delta_ridge"]
        geometry_delta = models["cross_run_geometry_delta_ridge"]
        lines.append(
            f"- {metric}: immediate {immediate['correct']}/{immediate['total']}; "
            f"full action {ridge['correct']}/{ridge['total']}; geometry no score "
            f"{geometry['correct']}/{geometry['total']}; score only "
            f"{score['correct']}/{score['total']}; action delta "
            f"{delta['correct']}/{delta['total']}; geometry delta "
            f"{geometry_delta['correct']}/{geometry_delta['total']}"
        )
    lines.extend(["", "## Two-axis Pareto shadow", ""])
    for name, row in report["pooled_pareto_shadow"].items():
        lines.append(
            f"- {name}: proposals {row['proposals']}/{row['pairs']}; "
            f"non-contradicted {row['non_contradicted']}; contradicted "
            f"{row['contradicted']}"
        )
    lines.extend(["", "## Joint reachable-set Pareto dominance", ""])
    joint = report["pooled_joint_pareto_dominance"]
    lines.append(
        f"- immediate score: {joint['immediate_score']['correct']}/"
        f"{joint['immediate_score']['total']}"
    )
    lines.append(
        f"- geometry utility delta: {joint['geometry_utility_delta']['correct']}/"
        f"{joint['geometry_utility_delta']['total']}"
    )
    lines.extend(["", f"> {report['claim']}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teacher-dir", type=pathlib.Path, action="append", required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    report = evaluate_cross_run([load_run(path) for path in args.teacher_dir])
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
