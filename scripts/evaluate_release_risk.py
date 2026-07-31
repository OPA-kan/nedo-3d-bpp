"""
Uncertainty and counterfactual evaluation for the release-risk analysis.

The first Phi -> Y report (reports/replay-analysis/findings-20260730.md)
was computed on 679 rows clustered in 16 snapshots, so none of its point
estimates carry sampling uncertainty. This script quantifies that and
runs the offline re-ranking the risk model would imply, all on the saved
candidate sets — no new simulator runs:

1. grouped (leave-one-snapshot-out) logistic CV, so every row is scored
   by a model that never saw its snapshot;
2. case- and pool-extrapolation splits (train b000 -> test b001 etc.);
3. snapshot-clustered bootstrap CIs for AUCs and for the danger rates of
   the gate verdicts and the high-support region (which stays a
   "low-risk region", not a safety proof);
4. an offline re-ranking sweep Q_lambda = Q_old - lambda * P_rot using
   the held-out predictions, reporting per-lambda selected rotation
   rate, placed-safe rate, top1-change rate, and score opportunity loss
   per snapshot;
5. horizontal displacement revisited with item attributes joined from
   the saved state snapshots (mass, friction, softness, density...),
   evaluated on continuous d_xy as well as the binary label.

Rows are a stratified sample: the re-ranking argmax runs over the
sampled candidate set (top bands are densely sampled and the originally
selected action is force-included), which approximates but does not
equal the full-population argmax.
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

DEFAULT_DATASET_ROOT = ROOT / "reports" / "replay-dataset"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "replay-analysis"

PHI_FEATURES = (
    "support_ratio",
    "com_margin",
    "drop_normalized",
    "abs_support_imbalance",
    "abs_left_right_imbalance",
    "abs_front_back_imbalance",
)
ITEM_FEATURES = (
    "mass",
    "lateral_friction",
    "restitution",
    "is_soft",
    "density",
    "min_over_max_extent",
)
LAMBDA_GRID = (0.0, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
BOOTSTRAP_ITERATIONS = 1000
BOOTSTRAP_SEED = 20260731


def load_release_rows(
    dataset_dirs: list[pathlib.Path],
    open_final_holdout: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Return (all rows, release rows with phi, step summaries), with item
    attributes joined. Datasets whose manifest carries
    ``split == "final_holdout"`` are skipped unless explicitly opened
    (protocol section 3.1).
    """
    all_rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for directory in dataset_dirs:
        manifest = directory / "manifest.json"
        if not manifest.exists():
            continue
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        if payload.get("status") == "running":
            continue
        split = payload.get("split", "development")
        if split == "final_holdout" and not open_final_holdout:
            print(
                f"skip (final_holdout stays closed): {directory.name}",
                file=sys.stderr,
            )
            continue
        case_payload = payload.get("case")
        if isinstance(case_payload, dict):
            for step_summary in case_payload.get("steps", []):
                if isinstance(step_summary, dict):
                    step_summary = dict(step_summary)
                    step_summary["_dataset_dir"] = directory.name
                    step_summary["_split"] = split
                    summaries.append(step_summary)
        states: dict[str, dict[int, dict[str, Any]]] = {}
        for state_path in directory.glob("step-*-state.json"):
            state = json.loads(state_path.read_text(encoding="utf-8"))
            pool = state.get("observation", {}).get("pool_list", [])
            states[state_path.name] = {
                int(item["index"]): item for item in pool
            }
        for jsonl in sorted(directory.glob("step-*-candidates.jsonl")):
            with jsonl.open(encoding="utf-8") as handle:
                for line in handle:
                    row = json.loads(line)
                    row["_dataset_dir"] = directory.name
                    row["_split"] = split
                    items = states.get(row["snapshot_path"], {})
                    row["_item"] = items.get(int(row["item_index"]))
                    all_rows.append(row)
    release = [
        row
        for row in all_rows
        if row["kind"] == "release_candidate"
        and isinstance(row.get("phi_modelling"), dict)
    ]
    return all_rows, release, summaries


def phi_vector(row: dict[str, Any]) -> list[float]:
    phi = row["phi_modelling"]
    return [
        float(phi["support_ratio"]),
        float(phi["com_margin"]),
        float(phi["drop_normalized"]),
        abs(float(phi["support_imbalance"])),
        abs(float(phi["left_right_imbalance"])),
        abs(float(phi["front_back_imbalance"])),
    ]


def item_vector(row: dict[str, Any]) -> list[float] | None:
    item = row.get("_item")
    if not isinstance(item, dict):
        return None
    length = float(item["length"])
    width = float(item["width"])
    height = float(item["height"])
    volume = max(1e-9, length * width * height)
    extents = sorted((length, width, height))
    return [
        float(item.get("mass", 1.0)),
        float(item.get("lateralFriction", 0.5)),
        float(item.get("restitution", 0.0)),
        1.0 if item.get("is_soft") else 0.0,
        float(item.get("mass", 1.0)) / volume,
        extents[0] / max(1e-9, extents[2]),
    ]


def label_of(row: dict[str, Any], label: str) -> bool:
    return bool(row["physical"]["Y"][label])


def rank_auc(scores: np.ndarray, labels: np.ndarray) -> float | None:
    labels = labels.astype(bool)
    positives = int(labels.sum())
    negatives = int(len(labels) - positives)
    if positives == 0 or negatives == 0:
        return None
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(len(scores), dtype=np.float64)
    sorted_scores = scores[order]
    i = 0
    while i < len(scores):
        j = i
        while (
            j + 1 < len(scores)
            and sorted_scores[j + 1] == sorted_scores[i]
        ):
            j += 1
        ranks[order[i: j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    positive_rank_sum = float(ranks[labels].sum())
    return (
        positive_rank_sum - positives * (positives + 1) / 2.0
    ) / (positives * negatives)


def fit_logistic_np(
    features: np.ndarray,
    targets: np.ndarray,
    epochs: int = 3000,
    learning_rate: float = 0.5,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Standardize, fit with batch GD; return (weights, mean, scale)."""
    mean = features.mean(axis=0)
    scale = features.std(axis=0)
    scale[scale <= 1e-12] = 1.0
    standardized = (features - mean) / scale
    design = np.hstack(
        [np.ones((len(standardized), 1)), standardized]
    )
    weights = np.zeros(design.shape[1])
    for _ in range(epochs):
        z = np.clip(design @ weights, -30.0, 30.0)
        gradient = design.T @ (1.0 / (1.0 + np.exp(-z)) - targets)
        weights -= learning_rate * gradient / len(design)
    return weights, mean, scale


def predict_logistic_np(
    features: np.ndarray,
    weights: np.ndarray,
    mean: np.ndarray,
    scale: np.ndarray,
) -> np.ndarray:
    standardized = (features - mean) / scale
    design = np.hstack(
        [np.ones((len(standardized), 1)), standardized]
    )
    z = np.clip(design @ weights, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-z))


def leave_one_group_out_predictions(
    features: np.ndarray,
    targets: np.ndarray,
    groups: list[str],
) -> np.ndarray:
    """Held-out probability for every row, trained without its group."""
    predictions = np.full(len(targets), np.nan)
    for group in sorted(set(groups)):
        holdout = np.array([g == group for g in groups])
        train = ~holdout
        if targets[train].sum() == 0 or targets[train].sum() == train.sum():
            predictions[holdout] = float(targets[train].mean())
            continue
        weights, mean, scale = fit_logistic_np(
            features[train], targets[train]
        )
        predictions[holdout] = predict_logistic_np(
            features[holdout], weights, mean, scale
        )
    return predictions


def clustered_bootstrap_auc(
    scores: np.ndarray,
    labels: np.ndarray,
    groups: list[str],
    iterations: int = BOOTSTRAP_ITERATIONS,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Resample snapshots with replacement; AUC over pooled rows."""
    rng = np.random.default_rng(seed)
    unique = sorted(set(groups))
    by_group = {
        group: np.array([g == group for g in groups]) for group in unique
    }
    values = []
    for _ in range(iterations):
        chosen = rng.choice(unique, size=len(unique), replace=True)
        index_arrays = [np.flatnonzero(by_group[g]) for g in chosen]
        pooled = np.concatenate(index_arrays)
        auc = rank_auc(scores[pooled], labels[pooled])
        if auc is not None:
            values.append(auc)
    if not values:
        return {"point": rank_auc(scores, labels)}
    array = np.asarray(values)
    return {
        "point": rank_auc(scores, labels),
        "bootstrap_n": len(values),
        "ci_2.5": float(np.percentile(array, 2.5)),
        "ci_97.5": float(np.percentile(array, 97.5)),
    }


def clustered_bootstrap_rate(
    flags: np.ndarray,
    weights: np.ndarray,
    groups: list[str],
    iterations: int = BOOTSTRAP_ITERATIONS,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Weighted rate with snapshot-clustered bootstrap CI."""
    rng = np.random.default_rng(seed)
    unique = sorted(set(groups))
    by_group = {
        group: np.array([g == group for g in groups]) for group in unique
    }
    point = (
        float((flags * weights).sum() / weights.sum())
        if weights.sum() > 0
        else None
    )
    values = []
    for _ in range(iterations):
        chosen = rng.choice(unique, size=len(unique), replace=True)
        pooled = np.concatenate(
            [np.flatnonzero(by_group[g]) for g in chosen]
        )
        total = weights[pooled].sum()
        if total > 0:
            values.append(
                float((flags[pooled] * weights[pooled]).sum() / total)
            )
    if not values:
        return {"point": point, "n": int(len(flags))}
    array = np.asarray(values)
    return {
        "point": point,
        "n": int(len(flags)),
        "raw_positives": int(flags.sum()),
        "ci_2.5": float(np.percentile(array, 2.5)),
        "ci_97.5": float(np.percentile(array, 97.5)),
    }


def extrapolation_report(
    features: np.ndarray,
    targets: np.ndarray,
    case_ids: list[str],
    splitter,
) -> dict[str, Any]:
    """
    Leave-one-side-out extrapolation: for every side of the split, train
    on all other sides and test on the held-out one. With two sides this
    is the original both-ways split; with more (several pools) each side
    still gets a genuine out-of-side test.
    """
    sides = sorted({splitter(case) for case in case_ids})
    report: dict[str, Any] = {}
    if len(sides) < 2:
        return {f"test_{sides[0]}": {"skipped": "single side"}} if sides else {}
    for test_side in sides:
        test = np.array(
            [splitter(case) == test_side for case in case_ids]
        )
        train = ~test
        if targets[train].sum() in (0, train.sum()):
            report[f"test_{test_side}"] = {"skipped": "one-class train"}
            continue
        weights, mean, scale = fit_logistic_np(
            features[train], targets[train]
        )
        scores = predict_logistic_np(
            features[test], weights, mean, scale
        )
        report[f"test_{test_side}"] = {
            "train_n": int(train.sum()),
            "test_n": int(test.sum()),
            "test_auc": rank_auc(scores, targets[test]),
        }
    return report


def rerank_sweep(
    all_rows: list[dict[str, Any]],
    release_predictions: dict[tuple[str, str], float],
) -> list[dict[str, Any]]:
    """
    Offline Q_lambda = Q_old - lambda * P_rot, restricted to each
    snapshot's sampled *release* candidates: that is the population the
    risk model scores, and the live selection rule (settled preference,
    lookahead) is not reproducible from rows alone. The lambda = 0 line
    is the score-argmax baseline the deltas are measured against; the
    change rate against the policy's actual selection is only reported
    for snapshots whose original selection was itself a release
    candidate.
    """
    snapshots: dict[str, list[dict[str, Any]]] = {}
    originals: dict[str, dict[str, Any]] = {}
    for row in all_rows:
        if row.get("selected"):
            originals[row["snapshot_id"]] = row
        if (
            row["kind"] == "release_candidate"
            and isinstance(row.get("phi_modelling"), dict)
            and row.get("score_immediate") is not None
        ):
            snapshots.setdefault(row["snapshot_id"], []).append(row)

    sweep = []
    for lam in LAMBDA_GRID:
        selected_rotated = 0
        selected_unsafe = 0
        changed_vs_baseline = 0
        changed_vs_original = 0
        original_release_snapshots = 0
        losses = []
        risks = []
        evaluated = 0
        for snapshot_id, rows in sorted(snapshots.items()):
            scores = [
                float(row["score_immediate"])
                - lam
                * release_predictions.get(
                    (snapshot_id, row["candidate_id"]), 0.0
                )
                for row in rows
            ]
            best_row = rows[int(np.argmax(scores))]
            baseline_row = rows[
                int(
                    np.argmax(
                        [float(row["score_immediate"]) for row in rows]
                    )
                )
            ]
            evaluated += 1
            if label_of(best_row, "rotated_over_30"):
                selected_rotated += 1
            if label_of(best_row, "not_placed_safe"):
                selected_unsafe += 1
            if best_row["candidate_id"] != baseline_row["candidate_id"]:
                changed_vs_baseline += 1
            original = originals.get(snapshot_id)
            if (
                original is not None
                and original["kind"] == "release_candidate"
            ):
                original_release_snapshots += 1
                if original["candidate_id"] != best_row["candidate_id"]:
                    changed_vs_original += 1
            losses.append(
                float(baseline_row["score_immediate"])
                - float(best_row["score_immediate"])
            )
            risks.append(
                release_predictions.get(
                    (snapshot_id, best_row["candidate_id"]), 0.0
                )
            )
        sweep.append(
            {
                "lambda": lam,
                "snapshots": evaluated,
                "selected_rotated_over_30": selected_rotated,
                "selected_not_placed_safe": selected_unsafe,
                "changed_vs_score_argmax": changed_vs_baseline,
                "original_release_snapshots": original_release_snapshots,
                "changed_vs_original_release_selection": changed_vs_original,
                "mean_selected_p_rot": float(np.mean(risks)),
                "mean_score_opportunity_loss": float(np.mean(losses)),
                "median_score_opportunity_loss": float(np.median(losses)),
                "max_score_opportunity_loss": float(np.max(losses)),
            }
        )
    return sweep


def shadow_pair_report(
    summaries: list[dict[str, Any]],
    all_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Counterfactual pair comparison on changed snapshots: for every step
    where the shadow rerank chose a different candidate than the policy,
    join both force-included rows and compare their physical labels.
    These are the protocol's primary adoption metrics: rotation danger
    difference, placed-safe difference, and safe -> dangerous reversals.
    """
    rows_by_id: dict[tuple[str, str], dict[str, Any]] = {
        (row["snapshot_id"], row["candidate_id"]): row for row in all_rows
    }
    pairs = []
    changed_total = 0
    unmatched = 0
    for summary in summaries:
        pair = summary.get("shadow_pair")
        if not isinstance(pair, dict) or not pair.get("changed"):
            continue
        changed_total += 1
        snapshot_id = summary.get("snapshot_id")
        baseline = rows_by_id.get(
            (snapshot_id, pair.get("baseline_candidate_id"))
        )
        shadow = rows_by_id.get(
            (snapshot_id, pair.get("shadow_candidate_id"))
        )
        if (
            baseline is None
            or shadow is None
            or not isinstance(baseline.get("physical"), dict)
            or not isinstance(shadow.get("physical"), dict)
        ):
            unmatched += 1
            continue
        pairs.append(
            {
                "snapshot_id": snapshot_id,
                "split": summary.get("_split"),
                "baseline_rotated": label_of(baseline, "rotated_over_30"),
                "shadow_rotated": label_of(shadow, "rotated_over_30"),
                "baseline_unsafe": label_of(baseline, "not_placed_safe"),
                "shadow_unsafe": label_of(shadow, "not_placed_safe"),
                "score_loss": (
                    float(baseline.get("score_immediate", 0.0))
                    - float(shadow.get("score_immediate", 0.0))
                ),
            }
        )
    baseline_rotated = sum(1 for p in pairs if p["baseline_rotated"])
    shadow_rotated = sum(1 for p in pairs if p["shadow_rotated"])
    baseline_unsafe = sum(1 for p in pairs if p["baseline_unsafe"])
    shadow_unsafe = sum(1 for p in pairs if p["shadow_unsafe"])
    safe_to_dangerous = sum(
        1
        for p in pairs
        if not p["baseline_unsafe"] and p["shadow_unsafe"]
    )
    dangerous_to_safe = sum(
        1
        for p in pairs
        if p["baseline_unsafe"] and not p["shadow_unsafe"]
    )
    return {
        "changed_snapshots": changed_total,
        "labelled_pairs": len(pairs),
        "unmatched_pairs": unmatched,
        "rotation_danger_difference": baseline_rotated - shadow_rotated,
        "baseline_rotated": baseline_rotated,
        "shadow_rotated": shadow_rotated,
        "placed_safe_difference": baseline_unsafe - shadow_unsafe,
        "baseline_not_placed_safe": baseline_unsafe,
        "shadow_not_placed_safe": shadow_unsafe,
        "safe_to_dangerous_reversals": safe_to_dangerous,
        "dangerous_to_safe_conversions": dangerous_to_safe,
        "mean_pair_score_loss": (
            float(np.mean([p["score_loss"] for p in pairs]))
            if pairs
            else None
        ),
        "pairs": pairs,
    }


def spearman_np(x: np.ndarray, y: np.ndarray) -> float | None:
    if len(x) < 3:
        return None

    def ranks(values: np.ndarray) -> np.ndarray:
        order = np.argsort(values, kind="mergesort")
        out = np.empty(len(values), dtype=np.float64)
        sorted_values = values[order]
        i = 0
        while i < len(values):
            j = i
            while (
                j + 1 < len(values)
                and sorted_values[j + 1] == sorted_values[i]
            ):
                j += 1
            out[order[i: j + 1]] = (i + j) / 2.0 + 1.0
            i = j + 1
        return out

    rx = ranks(x)
    ry = ranks(y)
    rx -= rx.mean()
    ry -= ry.mean()
    denominator = float(np.sqrt((rx**2).sum() * (ry**2).sum()))
    if denominator <= 0:
        return None
    return float((rx * ry).sum() / denominator)


def dxy_report(release_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Continuous d_xy and the binary slide label, phi vs phi+item."""
    rows = [row for row in release_rows if item_vector(row) is not None]
    if len(rows) < 30:
        return {"skipped": "not enough rows with item attributes"}
    groups = [row["snapshot_id"] for row in rows]
    phi = np.array([phi_vector(row) for row in rows])
    item = np.array([item_vector(row) for row in rows])
    both = np.hstack([phi, item])
    d_xy = np.array(
        [float(row["physical"]["d_xy"]) for row in rows]
    )
    binary = np.array(
        [
            label_of(row, "horizontal_displaced_over_half_footprint")
            for row in rows
        ],
        dtype=float,
    )

    univariate = {}
    names = list(PHI_FEATURES) + list(ITEM_FEATURES)
    for name, column in zip(names, np.hstack([phi, item]).T):
        univariate[name] = spearman_np(column, d_xy)

    report: dict[str, Any] = {
        "n": len(rows),
        "univariate_spearman_d_xy": univariate,
    }
    for label, features in (("phi_only", phi), ("phi_plus_item", both)):
        predictions = leave_one_group_out_predictions(
            features, binary, groups
        )
        report[f"binary_loso_auc_{label}"] = clustered_bootstrap_auc(
            predictions, binary.astype(bool), groups
        )
        held_out_regression = np.full(len(rows), np.nan)
        target = np.log1p(d_xy)
        for group in sorted(set(groups)):
            holdout = np.array([g == group for g in groups])
            train = ~holdout
            mean = features[train].mean(axis=0)
            scale = features[train].std(axis=0)
            scale[scale <= 1e-12] = 1.0
            design_train = np.hstack(
                [
                    np.ones((int(train.sum()), 1)),
                    (features[train] - mean) / scale,
                ]
            )
            design_test = np.hstack(
                [
                    np.ones((int(holdout.sum()), 1)),
                    (features[holdout] - mean) / scale,
                ]
            )
            coefficients, *_ = np.linalg.lstsq(
                design_train, target[train], rcond=None
            )
            held_out_regression[holdout] = design_test @ coefficients
        report[f"continuous_loso_spearman_{label}"] = spearman_np(
            held_out_regression, d_xy
        )
    return report


def evaluate(
    dataset_dirs: list[pathlib.Path],
    open_final_holdout: bool = False,
) -> dict[str, Any]:
    all_rows, release, summaries = load_release_rows(
        dataset_dirs, open_final_holdout=open_final_holdout
    )
    groups = [row["snapshot_id"] for row in release]
    features = np.array([phi_vector(row) for row in release])
    weights = np.array(
        [float(row["sampling"]["sampling_weight"]) for row in release]
    )
    case_ids = [row["case_id"] for row in release]

    result: dict[str, Any] = {
        "rows": len(all_rows),
        "release_rows": len(release),
        "snapshots": len(set(groups)),
        "lambda_grid": list(LAMBDA_GRID),
    }

    loso_predictions: dict[str, np.ndarray] = {}
    for label in ("rotated_over_30", "not_placed_safe"):
        targets = np.array(
            [label_of(row, label) for row in release], dtype=float
        )
        predictions = leave_one_group_out_predictions(
            features, targets, groups
        )
        loso_predictions[label] = predictions
        result[f"loso_auc_{label}"] = clustered_bootstrap_auc(
            predictions, targets.astype(bool), groups
        )
        result[f"extrapolation_case_{label}"] = extrapolation_report(
            features,
            targets,
            case_ids,
            lambda case: case.split("-")[0],
        )
        result[f"extrapolation_pool_{label}"] = extrapolation_report(
            features,
            targets,
            case_ids,
            lambda case: case.split("-")[1],
        )

    for label in ("rotated_over_30", "not_placed_safe"):
        flags = np.array(
            [label_of(row, label) for row in release], dtype=float
        )
        segments: dict[str, np.ndarray] = {
            "all_release": np.ones(len(release), dtype=bool),
            "gate_pass": np.array(
                [row.get("gate_passed") is True for row in release]
            ),
            "gate_reject": np.array(
                [row.get("gate_passed") is False for row in release]
            ),
            "support_ratio_ge_0.6": np.array(
                [
                    float(row["phi_modelling"]["support_ratio"]) >= 0.6
                    for row in release
                ]
            ),
        }
        for segment_name, mask in segments.items():
            key = f"rate_{label}__{segment_name}"
            if mask.sum() == 0:
                result[key] = {"skipped": "empty segment"}
                continue
            result[key] = clustered_bootstrap_rate(
                flags[mask],
                weights[mask],
                [g for g, keep in zip(groups, mask) if keep],
            )

    rotation_predictions = {
        (row["snapshot_id"], row["candidate_id"]): float(pred)
        for row, pred in zip(release, loso_predictions["rotated_over_30"])
    }
    result["rerank_sweep"] = rerank_sweep(all_rows, rotation_predictions)
    result["shadow_pairs"] = shadow_pair_report(summaries, all_rows)
    result["d_xy"] = dxy_report(release)
    result["splits"] = dict(
        sorted(
            {
                row["_split"]: sum(
                    1 for r in all_rows if r["_split"] == row["_split"]
                )
                for row in all_rows
            }.items()
        )
    )
    return result


def fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Release risk: uncertainty and offline re-ranking evaluation",
        "",
        f"- rows: {result['rows']} (release: {result['release_rows']}) "
        f"in {result['snapshots']} snapshots",
        "- All CIs are snapshot-clustered bootstrap "
        f"({BOOTSTRAP_ITERATIONS} iterations, percentile 2.5/97.5).",
        "- Predictions are leave-one-snapshot-out: no row is scored by a "
        "model that saw its snapshot.",
        "",
        "## Grouped-CV AUC with uncertainty",
        "",
        "| label | LOSO AUC | 95% CI |",
        "|---|---:|---|",
    ]
    for label in ("rotated_over_30", "not_placed_safe"):
        entry = result[f"loso_auc_{label}"]
        lines.append(
            f"| {label} | {fmt(entry.get('point'))} "
            f"| [{fmt(entry.get('ci_2.5'))}, {fmt(entry.get('ci_97.5'))}] |"
        )
    lines.append("")

    lines.append("## Extrapolation splits")
    lines.append("")
    lines.append("| label | split | direction | train n | test n | AUC |")
    lines.append("|---|---|---|---:|---:|---:|")
    for label in ("rotated_over_30", "not_placed_safe"):
        for split in ("case", "pool"):
            report = result[f"extrapolation_{split}_{label}"]
            for direction, entry in sorted(report.items()):
                if not isinstance(entry, dict) or "skipped" in entry:
                    reason = (
                        entry.get("skipped")
                        if isinstance(entry, dict)
                        else str(entry)
                    )
                    lines.append(
                        f"| {label} | {split} | {direction} | - | - "
                        f"| {reason} |"
                    )
                else:
                    lines.append(
                        f"| {label} | {split} | {direction} "
                        f"| {entry['train_n']} | {entry['test_n']} "
                        f"| {fmt(entry['test_auc'])} |"
                    )
    lines.append("")

    lines.append("## Danger rates with uncertainty (weighted)")
    lines.append("")
    lines.append("| label | segment | n | raw+ | rate | 95% CI |")
    lines.append("|---|---|---:|---:|---:|---|")
    for label in ("rotated_over_30", "not_placed_safe"):
        for segment in (
            "all_release",
            "gate_pass",
            "gate_reject",
            "support_ratio_ge_0.6",
        ):
            entry = result[f"rate_{label}__{segment}"]
            if "skipped" in entry:
                continue
            lines.append(
                f"| {label} | {segment} | {entry['n']} "
                f"| {entry.get('raw_positives', '-')} "
                f"| {fmt(entry['point'])} "
                f"| [{fmt(entry.get('ci_2.5'))}, "
                f"{fmt(entry.get('ci_97.5'))}] |"
            )
    lines.append("")
    lines.append(
        "`support_ratio_ge_0.6` is a low-risk *region estimate*, not a "
        "safety proof; its CI is the thing to read."
    )
    lines.append("")

    lines.append(
        "## Offline re-ranking sweep over release candidates "
        "(Q_old - lambda * P_rot)"
    )
    lines.append("")
    lines.append(
        "| lambda | snapshots | selected rotated | selected unsafe "
        "| changed vs score-argmax | changed vs original release sel. "
        "| mean P_rot of selection | mean score loss | median | max |"
    )
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for entry in result["rerank_sweep"]:
        lines.append(
            f"| {entry['lambda']} | {entry['snapshots']} "
            f"| {entry['selected_rotated_over_30']} "
            f"| {entry['selected_not_placed_safe']} "
            f"| {entry['changed_vs_score_argmax']} "
            f"| {entry['changed_vs_original_release_selection']}"
            f"/{entry['original_release_snapshots']} "
            f"| {fmt(entry['mean_selected_p_rot'])} "
            f"| {fmt(entry['mean_score_opportunity_loss'])} "
            f"| {fmt(entry['median_score_opportunity_loss'])} "
            f"| {fmt(entry['max_score_opportunity_loss'])} |"
        )
    lines.append("")
    lines.append(
        "Restricted to sampled release candidates (the population the "
        "risk model scores); the live settled-preference and lookahead "
        "are not reproduced here. P_rot is the leave-one-snapshot-out "
        "prediction, so no selection is scored by a model that saw its "
        "snapshot."
    )
    lines.append("")

    pairs = result.get("shadow_pairs", {})
    lines.append("## Counterfactual pairs on changed snapshots (primary)")
    lines.append("")
    lines.append(
        f"- changed snapshots: {pairs.get('changed_snapshots', 0)} "
        f"(labelled pairs: {pairs.get('labelled_pairs', 0)}, "
        f"unmatched: {pairs.get('unmatched_pairs', 0)})"
    )
    lines.append(
        f"- rotation danger difference (baseline - shadow): "
        f"{pairs.get('rotation_danger_difference')} "
        f"(baseline {pairs.get('baseline_rotated')} vs shadow "
        f"{pairs.get('shadow_rotated')})"
    )
    lines.append(
        f"- placed-safe difference: {pairs.get('placed_safe_difference')} "
        f"(not_placed_safe baseline "
        f"{pairs.get('baseline_not_placed_safe')} vs shadow "
        f"{pairs.get('shadow_not_placed_safe')})"
    )
    lines.append(
        f"- safe -> dangerous reversals: "
        f"{pairs.get('safe_to_dangerous_reversals')} "
        f"(dangerous -> safe: "
        f"{pairs.get('dangerous_to_safe_conversions')})"
    )
    lines.append(
        f"- mean pair score loss: {fmt(pairs.get('mean_pair_score_loss'))}"
    )
    lines.append("")

    dxy = result["d_xy"]
    lines.append("## Horizontal displacement with item attributes")
    lines.append("")
    if "skipped" in dxy:
        lines.append(f"Skipped: {dxy['skipped']}")
        return "\n".join(lines) + "\n"
    lines.append(f"Rows with joined item attributes: {dxy['n']}")
    lines.append("")
    lines.append("| feature | Spearman vs d_xy |")
    lines.append("|---|---:|")
    for name, value in dxy["univariate_spearman_d_xy"].items():
        lines.append(f"| {name} | {fmt(value)} |")
    lines.append("")
    lines.append("| model | binary LOSO AUC | 95% CI | continuous LOSO Spearman |")
    lines.append("|---|---:|---|---:|")
    for label in ("phi_only", "phi_plus_item"):
        entry = dxy[f"binary_loso_auc_{label}"]
        lines.append(
            f"| {label} | {fmt(entry.get('point'))} "
            f"| [{fmt(entry.get('ci_2.5'))}, {fmt(entry.get('ci_97.5'))}] "
            f"| {fmt(dxy[f'continuous_loso_spearman_{label}'])} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset-root",
        type=pathlib.Path,
        default=DEFAULT_DATASET_ROOT,
    )
    parser.add_argument(
        "--dataset", type=pathlib.Path, nargs="*",
        help="Explicit dataset directories (overrides --dataset-root).",
    )
    parser.add_argument(
        "--output-dir", type=pathlib.Path, default=DEFAULT_OUTPUT_DIR
    )
    parser.add_argument(
        "--open-final-holdout",
        action="store_true",
        help=(
            "Include final_holdout datasets. ONLY for the one-shot final "
            "evaluation of docs/RELEASE_RISK_PROTOCOL.md section 7."
        ),
    )
    args = parser.parse_args()
    if args.dataset:
        dataset_dirs = list(args.dataset)
    else:
        dataset_dirs = sorted(
            path for path in args.dataset_root.iterdir() if path.is_dir()
        )
    if args.open_final_holdout:
        print(
            "WARNING: final_holdout datasets are being opened; this is "
            "only legitimate for the one-shot final evaluation.",
            file=sys.stderr,
        )
    result = evaluate(
        dataset_dirs, open_final_holdout=args.open_final_holdout
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "risk-evaluation.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    markdown_path = args.output_dir / "risk-evaluation.md"
    markdown_path.write_text(render_markdown(result), encoding="utf-8")
    print(markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
