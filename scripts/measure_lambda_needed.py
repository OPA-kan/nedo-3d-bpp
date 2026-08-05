"""
What risk weight would have changed the fatal choice?

There is no P_rot gate in the shipped agent -- RELEASE_RISK_GATE_MODE
defaults to "off" -- so P_rot only enters as a penalty:

    Q_adjusted = Ranker.score - lambda_rot * P_rot - lambda_slide * P_slide

with lambda_rot 1.0 and lambda_slide 0.5 by default. That makes the question
arithmetic rather than another replay: on the board where the episode dies,
score every legal alternative the same way the agent does, and find the
smallest lambda_rot at which some safer pose overtakes the one that toppled.

Reading the answer:

  small lambda (order 1)   the risk term is nearly competitive and a modest
                           reweight flips the decision
  large lambda (order 10)  Ranker.score's spread dwarfs P_rot, and no
                           reweight fixes this without rewriting the score
  no such lambda           every safer pose is worse on Q by more than the
                           entire risk range -- the alternatives were not
                           actually available to a reranking policy

Ranker.score's terms are `12*volume + 2*support + depth - 0.12*|x| -
0.18*z*mass + routing`, so a support difference of 0.14 already outweighs a
P_rot difference of 0.28 at lambda 1. That is the hypothesis this checks; it
is not assumed.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "simulator"))

from scripts.measure_anchor_recall import (  # noqa: E402
    load_agent_module,
    policy_observation,
)
from src.ground_handling.env import GroundHandlingEnv  # noqa: E402


def enumerate_scored(agent_module, container, item, containers, stride):
    """Every legal release pose with the score and hazards the agent uses."""
    from scripts.fast_afterstate_env import AfterstateBoard

    has_priority_container = any(
        bool(c.get("is_prioritized")) for c in containers
    )
    board = AfterstateBoard(agent_module, container)
    rows = []
    x = board.x0 + stride / 2.0
    while x < -board.x0:
        y = board.y0 + stride / 2.0
        while y < -board.y0:
            for orientation in agent_module.unique_orientations(item):
                dx, dy, dz = agent_module.get_rotated_dimensions(
                    item["length"], item["width"], item["height"], orientation
                )
                bottom = board.drop_height(x, y, dx, dy)
                candidate = agent_module.AABB(
                    center=(x, y, bottom + dz / 2.0),
                    size=(dx, dy, dz),
                    name="release_candidate",
                )
                if (
                    agent_module.Geometry.release_rejection_reason(
                        candidate, container
                    )
                    is not None
                ):
                    continue
                q = float(
                    agent_module.Ranker.score(
                        candidate, item, container, has_priority_container
                    )
                )
                p_rot = float(
                    agent_module.release_rotation_risk_probability_mech(
                        float(candidate.center[0]),
                        float(candidate.center[1]),
                        float(candidate.center[2]),
                        tuple(float(v) for v in candidate.size),
                        container,
                    )
                )
                p_slide = float(
                    agent_module.release_large_slide_probability(
                        candidate, item, container, int(orientation)
                    )
                )
                rows.append(
                    {
                        "x": float(x),
                        "y": float(y),
                        "z": float(candidate.center[2]),
                        "orientation": int(orientation),
                        "q": q,
                        "p_rot": p_rot,
                        "p_slide": p_slide,
                        "support": float(
                            agent_module.Geometry.support_ratio(
                                candidate, container
                            )
                        ),
                    }
                )
            y += stride
        x += stride
    return rows


def lambda_to_flip(rows, chosen, slide_lambda):
    """
    Smallest lambda_rot at which a strictly safer pose outranks the chosen one.

    Both sides move with lambda, so this solves per alternative:

        q_a - L*p_a - s*ps_a  >  q_c - L*p_c - s*ps_c
        L * (p_c - p_a)       >  (q_c - s*ps_c) - (q_a - s*ps_a)

    which only has a solution when p_a < p_c -- a pose that is not safer
    cannot be promoted by raising the risk weight, at any weight.
    """
    base_c = chosen["q"] - slide_lambda * chosen["p_slide"]
    best = None
    for row in rows:
        gap = chosen["p_rot"] - row["p_rot"]
        if gap <= 1e-9:
            continue
        need = (base_c - (row["q"] - slide_lambda * row["p_slide"])) / gap
        need = max(need, 0.0)
        if best is None or need < best[0]:
            best = (need, row)
    return best


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--stride", type=float, default=0.05)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    agent_module = load_agent_module()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    key, case = next(iter(config.items()))
    env = GroundHandlingEnv(
        config=json.loads(json.dumps(case)), verbose=False, render_mode=None
    )
    solver = agent_module.Agent("")
    env.reset_settings()
    solver.get_init_states(env.get_init_states())
    env.reset_item_stream()
    raw, _ = env.reset(seed=42)

    placed = 0
    snapshot = None
    while True:
        observation = policy_observation(env, raw)
        action = solver.policy(observation)
        if solver.last_action_source == "unsafe_protocol_fallback":
            print(f"{key}: stopped without a topple after {placed} placements")
            env.close()
            return 0
        container_index = int(action.get("container_idx", 0))
        snapshot = {
            "container": json.loads(
                json.dumps(observation["container_list"][container_index])
            ),
            "containers": json.loads(json.dumps(observation["container_list"])),
            "item": json.loads(
                json.dumps(observation["pool_list"][int(action["item_idx"])])
            ),
            "action": {
                "place_pos": [float(v) for v in action["place_pos"]],
                "orientation": int(action["orientation"]),
            },
        }
        raw, _reward, terminated, truncated, info = env.step(action)
        status = (info or {}).get("status", {})
        if not all(
            bool(status.get(flag))
            for flag in ("is_included", "is_valid", "is_placed_safe")
        ):
            break
        placed += 1
        if terminated or truncated:
            print(f"{key}: ended cleanly after {placed} placements")
            env.close()
            return 0
    env.close()

    container = snapshot["container"]
    item = snapshot["item"]
    orientation = snapshot["action"]["orientation"]
    dims = agent_module.get_rotated_dimensions(
        item["length"], item["width"], item["height"], orientation
    )
    cx, cy, cz = snapshot["action"]["place_pos"]
    chosen_box = agent_module.AABB(
        center=(cx, cy, cz), size=tuple(float(v) for v in dims),
        name="release_candidate",
    )
    has_priority_container = any(
        bool(c.get("is_prioritized")) for c in snapshot["containers"]
    )
    chosen = {
        "q": float(
            agent_module.Ranker.score(
                chosen_box, item, container, has_priority_container
            )
        ),
        "p_rot": float(
            agent_module.release_rotation_risk_probability_mech(
                cx, cy, cz, tuple(float(v) for v in dims), container
            )
        ),
        "p_slide": float(
            agent_module.release_large_slide_probability(
                chosen_box, item, container, orientation
            )
        ),
        "support": float(
            agent_module.Geometry.support_ratio(chosen_box, container)
        ),
    }

    rows = enumerate_scored(
        agent_module, container, item, snapshot["containers"], args.stride
    )
    slide_lambda = float(agent_module.RELEASE_RISK_SLIDE_LAMBDA)
    live_lambda = float(agent_module.RELEASE_RISK_RERANK_LAMBDA)

    print(f"{key}: {placed} placed, then the chosen pose toppled")
    print(
        f'  chosen   Q {chosen["q"]:+.4f}  P_rot {chosen["p_rot"]:.4f}  '
        f'P_slide {chosen["p_slide"]:.4f}  support {chosen["support"]:.3f}'
    )
    print(f"  shipped  lambda_rot {live_lambda}, lambda_slide {slide_lambda}")
    print(f"  legal release alternatives enumerated: {len(rows)}")
    if not rows:
        print("  none -- the fatal pose is not in the release grid, so this")
        print("  case cannot be decomposed by this instrument.")
        return 0

    q = np.array([r["q"] for r in rows])
    p = np.array([r["p_rot"] for r in rows])
    adjusted = q - live_lambda * p - slide_lambda * np.array(
        [r["p_slide"] for r in rows]
    )
    chosen_adjusted = (
        chosen["q"] - live_lambda * chosen["p_rot"]
        - slide_lambda * chosen["p_slide"]
    )
    print(
        f"  Q spread over alternatives   : {q.min():+.3f} .. {q.max():+.3f} "
        f"(range {q.max() - q.min():.3f})"
    )
    print(
        f"  P_rot spread                 : {p.min():.4f} .. {p.max():.4f} "
        f"(range {p.max() - p.min():.4f})"
    )
    print(
        f"  alternatives outranking the chosen pose at the shipped lambda: "
        f"{int((adjusted > chosen_adjusted).sum())}"
    )

    best = lambda_to_flip(rows, chosen, slide_lambda)
    report = {
        "case": key,
        "placed": placed,
        "chosen": chosen,
        "lambda_rot_shipped": live_lambda,
        "lambda_slide_shipped": slide_lambda,
        "alternatives": len(rows),
        "q_range": [float(q.min()), float(q.max())],
        "p_rot_range": [float(p.min()), float(p.max())],
    }
    if best is None:
        print(
            "\n  no lambda_rot flips this: every safer pose is worse on Q, and"
            "\n  raising the risk weight cannot promote a pose that is not"
            "\n  safer. The repair is not a weight."
        )
        report["lambda_needed"] = None
    else:
        need, row = best
        print(
            f"\n  smallest lambda_rot that promotes a safer pose: {need:.3f}"
            f"  ({need / live_lambda:.1f}x the shipped weight)"
        )
        print(
            f'  that pose: P_rot {row["p_rot"]:.4f} (chosen {chosen["p_rot"]:.4f}), '
            f'Q {row["q"]:+.4f} (chosen {chosen["q"]:+.4f}), '
            f'support {row["support"]:.3f} (chosen {chosen["support"]:.3f})'
        )
        report["lambda_needed"] = float(need)
        report["promoted"] = row
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
