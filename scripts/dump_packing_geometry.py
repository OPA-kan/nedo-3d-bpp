"""
Replay a case to termination and dump the geometry of what got packed.

The output is what the section drawings are built from, and it is
deliberately raw: the container's published half-spaces, the shelf AABBs the
agent derives from `cut_x` and the shelf flag, and every settled item AABB
as `packed_aabbs_local` reports it. Nothing is normalised or idealised --
the point of looking at these boards is that the envelope is not the box
`length x width x height` implies.

Two fields exist because reading them wrong cost a wrong conclusion:

  offset_x   `points`/`n_vecs` live in a frame offset in x, while items are
             local. Without it the second container's outline is drawn 2.5 m
             away from its contents.
  shelf      `container_requires_shelf` reads the `shelf` key first and only
             then `require_shelf`; asking for `require_shelf` directly
             reports False for a container that has a main shelf.

Usage:
    python scripts/dump_packing_geometry.py CONFIG CASE_ID OUTPUT.json
"""
from __future__ import annotations

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


def reachability_map(agent_module, container, item, stride=0.10):
    """
    At the board the episode ended on, why each column is or is not usable.

    Three outcomes per (x, y), tested at the drop height a release would
    reach, in the order the shipped contract tests them:

      supported     the item can go here AND its settled proxy clears
                    MIN_SUPPORT_RATIO -- somewhere it would actually stand
      unsupported   the release contract allows the drop, but the pose
                    would rest on too little
      blocked       it fits and the space is free, but transport_path_clear
                    refuses -- reachability spent by earlier placements
      no room       containment or static geometry refuses

    The supported/unsupported split is not cosmetic. `release_rejection_reason`
    tests containment, static geometry, the corridor and the attribute guard
    -- and NOT support; only the settled path calls `has_stable_support`. So
    an earlier version of this map reported "legal" for columns nothing would
    stand on, and `usable = fits AND reachable AND supportable` was being
    read off two of its three terms.

    Support is measured on `settled_proxy_candidate`, not on the release pose
    itself: a release candidate is sent 16 mm clear of its surface and scores
    support 0 by construction, so testing it directly would call every column
    unsupported.

    Only `blocked` and `unsupported` are recoverable by placing differently,
    and they are recoverable in different ways, which is why they are counted
    apart rather than folded into one rejection total.

    A column counts as `legal` when ANY orientation fits there. Testing a
    single orientation reported zero legal columns on boards a 5 cm
    all-orientation scan had found 34 placements on -- the map was drawing
    the first orientation's luck, not the board's.
    """
    from scripts.fast_afterstate_env import AfterstateBoard

    board = AfterstateBoard(agent_module, container)
    orientations = list(agent_module.unique_orientations(item))
    rank = {"no_room": 0, "blocked": 1, "unsupported": 2, "supported": 3}
    minimum_support = float(
        getattr(agent_module, "MIN_SUPPORT_RATIO", 0.55)
    )
    cells = []
    x = board.x0 + stride / 2.0
    while x < -board.x0:
        y = board.y0 + stride / 2.0
        while y < -board.y0:
            best = "no_room"
            best_bottom = None
            for orientation in orientations:
                dx, dy, dz = agent_module.get_rotated_dimensions(
                    item["length"], item["width"], item["height"], orientation
                )
                bottom = float(board.drop_height(x, y, dx, dy))
                candidate = agent_module.AABB(
                    center=(x, y, bottom + dz / 2.0),
                    size=(dx, dy, dz),
                    name="release_candidate",
                )
                if not agent_module.Geometry.inside_container(
                    candidate, container
                ):
                    state = "no_room"
                elif not agent_module.Geometry.clears_static_geometry(
                    candidate, container
                ):
                    state = "no_room"
                elif not agent_module.Geometry.transport_path_clear(
                    candidate, container
                ):
                    state = "blocked"
                else:
                    proxy = agent_module.settled_proxy_candidate(
                        candidate, container
                    )
                    support = float(
                        agent_module.Geometry.support_ratio(proxy, container)
                    )
                    state = (
                        "supported" if support >= minimum_support
                        else "unsupported"
                    )
                if rank[state] > rank[best]:
                    best, best_bottom = state, bottom
                if best == "supported":
                    break
            cells.append(
                [
                    round(float(x), 3),
                    round(float(y), 3),
                    round(best_bottom if best_bottom is not None else 0.0, 3),
                    best,
                ]
            )
            y += stride
        x += stride
    counts = {"supported": 0, "unsupported": 0, "blocked": 0, "no_room": 0}
    for cell in cells:
        counts[cell[3]] += 1
    return {
        "stride": stride,
        "counts": counts,
        "orientations": len(orientations),
        "item": [
            round(float(item[k]), 3) for k in ("length", "width", "height")
        ],
        "cells": cells,
    }


def classify_termination(source, status, maps):
    """
    Why the episode stopped, in terms that do not average together.

    Five endings were being scored as one "space utilisation failure", and
    they are not the same event: a board that topples with 80 placeable
    columns left and a board with 2 reachable columns need opposite repairs.
    Reading them as one number mixes the learning signal.

    `maps` is the per-container reachability census at the terminal board.
    """
    if status and not status.get("is_placed_safe", True):
        return "stability_termination"
    if status and not status.get("is_valid", True):
        return "transport_invalid"
    if status and not status.get("is_included", True):
        return "containment_violation"
    if source != "unsafe_protocol_fallback":
        return "stream_or_step_limit"

    totals = {"supported": 0, "unsupported": 0, "blocked": 0, "no_room": 0}
    for census in maps:
        for key in totals:
            totals[key] += census.get(key, 0)
    if totals["supported"] > 0:
        # the contract admits a supported pose somewhere and the agent still
        # returned the fallback -- the search, not the board, ran out
        return "search_exhaustion"
    if totals["unsupported"] > 0 and totals["blocked"] == 0:
        return "support_surface_exhaustion"
    if totals["blocked"] > 0 and totals["unsupported"] == 0:
        return "transport_exhaustion"
    if totals["blocked"] > 0 or totals["unsupported"] > 0:
        return "support_and_transport_exhaustion"
    return "geometric_exhaustion"


def dump(config_path, case_key, output_path):
    agent_module = load_agent_module()
    config = json.loads(pathlib.Path(config_path).read_text(encoding="utf-8"))
    case = config.get(case_key) or next(iter(config.values()))
    env = GroundHandlingEnv(
        config=json.loads(json.dumps(case)), verbose=False, render_mode=None
    )
    solver = agent_module.Agent("")
    env.reset_settings()
    solver.get_init_states(env.get_init_states())
    env.reset_item_stream()
    raw, _ = env.reset(seed=42)

    step = 0
    final_status = {}
    final_source = None
    try:
        while True:
            observation = policy_observation(env, raw)
            action = solver.policy(observation)
            final_source = solver.last_action_source
            if final_source == "unsafe_protocol_fallback":
                break
            raw, _reward, terminated, truncated, info = env.step(action)
            status = (info or {}).get("status", {})
            final_status = {k: bool(v) for k, v in status.items()}
            step += 1
            if not all(
                bool(status.get(flag))
                for flag in ("is_included", "is_valid", "is_placed_safe")
            ):
                break
            if terminated or truncated:
                break
    finally:
        observation = policy_observation(env, raw)
        containers = []
        for index, container in enumerate(observation["container_list"]):
            items = []
            for packed, is_soft, is_prioritized in agent_module.packed_aabbs_local(
                container
            ):
                items.append(
                    {
                        "c": [round(float(v), 4) for v in packed.center],
                        "s": [round(float(v), 4) for v in packed.size],
                        "soft": bool(is_soft),
                        "prio": bool(is_prioritized),
                    }
                )
            containers.append(
                {
                    "index": index,
                    "length": float(container["length"]),
                    "width": float(container["width"]),
                    "height": float(container["height"]),
                    "thickness": float(container["thickness"]),
                    "buffer": float(container.get("buffer") or 0.0),
                    "cut_x": float(container.get("cut_x") or 0.0),
                    "cut_y": float(container.get("cut_y") or 0.0),
                    "offset_x": float(agent_module.container_offset_x(container)),
                    "shelf": bool(agent_module.container_requires_shelf(container)),
                    "prio": bool(container.get("is_prioritized")),
                    "shelves": [
                        {
                            "min": [float(v) for v in plate.minimum],
                            "max": [float(v) for v in plate.maximum],
                            "name": plate.name,
                        }
                        for plate in agent_module.shelf_aabbs(container)
                    ],
                    "points": [
                        [float(v) for v in point]
                        for point in (container.get("points") or [])
                    ],
                    "n_vecs": [
                        [float(v) for v in normal]
                        for normal in (container.get("n_vecs") or [])
                    ],
                    "items": items,
                }
            )
            pool = observation.get("pool_list") or []
            if pool:
                try:
                    containers[-1]["reachability"] = reachability_map(
                        agent_module, container, pool[0]
                    )
                except Exception as error:  # a map is a nicety, the dump is not
                    containers[-1]["reachability_error"] = str(error)
        census = [
            c["reachability"]["counts"]
            for c in containers
            if isinstance(c.get("reachability"), dict)
            and "counts" in c["reachability"]
        ]
        payload = {
            "case": case_key,
            "steps": step,
            "final_status": final_status,
            "final_source": final_source,
            "termination": classify_termination(
                final_source, final_status, census
            ),
            "containers": containers,
        }
        pathlib.Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(output_path).write_text(
            json.dumps(payload), encoding="utf-8"
        )
        summary = ", ".join(
            f'c{c["index"]}={len(c["items"])} items' for c in containers
        )
        print(
            f'{case_key}: {step} steps, {summary}, '
            f'termination={payload["termination"]} -> {output_path}'
        )
        for c in containers:
            counts = (c.get("reachability") or {}).get("counts")
            if counts:
                print(
                    f'   c{c["index"]}  supported {counts["supported"]:3d}  '
                    f'unsupported {counts["unsupported"]:3d}  '
                    f'blocked {counts["blocked"]:3d}  '
                    f'no_room {counts["no_room"]:3d}'
                )
        try:
            env.close()
        except Exception:
            pass


if __name__ == "__main__":
    dump(sys.argv[1], sys.argv[2], sys.argv[3])
