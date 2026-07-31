"""
S0 of the slide ladder: an equivariant local-frame model for d_xy.

Premise (evidence: slide-direction-downhill): large slides go downhill
-- toward the CoM offset from the support centroid -- so direction is
predictable from the pre-release contact state. The historical d_xy
attempts discarded direction by using invariant scalars. Here every
row gets a canonical local frame (longitudinal axis u = CoM-offset
direction), mirror symmetry holds by construction (all features are
invariant under reflection about u; the transverse target flips), and
the model predicts the SIGNED longitudinal displacement plus the
magnitude.

Frozen-protocol reporting: LOSO by snapshot, leave-one-side-out
extrapolation (case and pool), the invariant-scalar baseline
co-reported, no new physics.
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

import scripts.evaluate_release_risk as err  # noqa: E402
import scripts.evaluate_mechanics_features as emf  # noqa: E402

DEFAULT_DATASET_ROOT = ROOT / "reports" / "replay-dataset"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "replay-analysis"
LARGE_SLIDE_METERS = 0.30
DIRECTION_MIN_METERS = 0.05
RIDGE_ALPHA = 1.0

EQUIVARIANT_FEATURES = (
    "com_offset",
    "downhill_margin",
    "uphill_margin",
    "d_min",
    "B_min",
    "log1p_eta_max",
    "drop_meters",
    "support_ratio",
    "mass",
    "lateral_friction",
    "density",
    "is_soft",
)


def support_centroid(
    patches: list[dict[str, Any]],
) -> tuple[float, float] | None:
    """Area-weighted centroid of the predicted contact patches."""
    total = 0.0
    sx = 0.0
    sy = 0.0
    for patch in patches:
        xs = [c[0] for c in patch["corners"]]
        ys = [c[1] for c in patch["corners"]]
        area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        if area <= 0.0:
            continue
        total += area
        sx += area * (min(xs) + max(xs)) / 2.0
        sy += area * (min(ys) + max(ys)) / 2.0
    if total <= 0.0:
        return None
    return sx / total, sy / total


def ray_hull_margin(
    hull: list[tuple[float, float]],
    point: tuple[float, float],
    direction: tuple[float, float],
) -> float:
    """
    Distance from point to the hull boundary along +direction; 0 when
    the hull is degenerate or the ray never crosses it (point outside).
    """
    if len(hull) < 3:
        return 0.0
    px, py = point
    ux, uy = direction
    best = None
    for index, start in enumerate(hull):
        end = hull[(index + 1) % len(hull)]
        ex, ey = end[0] - start[0], end[1] - start[1]
        denominator = ux * ey - uy * ex
        if abs(denominator) < 1e-12:
            continue
        # point + t*u = start + s*(end-start)
        t = ((start[0] - px) * ey - (start[1] - py) * ex) / denominator
        s = ((start[0] - px) * uy - (start[1] - py) * ux) / denominator
        if t >= 0.0 and -1e-9 <= s <= 1.0 + 1e-9:
            if best is None or t < best:
                best = t
    return float(best) if best is not None else 0.0


def frame_row(
    agent,
    row: dict[str, Any],
    container: dict[str, Any],
) -> dict[str, Any] | None:
    settle = row["physical"].get("settle_metrics")
    if not settle:
        return None
    item = row.get("_item")
    if not isinstance(item, dict):
        return None
    x, y, z_command = (float(v) for v in row["center"])
    dims = tuple(float(v) for v in row["size"])
    z_rest = float(agent.release_rest_height(x, y, dims, container))
    patches = emf.contact_patches(agent, container, x, y, dims, z_rest)
    centroid = support_centroid(patches)
    if centroid is None:
        return None
    ex, ey = x - centroid[0], y - centroid[1]
    offset = math.hypot(ex, ey)
    if offset < 1e-9:
        ux, uy = 1.0, 0.0
        degenerate_frame = True
    else:
        ux, uy = ex / offset, ey / offset
        degenerate_frame = False

    corner_tops: dict[tuple[float, float], float] = {}
    for patch in patches:
        for corner in patch["corners"]:
            previous = corner_tops.get(corner)
            if previous is None or patch["top"] > previous:
                corner_tops[corner] = patch["top"]
    hull = emf.convex_hull(list(corner_tops))

    mech = row.get("_mech")
    if mech is None:
        mech = emf.mechanics_features(agent, container, x, y, z_command, dims)

    phi = row["phi_modelling"]
    volume = max(1e-9, dims[0] * dims[1] * dims[2])
    dx, dy = (
        float(settle["settle_displacement_xyz"][0]),
        float(settle["settle_displacement_xyz"][1]),
    )
    magnitude = math.hypot(dx, dy)
    return {
        "features": {
            "com_offset": offset,
            "downhill_margin": ray_hull_margin(hull, (x, y), (ux, uy)),
            "uphill_margin": ray_hull_margin(hull, (x, y), (-ux, -uy)),
            "d_min": float(mech["d_min"]),
            "B_min": float(mech["B_min"]),
            "log1p_eta_max": float(mech["log1p_eta_max"]),
            "drop_meters": float(mech["drop_meters"]),
            "support_ratio": float(phi["support_ratio"]),
            "mass": float(item.get("mass", 1.0)),
            "lateral_friction": float(item.get("lateralFriction", 0.5)),
            "density": float(item.get("mass", 1.0)) / volume,
            "is_soft": 1.0 if item.get("is_soft") else 0.0,
        },
        "d_long": dx * ux + dy * uy,
        "d_trans": -dx * uy + dy * ux,
        "d_mag": magnitude,
        "degenerate_frame": degenerate_frame,
        "snapshot_id": row["snapshot_id"],
        "case_side": row["case_id"].split("-")[0],
        "pool_side": row["case_id"].split("-")[1],
    }


def prepare(dataset_dirs: list[pathlib.Path]) -> list[dict[str, Any]]:
    agent = emf.load_agent_module()
    _all_rows, release, _summaries = err.load_release_rows(dataset_dirs)
    containers = emf.load_containers(dataset_dirs)
    rows = []
    for row in release:
        container = containers.get(
            (row["_dataset_dir"], row["snapshot_path"])
        )
        if container is None:
            continue
        framed = frame_row(agent, row, container)
        if framed is not None:
            framed["_source"] = row
            rows.append(framed)
    return rows


def ridge_loso(
    features: np.ndarray,
    targets: np.ndarray,
    groups: list[str],
    alpha: float = RIDGE_ALPHA,
) -> np.ndarray:
    """Held-out predictions: standardized ridge, leave-one-group-out."""
    predictions = np.zeros(len(targets))
    unique = sorted(set(groups))
    group_array = np.array(groups)
    for group in unique:
        mask = group_array == group
        train_x, train_y = features[~mask], targets[~mask]
        mean = train_x.mean(axis=0)
        scale = train_x.std(axis=0)
        scale[scale <= 1e-12] = 1.0
        design = (train_x - mean) / scale
        gram = design.T @ design + alpha * np.eye(design.shape[1])
        weights = np.linalg.solve(gram, design.T @ (train_y - train_y.mean()))
        held = (features[mask] - mean) / scale
        predictions[mask] = held @ weights + train_y.mean()
    return predictions


def side_extrapolation(
    features: np.ndarray,
    targets: np.ndarray,
    sides: list[str],
    alpha: float = RIDGE_ALPHA,
) -> dict[str, float | None]:
    report: dict[str, float | None] = {}
    side_array = np.array(sides)
    for side in sorted(set(sides)):
        mask = side_array == side
        if mask.all() or not mask.any():
            continue
        train_x, train_y = features[~mask], targets[~mask]
        mean = train_x.mean(axis=0)
        scale = train_x.std(axis=0)
        scale[scale <= 1e-12] = 1.0
        design = (train_x - mean) / scale
        gram = design.T @ design + alpha * np.eye(design.shape[1])
        weights = np.linalg.solve(gram, design.T @ (train_y - train_y.mean()))
        held = (features[mask] - mean) / scale
        prediction = held @ weights + train_y.mean()
        report[side] = err.spearman_np(prediction, targets[mask])
    return report


def evaluate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups = [r["snapshot_id"] for r in rows]
    equivariant = np.array(
        [[r["features"][k] for k in EQUIVARIANT_FEATURES] for r in rows]
    )
    invariant_baseline = np.array(
        [
            err.phi_vector(r["_source"])
            + (err.item_vector(r["_source"]) or [0.0] * 6)
            for r in rows
        ]
    )
    d_mag = np.array([r["d_mag"] for r in rows])
    d_long = np.array([r["d_long"] for r in rows])
    d_trans = np.array([r["d_trans"] for r in rows])

    result: dict[str, Any] = {
        "rows": len(rows),
        "snapshots": len(set(groups)),
        "degenerate_frames": int(
            sum(r["degenerate_frame"] for r in rows)
        ),
        "feature_order": list(EQUIVARIANT_FEATURES),
        "transverse_mean_abs": float(np.abs(d_trans).mean()),
        "longitudinal_mean_abs": float(np.abs(d_long).mean()),
    }

    for name, features in (
        ("invariant_baseline", invariant_baseline),
        ("equivariant", equivariant),
    ):
        entry: dict[str, Any] = {}
        pred_mag = ridge_loso(features, d_mag, groups)
        entry["loso_spearman_magnitude"] = err.spearman_np(pred_mag, d_mag)
        pred_long = ridge_loso(features, d_long, groups)
        entry["loso_spearman_longitudinal"] = err.spearman_np(
            pred_long, d_long
        )
        moving = d_mag > DIRECTION_MIN_METERS
        if moving.any():
            entry["direction_accuracy_moving"] = float(
                (np.sign(pred_long[moving]) == np.sign(d_long[moving]))
                .mean()
            )
        large = (d_mag > LARGE_SLIDE_METERS).astype(float)
        weights_l, mean_l, scale_l = err.fit_logistic_np(features, large)
        entry["large_slide_auc_insample"] = err.rank_auc(
            err.predict_logistic_np(features, weights_l, mean_l, scale_l),
            large.astype(bool),
        )
        pred_large = err.leave_one_group_out_predictions(
            features, large, groups
        )
        entry["large_slide_auc_loso"] = err.rank_auc(
            pred_large, large.astype(bool)
        )
        entry["extrapolation_case"] = side_extrapolation(
            features, d_mag, [r["case_side"] for r in rows]
        )
        entry["extrapolation_pool"] = side_extrapolation(
            features, d_mag, [r["pool_side"] for r in rows]
        )
        result[name] = entry

    # The zero-parameter geometric prior: always predict downhill.
    moving = d_mag > DIRECTION_MIN_METERS
    result["downhill_prior_direction_accuracy"] = float(
        (d_long[moving] > 0).mean()
    ) if moving.any() else None
    return result


def fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Slide S0: equivariant local-frame model vs invariant baseline",
        "",
        f"- rows {result['rows']} in {result['snapshots']} snapshots; "
        f"degenerate frames {result['degenerate_frames']}",
        f"- mean |longitudinal| {fmt(result['longitudinal_mean_abs'])} m "
        f"vs mean |transverse| {fmt(result['transverse_mean_abs'])} m "
        "(mirror symmetry predicts small transverse)",
        f"- downhill prior alone gets "
        f"{fmt(result['downhill_prior_direction_accuracy'])} direction "
        "accuracy on moving rows",
        "",
        "| metric | invariant baseline | equivariant |",
        "|---|---:|---:|",
    ]
    metric_names = (
        ("loso_spearman_magnitude", "LOSO Spearman |d_xy|"),
        ("loso_spearman_longitudinal", "LOSO Spearman d_long"),
        ("direction_accuracy_moving", "direction accuracy (moving)"),
        ("large_slide_auc_loso", "large-slide AUC (LOSO)"),
    )
    for key, label in metric_names:
        lines.append(
            f"| {label} "
            f"| {fmt(result['invariant_baseline'].get(key))} "
            f"| {fmt(result['equivariant'].get(key))} |"
        )
    for side_key in ("extrapolation_case", "extrapolation_pool"):
        for side, value in sorted(
            result["equivariant"][side_key].items()
        ):
            base = result["invariant_baseline"][side_key].get(side)
            lines.append(
                f"| extrapolation {side} (Spearman |d|) "
                f"| {fmt(base)} | {fmt(value)} |"
            )
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset-root", type=pathlib.Path, default=DEFAULT_DATASET_ROOT
    )
    parser.add_argument(
        "--output-dir", type=pathlib.Path, default=DEFAULT_OUTPUT_DIR
    )
    args = parser.parse_args()
    dataset_dirs = sorted(
        path for path in args.dataset_root.iterdir() if path.is_dir()
    )
    rows = prepare(dataset_dirs)
    result = evaluate(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "slide-equivariant.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    markdown_path = args.output_dir / "slide-equivariant.md"
    markdown_path.write_text(render_markdown(result), encoding="utf-8")
    print(markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
