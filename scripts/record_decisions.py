"""
Record every decision an unperturbed replay makes, for scoring later.

`measure_risk_percentile.py` scored alternatives BETWEEN the policy call and
the step, and that changed the run. The same case ends after 21 placements
with no topple under a plain replay, and after 16 with a topple under the
scanning one, reproducibly in both cases. The policy deadline is re-taken
from perf_counter inside every `policy()` call, so the scan does not steal
time -- but it does hammer the module-level caches the agent's own search
depends on (`_cached_container_z_interval`, an lru_cache of 65536 entries,
and `_PACKED_AABBS_CACHE`, which clears itself past 256 keys), and a search
bounded by wall-clock explores less when its cache is cold.

So measurement and behaviour have to be decoupled. This pass does nothing
but replay and write down what happened; scoring runs afterwards, in
`score_decisions.py`, against the recorded boards. The replay does no
candidate enumeration and touches no agent internals beyond the policy call
the agent would make anyway.

What is recorded per step is enough to rebuild the decision exactly: the
container (with its packed items at that moment), the item, the chosen pose,
the action source, and the status the simulator returned.
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


def record(config_path, output_path):
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
        source = solver.last_action_source
        if source == "unsafe_protocol_fallback":
            outcome = "no safe placement found"
            break
        container_index = int(action.get("container_idx", 0))
        entry = {
            "step": placed,
            "source": source,
            # Decisive for whether a risk comparison is even meaningful:
            # risk_adjusted_score returns the score UNCHANGED for anything
            # that is not a release_candidate, so a settled pick never paid
            # the P_rot penalty and must not be ranked against release poses
            # as though it had.
            "candidate_kind": getattr(solver, "last_candidate_kind", None),
            "container_index": container_index,
            "containers": json.loads(json.dumps(observation["container_list"])),
            "item": json.loads(
                json.dumps(observation["pool_list"][int(action["item_idx"])])
            ),
            "place_pos": [float(v) for v in action["place_pos"]],
            "orientation": int(action["orientation"]),
            "pool_size": len(observation["pool_list"]),
        }
        raw, _reward, terminated, truncated, info = env.step(action)
        status = (info or {}).get("status", {})
        entry["status"] = {k: bool(v) for k, v in status.items()}
        entry["safe"] = all(
            bool(status.get(flag))
            for flag in ("is_included", "is_valid", "is_placed_safe")
        )
        steps.append(entry)
        if not entry["safe"]:
            outcome = "simulator rejected the chosen pose"
            break
        placed += 1
        if terminated or truncated:
            outcome = "episode terminated"
            break
    env.close()

    payload = {
        "case": key,
        "placed": placed,
        "outcome": outcome,
        "steps": steps,
    }
    pathlib.Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(output_path).write_text(
        json.dumps(payload), encoding="utf-8"
    )
    print(f"{key}: {placed} placed, {outcome} -> {output_path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    record(args.config, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
