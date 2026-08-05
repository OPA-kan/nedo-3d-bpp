"""
At the board the agent gives up on, what is actually still available?

The voxel pocket count is pure geometry on a 5 cm grid and is an UPPER
bound: it ignores the inclusion clearance, the lateral clearance against
settled items, the transport corridor, the support ratio, and the risk gate
-- every one of which can veto a pocket that looks free. It also cannot see
whether any items remain to place.

So this replays to the stopping point and asks the shipped contract itself,
on the real container, for the items really left in the pool. Three counts
per item, nested:

  geometry   release_rejection_reason is None
  gated      ... and the risk model puts P_rot below the shipped threshold

If geometry is large and gated is zero, the agent stopped because
everything left was judged unsafe, not because the container was full.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(".").resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "simulator"))

from scripts.measure_anchor_recall import load_agent_module, policy_observation  # noqa: E402
from src.ground_handling.env import GroundHandlingEnv  # noqa: E402

ag = load_agent_module()
STRIDE = 0.05
LATTICE = 0.25


def scan(container, item):
    """(geometry slots, gated slots) for one item, deduped on a coarse lattice."""
    from scripts.fast_afterstate_env import AfterstateBoard

    board = AfterstateBoard(ag, container)
    geo, gated = set(), set()
    x = board.x0 + STRIDE / 2.0
    while x < -board.x0:
        y = board.y0 + STRIDE / 2.0
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
                if ag.Geometry.release_rejection_reason(candidate, container) is not None:
                    continue
                key = (
                    int(round(x / LATTICE)),
                    int(round(y / LATTICE)),
                    int(round(bottom / 0.10)),
                )
                geo.add(key)
                try:
                    _adjusted, probability = ag.risk_adjusted_score(
                        0.0, candidate, item, container, int(orientation), 1.0
                    )
                except Exception:
                    probability = None
                if probability is None or probability < 0.5:
                    gated.add(key)
            y += STRIDE
        x += STRIDE
    return len(geo), len(gated)


def main():
    config_path = sys.argv[1]
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

    placed = 0
    reason = "terminated"
    while True:
        obs = policy_observation(env, raw)
        action = solver.policy(obs)
        if solver.last_action_source == "unsafe_protocol_fallback":
            reason = "agent found no safe placement"
            break
        raw, _r, term, trunc, info = env.step(action)
        status = (info or {}).get("status", {})
        if not all(
            bool(status.get(k)) for k in ("is_included", "is_valid", "is_placed_safe")
        ):
            reason = f"simulator rejected: {status}"
            break
        placed += 1
        if term or trunc:
            reason = "episode ended"
            break

    obs = policy_observation(env, raw)
    pool = obs["pool_list"]
    print(f"{pathlib.Path(config_path).stem}: {placed} placed, stop = {reason}")
    print(f"items still in the visible pool: {len(pool)}\n")
    print(f'{"pool slot":>9s} {"dims":>18s} {"container":>10s} {"geometry":>9s} {"gated":>7s}')
    for slot, item in enumerate(pool):
        dims = f'{item["length"]:.2f}x{item["width"]:.2f}x{item["height"]:.2f}'
        for ci, container in enumerate(obs["container_list"]):
            geo, gated = scan(container, item)
            print(f"{slot:9d} {dims:>18s} {ci:10d} {geo:9d} {gated:7d}")
    env.close()


if __name__ == "__main__":
    main()
