"""
Stage A of the residual acceptance-capacity proposal
(docs/theory/PREVIEW_RESIDUAL_VALUE.md section 9).

Computes analytic acceptance-capacity descriptors of each saved replay
snapshot state s -- reachable feasible anchors per remaining item class,
largest acceptable class, anchor connectivity, a greedy-independent-set
lower bound on simultaneous placements, and a transport-corridor depth
proxy -- then asks whether they explain placed-to-go beyond a baseline
of step, occupied volume, case source, and pool size (LOSO OLS).

This is a sanity check of the STATE value V_cap(s). It does not validate
the per-action R_future(s,a); that is Stage B, which applies the same
descriptors to counterfactual T(s,a) states and preserves within-snapshot
differences. No score integration happens here.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_task_b_config import build_task_b_config  # noqa: E402

DEFAULT_DATASET_ROOT = ROOT / "reports" / "replay-dataset"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "replay-analysis"
SOURCE_CONFIG = ROOT / "simulator" / "configs" / "sample_config.json"

ANCHORS_PER_CLASS_ORIENTATION = 40
DIMS_ROUND = 3


def load_agent_module():
    spec = importlib.util.spec_from_file_location(
        "residual_agent", ROOT / "agent" / "agent.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def rebuild_case_items(case_id: str) -> tuple[list[dict[str, Any]], int]:
    """Rebuild the task-b item list and pool size from the committed source."""
    source_case, pool = case_id.split("-", 1)
    source_case = source_case.removeprefix("b")
    look_ahead = int(pool.removeprefix("k"))
    source = json.loads(SOURCE_CONFIG.read_text(encoding="utf-8"))
    config = build_task_b_config(
        source,
        source_case=source_case,
        task_id=case_id,
        look_ahead=look_ahead,
        policy_timeout=8.0,
    )[case_id]
    return config["item_stream"]["item_list"], look_ahead


def remaining_classes(
    item_list: list[dict[str, Any]],
    packed_indices: set[int],
) -> list[dict[str, Any]]:
    """Quantize remaining items into dims classes with multiplicity."""
    classes: dict[tuple, dict[str, Any]] = {}
    for item in item_list:
        if int(item["index"]) in packed_indices:
            continue
        signature = tuple(
            round(float(item[key]), DIMS_ROUND)
            for key in ("length", "width", "height")
        )
        entry = classes.get(signature)
        if entry is None:
            classes[signature] = {
                "signature": signature,
                "representative": dict(item),
                "count": 1,
                "volume": float(
                    item["length"] * item["width"] * item["height"]
                ),
            }
        else:
            entry["count"] += 1
    return sorted(
        classes.values(), key=lambda entry: -entry["volume"]
    )


def class_anchors(
    agent,
    observation: dict[str, Any],
    representative: dict[str, Any],
    per_orientation: int = ANCHORS_PER_CLASS_ORIENTATION,
) -> tuple[list[Any], bool]:
    """Reachable settled anchors for one class; (anchors, truncated)."""
    anchors: list[Any] = []
    truncated = False
    for orientation in agent.unique_orientations(representative):
        produced = 0
        for candidate in agent.CandidateGenerator.iter_cartesian_attempts(
            observation,
            representative,
            0,
            orientation,
            limit=per_orientation,
            attempt_kind="settled",
        ):
            if candidate is None:
                continue
            anchors.append(candidate)
            produced += 1
            if produced >= per_orientation:
                truncated = True
                break
    return anchors, truncated


def anchors_conflict(first, second, clearance: float) -> bool:
    """3D AABB interference with lateral clearance: cannot coexist."""
    x_gap = max(
        second.minimum[0] - first.maximum[0],
        first.minimum[0] - second.maximum[0],
    )
    y_gap = max(
        second.minimum[1] - first.maximum[1],
        first.minimum[1] - second.maximum[1],
    )
    z_gap = max(
        second.minimum[2] - first.maximum[2],
        first.minimum[2] - second.maximum[2],
    )
    if z_gap >= -1e-9:
        # Vertically separated (stacking) placements do not conflict for
        # the lower bound; conservative for support but keeps the bound a
        # bound.
        return False
    return x_gap < clearance and y_gap < clearance


def greedy_simultaneous_placements(
    agent,
    class_entries: list[dict[str, Any]],
    class_anchor_lists: list[list[Any]],
) -> tuple[int, float]:
    """
    Greedy independent set on the occupancy-conflict graph, respecting
    class multiplicity; deterministic order: class volume desc, then
    generator order. Returns (count, packed volume).
    """
    nodes = []
    for entry, anchors in zip(class_entries, class_anchor_lists):
        for order, anchor in enumerate(anchors):
            nodes.append((entry, order, anchor))
    nodes.sort(key=lambda node: (-node[0]["volume"], node[1]))

    clearance = float(agent.SETTLED_ITEM_CLEARANCE)
    chosen: list[Any] = []
    used_per_class: dict[tuple, int] = {}
    total_volume = 0.0
    for entry, _order, anchor in nodes:
        signature = entry["signature"]
        if used_per_class.get(signature, 0) >= entry["count"]:
            continue
        if any(
            anchors_conflict(anchor, taken, clearance) for taken in chosen
        ):
            continue
        chosen.append(anchor)
        used_per_class[signature] = used_per_class.get(signature, 0) + 1
        total_volume += float(entry["volume"])
    return len(chosen), total_volume


def anchor_components(anchors: list[Any]) -> tuple[int, int]:
    """Connected components under footprint overlap; (count, largest)."""
    n = len(anchors)
    if n == 0:
        return 0, 0
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            a, b = anchors[i], anchors[j]
            if (
                a.minimum[0] < b.maximum[0]
                and b.minimum[0] < a.maximum[0]
                and a.minimum[1] < b.maximum[1]
                and b.minimum[1] < a.maximum[1]
            ):
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
    sizes: dict[int, int] = {}
    for i in range(n):
        root = find(i)
        sizes[root] = sizes.get(root, 0) + 1
    return len(sizes), max(sizes.values())


def snapshot_descriptors(
    agent,
    observation: dict[str, Any],
    item_list: list[dict[str, Any]],
) -> dict[str, Any]:
    container = observation["container_list"][0]
    packed = {
        int(item["index"]) for item in container.get("packed_items", [])
    }
    classes = remaining_classes(item_list, packed)
    anchor_lists: list[list[Any]] = []
    truncated_any = False
    per_class = []
    for entry in classes:
        anchors, truncated = class_anchors(
            agent, observation, entry["representative"]
        )
        anchor_lists.append(anchors)
        truncated_any = truncated_any or truncated
        components, largest = anchor_components(anchors)
        depth = max(
            (float(anchor.center[1]) for anchor in anchors),
            default=None,
        )
        per_class.append(
            {
                "signature": list(entry["signature"]),
                "count": entry["count"],
                "volume": entry["volume"],
                "anchors": len(anchors),
                "components": components,
                "largest_component": largest,
                "max_depth": depth,
            }
        )

    placeable = [
        (entry, stats)
        for entry, stats in zip(classes, per_class)
        if stats["anchors"] > 0
    ]
    cap_volume = max(
        (entry["volume"] for entry, _stats in placeable), default=0.0
    )
    corridor_volume = max(
        (
            entry["volume"]
            for entry, stats in placeable
            if stats["max_depth"] is not None and stats["max_depth"] >= 0.0
        ),
        default=0.0,
    )
    simultaneous_count, simultaneous_volume = (
        greedy_simultaneous_placements(agent, classes, anchor_lists)
    )
    largest_class_components = (
        placeable[0][1]["components"] if placeable else 0
    )
    return {
        "remaining_items": sum(entry["count"] for entry in classes),
        "remaining_classes": len(classes),
        "anchor_total": int(sum(len(a) for a in anchor_lists)),
        "cap_volume": float(cap_volume),
        "corridor_volume": float(corridor_volume),
        "simultaneous_count": int(simultaneous_count),
        "simultaneous_volume": float(simultaneous_volume),
        "largest_class_components": int(largest_class_components),
        "anchors_truncated": bool(truncated_any),
        "per_class": per_class,
    }


def occupied_volume_ratio(observation: dict[str, Any]) -> float:
    container = observation["container_list"][0]
    capacity = max(1e-9, float(container.get("volume") or 1.0))
    packed_volume = sum(
        float(item["length"]) * float(item["width"]) * float(item["height"])
        for item in container.get("packed_items", [])
    )
    return packed_volume / capacity


def collect_rows(
    dataset_dirs: list[pathlib.Path], agent
) -> list[dict[str, Any]]:
    rows = []
    item_cache: dict[str, tuple[list[dict[str, Any]], int]] = {}
    for directory in dataset_dirs:
        manifest_path = directory / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") == "running":
            continue
        split = manifest.get("split", "development")
        if split == "final_holdout":
            print(
                f"skip (final_holdout stays closed): {directory.name}",
                file=sys.stderr,
            )
            continue
        case = manifest.get("case") or {}
        case_id = str(case.get("case_id", ""))
        episode_steps = case.get("episode_steps_executed")
        if not case_id or episode_steps is None:
            continue
        if case_id not in item_cache:
            item_cache[case_id] = rebuild_case_items(case_id)
        item_list, look_ahead = item_cache[case_id]
        for state_path in sorted(directory.glob("step-*-state.json")):
            state = json.loads(state_path.read_text(encoding="utf-8"))
            step = int(state["step"])
            observation = state["observation"]
            descriptors = snapshot_descriptors(
                agent, observation, item_list
            )
            rows.append(
                {
                    "dataset": directory.name,
                    "split": split,
                    "case_id": case_id,
                    "snapshot_id": f"{directory.name}:{step}",
                    "step": step,
                    "look_ahead": look_ahead,
                    "case_source": case_id.split("-")[0],
                    "occupied_volume_ratio": occupied_volume_ratio(
                        observation
                    ),
                    "placed_to_go": int(episode_steps) - 1 - step,
                    **{
                        key: value
                        for key, value in descriptors.items()
                        if key != "per_class"
                    },
                    "per_class": descriptors["per_class"],
                }
            )
    return rows


BASELINE_FEATURES = (
    "step",
    "occupied_volume_ratio",
    "is_b001",
    "look_ahead",
)
DESCRIPTOR_FEATURES = (
    "cap_volume",
    "corridor_volume",
    "simultaneous_count",
    "simultaneous_volume",
    "largest_class_components",
    "anchor_total",
)


def design_matrix(
    rows: list[dict[str, Any]], features: tuple[str, ...]
) -> np.ndarray:
    columns = []
    for row in rows:
        values = []
        for feature in features:
            if feature == "is_b001":
                values.append(1.0 if row["case_source"] == "b001" else 0.0)
            else:
                values.append(float(row[feature]))
        columns.append(values)
    return np.asarray(columns, dtype=np.float64)


def loso_regression(
    rows: list[dict[str, Any]], features: tuple[str, ...]
) -> dict[str, Any]:
    """Leave-one-snapshot-out OLS; returns held-out MAE and R^2."""
    targets = np.array(
        [float(row["placed_to_go"]) for row in rows], dtype=np.float64
    )
    matrix = design_matrix(rows, features)
    groups = [row["snapshot_id"] for row in rows]
    predictions = np.full(len(rows), np.nan)
    for group in sorted(set(groups)):
        holdout = np.array([g == group for g in groups])
        train = ~holdout
        mean = matrix[train].mean(axis=0)
        scale = matrix[train].std(axis=0)
        scale[scale <= 1e-12] = 1.0
        design_train = np.hstack(
            [
                np.ones((int(train.sum()), 1)),
                (matrix[train] - mean) / scale,
            ]
        )
        design_test = np.hstack(
            [
                np.ones((int(holdout.sum()), 1)),
                (matrix[holdout] - mean) / scale,
            ]
        )
        coefficients, *_ = np.linalg.lstsq(
            design_train, targets[train], rcond=None
        )
        predictions[holdout] = design_test @ coefficients
    residuals = targets - predictions
    total = targets - targets.mean()
    return {
        "features": list(features),
        "n": len(rows),
        "loso_mae": float(np.abs(residuals).mean()),
        "loso_r2": float(1.0 - (residuals**2).sum() / (total**2).sum()),
    }


def spearman(x: np.ndarray, y: np.ndarray) -> float | None:
    if len(x) < 3:
        return None

    def ranks(values: np.ndarray) -> np.ndarray:
        order = np.argsort(values, kind="mergesort")
        out = np.empty(len(values))
        i = 0
        sorted_values = values[order]
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

    rx, ry = ranks(x), ranks(y)
    rx -= rx.mean()
    ry -= ry.mean()
    denominator = float(np.sqrt((rx**2).sum() * (ry**2).sum()))
    return (
        float((rx * ry).sum() / denominator) if denominator > 0 else None
    )


def residual_correlations(
    rows: list[dict[str, Any]]
) -> dict[str, float | None]:
    """Spearman of each descriptor against the baseline's residual."""
    targets = np.array([float(row["placed_to_go"]) for row in rows])
    matrix = design_matrix(rows, BASELINE_FEATURES)
    mean = matrix.mean(axis=0)
    scale = matrix.std(axis=0)
    scale[scale <= 1e-12] = 1.0
    design = np.hstack(
        [np.ones((len(rows), 1)), (matrix - mean) / scale]
    )
    coefficients, *_ = np.linalg.lstsq(design, targets, rcond=None)
    residual = targets - design @ coefficients
    report = {}
    for feature in DESCRIPTOR_FEATURES:
        values = np.array([float(row[feature]) for row in rows])
        report[feature] = spearman(values, residual)
    return report


def fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Residual acceptance capacity: Stage A sanity check",
        "",
        "V_cap(s) vs placed-to-go. This checks the STATE descriptors only;",
        "it does not validate the per-action R_future(s,a) (Stage B).",
        "",
        f"- snapshots: {result['n_snapshots']} "
        f"(rows {result['n_rows']}, final_holdout closed)",
        f"- anchors truncated somewhere: {result['any_truncated']}",
        "",
        "## LOSO regression on placed-to-go",
        "",
        "| model | LOSO MAE | LOSO R2 |",
        "|---|---:|---:|",
    ]
    for name in ("baseline", "baseline_plus_descriptors"):
        entry = result[name]
        lines.append(
            f"| {name} | {fmt(entry['loso_mae'])} "
            f"| {fmt(entry['loso_r2'])} |"
        )
    lines.append("")
    lines.append(
        f"MAE improvement: {fmt(result['mae_improvement'])} "
        f"({fmt(result['mae_improvement_ratio'], 1)}% of baseline MAE)"
    )
    lines.append("")
    lines.append("## Descriptor vs baseline residual (Spearman)")
    lines.append("")
    lines.append("| descriptor | rho |")
    lines.append("|---|---:|")
    for feature, value in result["residual_spearman"].items():
        lines.append(f"| {feature} | {fmt(value)} |")
    lines.append("")
    lines.append("## Snapshot table")
    lines.append("")
    lines.append(
        "| snapshot | step | to-go | occ.vol | cap_vol | corr_vol "
        "| simul# | simul_vol | comp(top) | anchors |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in result["rows"]:
        lines.append(
            f"| {row['case_id']}:{row['step']} | {row['step']} "
            f"| {row['placed_to_go']} "
            f"| {fmt(row['occupied_volume_ratio'])} "
            f"| {fmt(row['cap_volume'])} | {fmt(row['corridor_volume'])} "
            f"| {row['simultaneous_count']} "
            f"| {fmt(row['simultaneous_volume'])} "
            f"| {row['largest_class_components']} "
            f"| {row['anchor_total']} |"
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

    agent = load_agent_module()
    dataset_dirs = sorted(
        path for path in args.dataset_root.iterdir() if path.is_dir()
    )
    rows = collect_rows(dataset_dirs, agent)
    if len(rows) < 8:
        print("not enough snapshots", file=sys.stderr)
        return 1

    baseline = loso_regression(rows, BASELINE_FEATURES)
    extended = loso_regression(
        rows, BASELINE_FEATURES + DESCRIPTOR_FEATURES
    )
    result = {
        "n_rows": len(rows),
        "n_snapshots": len({row["snapshot_id"] for row in rows}),
        "any_truncated": any(row["anchors_truncated"] for row in rows),
        "baseline": baseline,
        "baseline_plus_descriptors": extended,
        "mae_improvement": baseline["loso_mae"] - extended["loso_mae"],
        "mae_improvement_ratio": (
            100.0
            * (baseline["loso_mae"] - extended["loso_mae"])
            / baseline["loso_mae"]
            if baseline["loso_mae"] > 0
            else None
        ),
        "residual_spearman": residual_correlations(rows),
        "rows": sorted(
            (
                {k: v for k, v in row.items() if k != "per_class"}
                for row in rows
            ),
            key=lambda row: (row["case_id"], row["step"]),
        ),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "residual-capacity-stage-a.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    markdown_path = args.output_dir / "residual-capacity-stage-a.md"
    markdown_path.write_text(render_markdown(result), encoding="utf-8")
    print(markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
