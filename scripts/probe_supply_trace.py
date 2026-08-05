"""
Is the binding constraint space, or supply?

The voxel audit says a third of the envelope is occupied when the agent
stops, which reads as a large loss -- but only if there were items left to
put in it. c000-k1 publishes 41 items in its stream and the agent places
about 22, so the question is whether the other 19 were ever offered.

This logs, per step, how many items are visible, so the end of the episode
can be attributed: an empty pool means the stream ran dry, a full pool means
the agent stopped with items in hand.
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


def main():
    path = sys.argv[1]
    cfg = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    key, case = list(cfg.items())[0]
    total = len(case["item_stream"]["item_list"])
    env = GroundHandlingEnv(
        config=json.loads(json.dumps(case)), verbose=False, render_mode=None
    )
    solver = ag.Agent("")
    env.reset_settings()
    solver.get_init_states(env.get_init_states())
    env.reset_item_stream()
    raw, _ = env.reset(seed=42)

    placed = 0
    trace = []
    reason = "?"
    while True:
        obs = policy_observation(env, raw)
        pool = len(obs["pool_list"])
        action = solver.policy(obs)
        source = solver.last_action_source
        trace.append((placed, pool, source))
        if source == "unsafe_protocol_fallback":
            reason = "agent had no safe placement"
            break
        raw, _r, term, trunc, info = env.step(action)
        status = (info or {}).get("status", {})
        if not all(
            bool(status.get(k)) for k in ("is_included", "is_valid", "is_placed_safe")
        ):
            reason = f"simulator rejected the chosen pose: {status}"
            break
        placed += 1
        if term or trunc:
            reason = "episode terminated"
            break
    env.close()

    print(f"{key}: stream publishes {total} items; agent placed {placed}")
    print(f"stop reason: {reason}\n")
    print(f'{"step":>5s} {"visible pool":>13s}  source')
    for step, pool, source in trace:
        print(f"{step:5d} {pool:13d}  {source}")


if __name__ == "__main__":
    main()
