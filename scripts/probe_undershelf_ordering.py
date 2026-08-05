"""
Is the space under the main shelf a now-or-never region?

Forcing a placement there on an EMPTY container succeeds -- physics returns
is_included / is_valid / is_placed_safe all true. Trying the same at the
board the agent stops on finds no legal pose at all: zero candidates clear
the shipped contract, so the volume closes during the episode.

That makes the interesting question an ordering one, which is exactly L4's
job. This fills the under-shelf volume FIRST, then hands the board back to
the shipped agent and lets it finish. If the total beats the baseline, the
agent is losing placements by never entering a region that only accepts
items early.

Both arms replay the same case with the same seed. The agent is
deadline-driven, so the two arms are still not perfectly paired -- this
reports the count, not a significance claim.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(".").resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "simulator"))

from scripts.measure_anchor_recall import load_agent_module, policy_observation  # noqa: E402
from scripts.fast_afterstate_env import AfterstateBoard  # noqa: E402
from src.ground_handling.env import GroundHandlingEnv  # noqa: E402

ag = load_agent_module()


def poses(container, item, floor, shelf, board=None):
    """
    Grid poses wholly under the main shelf, each at its DROP height.

    The first version pinned every pose to `floor`, so it only ever
    proposed a first layer -- and the under-shelf volume is 0.74 m tall.
    That is why the prefill arms seeded 2 items and the region looked
    fungible. Filling it with stacking allowed reaches 6 items and 30.5%
    of the volume, so the earlier rejection was measuring the bug.
    """
    under = float(shelf.minimum[2])
    ylo, yhi = float(shelf.minimum[1]), float(shelf.maximum[1])
    half = container["length"] / 2.0
    out = []
    for orientation in ag.unique_orientations(item):
        dx, dy, dz = ag.get_rotated_dimensions(
            item["length"], item["width"], item["height"], orientation
        )
        if floor + dz > under - 0.02:
            continue
        y = ylo + dy / 2.0 + 0.01
        while y + dy / 2.0 <= yhi:
            x = -half + dx / 2.0
            while x + dx / 2.0 <= half:
                out.append((orientation, round(x, 3), round(y, 3), dx, dy, dz))
                x += 0.05
            y += 0.05
    return out


def prefill(env, raw, container_index, budget):
    """Place as many items as will fit under the main shelf, largest first."""
    placed = 0
    while placed < budget:
        obs = policy_observation(env, raw)
        container = obs["container_list"][container_index]
        mains = [a for a in ag.shelf_aabbs(container) if a.name == "main_shelf"]
        if not mains:
            return raw, placed, False
        shelf = mains[0]
        floor = float(container["thickness"]) + ag.INCLUSION_CLEARANCE
        pool = sorted(
            enumerate(obs["pool_list"]),
            key=lambda kv: -(kv[1]["length"] * kv[1]["width"] * kv[1]["height"]),
        )
        progressed = False
        for slot, item in pool:
            for orientation, x, y, dx, dy, dz, bottom in poses(
                container, item, floor, shelf, AfterstateBoard(ag, container)
            ):
                box = ag.AABB(
                    center=(x, y, bottom + dz / 2.0),
                    size=(dx, dy, dz),
                    name="release_candidate",
                )
                if ag.Geometry.release_rejection_reason(box, container) is not None:
                    continue
                action = {
                    "item_idx": slot,
                    "container_idx": container_index,
                    "place_pos": [x, y, bottom + dz / 2.0],
                    "orientation": int(orientation),
                }
                raw, _r, term, trunc, info = env.step(action)
                status = (info or {}).get("status", {})
                if all(
                    bool(status.get(k))
                    for k in ("is_included", "is_valid", "is_placed_safe")
                ):
                    placed += 1
                    progressed = True
                if term or trunc:
                    return raw, placed, True
                break
            if progressed:
                break
        if not progressed:
            break
    return raw, placed, False


def run(config_path, container_index, prefill_budget):
    cfg = json.loads(pathlib.Path(config_path).read_text(encoding="utf-8"))
    case = list(cfg.values())[0]
    env = GroundHandlingEnv(
        config=json.loads(json.dumps(case)), verbose=False, render_mode=None
    )
    solver = ag.Agent("")
    env.reset_settings()
    solver.get_init_states(env.get_init_states())
    env.reset_item_stream()
    raw, _ = env.reset(seed=42)

    seeded = 0
    done = False
    if prefill_budget:
        raw, seeded, done = prefill(env, raw, container_index, prefill_budget)

    placed = 0
    while not done:
        obs = policy_observation(env, raw)
        action = solver.policy(obs)
        if solver.last_action_source == "unsafe_protocol_fallback":
            break
        raw, _r, term, trunc, info = env.step(action)
        status = (info or {}).get("status", {})
        if not all(
            bool(status.get(k)) for k in ("is_included", "is_valid", "is_placed_safe")
        ):
            break
        placed += 1
        if term or trunc:
            break
    env.close()
    return {"prefilled": seeded, "agent_placed": placed, "total": seeded + placed}


if __name__ == "__main__":
    result = run(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
    print(json.dumps(result))
