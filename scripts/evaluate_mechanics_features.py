"""
Mechanical topple features (MATHEMATICAL_MODEL.md section 5.2.1) on the
saved replay datasets -- no new physics runs.

For every release candidate row the predicted contact state is
reconstructed from the stored snapshot observation with the agent's own
geometry (release_rest_height and the same surface set it uses), the
support polygon is the convex hull of the predicted contact patches, and
each hull edge is a tipping axis giving:

    d_e     directional margin (signed, inside positive)
    h_e     CoM height above that axis
    theta_c,e = arctan(d_e / h_e)
    B_e     = sqrt(d_e^2 + h_e^2) - h_e   (0 when d_e <= 0)
    eta_e   = drop / B_e

Model aggregates: (d_min, theta_c_min, B_min, log1p(eta_max)). Inputs
are pre-release predictions only; replay observables stay labels.

Frozen-protocol comparison of static / mechanics / static+mechanics:
LOSO AUC with snapshot-clustered bootstrap CI, per-case and per-pool
worst subgroup AUC, leave-one-side-out extrapolation, and
within-snapshot discordant-pair ranking accuracy (the rerank-relevant
metric; the two actually-changed shadow pairs are far too few to score
alone, which is reported rather than hidden).
"""
from __future__ import annotations

import argparse
import importlib.util
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

DEFAULT_DATASET_ROOT = ROOT / "reports" / "replay-dataset"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "replay-analysis"

ETA_EPSILON = 1e-6
ETA_CAP = 1e6

MECH_FEATURES = ("d_min", "theta_c_min", "B_min", "log1p_eta_max")


def load_agent_module():
    spec = importlib.util.spec_from_file_location(
        "mech_agent", ROOT / "agent" / "agent.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Monotone chain; returns CCW hull without the repeated last point."""
    unique = sorted(set(points))
    if len(unique) <= 2:
        return unique

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def contact_patches(
    agent,
    container: dict[str, Any],
    x: float,
    y: float,
    dims: tuple[float, float, float],
    z_rest: float,
) -> list[dict[str, Any]]:
    """Footprint-intersected predicted contact patches at the rest height.

    The surface universe matches release_rest_height exactly: floor,
    shelves, and every packed AABB (soft and priority included -- they
    physically support even though they are excluded as planning
    surfaces elsewhere).
    """
    dx, dy, _dz = dims
    fx0, fx1 = x - dx / 2.0, x + dx / 2.0
    fy0, fy1 = y - dy / 2.0, y + dy / 2.0
    tolerance = float(agent.CONTACT_TOLERANCE)

    floor_top = float(container["thickness"]) + float(
        container.get("buffer", 0.0)
    )
    length = float(container["length"])
    width = float(container["width"])
    surfaces: list[tuple[float, float, float, float, float]] = [
        (-length / 2.0, length / 2.0, -width / 2.0, width / 2.0, floor_top)
    ]
    for box in agent.shelf_aabbs(container):
        surfaces.append(
            (
                float(box.minimum[0]),
                float(box.maximum[0]),
                float(box.minimum[1]),
                float(box.maximum[1]),
                float(box.top),
            )
        )
    for box, _soft, _prio in agent.packed_aabbs_local(container):
        surfaces.append(
            (
                float(box.minimum[0]),
                float(box.maximum[0]),
                float(box.minimum[1]),
                float(box.maximum[1]),
                float(box.top),
            )
        )

    patches = []
    for sx0, sx1, sy0, sy1, top in surfaces:
        if abs(top - z_rest) > tolerance:
            continue
        ox0, ox1 = max(fx0, sx0), min(fx1, sx1)
        oy0, oy1 = max(fy0, sy0), min(fy1, sy1)
        if ox1 - ox0 <= 1e-9 or oy1 - oy0 <= 1e-9:
            continue
        patches.append(
            {
                "corners": [
                    (ox0, oy0),
                    (ox0, oy1),
                    (ox1, oy0),
                    (ox1, oy1),
                ],
                "top": top,
            }
        )
    return patches


def mechanics_features(
    agent,
    container: dict[str, Any],
    x: float,
    y: float,
    z_command: float,
    dims: tuple[float, float, float],
) -> dict[str, float]:
    """Phi_mech for one release candidate from predicted contact state."""
    dx, dy, dz = dims
    z_rest = float(agent.release_rest_height(x, y, dims, container))
    z_com = z_rest + dz / 2.0
    drop = max(0.0, (float(z_command) - dz / 2.0) - z_rest)

    patches = contact_patches(agent, container, x, y, dims, z_rest)
    degenerate = not patches
    if degenerate:
        # By construction of release_rest_height at least one surface
        # matched; an empty set means numeric-tolerance starvation, which
        # we score as the worst case rather than dropping the row.
        d_min = 0.0
        h_at_min = dz / 2.0
        b_min = 0.0
    else:
        corner_tops: dict[tuple[float, float], float] = {}
        for patch in patches:
            for corner in patch["corners"]:
                previous = corner_tops.get(corner)
                if previous is None or patch["top"] > previous:
                    corner_tops[corner] = patch["top"]
        hull = convex_hull(list(corner_tops))
        d_min = math.inf
        h_at_min = dz / 2.0
        b_min = math.inf
        if len(hull) < 3:
            # Line or point contact: no interior, zero margin about the
            # contact line itself.
            d_min = 0.0
            z_e = max(patch["top"] for patch in patches)
            h_at_min = max(1e-6, z_com - z_e)
            b_min = 0.0
        else:
            for index, start in enumerate(hull):
                end = hull[(index + 1) % len(hull)]
                ex, ey = end[0] - start[0], end[1] - start[1]
                norm = math.hypot(ex, ey)
                if norm <= 1e-12:
                    continue
                # CCW hull: interior lies left of each edge.
                signed = (
                    (x - start[0]) * ey - (y - start[1]) * ex
                ) / norm * -1.0
                z_e = max(
                    corner_tops.get(start, z_rest),
                    corner_tops.get(end, z_rest),
                )
                h_e = max(1e-6, z_com - z_e)
                b_e = (
                    math.sqrt(signed * signed + h_e * h_e) - h_e
                    if signed > 0.0
                    else 0.0
                )
                if signed < d_min:
                    d_min = signed
                    h_at_min = h_e
                if b_e < b_min:
                    b_min = b_e
            if not math.isfinite(d_min):
                d_min, b_min = 0.0, 0.0

    theta_c = math.atan2(d_min, h_at_min)
    eta = min(ETA_CAP, drop / max(b_min, ETA_EPSILON))
    return {
        "d_min": float(d_min),
        "theta_c_min": float(theta_c),
        "B_min": float(b_min),
        "log1p_eta_max": float(math.log1p(eta)),
        "drop_meters": float(drop),
        "z_rest": float(z_rest),
        "degenerate_contact": bool(degenerate),
    }


def load_containers(
    dataset_dirs: list[pathlib.Path],
) -> dict[tuple[str, str], dict[str, Any]]:
    containers: dict[tuple[str, str], dict[str, Any]] = {}
    for directory in dataset_dirs:
        manifest = directory / "manifest.json"
        if not manifest.exists():
            continue
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        if payload.get("status") == "running":
            continue
        if payload.get("split", "development") == "final_holdout":
            continue
        for state_path in directory.glob("step-*-state.json"):
            state = json.loads(state_path.read_text(encoding="utf-8"))
            container = state["observation"]["container_list"][0]
            containers[(directory.name, state_path.name)] = container
    return containers


def mech_vector(row: dict[str, Any]) -> list[float]:
    mech = row["_mech"]
    return [mech[name] for name in MECH_FEATURES]


def subgroup_worst_auc(
    predictions: np.ndarray,
    labels: np.ndarray,
    keys: list[str],
) -> dict[str, Any]:
    table = {}
    for key in sorted(set(keys)):
        mask = np.array([k == key for k in keys])
        auc = err.rank_auc(predictions[mask], labels[mask])
        table[key] = {
            "n": int(mask.sum()),
            "positives": int(labels[mask].sum()),
            "auc": auc,
        }
    scored = [
        entry["auc"] for entry in table.values() if entry["auc"] is not None
    ]
    return {
        "groups": table,
        "worst": min(scored) if scored else None,
    }


def within_snapshot_pair_accuracy(
    predictions: np.ndarray,
    labels: np.ndarray,
    groups: list[str],
) -> dict[str, Any]:
    """
    Over all within-snapshot pairs with discordant labels: fraction where
    the dangerous candidate receives the higher predicted risk (ties
    count half). This is the ranking event shadow rerank actually needs
    to get right inside one decision.
    """
    by_group: dict[str, list[int]] = {}
    for index, group in enumerate(groups):
        by_group.setdefault(group, []).append(index)
    correct = 0.0
    total = 0
    for indices in by_group.values():
        positives = [i for i in indices if labels[i]]
        negatives = [i for i in indices if not labels[i]]
        for p in positives:
            for n in negatives:
                total += 1
                if predictions[p] > predictions[n]:
                    correct += 1.0
                elif predictions[p] == predictions[n]:
                    correct += 0.5
    return {
        "pairs": total,
        "accuracy": (correct / total) if total else None,
    }


def evaluate(dataset_dirs: list[pathlib.Path]) -> dict[str, Any]:
    agent = load_agent_module()
    all_rows, release, summaries = err.load_release_rows(dataset_dirs)
    containers = load_containers(dataset_dirs)

    rows = []
    degenerate = 0
    for row in release:
        container = containers.get(
            (row["_dataset_dir"], row["snapshot_path"])
        )
        if container is None:
            continue
        x, y, z_command = (float(v) for v in row["center"])
        dims = tuple(float(v) for v in row["size"])
        row["_mech"] = mechanics_features(
            agent, container, x, y, z_command, dims
        )
        degenerate += int(row["_mech"]["degenerate_contact"])
        rows.append(row)

    groups = [row["snapshot_id"] for row in rows]
    case_sources = [row["case_id"].split("-")[0] for row in rows]
    pools = [row["case_id"].split("-")[1] for row in rows]
    static = np.array([err.phi_vector(row) for row in rows])
    mech = np.array([mech_vector(row) for row in rows])
    combined = np.hstack([static, mech])
    feature_sets = {
        "static_only": static,
        "mechanics_only": mech,
        "static_plus_mechanics": combined,
    }

    result: dict[str, Any] = {
        "rows": len(rows),
        "snapshots": len(set(groups)),
        "degenerate_contact_rows": degenerate,
        "mech_feature_order": list(MECH_FEATURES),
        "labels": {},
        "shadow_pairs_note": (
            "Only 2 actually-changed shadow pairs exist across the "
            "datasets; within-snapshot discordant-pair accuracy is the "
            "statistically usable ranking metric until more changed "
            "pairs accumulate."
        ),
    }

    for label in ("rotated_over_30", "not_placed_safe"):
        targets = np.array(
            [err.label_of(row, label) for row in rows], dtype=float
        )
        label_report: dict[str, Any] = {}
        for name, features in feature_sets.items():
            predictions = err.leave_one_group_out_predictions(
                features, targets, groups
            )
            entry: dict[str, Any] = {
                "loso_auc": err.clustered_bootstrap_auc(
                    predictions, targets.astype(bool), groups
                ),
                "worst_case": subgroup_worst_auc(
                    predictions, targets.astype(bool), case_sources
                ),
                "worst_pool": subgroup_worst_auc(
                    predictions, targets.astype(bool), pools
                ),
                "pair_ranking": within_snapshot_pair_accuracy(
                    predictions, targets.astype(bool), groups
                ),
                "extrapolation_case": err.extrapolation_report(
                    features,
                    targets,
                    [row["case_id"] for row in rows],
                    lambda case: case.split("-")[0],
                ),
                "extrapolation_pool": err.extrapolation_report(
                    features,
                    targets,
                    [row["case_id"] for row in rows],
                    lambda case: case.split("-")[1],
                ),
            }
            label_report[name] = entry
        result["labels"][label] = label_report

    # Univariate orientation check for each mechanics feature.
    rotated = np.array(
        [err.label_of(row, "rotated_over_30") for row in rows]
    )
    result["mech_univariate_auc_rotated"] = {}
    for index, name in enumerate(MECH_FEATURES):
        scores = mech[:, index]
        if name in ("d_min", "theta_c_min", "B_min"):
            scores = -scores  # lower margin/barrier = more dangerous
        result["mech_univariate_auc_rotated"][name] = err.rank_auc(
            scores, rotated
        )
    return result


def fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def worst_extrapolation(report: dict[str, Any]) -> float | None:
    values = [
        entry["test_auc"]
        for entry in report.values()
        if isinstance(entry, dict) and entry.get("test_auc") is not None
    ]
    return min(values) if values else None


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Mechanical topple features: frozen-split comparison",
        "",
        f"- release rows: {result['rows']} in {result['snapshots']} "
        "snapshots (development+validation; final_holdout closed)",
        f"- degenerate contact rows: {result['degenerate_contact_rows']}",
        "- Phi_mech inputs are pre-release predicted contact state only; "
        "replay observables stay labels (MATHEMATICAL_MODEL 5.2.1).",
        f"- {result['shadow_pairs_note']}",
        "",
        "## Univariate mechanics AUC (rotated_over_30, danger-oriented)",
        "",
        "| feature | AUC |",
        "|---|---:|",
    ]
    for name, value in result["mech_univariate_auc_rotated"].items():
        lines.append(f"| {name} | {fmt(value)} |")
    for label, label_report in result["labels"].items():
        lines.append("")
        lines.append(f"## {label}")
        lines.append("")
        lines.append(
            "| feature set | LOSO AUC | 95% CI | worst case | worst pool "
            "| worst extrap. (case) | worst extrap. (pool) "
            "| pair acc. (n) |"
        )
        lines.append("|---|---:|---|---:|---:|---:|---:|---:|")
        for name, entry in label_report.items():
            loso = entry["loso_auc"]
            pair = entry["pair_ranking"]
            lines.append(
                f"| {name} | {fmt(loso.get('point'))} "
                f"| [{fmt(loso.get('ci_2.5'))}, {fmt(loso.get('ci_97.5'))}] "
                f"| {fmt(entry['worst_case']['worst'])} "
                f"| {fmt(entry['worst_pool']['worst'])} "
                f"| {fmt(worst_extrapolation(entry['extrapolation_case']))} "
                f"| {fmt(worst_extrapolation(entry['extrapolation_pool']))} "
                f"| {fmt(pair['accuracy'])} ({pair['pairs']}) |"
            )
        lines.append("")
        lines.append("### Extrapolation detail")
        lines.append("")
        lines.append("| feature set | split | direction | AUC |")
        lines.append("|---|---|---|---:|")
        for name, entry in label_report.items():
            for split in ("case", "pool"):
                for direction, cell in sorted(
                    entry[f"extrapolation_{split}"].items()
                ):
                    if isinstance(cell, dict) and "test_auc" in cell:
                        lines.append(
                            f"| {name} | {split} | {direction} "
                            f"| {fmt(cell['test_auc'])} |"
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
    result = evaluate(dataset_dirs)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "mechanics-features.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    markdown_path = args.output_dir / "mechanics-features.md"
    markdown_path.write_text(render_markdown(result), encoding="utf-8")
    print(markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
