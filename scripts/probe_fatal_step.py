"""
The step that ends the episode: was a safer option available?

One unsafe placement terminates the run -- the simulator sets terminated
directly on `is_placed_safe == False` -- and c000-k1 dies that way with
about half its stream unplaced and 34 gated-safe slots still open. So the
whole episode reduces to not making that one drop.

This replays to the fatal step and, at that board, scores every legal pose
for the pending item with the shipped risk model, then reports where the
chosen pose sat in that distribution. Two outcomes mean different repairs:

  chosen P_rot is high relative to the alternatives
      the ranker is overriding the risk signal -- an L2/L4 weighting
      problem, fixable without touching the risk model.

  chosen P_rot is low and typical
      the risk model is miscalibrated exactly where it matters, and no
      amount of reranking on its output helps.

The replay runs alone: the agent is deadline-driven, and the same case
reaches step 22 unloaded and step 16 under load, so a contended run would
score a different board.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(".").resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "simulator"))

from scripts.measure_anchor_recall import load_agent_module, policy_observation  # noqa: E402
from src.ground_handling.env import GroundHandlingEnv  # noqa: E402

ag = load_agent_module()
STRIDE = 0.05


def score_alternatives(container, item):
    from scripts.fast_afterstate_env import AfterstateBoard

    board = AfterstateBoard(ag, container)
    rows = []
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
                try:
                    _adjusted, probability = ag.risk_adjusted_score(
                        0.0, candidate, item, container, int(orientation), 1.0
                    )
                except Exception:
                    probability = None
                rows.append(
                    {
                        "x": float(x),
                        "y": float(y),
                        "z": float(bottom + dz / 2.0),
                        "orientation": int(orientation),
                        "p_rot": None if probability is None else float(probability),
                    }
                )
            y += STRIDE
        x += STRIDE
    return rows


def main():
    path = sys.argv[1]
    cfg = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    key, case = list(cfg.items())[0]
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
        obs = policy_observation(env, raw)
        action = solver.policy(obs)
        source = solver.last_action_source
        if source == "unsafe_protocol_fallback":
            print(f"{key}: stopped at step {placed} with no safe placement (not a topple)")
            env.close()
            return
        # snapshot BEFORE stepping: this may be the fatal one
        container_index = int(action.get("container_idx", 0))
        container = json.loads(json.dumps(obs["container_list"][container_index]))
        item = json.loads(json.dumps(obs["pool_list"][int(action["item_idx"])]))
        chosen = {
            "place_pos": [float(v) for v in action["place_pos"]],
            "orientation": int(action["orientation"]),
            "source": source,
        }

        raw, _r, term, trunc, info = env.step(action)
        status = (info or {}).get("status", {})
        if not all(
            bool(status.get(k)) for k in ("is_included", "is_valid", "is_placed_safe")
        ):
            break
        placed += 1
        if term or trunc:
            print(f"{key}: episode ended cleanly after {placed} placements")
            env.close()
            return
    env.close()

    print(f"{key}: {placed} placed, then the drop below was rejected")
    print(f"  status  {status}")
    print(f"  source  {chosen['source']}")
    print(
        f'  item    {item["length"]:.2f} x {item["width"]:.2f} x {item["height"]:.2f}'
        f'  soft={bool(item.get("is_soft"))} prio={bool(item.get("is_prioritized"))}'
    )
    print(
        f'  pose    {[round(v, 3) for v in chosen["place_pos"]]} '
        f'orn {chosen["orientation"]}'
    )

    dims = ag.get_rotated_dimensions(
        item["length"], item["width"], item["height"], chosen["orientation"]
    )
    x, y, z = chosen["place_pos"]
    chosen_p = float(
        ag.release_rotation_risk_probability_mech(
            x, y, z, tuple(float(v) for v in dims), container
        )
    )

    rows = score_alternatives(container, item)
    values = np.array(
        [r["p_rot"] for r in rows if r["p_rot"] is not None], dtype=np.float64
    )
    print(f"\n  P_rot of the chosen pose : {chosen_p:.4f}")
    if values.size == 0:
        print("  no scored alternatives")
        return
    better = int((values < chosen_p).sum())
    print(f"  legal alternatives scored: {values.size}")
    print(
        f"  P_rot distribution       : min {values.min():.4f}  "
        f"p25 {np.quantile(values, .25):.4f}  median {np.median(values):.4f}  "
        f"p75 {np.quantile(values, .75):.4f}  max {values.max():.4f}"
    )
    print(
        f"  alternatives strictly safer than the chosen pose: {better} "
        f"({100 * better / values.size:.1f}%)"
    )
    print(
        f"  gate threshold is 0.5; poses under it: "
        f"{int((values < 0.5).sum())}/{values.size}"
    )


if __name__ == "__main__":
    main()
