"""
How much of the container is free, but no longer reachable?

Transport enters at `y = -width/2` and runs toward +y at the target's x,
then sideways at the target's y. So an item parked mid-depth shadows
everything behind it in that lane: the space stays empty and stops being
usable. The sections show exactly that -- cargo against the far wall with
an empty band in front of it, and an empty far region behind a mid-depth
row.

This separates the two ways a pose can be refused at a real terminal board:

  blocked   passes containment and static geometry -- the space is
            genuinely free and the item fits in it -- but fails
            `transport_path_clear`. Reachability lost to earlier choices.

  no room   fails containment or static geometry. The space is not there.

Only the first is recoverable by ordering, which is why they are counted
apart rather than as one rejection total. The y distribution of the blocked
poses says whether the loss is concentrated at depth, as the corridor model
predicts.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import statistics
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


def scan(container, item, stride):
    """Classify every grid pose at its drop height."""
    from scripts.fast_afterstate_env import AfterstateBoard

    board = AfterstateBoard(ag, container)
    counts = collections.Counter()
    blocked_y = []
    legal_y = []
    x = board.x0 + stride / 2.0
    while x < -board.x0:
        y = board.y0 + stride / 2.0
        while y < -board.y0:
            for orientation in ag.unique_orientations(item):
                dx, dy, dz = ag.get_rotated_dimensions(
                    item["length"], item["width"], item["height"], orientation
                )
                bottom = board.drop_height(x, y, dx, dy)
                candidate = ag.AABB(
                    center=(x, y, bottom + dz / 2.0),
                    size=(dx, dy, dz),
                    name="release_candidate",
                )
                if not ag.Geometry.inside_container(candidate, container):
                    counts["no room (containment)"] += 1
                    continue
                if not ag.Geometry.clears_static_geometry(candidate, container):
                    counts["no room (static geometry)"] += 1
                    continue
                if not ag.Geometry.transport_path_clear(candidate, container):
                    counts["blocked (corridor)"] += 1
                    blocked_y.append(float(y))
                    continue
                counts["legal"] += 1
                legal_y.append(float(y))
            y += stride
        x += stride
    return counts, blocked_y, legal_y


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--stride", type=float, default=0.05)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    key, case = next(iter(config.items()))
    env = GroundHandlingEnv(
        config=json.loads(json.dumps(case)), verbose=False, render_mode=None
    )
    solver = ag.Agent("")
    env.reset_settings()
    solver.get_init_states(env.get_init_states())
    env.reset_item_stream()
    raw, _ = env.reset(seed=42)

    placed = 0
    while True:
        observation = policy_observation(env, raw)
        action = solver.policy(observation)
        if solver.last_action_source == "unsafe_protocol_fallback":
            break
        raw, _r, terminated, truncated, info = env.step(action)
        status = (info or {}).get("status", {})
        if not all(
            bool(status.get(f))
            for f in ("is_included", "is_valid", "is_placed_safe")
        ):
            break
        placed += 1
        if terminated or truncated:
            break

    observation = policy_observation(env, raw)
    print(f"{key}: {placed} placed; scanning the board it stopped on\n")
    report = []
    for container_index, container in enumerate(observation["container_list"]):
        width = float(container["width"])
        for slot, item in enumerate(observation["pool_list"]):
            counts, blocked_y, legal_y = scan(container, item, args.stride)
            total = sum(counts.values())
            recoverable = counts["blocked (corridor)"]
            print(
                f'container {container_index}, pool item {slot} '
                f'({item["length"]:.2f}x{item["width"]:.2f}x{item["height"]:.2f})'
            )
            for reason, count in counts.most_common():
                print(
                    f'  {reason:28s} {count:6d}  '
                    f'{100 * count / max(total, 1):5.1f}%'
                )
            if blocked_y:
                print(
                    f'  blocked poses sit at y median '
                    f'{statistics.median(blocked_y):+.3f} '
                    f'(entry {-width / 2:+.3f}, far wall {width / 2:+.3f})'
                )
            if legal_y:
                print(
                    f'  legal poses sit at y median '
                    f'{statistics.median(legal_y):+.3f}'
                )
            report.append(
                {
                    "container": container_index,
                    "pool_slot": slot,
                    "counts": dict(counts),
                    "blocked_y_median": (
                        statistics.median(blocked_y) if blocked_y else None
                    ),
                    "legal_y_median": (
                        statistics.median(legal_y) if legal_y else None
                    ),
                    "recoverable_share": recoverable / max(total, 1),
                }
            )
            print()
    env.close()

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {"case": key, "placed": placed, "scans": report},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
