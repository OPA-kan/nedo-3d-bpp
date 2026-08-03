"""
Geometric pockets and per-class margins: the first stage only.

Two measured breakdowns forced this change of primitive. Discrete candidate
counts are CONSTANT across the safe actions at a decision point while the
outcome differs -- zero information, not weak correlation -- and slot counts
derived from candidate positions are contaminated by generator density: at
c001-k1 step 18 the same physical board gave 135 candidates per slot for the
smallest class and 22 for a mid-sized one. Neither is a property of the board.

So the observation unit moves from candidate points to pockets built from
geometry: a support-plane component, a maximal free rectangle on it, and the
vertical clearance above that rectangle. Nothing here is derived from where
the anchor generator happens to sample.

STAGE 1 ONLY, deliberately. This computes (w, l, h) and nothing else -- no
corridor reachability, no support quality. If the margins fail to separate
actions with corridor and support included from the start, the failure cannot
be attributed. Those attributes go in after this stage is shown to reproduce
the known dead ends.

Pockets are validated through the same Geometry contract the candidate
generator uses, so "a pocket exists" cannot disagree with "the oracle found a
candidate" for reasons of definition.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SIMULATOR = ROOT / "simulator"

from scripts.measure_anchor_recall import (  # noqa: E402
    json_safe,
    load_agent_module,
    policy_observation,
)
from scripts.measure_board_value import BAGGAGE_TYPES  # noqa: E402

DEFAULT_CELL = 0.05
# Every distinct footprint/height a published type can present. The pocket
# frontier only has to resolve heights the arrivals actually need.
def class_orientations() -> list[dict[str, Any]]:
    poses = []
    for entry in BAGGAGE_TYPES:
        dims = (
            float(entry["length"]),
            float(entry["width"]),
            float(entry["height"]),
        )
        seen = set()
        for i in range(3):
            for j in range(3):
                if i == j:
                    continue
                k = 3 - i - j
                pose = (dims[i], dims[j], dims[k])
                key = (round(min(pose[0], pose[1]), 6),
                       round(max(pose[0], pose[1]), 6),
                       round(pose[2], 6))
                if key in seen:
                    continue
                seen.add(key)
                poses.append(
                    {
                        "class": entry["name"],
                        "footprint": (pose[0], pose[1]),
                        "height": pose[2],
                    }
                )
    return poses


def support_levels(agent, container) -> list[float]:
    tops = {
        round(float(component.top), 6)
        for component in agent.support_plane_components(
            agent.support_surfaces(container)
        )
    }
    return sorted(tops)


def usable_mask(
    agent, container, level: float, height: float, cell: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Cells where a probe of the given height, resting on ``level``, is legal.

    The probe is one cell wide, so the mask answers "is this square metre of
    the level usable at all", independent of any particular item. Legality is
    the agent's own contract -- inclusion, static geometry, stable support --
    so a pocket cannot exist where the generator would refuse a candidate.
    """
    length = float(container["length"])
    width = float(container["width"])
    xs = np.arange(-length / 2.0 + cell / 2.0, length / 2.0, cell)
    ys = np.arange(-width / 2.0 + cell / 2.0, width / 2.0, cell)
    mask = np.zeros((len(ys), len(xs)), dtype=bool)
    size = (cell, cell, height)
    for row, y in enumerate(ys):
        for col, x in enumerate(xs):
            probe = agent.AABB(
                center=(float(x), float(y), level + height / 2.0),
                size=size,
                name="pocket_probe",
            )
            if not agent.Geometry.inside_container(probe, container):
                continue
            if not agent.Geometry.clears_static_geometry(probe, container):
                continue
            if not agent.Geometry.has_stable_support(probe, container):
                continue
            mask[row, col] = True
    return mask, xs, ys


def maximal_rectangles(mask: np.ndarray) -> list[tuple[int, int, int, int]]:
    """
    Every rectangle of true cells that cannot be grown in any direction.

    Not the single largest: a board with one wide-flat pocket and one
    narrow-tall pocket is exactly the case the two-scalar reduction got
    wrong, so the frontier needs both.
    """
    rows, cols = mask.shape
    found: set[tuple[int, int, int, int]] = set()
    heights = np.zeros(cols, dtype=int)
    for row in range(rows):
        heights = np.where(mask[row], heights + 1, 0)
        for col in range(cols):
            if heights[col] == 0:
                continue
            limit = heights[col]
            left = col
            while left > 0 and heights[left - 1] >= limit:
                left -= 1
            right = col
            while right + 1 < cols and heights[right + 1] >= limit:
                right += 1
            # Only keep it if it cannot be grown upward at this width.
            if row + 1 < rows and all(
                mask[row + 1, index] for index in range(left, right + 1)
            ):
                continue
            found.add((left, right, row - limit + 1, row))
    # Drop rectangles contained in another.
    rectangles = sorted(found)
    maximal = []
    for rect in rectangles:
        x0, x1, y0, y1 = rect
        if any(
            other != rect
            and other[0] <= x0
            and x1 <= other[1]
            and other[2] <= y0
            and y1 <= other[3]
            for other in rectangles
        ):
            continue
        maximal.append(rect)
    return maximal


def extract_pockets(
    agent, container, container_index: int, cell: float, cap: int
) -> dict[str, Any]:
    poses = class_orientations()
    heights = sorted({round(pose["height"], 6) for pose in poses})
    levels = support_levels(agent, container)
    raw: list[dict[str, Any]] = []
    for level in levels:
        for height in heights:
            mask, xs, ys = usable_mask(
                agent, container, level, height, cell
            )
            if not mask.any():
                continue
            for x0, x1, y0, y1 in maximal_rectangles(mask):
                raw.append(
                    {
                        "container": container_index,
                        "level": level,
                        "height": height,
                        "w": float((x1 - x0 + 1) * cell),
                        "l": float((y1 - y0 + 1) * cell),
                        "x": float((xs[x0] + xs[x1]) / 2.0),
                        "y": float((ys[y0] + ys[y1]) / 2.0),
                    }
                )
    deduped = dedupe(raw)
    frontier = pareto_frontier(deduped)
    capped = len(frontier) > cap
    return {
        "pockets_raw": len(raw),
        "pockets_after_dedup": len(deduped),
        "pareto_size": len(frontier),
        "pocket_cap": cap,
        "pocket_capped": capped,
        "cap_rule": "largest min-side first; recorded so a cap is never read as absence",
        "pockets": sorted(
            frontier,
            key=lambda p: -min(p["w"], p["l"]),
        )[:cap],
    }


def dedupe(pockets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    One physical pocket produces many near-identical rectangles across the
    height sweep. Collapsing them keeps the frontier from tracking the height
    discretisation the way slot counts tracked generator density.
    """
    kept: list[dict[str, Any]] = []
    for pocket in sorted(
        pockets, key=lambda p: (-p["w"] * p["l"], -p["height"])
    ):
        duplicate = False
        for other in kept:
            if other["container"] != pocket["container"]:
                continue
            if abs(other["level"] - pocket["level"]) > 1e-6:
                continue
            if abs(other["height"] - pocket["height"]) > 1e-6:
                continue
            if (
                abs(other["x"] - pocket["x"]) < 0.10
                and abs(other["y"] - pocket["y"]) < 0.10
                and abs(other["w"] - pocket["w"]) < 0.10
                and abs(other["l"] - pocket["l"]) < 0.10
            ):
                duplicate = True
                break
        if not duplicate:
            kept.append(pocket)
    return kept


def pareto_frontier(pockets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop pockets beaten on width, length and height at once."""
    frontier = []
    for pocket in pockets:
        dominated = False
        for other in pockets:
            if other is pocket:
                continue
            if (
                other["container"] == pocket["container"]
                and other["w"] >= pocket["w"]
                and other["l"] >= pocket["l"]
                and other["height"] >= pocket["height"]
                and (
                    other["w"] > pocket["w"]
                    or other["l"] > pocket["l"]
                    or other["height"] > pocket["height"]
                )
            ):
                dominated = True
                break
        if not dominated:
            frontier.append(pocket)
    return frontier


def pocket_margin(pocket: dict[str, Any], pose: dict[str, Any]) -> float:
    """
    Simultaneous relative slack. A pocket wide enough but too low scores by
    the height term, which is the coupling the two-scalar reduction lost.
    """
    fw, fl = pose["footprint"]
    height = pose["height"]
    options = []
    for width, length in ((fw, fl), (fl, fw)):
        options.append(
            min(
                (pocket["w"] - width) / width,
                (pocket["l"] - length) / length,
                (pocket["height"] - height) / height,
            )
        )
    return max(options)


def pose_fits_pocket(agent, containers, pocket, pose) -> bool:
    """
    Validate the pocket with a REAL item, not the one-cell probe.

    Stage 1 built the mask from cell-sized probes and failed its first test:
    at a state where the oracle enumerated both generators and found zero
    candidates, five of seven classes still showed positive margin. Cell-level
    validity does not compose to item-level validity, and corridor clearance is
    the reason it cannot -- a 5 cm probe sweeps a 5 cm corridor while a 0.45 m
    item sweeps a 0.45 m one. Support ratio has the same shape of problem.

    So a pocket only counts for a class if an item of that class, placed there,
    passes the same contract the candidate generator applies.
    """
    container = containers[int(pocket["container"])]
    footprint = pose["footprint"]
    for width, length in (footprint, (footprint[1], footprint[0])):
        if width > pocket["w"] + 1e-9 or length > pocket["l"] + 1e-9:
            continue
        probe = agent.AABB(
            center=(
                float(pocket["x"]),
                float(pocket["y"]),
                float(pocket["level"]) + pose["height"] / 2.0,
            ),
            size=(float(width), float(length), float(pose["height"])),
            name="pocket_item_probe",
        )
        if agent.Geometry.rejection_reason(probe, container) is None:
            return True
    return False


def class_margins(
    pockets: list[dict[str, Any]], agent=None, containers=None
) -> dict[str, Any]:
    poses = class_orientations()
    result = {}
    for entry in BAGGAGE_TYPES:
        name = entry["name"]
        own = [pose for pose in poses if pose["class"] == name]
        scored = []
        for pocket in pockets:
            usable = own
            if agent is not None and containers is not None:
                usable = [
                    pose
                    for pose in own
                    if pose_fits_pocket(agent, containers, pocket, pose)
                ]
            if not usable:
                continue
            best = max(pocket_margin(pocket, pose) for pose in usable)
            scored.append((best, pocket))
        scored.sort(key=lambda item: -item[0])
        # Independent escape routes: a second pocket at the same level and
        # overlapping footprint is the same route seen twice.
        chosen: list[tuple[float, dict[str, Any]]] = []
        for margin, pocket in scored:
            if any(
                other["container"] == pocket["container"]
                and abs(other["level"] - pocket["level"]) < 1e-6
                and abs(other["x"] - pocket["x"]) < 0.20
                and abs(other["y"] - pocket["y"]) < 0.20
                for _m, other in chosen
            ):
                continue
            chosen.append((margin, pocket))
            if len(chosen) >= 2:
                break
        result[name] = {
            "mu_1": chosen[0][0] if chosen else -1.0,
            "mu_2": chosen[1][0] if len(chosen) > 1 else -1.0,
            "extinct": not chosen or chosen[0][0] <= 0.0,
        }
    return result


def board_margins(agent, containers, cell: float, cap: int) -> dict[str, Any]:
    pockets: list[dict[str, Any]] = []
    stats = {
        "pockets_raw": 0,
        "pockets_after_dedup": 0,
        "pareto_size": 0,
        "pocket_capped": False,
    }
    for index, container in enumerate(containers):
        extracted = extract_pockets(agent, container, index, cell, cap)
        pockets.extend(extracted["pockets"])
        for key in ("pockets_raw", "pockets_after_dedup", "pareto_size"):
            stats[key] += extracted[key]
        stats["pocket_capped"] = (
            stats["pocket_capped"] or extracted["pocket_capped"]
        )
        stats["pocket_cap"] = extracted["pocket_cap"]
        stats["cap_rule"] = extracted["cap_rule"]
    margins = class_margins(pockets, agent, containers)
    alive = [name for name, row in margins.items() if not row["extinct"]]
    return {
        **stats,
        "pocket_count": len(pockets),
        "class_margins": margins,
        "extinct_classes": sum(
            1 for row in margins.values() if row["extinct"]
        ),
        "alive_classes": alive,
        "min_mu_1": min(row["mu_1"] for row in margins.values()),
        "min_mu_2": min(row["mu_2"] for row in margins.values()),
        "sole_route_classes": sum(
            1
            for row in margins.values()
            if row["mu_1"] > 0.0 and row["mu_2"] <= 0.0
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument(
        "--step",
        type=int,
        required=True,
        help="Replay to this step and describe the board the agent faces.",
    )
    parser.add_argument("--cell", type=float, default=DEFAULT_CELL)
    parser.add_argument(
        "--pocket-cap",
        type=int,
        default=10000,
        help=(
            "Deliberately huge for the validation runs: measure the real "
            "frontier size first, then set a production cap from it."
        ),
    )
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    from scripts.measure_dead_end_branch import replay_to_step  # noqa: E402

    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.case not in config:
        raise SystemExit(f"unknown case {args.case!r}: {', '.join(config)}")
    agent_module = load_agent_module()
    started = time.perf_counter()
    env, _solver, observation, rescues = replay_to_step(
        agent_module, json.loads(json.dumps(config[args.case])), args.step
    )
    try:
        result = board_margins(
            agent_module,
            observation["container_list"],
            args.cell,
            args.pocket_cap,
        )
    finally:
        try:
            env.close()
        except Exception:
            pass
    result.update(
        {
            "case_id": args.case,
            "step": args.step,
            "cell": args.cell,
            "replay_rescues": rescues,
            "seconds": round(time.perf_counter() - started, 1),
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(json_safe(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"{args.case} step {args.step}: pockets raw={result['pockets_raw']} "
        f"dedup={result['pockets_after_dedup']} pareto={result['pareto_size']} "
        f"capped={result['pocket_capped']}"
    )
    print(
        f"  extinct={result['extinct_classes']}/7 "
        f"sole_route={result['sole_route_classes']} "
        f"min_mu1={result['min_mu_1']:.3f} ({result['seconds']}s)"
    )
    for name, row in result["class_margins"].items():
        print(
            f"    {name:16s} mu1={row['mu_1']:+.3f} mu2={row['mu_2']:+.3f}"
            f"{'  EXTINCT' if row['extinct'] else ''}"
        )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
