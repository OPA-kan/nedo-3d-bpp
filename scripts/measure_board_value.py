"""
F1 of the Task C board-value proposal (docs/theory/TASK_C_BOARD_VALUE.md).

Computes, for each saved replay snapshot, the two quantities the theory puts
at its centre and which no existing instrument measures:

- ``R_c(s)``: per-class independent alternative count, as a greedy lower
  bound on the maximum set of mutually non-conflicting placements of one
  baggage type. The existing Stage A instrument collapses every class into a
  single ``combined_simultaneous_count``; the theory needs the vector.
- ``H(s)``: class-vs-resource competition. Resources are the geometry-derived
  support-plane components (never anchor counts, which would make the value a
  function of stride and grid density -- ABC spec section 8). Reported both as
  the Hall deficiency ``|C| - nu(s)`` (exact, one bipartite matching) and as
  the expansion ratio ``min |N(C')| / |C'|`` (exact by enumerating the 127
  non-empty subsets of the seven baggage types).

The question F1 answers is only whether these saturate the way ``A(s)`` does.
If they do, the theory is a dead end for Task C and dies cheaply here. It is
not an adoption test and computes no policy.

INFORMATION CONTRACT: the class set is the published type prior, not the true
remaining multiset. A Task C agent never learns what remains -- the simulator
passes the full item list only through ``get_info_for_optimization``, which
the harness calls only when ``optimize`` is set (Task A). Stage A's
``remaining_classes`` reconstructs the truth from the case item list, which is
valid for an offline descriptor but would be an information leak as an online
feature. This script therefore deliberately does not use it.
"""
from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import sys
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.measure_residual_capacity import (  # noqa: E402
    ACCEPT_CAP_PER_ORIENTATION,
    RELEASE_STRIDE_DIVISOR,
    anchors_conflict,
    load_agent_module,
)

DEFAULT_DATASET_ROOT = ROOT / "reports" / "replay-dataset"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "replay-analysis"
# Stride 64 with the release divisor 16 (release stride 4) is the calibrated
# Stage A setting. F1 only asks whether the quantities discriminate, so it
# buys snapshot coverage rather than per-snapshot exactness.
DEFAULT_STRIDE = 64
DEFAULT_PHASES = 1
# Anchors per (class, kind) fed to the greedy bound and the resource map.
# Systematic subsample of the already stride-sampled scan; the greedy over a
# subsample is still a lower bound on the full-scan independent set, which is
# the direction the claim needs. Recorded per row so a saturated R cannot be
# mistaken for the cap.
DEFAULT_MAX_ANCHORS = 400

# Baggage type prior. Provenance: simulator/configs/item_params.xlsx,
# Sheet1, columns C..I (the seven published types). This is a constant of
# the competition, not of a case: it is what a Task C agent may assume about
# arrivals it cannot see. tests/test_measure_board_value.py re-derives it
# from the workbook whenever openpyxl is installed.
BAGGAGE_TYPES = (
    {
        "name": "suitcase_large",
        "length": 0.75, "width": 0.56, "height": 0.27,
        "mass": 18, "is_soft": False, "lateralFriction": 0.4,
    },
    {
        "name": "suitcase_medium",
        "length": 0.65, "width": 0.45, "height": 0.25,
        "mass": 13, "is_soft": False, "lateralFriction": 0.4,
    },
    {
        "name": "suitcase_small",
        "length": 0.55, "width": 0.40, "height": 0.24,
        "mass": 8, "is_soft": False, "lateralFriction": 0.4,
    },
    {
        "name": "duffel",
        "length": 0.60, "width": 0.30, "height": 0.25,
        "mass": 7, "is_soft": True, "lateralFriction": 0.8,
    },
    {
        "name": "cardboard",
        "length": 0.50, "width": 0.40, "height": 0.40,
        "mass": 10, "is_soft": True, "lateralFriction": 0.6,
    },
    {
        "name": "backpack_large",
        "length": 0.65, "width": 0.35, "height": 0.23,
        "mass": 12, "is_soft": True, "lateralFriction": 0.8,
    },
    {
        "name": "daypack_small",
        "length": 0.45, "width": 0.30, "height": 0.20,
        "mass": 5, "is_soft": True, "lateralFriction": 0.8,
    },
)


def type_representative(entry: dict[str, Any], index: int) -> dict[str, Any]:
    """One item dict the placement core accepts, from a type prior entry."""
    return {
        "index": -(index + 1),
        "length": float(entry["length"]),
        "width": float(entry["width"]),
        "height": float(entry["height"]),
        "mass": float(entry["mass"]),
        "is_soft": bool(entry["is_soft"]),
        "is_prioritized": False,
        "lateralFriction": float(entry["lateralFriction"]),
    }


def container_class_anchors(
    agent,
    observation: dict[str, Any],
    representative: dict[str, Any],
    container_idx: int,
    kind: str,
    stride: int,
    phase: int,
) -> tuple[list[Any], float, bool]:
    """
    Systematically sampled reachable anchors of one kind, for one class, in
    one container.

    Stage A's ``class_anchors`` is fixed to container 0; Task C cases may
    run two containers, and a resource set that silently drops the second
    one would make the Hall statistics wrong rather than approximate.
    Returns (anchors, Horvitz-Thompson count estimate, capped).
    """
    anchors: list[Any] = []
    capped = False
    for orientation in agent.unique_orientations(representative):
        produced = 0
        for candidate in agent.CandidateGenerator.iter_cartesian_attempts(
            observation,
            representative,
            container_idx,
            orientation,
            limit=ACCEPT_CAP_PER_ORIENTATION,
            attempt_kind=kind,
            stride=stride,
            stride_offset=phase,
        ):
            if candidate is None:
                continue
            anchors.append(candidate)
            produced += 1
            if produced >= ACCEPT_CAP_PER_ORIENTATION:
                capped = True
                break
    return anchors, float(len(anchors) * stride), capped


def subsample(items: list[Any], limit: int) -> list[Any]:
    """Deterministic systematic subsample preserving scan spread."""
    if limit <= 0 or len(items) <= limit:
        return items
    step = len(items) / float(limit)
    return [items[int(index * step)] for index in range(limit)]


def greedy_independent_set(agent, anchors: list[Any]) -> int:
    """
    Greedy lower bound on the maximum set of mutually non-conflicting
    placements of ONE class. Deterministic in scan order.

    Conflict is the occupancy relation of Stage A's ``anchors_conflict``:
    3D AABB interference with lateral clearance, treating vertically
    separated placements as compatible. The theory's rho(o) is strictly
    wider (corridor, support component, clearance), so this over-counts
    independence relative to the full relation and is a lower bound only
    with respect to THIS relation. Recorded as such; never report it as
    R_c itself.
    """
    if not anchors:
        return 0
    clearance = float(agent.SETTLED_ITEM_CLEARANCE)
    minima = np.asarray(
        [np.asarray(anchor.minimum, dtype=float) for anchor in anchors]
    )
    maxima = np.asarray(
        [np.asarray(anchor.maximum, dtype=float) for anchor in anchors]
    )
    chosen_min: list[np.ndarray] = []
    chosen_max: list[np.ndarray] = []
    for index in range(len(anchors)):
        if chosen_min:
            taken_min = np.asarray(chosen_min)
            taken_max = np.asarray(chosen_max)
            gaps = np.maximum(
                taken_min - maxima[index], minima[index] - taken_max
            )
            # anchors_conflict semantics, vectorised
            conflicts = (
                (gaps[:, 2] < -1e-9)
                & (gaps[:, 0] < clearance)
                & (gaps[:, 1] < clearance)
            )
            if bool(conflicts.any()):
                continue
        chosen_min.append(minima[index])
        chosen_max.append(maxima[index])
    return len(chosen_min)


def container_components(agent, container) -> list[Any]:
    """Geometry-derived resource set of one container."""
    surfaces = agent.support_surfaces(container)
    components = agent.support_plane_components(surfaces)
    return agent.order_support_plane_components(components)


def component_geometry(components: list[Any]) -> list[dict[str, Any]]:
    """Flatten components to plain floats so the hot loop avoids numpy."""
    flattened = []
    for component in components:
        minimum = component.minimum_xy
        maximum = component.maximum_xy
        flattened.append(
            {
                "top": float(component.top),
                "min_x": float(minimum[0]),
                "max_x": float(maximum[0]),
                "min_y": float(minimum[1]),
                "max_y": float(maximum[1]),
                "component": component,
            }
        )
    return flattened


def map_anchors_to_components(
    agent,
    anchors: list[Any],
    container,
    geometry: list[dict[str, Any]],
    container_idx: int,
) -> set[tuple[int, int]]:
    """
    Which support components this class actually rests on -- the class side
    of the bipartite graph (C, Z(s)). Bounding-box screen first; the exact
    union-area call only runs for survivors.

    Returns resource -> the settled poses that rest on it, so the caller can
    derive each resource's slot capacity from the same greedy bound.
    """
    used: dict[tuple[int, int], list[Any]] = {}
    tolerance = float(agent.CONTACT_TOLERANCE)
    for anchor in anchors:
        settled = (
            agent.settled_proxy_candidate(anchor, container)
            if anchor.name == "release_candidate"
            else anchor
        )
        minimum = settled.minimum
        maximum = settled.maximum
        bottom = float(minimum[2])
        min_x, max_x = float(minimum[0]), float(maximum[0])
        min_y, max_y = float(minimum[1]), float(maximum[1])
        for component_idx, entry in enumerate(geometry):
            key = (container_idx, component_idx)
            if abs(entry["top"] - bottom) > tolerance:
                continue
            if (
                max_x <= entry["min_x"]
                or entry["max_x"] <= min_x
                or max_y <= entry["min_y"]
                or entry["max_y"] <= min_y
            ):
                continue
            if (
                agent.support_component_overlap_area(
                    settled, entry["component"]
                )
                <= agent.EPS
            ):
                continue
            used.setdefault(key, []).append(settled)
    return used


def maximum_matching(
    neighbourhoods: list[set[tuple[int, int]]],
    capacities: dict[tuple[int, int], int],
) -> int:
    """
    Maximum assignment of one slot per class, with per-resource capacity.

    Capacity is required, not cosmetic: a support-plane component can be the
    whole 2.9 m2 floor, and treating it as a single indivisible resource
    makes the Hall deficiency identically |C| - 1 regardless of the board.
    Kuhn's algorithm over capacity-expanded slots; m = 7 so cost is free.
    """
    assignment: dict[tuple[int, int, int], int] = {}

    def slots(resource: tuple[int, int]) -> list[tuple[int, int, int]]:
        return [
            (resource[0], resource[1], slot)
            for slot in range(max(0, capacities.get(resource, 0)))
        ]

    def augment(
        class_idx: int, seen: set[tuple[int, int, int]]
    ) -> bool:
        for resource in sorted(neighbourhoods[class_idx]):
            for slot in slots(resource):
                if slot in seen:
                    continue
                seen.add(slot)
                holder = assignment.get(slot)
                if holder is None or augment(holder, seen):
                    assignment[slot] = class_idx
                    return True
        return False

    matched = 0
    for class_idx in range(len(neighbourhoods)):
        if augment(class_idx, set()):
            matched += 1
    return matched


def hall_statistics(
    neighbourhoods: list[set[tuple[int, int]]],
    capacities: dict[tuple[int, int], int],
) -> dict[str, Any]:
    """
    Deficiency (exact, via Konig on the capacity-expanded graph) and the
    expansion ratio (exact, by enumerating the 2^m - 1 non-empty subsets of
    the seven types). The ratio counts capacity slots, not components, for
    the same reason.
    """
    total = len(neighbourhoods)
    matching = maximum_matching(neighbourhoods, capacities)
    deficiency = total - matching

    best_ratio = None
    worst_subset: tuple[int, ...] = ()
    for size in range(1, total + 1):
        for subset in itertools.combinations(range(total), size):
            union: set[tuple[int, int]] = set()
            for class_idx in subset:
                union |= neighbourhoods[class_idx]
            available = sum(
                max(0, capacities.get(resource, 0)) for resource in union
            )
            ratio = available / float(size)
            if best_ratio is None or ratio < best_ratio:
                best_ratio = ratio
                worst_subset = subset
    return {
        "matching": matching,
        "hall_deficiency": deficiency,
        "hall_ratio": best_ratio,
        "hall_worst_subset": [
            BAGGAGE_TYPES[i]["name"] for i in worst_subset
        ],
    }


def snapshot_board_value(
    agent,
    observation: dict[str, Any],
    stride: int,
    phases: int,
    max_anchors: int = DEFAULT_MAX_ANCHORS,
) -> dict[str, Any]:
    containers = observation.get("container_list", [])
    component_lists = [
        container_components(agent, container) for container in containers
    ]
    geometries = [
        component_geometry(components) for components in component_lists
    ]
    resource_total = sum(len(items) for items in component_lists)

    release_stride = max(1, stride // RELEASE_STRIDE_DIVISOR)
    per_class: list[dict[str, Any]] = []
    neighbourhoods_settled: list[set[tuple[int, int]]] = []
    neighbourhoods_any: list[set[tuple[int, int]]] = []
    any_capped = False
    anchors_truncated = False
    # Mixed-class poses per resource, from which slot capacity is derived.
    resource_poses: dict[tuple[int, int], list[Any]] = {}

    for type_idx, entry in enumerate(BAGGAGE_TYPES):
        representative = type_representative(entry, type_idx)
        settled_r: list[int] = []
        release_r: list[int] = []
        settled_estimates: list[float] = []
        release_estimates: list[float] = []
        settled_components: set[tuple[int, int]] = set()
        any_components: set[tuple[int, int]] = set()

        for phase in range(phases):
            settled_anchors: list[Any] = []
            release_anchors: list[Any] = []
            settled_estimate = 0.0
            release_estimate = 0.0
            for container_idx, container in enumerate(containers):
                for kind, stride_value in (
                    ("settled", stride),
                    ("release", release_stride),
                ):
                    anchors, estimate, capped = container_class_anchors(
                        agent,
                        observation,
                        representative,
                        container_idx,
                        kind,
                        stride_value,
                        phase % stride_value,
                    )
                    any_capped = any_capped or capped
                    if len(anchors) > max_anchors:
                        anchors_truncated = True
                    anchors = subsample(anchors, max_anchors)
                    if kind == "settled":
                        settled_anchors.extend(anchors)
                        settled_estimate += estimate
                    else:
                        release_anchors.extend(anchors)
                        release_estimate += estimate
                    used = map_anchors_to_components(
                        agent,
                        anchors,
                        container,
                        geometries[container_idx],
                        container_idx,
                    )
                    any_components |= set(used)
                    if kind == "settled":
                        settled_components |= set(used)
                    for resource, poses in used.items():
                        resource_poses.setdefault(resource, []).extend(
                            poses
                        )

            settled_r.append(greedy_independent_set(agent, settled_anchors))
            release_r.append(greedy_independent_set(agent, release_anchors))
            settled_estimates.append(settled_estimate)
            release_estimates.append(release_estimate)

        neighbourhoods_settled.append(settled_components)
        neighbourhoods_any.append(any_components)
        per_class.append(
            {
                "class": entry["name"],
                "volume": float(
                    entry["length"] * entry["width"] * entry["height"]
                ),
                "r_settled": float(np.mean(settled_r)),
                "r_release": float(np.mean(release_r)),
                "anchors_settled_ht": float(np.mean(settled_estimates)),
                "anchors_release_ht": float(np.mean(release_estimates)),
                "components_settled": len(settled_components),
                "components_any": len(any_components),
                "feasible": bool(
                    settled_estimates[0] > 0.0 or release_estimates[0] > 0.0
                ),
            }
        )

    capacities = {
        resource: greedy_independent_set(
            agent, subsample(poses, max_anchors)
        )
        for resource, poses in resource_poses.items()
    }
    settled_hall = hall_statistics(neighbourhoods_settled, capacities)
    any_hall = hall_statistics(neighbourhoods_any, capacities)
    r_settled = [row["r_settled"] for row in per_class]
    r_any = [
        row["r_settled"] + row["r_release"] for row in per_class
    ]
    return {
        "resource_components": resource_total,
        "resource_slots": int(sum(capacities.values())),
        "resource_slots_max": int(max(capacities.values(), default=0)),
        "accept_capped": any_capped,
        "anchors_truncated": anchors_truncated,
        "acceptance_A": sum(
            1 for row in per_class if row["feasible"]
        ),
        "r_settled_min": float(min(r_settled)),
        "r_settled_mean": float(np.mean(r_settled)),
        "r_settled_zero_classes": sum(
            1 for value in r_settled if value <= 0.0
        ),
        "r_settled_singleton_classes": sum(
            1 for value in r_settled if 0.0 < value <= 1.0
        ),
        "r_any_min": float(min(r_any)),
        "r_any_mean": float(np.mean(r_any)),
        "phi_log_settled": float(
            sum(np.log1p(value) for value in r_settled)
        ),
        "hall_deficiency_settled": settled_hall["hall_deficiency"],
        "hall_ratio_settled": settled_hall["hall_ratio"],
        "hall_worst_subset_settled": settled_hall["hall_worst_subset"],
        "hall_deficiency_any": any_hall["hall_deficiency"],
        "hall_ratio_any": any_hall["hall_ratio"],
        "per_class": per_class,
    }


def collect_rows(
    dataset_dirs: list[pathlib.Path],
    agent,
    stride: int,
    phases: int,
    max_anchors: int = DEFAULT_MAX_ANCHORS,
    limit: int = 0,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
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
        for state_path in sorted(directory.glob("step-*-state.json")):
            state = json.loads(state_path.read_text(encoding="utf-8"))
            step = int(state["step"])
            print(
                f"board value: {case_id} step {step}",
                file=sys.stderr,
                flush=True,
            )
            value = snapshot_board_value(
                agent,
                state["observation"],
                stride=stride,
                phases=phases,
                max_anchors=max_anchors,
            )
            rows.append(
                {
                    "dataset": directory.name,
                    "split": split,
                    "case_id": case_id,
                    "snapshot_id": f"{directory.name}:{step}",
                    "step": step,
                    "steps_to_terminal": int(episode_steps) - 1 - step,
                    **{
                        key: item
                        for key, item in value.items()
                        if key != "per_class"
                    },
                    "per_class": value["per_class"],
                }
            )
            if limit and len(rows) >= limit:
                return rows
    return rows


def spearman(x: np.ndarray, y: np.ndarray) -> float | None:
    if len(x) < 3:
        return None

    def ranks(values: np.ndarray) -> np.ndarray:
        order = np.argsort(values, kind="stable")
        result = np.empty(len(values), dtype=float)
        result[order] = np.arange(len(values), dtype=float)
        return result

    rx, ry = ranks(x), ranks(y)
    if np.std(rx) == 0 or np.std(ry) == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


SUMMARY_FIELDS = (
    "acceptance_A",
    "resource_slots",
    "r_settled_min",
    "r_settled_mean",
    "r_settled_zero_classes",
    "r_any_min",
    "r_any_mean",
    "phi_log_settled",
    "hall_deficiency_settled",
    "hall_ratio_settled",
    "hall_deficiency_any",
    "hall_ratio_any",
)


def saturation_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    A quantity is 'saturated' when it is constant across snapshots and can
    therefore never discriminate, which is what killed the 1-ply pool
    feasibility signal.
    """
    report = {}
    to_go = np.asarray(
        [float(row["steps_to_terminal"]) for row in rows], dtype=float
    )
    for field in SUMMARY_FIELDS:
        values = np.asarray(
            [float(row[field]) for row in rows], dtype=float
        )
        distinct = sorted({round(float(value), 6) for value in values})
        report[field] = {
            "min": float(values.min()),
            "max": float(values.max()),
            "mean": float(values.mean()),
            "distinct_values": len(distinct),
            "saturated": len(distinct) == 1,
            "spearman_steps_to_terminal": spearman(values, to_go),
        }
    return report


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Task C board value: F1 saturation check",
        "",
        "Per-class independent alternatives R_c and Hall-type class"
        " competition H on saved replay snapshots.",
        "This asks only whether the quantities discriminate at all.",
        "It is not an adoption test and no policy is computed.",
        "",
        f"- snapshots: {result['n_snapshots']}",
        f"- stride: {result['stride']} (release stride divisor"
        f" {RELEASE_STRIDE_DIVISOR}), phases: {result['phases']}",
        f"- classes: {len(BAGGAGE_TYPES)} (published type prior, not the"
        " true remaining multiset)",
        f"- accept cap fired somewhere: {result['any_capped']}",
        "",
        "## Saturation",
        "",
        "| quantity | min | max | mean | distinct | saturated |"
        " rho vs steps-to-terminal |",
        "|---|---:|---:|---:|---:|---|---:|",
    ]
    for field, stats in result["saturation"].items():
        rho = stats["spearman_steps_to_terminal"]
        lines.append(
            f"| {field} | {stats['min']:.3f} | {stats['max']:.3f} | "
            f"{stats['mean']:.3f} | {stats['distinct_values']} | "
            f"{'yes' if stats['saturated'] else 'no'} | "
            f"{'-' if rho is None else f'{rho:.3f}'} |"
        )
    lines.extend(
        [
            "",
            "## Snapshots",
            "",
            "| snapshot | step | to-go | A | R settled min/mean |"
            " zero classes | Hall def | Hall ratio |",
            "|---|---:|---:|---:|---|---:|---:|---:|",
        ]
    )
    for row in sorted(
        result["rows"], key=lambda item: (item["case_id"], item["step"])
    ):
        ratio = row["hall_ratio_settled"]
        lines.append(
            f"| {row['case_id']}:{row['step']} | {row['step']} | "
            f"{row['steps_to_terminal']} | {row['acceptance_A']} | "
            f"{row['r_settled_min']:.1f} / {row['r_settled_mean']:.1f} | "
            f"{row['r_settled_zero_classes']} | "
            f"{row['hall_deficiency_settled']} | "
            f"{'-' if ratio is None else f'{ratio:.2f}'} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset-root", type=pathlib.Path, default=DEFAULT_DATASET_ROOT
    )
    parser.add_argument(
        "--output-dir", type=pathlib.Path, default=DEFAULT_OUTPUT_DIR
    )
    parser.add_argument("--stride", type=int, default=DEFAULT_STRIDE)
    parser.add_argument("--phases", type=int, default=DEFAULT_PHASES)
    parser.add_argument(
        "--limit-snapshots",
        type=int,
        default=0,
        help="Stop after N snapshots (0 = all). For cost probes.",
    )
    parser.add_argument(
        "--max-anchors", type=int, default=DEFAULT_MAX_ANCHORS
    )
    args = parser.parse_args()

    agent = load_agent_module()
    dataset_dirs = sorted(
        path for path in args.dataset_root.iterdir() if path.is_dir()
    )
    rows = collect_rows(
        dataset_dirs,
        agent,
        stride=args.stride,
        phases=args.phases,
        max_anchors=args.max_anchors,
        limit=args.limit_snapshots,
    )
    if not rows:
        print("no snapshots", file=sys.stderr)
        return 1

    result = {
        "n_snapshots": len(rows),
        "stride": args.stride,
        "phases": args.phases,
        "any_capped": any(row["accept_capped"] for row in rows),
        "class_prior": [entry["name"] for entry in BAGGAGE_TYPES],
        "saturation": saturation_report(rows),
        "rows": rows,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "board-value-f1.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (args.output_dir / "board-value-f1.md").write_text(
        render_markdown(result), encoding="utf-8"
    )
    print(args.output_dir / "board-value-f1.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
