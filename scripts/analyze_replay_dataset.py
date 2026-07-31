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


def rank_auc(scores: list[float], labels: list[bool]) -> float | None:
    """AUC via average ranks (ties averaged); None without both classes."""
    positives = sum(1 for flag in labels if flag)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return None
    ranks = average_ranks(scores)
    positive_rank_sum = sum(
        rank for rank, flag in zip(ranks, labels) if flag
    )
    return (
        positive_rank_sum - positives * (positives + 1) / 2.0
    ) / (positives * negatives)


def danger_scores(row: dict[str, Any], feature: str) -> float:
    """Orient every feature so that higher = claimed more dangerous."""
    phi = row["phi_modelling"]
    if feature in ("support_ratio", "com_margin"):
        return -float(phi[feature])
    if feature.startswith("abs_"):
        return abs(float(phi[feature[len("abs_"):]]))
    return float(phi[feature])


AUC_FEATURES = (
    "support_ratio",
    "com_margin",
    "overhang_ratio",
    "drop_normalized",
    "abs_support_imbalance",
    "abs_left_right_imbalance",
    "abs_front_back_imbalance",
)
AUC_LABELS = (
    "not_placed_safe",
    "rotated_over_30",
    "horizontal_displaced_over_half_footprint",
)


def auc_report(release_rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [
        row
        for row in release_rows
        if isinstance(row.get("phi_modelling"), dict)
    ]
    report: dict[str, Any] = {"n": len(rows)}
    for feature in AUC_FEATURES:
        entry: dict[str, Any] = {}
        try:
            scores = [danger_scores(row, feature) for row in rows]
        except KeyError:
            report[feature] = None
            continue
        for target in AUC_LABELS:
            labels = [label_value(row, target) for row in rows]
            entry[target] = rank_auc(scores, labels)
        report[feature] = entry
    return report


def gate_reason_report(release_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Which threshold fires, split by whether the reject was justified."""
    tp: collections.Counter = collections.Counter()
    fp: collections.Counter = collections.Counter()
    for row in release_rows:
        if row.get("gate_passed") is not False:
            continue
        target = tp if label_value(row, "not_placed_safe") else fp
        for reason in row.get("gate_reasons") or []:
            target[reason] += 1
    reasons = sorted(set(tp) | set(fp))
    return {
        reason: {
            "rejected_dangerous": tp.get(reason, 0),
            "rejected_safe": fp.get(reason, 0),
        }
        for reason in reasons
    }


SUPPORT_SWEEP_THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)


def support_sweep_report(
    release_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Danger rate among release candidates whose support_ratio clears a
    threshold, versus the weighted share of the population accepted:
    the candidate hard-accept region for an A-style rule.
    """
    rows = [
        row
        for row in release_rows
        if isinstance(row.get("phi_modelling"), dict)
    ]
    total_weight = sum(row_weight(row) for row in rows)
    sweep = []
    for threshold in SUPPORT_SWEEP_THRESHOLDS:
        accepted = [
            row
            for row in rows
            if float(row["phi_modelling"]["support_ratio"]) >= threshold
        ]
        entry: dict[str, Any] = {
            "min_support_ratio": threshold,
            "n": len(accepted),
            "weighted_share_accepted": (
                sum(row_weight(row) for row in accepted) / total_weight
                if total_weight > 0
                else None
            ),
        }
        for target in ("not_placed_safe", "rotated_over_30"):
            entry[f"rate_{target}"] = (
                sum(1 for row in accepted if label_value(row, target))
                / len(accepted)
                if accepted
                else None
            )
            entry[f"weighted_rate_{target}"] = weighted_rate(
                [
                    (label_value(row, target), row_weight(row))
                    for row in accepted
                ]
            )
        sweep.append(entry)
    return sweep


LOGISTIC_FEATURES = (
    "support_ratio",
    "com_margin",
    "drop_normalized",
    "abs_support_imbalance",
    "abs_left_right_imbalance",
    "abs_front_back_imbalance",
)


def logistic_design(row: dict[str, Any]) -> list[float]:
    phi = row["phi_modelling"]
    return [
        1.0,
        float(phi["support_ratio"]),
        float(phi["com_margin"]),
        float(phi["drop_normalized"]),
        abs(float(phi["support_imbalance"])),
        abs(float(phi["left_right_imbalance"])),
        abs(float(phi["front_back_imbalance"])),
    ]


def fit_logistic(
    rows: list[dict[str, Any]],
    label: str,
    epochs: int = 4000,
    learning_rate: float = 0.5,
) -> list[float]:
    design = [logistic_design(row) for row in rows]
    targets = [1.0 if label_value(row, label) else 0.0 for row in rows]
    weights = [0.0] * len(design[0])
    for _ in range(epochs):
        gradient = [0.0] * len(weights)
        for x, y in zip(design, targets):
            z = sum(w * value for w, value in zip(weights, x))
            z = max(-30.0, min(30.0, z))
            error = 1.0 / (1.0 + math.exp(-z)) - y
            for k, value in enumerate(x):
                gradient[k] += error * value
        for k in range(len(weights)):
            weights[k] -= learning_rate * gradient[k] / len(design)
    return weights


def logistic_report(
    release_rows: list[dict[str, Any]], seed: int = 7
) -> dict[str, Any]:
    """
    Snapshot-held-out logistic fit on ``phi_modelling`` (with absolute
    imbalance transforms). This is a separability probe for the A/B/C
    decision, not the production risk model.
    """
    import random

    rows = [
        row
        for row in release_rows
        if isinstance(row.get("phi_modelling"), dict)
    ]
    snapshots = sorted({row["snapshot_id"] for row in rows})
    if len(snapshots) < 3 or len(rows) < 30:
        return {"skipped": "not enough snapshots or rows"}
    random.Random(seed).shuffle(snapshots)
    held_out = set(snapshots[: len(snapshots) // 3])
    train = [row for row in rows if row["snapshot_id"] not in held_out]
    test = [row for row in rows if row["snapshot_id"] in held_out]
    report: dict[str, Any] = {
        "train_n": len(train),
        "test_n": len(test),
        "features": ["intercept", *LOGISTIC_FEATURES],
    }
    for label in ("not_placed_safe", "rotated_over_30"):
        weights = fit_logistic(train, label)
        scores = [
            sum(w * value for w, value in zip(weights, logistic_design(row)))
            for row in test
        ]
        labels = [label_value(row, label) for row in test]
        best_single = None
        for feature in AUC_FEATURES:
            single = rank_auc(
                [danger_scores(row, feature) for row in test], labels
            )
            if single is not None and (
                best_single is None or single > best_single
            ):
                best_single = single
        report[label] = {
            "test_auc": rank_auc(scores, labels),
            "best_single_feature_test_auc": best_single,
            "weights": [round(w, 3) for w in weights],
        }
    return report


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
        "gate_reasons": gate_reason_report(release_rows),
        "auc": auc_report(release_rows),
        "support_sweep": support_sweep_report(release_rows),
        "logistic_probe": logistic_report(release_rows),
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

    lines.append("## Gate reject reasons (release candidates)")
    lines.append("")
    lines.append("| reason | rejected dangerous (TP) | rejected safe (FP) |")
    lines.append("|---|---:|---:|")
    for reason, entry in result["gate_reasons"].items():
        lines.append(
            f"| {reason} | {entry['rejected_dangerous']} "
            f"| {entry['rejected_safe']} |"
        )
    lines.append("")
    lines.append(
        "Dangerous/safe by `not_placed_safe`; a candidate can carry several "
        "reasons."
    )
    lines.append("")

    lines.append("## Single-feature AUC (higher score = claimed dangerous)")
    lines.append("")
    lines.append("| feature | " + " | ".join(AUC_LABELS) + " |")
    lines.append("|---|" + "---:|" * len(AUC_LABELS))
    for feature in AUC_FEATURES:
        entry = result["auc"].get(feature)
        if not entry:
            continue
        lines.append(
            f"| {feature} | "
            + " | ".join(fmt(entry[label]) for label in AUC_LABELS)
            + " |"
        )
    lines.append("")

    lines.append("## Hard-accept sweep on support_ratio (release candidates)")
    lines.append("")
    lines.append(
        "| min support_ratio | n | weighted share accepted "
        "| not_placed_safe raw/weighted | rotated_over_30 raw/weighted |"
    )
    lines.append("|---:|---:|---:|---:|---:|")
    for entry in result["support_sweep"]:
        lines.append(
            f"| {entry['min_support_ratio']} | {entry['n']} "
            f"| {fmt(entry['weighted_share_accepted'])} "
            f"| {fmt(entry['rate_not_placed_safe'])} / "
            f"{fmt(entry['weighted_rate_not_placed_safe'])} "
            f"| {fmt(entry['rate_rotated_over_30'])} / "
            f"{fmt(entry['weighted_rate_rotated_over_30'])} |"
        )
    lines.append("")

    probe = result["logistic_probe"]
    lines.append("## Logistic separability probe (snapshot-held-out)")
    lines.append("")
    if "skipped" in probe:
        lines.append(f"Skipped: {probe['skipped']}")
    else:
        lines.append(
            f"Train n={probe['train_n']}, test n={probe['test_n']}; "
            f"features: {', '.join(probe['features'])}"
        )
        lines.append("")
        lines.append(
            "| label | test AUC | best single-feature test AUC | weights |"
        )
        lines.append("|---|---:|---:|---|")
        for label in ("not_placed_safe", "rotated_over_30"):
            entry = probe[label]
            lines.append(
                f"| {label} | {fmt(entry['test_auc'])} "
                f"| {fmt(entry['best_single_feature_test_auc'])} "
                f"| {entry['weights']} |"
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
