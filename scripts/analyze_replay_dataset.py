"""
Phi -> Y analysis over stratified counterfactual replay datasets.

Reads the candidate rows produced by ``scripts/build_replay_dataset.py``
and answers, feature by feature, how far the recorded release features
explain the official physics labels:

- univariate relation of each ``phi_modelling`` feature to
  ``delta_theta_deg`` and ``d_xy`` (Spearman, plus outcome rates per
  feature quartile),
- safety rates split by the shadow gate verdict,
- the current gate's confusion matrix against each separated label,
- within-snapshot contrast between safe and dangerous release candidates,
- danger rates by score band, for release and settled candidates alike.

Rows are an unequal-probability sample: every population-level rate is
Horvitz-Thompson re-weighted by ``sampling.sampling_weight``. Raw counts
are reported next to weighted rates so thin cells stay visible.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_DATASET_ROOT = ROOT / "reports" / "replay-dataset"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "replay-analysis"

# Labels analysed as "danger" outcomes, in reporting order.
DANGER_LABELS = (
    "rotated_over_30",
    "horizontal_displaced_over_half_footprint",
    "displaced_over_half_footprint",
    "not_placed_safe",
    "not_valid",
)
CONTINUOUS_TARGETS = ("delta_theta_deg", "d_xy", "d_z")


def load_rows(dataset_dirs: list[pathlib.Path]) -> list[dict[str, Any]]:
    rows = []
    for directory in dataset_dirs:
        manifest_path = directory / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") == "running":
            print(f"skip (still running): {directory.name}", file=sys.stderr)
            continue
        for jsonl in sorted(directory.glob("step-*-candidates.jsonl")):
            with jsonl.open(encoding="utf-8") as handle:
                for line in handle:
                    row = json.loads(line)
                    row["_dataset_dir"] = directory.name
                    rows.append(row)
    return rows


def row_weight(row: dict[str, Any]) -> float:
    return float(row["sampling"]["sampling_weight"])


def label_value(row: dict[str, Any], label: str) -> bool:
    return bool(row["physical"]["Y"][label])


def weighted_rate(pairs: list[tuple[bool, float]]) -> float | None:
    total = sum(weight for _, weight in pairs)
    if total <= 0.0:
        return None
    return sum(weight for flag, weight in pairs if flag) / total


def average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while (
            j + 1 < len(order)
            and values[order[j + 1]] == values[order[i]]
        ):
            j += 1
        mean_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = mean_rank
        i = j + 1
    return ranks


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) != len(y) or len(x) < 3:
        return None
    rx = average_ranks(x)
    ry = average_ranks(y)
    mx = sum(rx) / len(rx)
    my = sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    vy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if vx <= 0.0 or vy <= 0.0:
        return None
    return cov / (vx * vy)


def quartile_edges(values: list[float]) -> list[float]:
    ordered = sorted(values)
    edges = []
    for q in (0.25, 0.5, 0.75):
        position = q * (len(ordered) - 1)
        low = int(math.floor(position))
        high = int(math.ceil(position))
        fraction = position - low
        edges.append(
            ordered[low] * (1.0 - fraction) + ordered[high] * fraction
        )
    return edges


def quartile_index(value: float, edges: list[float]) -> int:
    for index, edge in enumerate(edges):
        if value <= edge:
            return index
    return len(edges)


def feature_report(
    release_rows: list[dict[str, Any]], feature: str
) -> dict[str, Any] | None:
    rows = [
        row
        for row in release_rows
        if isinstance(row.get("phi_modelling"), dict)
        and feature in row["phi_modelling"]
        and row["physical"].get("delta_theta_deg") is not None
    ]
    if len(rows) < 3:
        return None
    values = [float(row["phi_modelling"][feature]) for row in rows]
    report: dict[str, Any] = {"n": len(rows)}
    for target in CONTINUOUS_TARGETS:
        targets = [float(row["physical"][target]) for row in rows]
        report[f"spearman_{target}"] = spearman(values, targets)
    edges = quartile_edges(values)
    report["quartile_edges"] = edges
    quartiles: list[dict[str, Any]] = []
    for q in range(4):
        in_q = [
            row
            for row, value in zip(rows, values)
            if quartile_index(value, edges) == q
        ]
        entry: dict[str, Any] = {"n": len(in_q)}
        if in_q:
            entry["mean_delta_theta_deg"] = sum(
                float(row["physical"]["delta_theta_deg"]) for row in in_q
            ) / len(in_q)
            entry["mean_d_xy"] = sum(
                float(row["physical"]["d_xy"]) for row in in_q
            ) / len(in_q)
            for outcome in ("rotated_over_30", "not_placed_safe"):
                entry[f"rate_{outcome}"] = sum(
                    1 for row in in_q if label_value(row, outcome)
                ) / len(in_q)
                entry[f"weighted_rate_{outcome}"] = weighted_rate(
                    [(label_value(row, outcome), row_weight(row)) for row in in_q]
                )
        quartiles.append(entry)
    report["quartiles"] = quartiles
    return report


def gate_split_report(release_rows: list[dict[str, Any]]) -> dict[str, Any]:
    split: dict[str, Any] = {}
    for verdict, rows in (
        ("pass", [r for r in release_rows if r.get("gate_passed") is True]),
        ("reject", [r for r in release_rows if r.get("gate_passed") is False]),
    ):
        entry: dict[str, Any] = {"n": len(rows)}
        for label in DANGER_LABELS:
            entry[f"rate_{label}"] = (
                sum(1 for row in rows if label_value(row, label)) / len(rows)
                if rows
                else None
            )
            entry[f"weighted_rate_{label}"] = weighted_rate(
                [(label_value(row, label), row_weight(row)) for row in rows]
            )
        split[verdict] = entry
    return split


def confusion_report(
    release_rows: list[dict[str, Any]], label: str
) -> dict[str, Any]:
    """Positive class = dangerous; the gate predicts positive by rejecting."""
    cells = {"tp": 0.0, "fp": 0.0, "fn": 0.0, "tn": 0.0}
    counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for row in release_rows:
        if row.get("gate_passed") is None:
            continue
        rejected = row["gate_passed"] is False
        dangerous = label_value(row, label)
        key = (
            "tp" if rejected and dangerous
            else "fp" if rejected
            else "fn" if dangerous
            else "tn"
        )
        cells[key] += row_weight(row)
        counts[key] += 1
    weight_total = sum(cells.values())
    precision = (
        cells["tp"] / (cells["tp"] + cells["fp"])
        if cells["tp"] + cells["fp"] > 0
        else None
    )
    recall = (
        cells["tp"] / (cells["tp"] + cells["fn"])
        if cells["tp"] + cells["fn"] > 0
        else None
    )
    false_pass_rate = (
        cells["fn"] / (cells["fn"] + cells["tn"])
        if cells["fn"] + cells["tn"] > 0
        else None
    )
    return {
        "label": label,
        "counts": counts,
        "weighted_cells": cells,
        "weighted_total": weight_total,
        "reject_precision": precision,
        "reject_recall": recall,
        "danger_rate_among_passed": false_pass_rate,
    }


def within_snapshot_contrast(
    release_rows: list[dict[str, Any]],
    features: list[str],
    label: str = "not_placed_safe",
) -> dict[str, Any]:
    """
    Mean feature difference (safe minus dangerous) inside each snapshot
    that contains both, so container state is held fixed. The sign
    aggregate counts snapshots where the safe mean exceeds the dangerous
    mean.
    """
    by_snapshot: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in release_rows:
        if isinstance(row.get("phi_modelling"), dict):
            by_snapshot[row["snapshot_id"]].append(row)

    per_feature: dict[str, dict[str, Any]] = {
        feature: {"diffs": [], "positive": 0, "snapshots": 0}
        for feature in features
    }
    used_snapshots = 0
    for rows in by_snapshot.values():
        safe = [row for row in rows if not label_value(row, label)]
        dangerous = [row for row in rows if label_value(row, label)]
        if not safe or not dangerous:
            continue
        used_snapshots += 1
        for feature in features:
            safe_values = [
                float(row["phi_modelling"][feature])
                for row in safe
                if feature in row["phi_modelling"]
            ]
            danger_values = [
                float(row["phi_modelling"][feature])
                for row in dangerous
                if feature in row["phi_modelling"]
            ]
            if not safe_values or not danger_values:
                continue
            diff = sum(safe_values) / len(safe_values) - sum(
                danger_values
            ) / len(danger_values)
            slot = per_feature[feature]
            slot["diffs"].append(diff)
            slot["snapshots"] += 1
            if diff > 0:
                slot["positive"] += 1

    result: dict[str, Any] = {"snapshots_with_both": used_snapshots}
    for feature, slot in per_feature.items():
        diffs = slot.pop("diffs")
        slot["mean_diff_safe_minus_dangerous"] = (
            sum(diffs) / len(diffs) if diffs else None
        )
    result["features"] = per_feature
    return result


def band_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    bands: dict[str, Any] = {}
    for band in ("top1", "top10", "top10pct", "tail"):
        in_band = [
            row for row in rows if row["stratum"]["score_band"] == band
        ]
        entry: dict[str, Any] = {"n": len(in_band)}
        for label in ("not_placed_safe", "rotated_over_30", "not_valid"):
            entry[f"rate_{label}"] = (
                sum(1 for row in in_band if label_value(row, label))
                / len(in_band)
                if in_band
                else None
            )
        bands[band] = entry
    return bands


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    release_rows = [
        row for row in rows if row["kind"] == "release_candidate"
    ]
    settled_rows = [row for row in rows if row["kind"] == "candidate"]
    features: list[str] = []
    for row in release_rows:
        if isinstance(row.get("phi_modelling"), dict):
            for key in row["phi_modelling"]:
                if key not in features and key != "initial_orientation":
                    features.append(key)

    strata_counts = collections.Counter(
        row["sampling"]["stratum_key"] for row in rows
    )
    dataset_counts = collections.Counter(
        row["_dataset_dir"] for row in rows
    )

    prevalence: dict[str, Any] = {}
    for kind, kind_rows in (
        ("release_candidate", release_rows),
        ("candidate", settled_rows),
    ):
        entry: dict[str, Any] = {"n": len(kind_rows)}
        for label in DANGER_LABELS:
            entry[f"rate_{label}"] = (
                sum(1 for row in kind_rows if label_value(row, label))
                / len(kind_rows)
                if kind_rows
                else None
            )
            entry[f"weighted_rate_{label}"] = weighted_rate(
                [
                    (label_value(row, label), row_weight(row))
                    for row in kind_rows
                ]
            )
        prevalence[kind] = entry

    return {
        "row_count": len(rows),
        "datasets": dict(sorted(dataset_counts.items())),
        "strata": dict(sorted(strata_counts.items())),
        "prevalence": prevalence,
        "gate_split": gate_split_report(release_rows),
        "confusion": [
            confusion_report(release_rows, label) for label in DANGER_LABELS
        ],
        "univariate": {
            feature: feature_report(release_rows, feature)
            for feature in features
        },
        "within_snapshot": within_snapshot_contrast(release_rows, features),
        "score_band": {
            "release_candidate": band_report(release_rows),
            "candidate": band_report(settled_rows),
        },
    }


def fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_markdown(result: dict[str, Any]) -> str:
    lines = ["# Replay dataset Phi -> Y analysis", ""]
    lines.append(f"- rows: {result['row_count']}")
    for name, count in result["datasets"].items():
        lines.append(f"- `{name}`: {count} rows")
    lines.append("")

    lines.append("## Label prevalence (per kind)")
    lines.append("")
    lines.append(
        "| kind | n | " + " | ".join(DANGER_LABELS) + " |"
    )
    lines.append("|---|---:|" + "---:|" * len(DANGER_LABELS))
    for kind, entry in result["prevalence"].items():
        cells = [
            f"{fmt(entry['rate_' + label])} / {fmt(entry['weighted_rate_' + label])}"
            for label in DANGER_LABELS
        ]
        lines.append(
            f"| {kind} | {entry['n']} | " + " | ".join(cells) + " |"
        )
    lines.append("")
    lines.append("Cells are `raw rate / weighted rate`.")
    lines.append("")

    lines.append("## Gate verdict split (release candidates)")
    lines.append("")
    lines.append("| verdict | n | " + " | ".join(DANGER_LABELS) + " |")
    lines.append("|---|---:|" + "---:|" * len(DANGER_LABELS))
    for verdict, entry in result["gate_split"].items():
        cells = [
            f"{fmt(entry['rate_' + label])} / {fmt(entry['weighted_rate_' + label])}"
            for label in DANGER_LABELS
        ]
        lines.append(
            f"| {verdict} | {entry['n']} | " + " | ".join(cells) + " |"
        )
    lines.append("")

    lines.append("## Current gate confusion (positive = dangerous)")
    lines.append("")
    lines.append(
        "| label | TP | FP | FN | TN | reject precision | reject recall "
        "| danger rate among passed |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for entry in result["confusion"]:
        counts = entry["counts"]
        lines.append(
            f"| {entry['label']} | {counts['tp']} | {counts['fp']} "
            f"| {counts['fn']} | {counts['tn']} "
            f"| {fmt(entry['reject_precision'])} "
            f"| {fmt(entry['reject_recall'])} "
            f"| {fmt(entry['danger_rate_among_passed'])} |"
        )
    lines.append("")
    lines.append(
        "Counts are raw rows; precision/recall/danger-rate are weighted."
    )
    lines.append("")

    lines.append("## Univariate Phi -> Y (release candidates)")
    lines.append("")
    lines.append(
        "| feature | n | rho(dtheta) | rho(d_xy) | rho(d_z) "
        "| Q1..Q4 rate not_placed_safe | Q1..Q4 mean dtheta |"
    )
    lines.append("|---|---:|---:|---:|---:|---|---|")
    for feature, entry in result["univariate"].items():
        if entry is None:
            lines.append(f"| {feature} | - | - | - | - | - | - |")
            continue
        q_rate = " / ".join(
            fmt(q.get("rate_not_placed_safe")) for q in entry["quartiles"]
        )
        q_theta = " / ".join(
            fmt(q.get("mean_delta_theta_deg"), 1) for q in entry["quartiles"]
        )
        lines.append(
            f"| {feature} | {entry['n']} "
            f"| {fmt(entry['spearman_delta_theta_deg'])} "
            f"| {fmt(entry['spearman_d_xy'])} "
            f"| {fmt(entry['spearman_d_z'])} "
            f"| {q_rate} | {q_theta} |"
        )
    lines.append("")

    contrast = result["within_snapshot"]
    lines.append("## Within-snapshot contrast (safe minus dangerous)")
    lines.append("")
    lines.append(
        f"Snapshots containing both safe and dangerous release rows: "
        f"{contrast['snapshots_with_both']}"
    )
    lines.append("")
    lines.append("| feature | snapshots | mean diff | safe-higher count |")
    lines.append("|---|---:|---:|---:|")
    for feature, entry in contrast["features"].items():
        lines.append(
            f"| {feature} | {entry['snapshots']} "
            f"| {fmt(entry['mean_diff_safe_minus_dangerous'])} "
            f"| {entry['positive']} |"
        )
    lines.append("")

    lines.append("## Danger rate by score band (raw)")
    lines.append("")
    for kind, bands in result["score_band"].items():
        lines.append(f"### {kind}")
        lines.append("")
        lines.append(
            "| band | n | not_placed_safe | rotated_over_30 | not_valid |"
        )
        lines.append("|---|---:|---:|---:|---:|")
        for band, entry in bands.items():
            lines.append(
                f"| {band} | {entry['n']} "
                f"| {fmt(entry['rate_not_placed_safe'])} "
                f"| {fmt(entry['rate_rotated_over_30'])} "
                f"| {fmt(entry['rate_not_valid'])} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset-root",
        type=pathlib.Path,
        default=DEFAULT_DATASET_ROOT,
        help="Directory whose immediate children are dataset directories.",
    )
    parser.add_argument(
        "--dataset",
        type=pathlib.Path,
        nargs="*",
        help="Explicit dataset directories (overrides --dataset-root).",
    )
    parser.add_argument(
        "--output-dir", type=pathlib.Path, default=DEFAULT_OUTPUT_DIR
    )
    args = parser.parse_args()

    if args.dataset:
        dataset_dirs = list(args.dataset)
    else:
        dataset_dirs = sorted(
            path for path in args.dataset_root.iterdir() if path.is_dir()
        )
    rows = load_rows(dataset_dirs)
    if not rows:
        print("no rows found", file=sys.stderr)
        return 1

    result = analyze(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "latest.json"
    md_path = args.output_dir / "latest.md"
    json_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    md_path.write_text(render_markdown(result), encoding="utf-8")
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
