"""
At every step, where does the chosen pose sit in the risk distribution?

The fatal step of c000-k1 turned out to be a pose the risk gate passed
(P_rot 0.278 against a 0.5 threshold) while 96.3% of the 827 legal
alternatives scored strictly safer. That is one step in one case, and the
interesting question is whether it is the agent's habit or its one mistake.

So this scores the chosen pose against every legal alternative at EVERY
step, not just the last one, and reports the percentile. Reading:

  percentile near 0    the agent takes the safest pose available
  percentile near 1    it takes the riskiest
  gate passes >> 0     the 0.5 threshold is not what is selecting, because
                       almost everything clears it

Alternatives are scored with `risk_adjusted_score`, which under the default
`mech` model calls the same `release_rotation_risk_probability_mech` used
for the chosen pose -- the two numbers are the same quantity, which was
checked rather than assumed.

The agent is deadline-driven and NOT reproducible across runs: the same case
reached 22 placements in one replay and 16 in another with nothing else
running. So the step COUNT here is not a measurement. The percentile at each
step is, because it compares a choice against its own alternatives on the
board that choice was made from.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
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

GATE = 0.5


def alternatives(agent_module, container, item, stride):
    from scripts.fast_afterstate_env import AfterstateBoard

    board = AfterstateBoard(agent_module, container)
    out = []
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
                _adjusted, probability = agent_module.risk_adjusted_score(
                    0.0, candidate, item, container, int(orientation), 1.0
                )
                if probability is not None:
                    out.append(float(probability))
            y += stride
        x += stride
    return np.asarray(out, dtype=np.float64)


def run(config_path, stride):
    agent_module = load_agent_module()
    config = json.loads(pathlib.Path(config_path).read_text(encoding="utf-8"))
    key, case = next(iter(config.items()))
    env = GroundHandlingEnv(
        config=json.loads(json.dumps(case)), verbose=False, render_mode=None
    )
    solver = agent_module.Agent("")
    env.reset_settings()
    solver.get_init_states(env.get_init_states())
    env.reset_item_stream()
    raw, _ = env.reset(seed=42)

    steps = []
    placed = 0
    outcome = "terminated"
    while True:
        observation = policy_observation(env, raw)
        action = solver.policy(observation)
        if solver.last_action_source == "unsafe_protocol_fallback":
            outcome = "no safe placement"
            break
        container_index = int(action.get("container_idx", 0))
        container = observation["container_list"][container_index]
        item = observation["pool_list"][int(action["item_idx"])]
        dims = agent_module.get_rotated_dimensions(
            item["length"],
            item["width"],
            item["height"],
            int(action["orientation"]),
        )
        x, y, z = (float(v) for v in action["place_pos"])
        chosen = float(
            agent_module.release_rotation_risk_probability_mech(
                x, y, z, tuple(float(v) for v in dims), container
            )
        )
        others = alternatives(agent_module, container, item, stride)

        raw, _reward, terminated, truncated, info = env.step(action)
        status = (info or {}).get("status", {})
        safe = all(
            bool(status.get(flag))
            for flag in ("is_included", "is_valid", "is_placed_safe")
        )
        steps.append(
            {
                "step": placed,
                "chosen_p_rot": chosen,
                "alternatives": int(others.size),
                "safer_alternatives": int((others < chosen).sum()),
                "percentile": (
                    float((others < chosen).mean()) if others.size else None
                ),
                "median_alternative": (
                    float(np.median(others)) if others.size else None
                ),
                "gate_passes": int((others < GATE).sum()),
                "soft": bool(item.get("is_soft")),
                "prioritized": bool(item.get("is_prioritized")),
                "fatal": not safe,
            }
        )
        if not safe:
            outcome = "simulator rejected the chosen pose"
            break
        placed += 1
        if terminated or truncated:
            break
    env.close()
    return {"case": key, "placed": placed, "outcome": outcome, "steps": steps}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--stride", type=float, default=0.05)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    report = run(args.config, args.stride)
    steps = report["steps"]
    print(f'{report["case"]}: {report["placed"]} placed, {report["outcome"]}\n')
    print(
        f'{"step":>4s} {"P_rot":>7s} {"median":>7s} {"alts":>5s} '
        f'{"safer":>6s} {"pct":>6s} {"gate<0.5":>9s}  flags'
    )
    for entry in steps:
        pct = "-" if entry["percentile"] is None else f'{entry["percentile"]:.3f}'
        median = (
            "-"
            if entry["median_alternative"] is None
            else f'{entry["median_alternative"]:.4f}'
        )
        flags = []
        if entry["soft"]:
            flags.append("soft")
        if entry["prioritized"]:
            flags.append("prio")
        if entry["fatal"]:
            flags.append("FATAL")
        print(
            f'{entry["step"]:4d} {entry["chosen_p_rot"]:7.4f} {median:>7s} '
            f'{entry["alternatives"]:5d} {entry["safer_alternatives"]:6d} '
            f'{pct:>6s} {entry["gate_passes"]:9d}  {" ".join(flags)}'
        )

    percentiles = [e["percentile"] for e in steps if e["percentile"] is not None]
    if percentiles:
        print(
            f"\npercentile of the chosen pose: median "
            f"{statistics.median(percentiles):.3f}, "
            f"mean {statistics.fmean(percentiles):.3f}, "
            f"over {len(percentiles)} steps"
        )
        print(
            "0 would mean the agent always takes the safest available pose; "
            "1 the riskiest."
        )
    gates = [
        e["gate_passes"] / e["alternatives"]
        for e in steps
        if e["alternatives"]
    ]
    if gates:
        print(
            f"fraction of alternatives clearing the 0.5 gate: median "
            f"{statistics.median(gates):.3f} -- the gate binds only where "
            f"this is well under 1."
        )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
