"""Evaluate a preregistered 1-NN ranker on the late-root teacher holdout.

The corpus is intentionally tiny.  This script therefore reports exact
correct/total counts per physical axis and makes no aggregate accuracy claim.
All normalization and neighbor labels come from the discovery split only.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

import numpy as np


DIRECTIONAL = (
    "lower_immediate_score_better",
    "higher_immediate_score_better",
)


def _read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _set_summary(state: dict[str, Any]) -> list[float]:
    result: list[float] = []
    for prefix in ("container", "packed_item", "visible_item"):
        names = state[f"{prefix}_features"]
        values = np.asarray(state[f"{prefix}_values"], dtype=float)
        result.append(float(len(values)))
        if len(values):
            for operation in (np.mean, np.std, np.min, np.max):
                result.extend(operation(values, axis=0).tolist())
        else:
            result.extend([0.0] * (4 * len(names)))
    return result


def _action_pair(row: dict[str, Any]) -> list[float]:
    lower = np.asarray(row["lower_action_tensor"]["values"], dtype=float)
    higher = np.asarray(row["higher_action_tensor"]["values"], dtype=float)
    if lower.shape != higher.shape:
        raise ValueError(f"action tensor shape mismatch in {row['teacher_id']}")
    return np.concatenate((lower, higher, higher - lower)).tolist()


def feature_vector(row: dict[str, Any], *, include_state: bool) -> list[float]:
    action = _action_pair(row)
    if not include_state:
        return action
    return _set_summary(row["source_state_tensor"]) + action


def _standardize(
    train: np.ndarray, test: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    mean = np.mean(train, axis=0)
    scale = np.std(train, axis=0)
    scale[scale == 0.0] = 1.0
    return (train - mean) / scale, (test - mean) / scale


def _majority(rows: list[dict[str, Any]], metric: str) -> str | None:
    labels = [
        row["labels"][metric]["relation"] for row in rows
        if row["labels"][metric]["relation"] in DIRECTIONAL
    ]
    if not labels:
        return None
    counts = {label: labels.count(label) for label in DIRECTIONAL}
    return max(DIRECTIONAL, key=lambda label: (counts[label], label.startswith("higher")))


def _nearest_predictions(
    discovery: list[dict[str, Any]], holdout: list[dict[str, Any]],
    metric: str, *, include_state: bool,
) -> dict[str, str]:
    eligible = [
        row for row in discovery
        if row["labels"][metric]["relation"] in DIRECTIONAL
    ]
    if not eligible:
        return {}
    train = np.asarray([
        feature_vector(row, include_state=include_state) for row in eligible
    ])
    test = np.asarray([
        feature_vector(row, include_state=include_state) for row in holdout
    ])
    train, test = _standardize(train, test)
    predictions = {}
    for row, vector in zip(holdout, test):
        distances = np.sum((train - vector) ** 2, axis=1)
        nearest = min(
            range(len(eligible)),
            key=lambda index: (float(distances[index]), eligible[index]["teacher_id"]),
        )
        predictions[row["teacher_id"]] = eligible[nearest]["labels"][metric]["relation"]
    return predictions


def evaluate(
    manifest: dict[str, Any], discovery: list[dict[str, Any]],
    holdout: list[dict[str, Any]],
) -> dict[str, Any]:
    if not manifest.get("model_training_ready"):
        raise ValueError("teacher manifest is not model_training_ready")
    metrics = sorted(discovery[0]["labels"])
    results = {}
    for metric in metrics:
        majority = _majority(discovery, metric)
        action_predictions = _nearest_predictions(
            discovery, holdout, metric, include_state=False
        )
        conditioned_predictions = _nearest_predictions(
            discovery, holdout, metric, include_state=True
        )
        directional_rows = [
            row for row in holdout
            if row["labels"][metric]["relation"] in DIRECTIONAL
        ]
        models = {
            "immediate_score": lambda row: "higher_immediate_score_better",
            "discovery_majority": lambda row: majority,
            "action_only_1nn": lambda row: action_predictions.get(row["teacher_id"]),
            "state_action_1nn": lambda row: conditioned_predictions.get(row["teacher_id"]),
        }
        results[metric] = {
            "directional_holdout_rows": len(directional_rows),
            "equal_holdout_rows_excluded": len(holdout) - len(directional_rows),
            "directional_discovery_rows": sum(
                row["labels"][metric]["relation"] in DIRECTIONAL
                for row in discovery
            ),
            "models": {
                name: {
                    "correct": sum(
                        predict(row) == row["labels"][metric]["relation"]
                        for row in directional_rows
                    ),
                    "total": len(directional_rows),
                }
                for name, predict in models.items()
            },
        }
    return {
        "schema_version": 1,
        "source_run_id": manifest.get("source_run_id"),
        "discovery_rows": len(discovery),
        "late_holdout_rows": len(holdout),
        "protocol": (
            "Per-axis directional evaluation. Feature scaling and 1-NN labels "
            "use discovery roots only; late roots are evaluated once."
        ),
        "feature_contract": (
            "Permutation-invariant count/mean/std/min/max summaries of observed "
            "state sets plus the ordered lower/higher candidate action tensors."
        ),
        "claim": (
            "Small-sample diagnostic only; exact counts are not evidence of "
            "generalization or official-score improvement."
        ),
        "axes": results,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Counterfactual teacher late-root baseline",
        "",
        f"Discovery rows: **{report['discovery_rows']}**  ",
        f"Late holdout rows: **{report['late_holdout_rows']}**",
        "",
        "| Axis | Directional holdout | Immediate score | Majority | Action 1-NN | State+action 1-NN |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    names = (
        "immediate_score", "discovery_majority", "action_only_1nn",
        "state_action_1nn",
    )
    for metric, row in report["axes"].items():
        cells = [f"{row['models'][name]['correct']}/{row['models'][name]['total']}" for name in names]
        lines.append(f"| {metric} | {row['directional_holdout_rows']} | " + " | ".join(cells) + " |")
    lines.extend(["", f"> {report['claim']}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teacher-dir", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.teacher_dir / "manifest.json").read_text(encoding="utf-8"))
    report = evaluate(
        manifest,
        _read_jsonl(args.teacher_dir / "discovery.jsonl"),
        _read_jsonl(args.teacher_dir / "late_holdout.jsonl"),
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
