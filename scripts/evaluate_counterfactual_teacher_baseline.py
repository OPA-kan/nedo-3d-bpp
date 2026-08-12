"""Evaluate a preregistered 1-NN ranker on the late-root teacher holdout.

The corpus is intentionally tiny.  This script therefore reports exact
correct/total counts per physical axis and makes no aggregate accuracy claim.
All normalization and neighbor labels come from the discovery split only.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import statistics
from typing import Any


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
        values = [
            [float(value) for value in row]
            for row in state[f"{prefix}_values"]
        ]
        result.append(float(len(values)))
        if values:
            columns = list(zip(*values))
            result.extend(statistics.fmean(column) for column in columns)
            result.extend(statistics.pstdev(column) for column in columns)
            result.extend(min(column) for column in columns)
            result.extend(max(column) for column in columns)
        else:
            result.extend([0.0] * (4 * len(names)))
    return result


def _action_pair(row: dict[str, Any]) -> list[float]:
    lower = [float(value) for value in row["lower_action_tensor"]["values"]]
    higher = [float(value) for value in row["higher_action_tensor"]["values"]]
    if len(lower) != len(higher):
        raise ValueError(f"action tensor shape mismatch in {row['teacher_id']}")
    return lower + higher + [right - left for left, right in zip(lower, higher)]


def feature_vector(row: dict[str, Any], *, include_state: bool) -> list[float]:
    action = _action_pair(row)
    if not include_state:
        return action
    return _set_summary(row["source_state_tensor"]) + action


def _standardize(
    train: list[list[float]], test: list[list[float]],
) -> tuple[list[list[float]], list[list[float]]]:
    columns = list(zip(*train))
    means = [statistics.fmean(column) for column in columns]
    scales = [statistics.pstdev(column) or 1.0 for column in columns]

    def transform(rows: list[list[float]]) -> list[list[float]]:
        return [
            [(value - means[index]) / scales[index] for index, value in enumerate(row)]
            for row in rows
        ]

    return transform(train), transform(test)


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
    train = [
        feature_vector(row, include_state=include_state) for row in eligible
    ]
    test = [
        feature_vector(row, include_state=include_state) for row in holdout
    ]
    train, test = _standardize(train, test)
    predictions = {}
    for row, vector in zip(holdout, test):
        distances = [
            math.fsum((left - right) ** 2 for left, right in zip(candidate, vector))
            for candidate in train
        ]
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
