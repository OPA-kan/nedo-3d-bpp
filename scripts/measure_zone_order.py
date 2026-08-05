"""
Does the loading order over zones matter, and which order wins?

The corridor measurement says the loss is reachability: at the terminal
board of dual-shelf-mixed, 62.9% of the poses where the space is free and
the item fits are refused only by `transport_path_clear`, and they sit deep
while the legal ones sit by the door. Transport enters at `y = -width/2`
and runs toward +y, so anything parked in front spends the lane behind it.

That makes loading order the lever, and the doctrine to test is:

    shelf top (if any) -> deep -> centre -> under the shelf

with under-shelf LAST, because it is a dead-end pocket that should only be
used when nothing else can reach. The reverse is the unloading order.

This tests it the cheap way. No ranker, no deadline, no learned anything: a
greedy filler that visits zones in a given order and drops every item it
can, on the real container, through the shipped contract and real physics.
Orders are compared on the same case, and the filler itself is
deterministic, so the comparison does not inherit the agent's run-to-run
spread (36 vs 35 placements on identical arguments).

What it can show: whether zone order changes how much fits at all. What it
cannot: what the shipped agent would score, since the agent also weighs
cog, stability and attributes that this filler ignores entirely.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "simulator"))

from scripts.measure_anchor_recall import (  # noqa: E402
    load_agent_module,
    policy_observation,
)
from src.ground_handling.env import GroundHandlingEnv  # noqa: E402

ag = load_agent_module()

ZONES = ("shelf_top", "deep", "centre", "under_shelf")
# Poses the shipped risk model prices above this are skipped. Not a policy
# proposal -- it only stops the filler destroying itself before the zone
# order has a chance to matter.
RISK_CAP = 0.15


def shelf_of(container):
    plates = [a for a in ag.shelf_aabbs(container) if a.name == "main_shelf"]
    return plates[0] if plates else None


def zone_of(y, top_z, shelf, width):
    """
    Which zone a pose belongs to.

    Deep and centre are split at a quarter of the width from the far wall,
    which is where the corridor scan put the boundary between blocked and
    legal poses (medians +0.250 and -0.400 on a 1.45 m container).

    On a container with a main shelf there is effectively no deep FLOOR
    zone: the shelf spans y 0.05..0.71 against a half-width of 0.76, so
    everything deep and low is under it. A first version of this classifier
    reported deep=0 on every arm, which read as a bug and is not one -- the
    four-zone doctrine collapses to shelf_top / under_shelf there, and only
    a shelf-less container distinguishes deep from centre.
    """
    if shelf is not None:
        if top_z > float(shelf.maximum[2]) - 1e-6:
            return "shelf_top"
        if float(shelf.minimum[1]) <= y <= float(shelf.maximum[1]):
            return "under_shelf"
    return "deep" if y >= width / 2.0 - width / 4.0 else "centre"


def candidates(container, item, shelf, stride):
    from scripts.fast_afterstate_env import AfterstateBoard

    board = AfterstateBoard(ag, container)
    width = float(container["width"])
    out = []
    x = board.x0 + stride / 2.0
    while x < -board.x0:
        y = board.y0 + stride / 2.0
        while y < -board.y0:
            for orientation in ag.unique_orientations(item):
                dx, dy, dz = ag.get_rotated_dimensions(
                    item["length"], item["width"], item["height"], orientation
                )
                bottom = float(board.drop_height(x, y, dx, dy))
                candidate = ag.AABB(
                    center=(x, y, bottom + dz / 2.0),
                    size=(dx, dy, dz),
                    name="release_candidate",
                )
                if (
                    ag.Geometry.release_rejection_reason(candidate, container)
                    is not None
                ):
                    continue
                # Without this the filler picks the deepest pose in the
                # zone, stacks against the far wall and topples within a
                # handful of placements -- every arm of the first run died
                # at 4 to 9 against the agent's 35, so it was measuring
                # which zone kills first, not which order packs more.
                _adjusted, p_rot = ag.risk_adjusted_score(
                    0.0, candidate, item, container, int(orientation), 1.0
                )
                if p_rot is not None and p_rot >= RISK_CAP:
                    continue
                out.append(
                    {
                        "x": float(x),
                        "y": float(y),
                        "z": bottom + dz / 2.0,
                        "orientation": int(orientation),
                        "p_rot": 0.0 if p_rot is None else float(p_rot),
                        "support": float(
                            ag.Geometry.support_ratio(candidate, container)
                        ),
                        "zone": zone_of(
                            float(y), bottom + dz, shelf, width
                        ),
                    }
                )
            y += stride
        x += stride
    return out


def fill(config_path, order, container_index, stride):
    config = json.loads(pathlib.Path(config_path).read_text(encoding="utf-8"))
    key, case = next(iter(config.items()))
    env = GroundHandlingEnv(
        config=json.loads(json.dumps(case)), verbose=False, render_mode=None
    )
    solver = ag.Agent("")
    env.reset_settings()
    solver.get_init_states(env.get_init_states())
    env.reset_item_stream()
    raw, _ = env.reset(seed=42)

    rank = {zone: index for index, zone in enumerate(order)}
    placed = 0
    per_zone = {zone: 0 for zone in ZONES}
    outcome = "exhausted"
    while True:
        observation = policy_observation(env, raw)
        container = observation["container_list"][container_index]
        shelf = shelf_of(container)
        best = None
        best_slot = None
        for slot, item in enumerate(observation["pool_list"]):
            for entry in candidates(container, item, shelf, stride):
                # zone first, then the safest pose in it, then the
                # deepest: inside a lane the far end is the one that stops
                # being reachable, but reaching for it on a bad support is
                # how the first version killed every arm.
                score = (
                    rank.get(entry["zone"], len(order)),
                    -round(entry["support"], 2),
                    round(entry["p_rot"], 3),
                    -entry["y"],
                )
                if best is None or score < best[0]:
                    best = (score, entry)
                    best_slot = slot
        if best is None:
            break
        entry = best[1]
        action = {
            "item_idx": best_slot,
            "container_idx": container_index,
            "place_pos": [entry["x"], entry["y"], entry["z"]],
            "orientation": entry["orientation"],
        }
        raw, _r, terminated, truncated, info = env.step(action)
        status = (info or {}).get("status", {})
        if not all(
            bool(status.get(f))
            for f in ("is_included", "is_valid", "is_placed_safe")
        ):
            outcome = f"rejected in {entry['zone']}"
            break
        placed += 1
        per_zone[entry["zone"]] += 1
        if terminated or truncated:
            outcome = "terminated"
            break
    env.close()
    return {
        "case": key,
        "order": list(order),
        "placed": placed,
        "per_zone": per_zone,
        "outcome": outcome,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--container", type=int, default=0)
    parser.add_argument("--stride", type=float, default=0.10)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    orders = {
        "doctrine": ("shelf_top", "deep", "centre", "under_shelf"),
        "reversed": ("under_shelf", "centre", "deep", "shelf_top"),
        "near_first": ("centre", "under_shelf", "deep", "shelf_top"),
        "deep_only_first": ("deep", "shelf_top", "centre", "under_shelf"),
    }
    results = []
    for name, order in orders.items():
        result = fill(args.config, order, args.container, args.stride)
        result["name"] = name
        results.append(result)
        zones = " ".join(
            f'{z}={result["per_zone"][z]}' for z in ZONES
        )
        print(
            f'{name:16s} placed {result["placed"]:3d}  '
            f'({result["outcome"]})  {zones}',
            flush=True,
        )
    best = max(results, key=lambda r: r["placed"])
    print(f'\nbest: {best["name"]} at {best["placed"]} placements')
    print(
        "greedy filler only -- it ignores cog, stability and the attribute "
        "rules the official score also grades, so a higher count here is "
        "not a higher score."
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
