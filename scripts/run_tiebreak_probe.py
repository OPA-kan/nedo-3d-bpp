#!/usr/bin/env python3
"""Causality probe: does the near-tie q tiebreak hurt on pool-1 episodes?

On c000-k1 the branch-label pairs showed the higher-q sibling reaching the
worse ending in 14-15 of 17-18 decided pairs. That is an observational
inversion; this probe tests it causally at episode level without touching
the shipped agent. Three arms per config:

- ``live_base``: the unmodified policy end to end.
- ``offline_top_q``: at every step, deterministically reconstruct the
  spatially distinct top candidates from a fixed attempt budget and force
  the highest-q member. This is the control that isolates the
  deterministic-reconstruction effect from the tiebreak direction.
- ``offline_min_q``: identical reconstruction, force the lowest-q member.

If the inversion is causal, offline_min_q beats offline_top_q on final
placed/fill; live_base calibrates both against the shipped behaviour. The
policy is still called on every step so its internal state advances
exactly as in an unforced run.
"""

from __future__ import annotations

import argparse
import copy
import json
import pathlib
import sys
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
SIMULATOR = ROOT / "simulator"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SIMULATOR) not in sys.path:
    sys.path.insert(0, str(SIMULATOR))

from scripts.build_branch_labels import (  # noqa: E402
    _top_candidate_decisions,
    reconstruct_siblings,
)
from scripts.measure_anchor_recall import (  # noqa: E402
    load_agent_module,
    policy_observation,
)
from scripts.measurement_budget import record_from_env  # noqa: E402

ARMS = ("live_base", "offline_top_q", "offline_min_q")


def _forced_action(decision) -> dict[str, Any]:
    return {
        "item_idx": int(decision.action["item_idx"]),
        "container_idx": int(decision.action["container_idx"]),
        "place_pos": np.asarray(decision.action["place_pos"], dtype=np.float32),
        "orientation": int(decision.action["orientation"]),
    }


def run_arm(
    agent, task: dict[str, Any], arm: str, *,
    budget: int, siblings: int,
) -> dict[str, Any]:
    from src.ground_handling.env import GroundHandlingEnv

    record_from_env(1)
    env = GroundHandlingEnv(config=task, verbose=False, render_mode=None)
    solver = agent.Agent("")
    step = 0
    overridden = 0
    override_agreements = 0
    try:
        env.reset_settings()
        solver.get_init_states(env.get_init_states())
        env.reset_item_stream()
        raw_observation, _info = env.reset(seed=42)
        terminated = truncated = False
        while not terminated and not truncated:
            observation = policy_observation(env, raw_observation)
            action = solver.policy(observation)
            if arm != "live_base":
                selected, _components = reconstruct_siblings(
                    agent, observation,
                    budget=budget, limit=siblings, mode="top_candidates",
                )
                if selected:
                    ordered = sorted(selected, key=lambda d: -float(d.score))
                    choice = ordered[0] if arm == "offline_top_q" else ordered[-1]
                    forced = _forced_action(choice)
                    if (
                        int(action.get("item_idx", -1)) == forced["item_idx"]
                        and int(action.get("container_idx", -1))
                        == forced["container_idx"]
                        and int(action.get("orientation", -1))
                        == forced["orientation"]
                        and np.allclose(
                            np.asarray(action.get("place_pos", ()), dtype=float),
                            forced["place_pos"], atol=1e-6,
                        )
                    ):
                        override_agreements += 1
                    action = forced
                    overridden += 1
            raw_observation, _reward, terminated, truncated, _info = env.step(
                action
            )
            step += 1
        evaluation = env.evaluate()
    finally:
        env.close()
    return {
        "arm": arm,
        "steps": step,
        "overridden_steps": overridden,
        "override_agreements_with_policy": override_agreements,
        "evaluation": {
            key: value for key, value in evaluation.items()
            if key != "step_metrics"
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--arm", choices=ARMS, action="append")
    parser.add_argument("--sibling-budget", type=int, default=4096)
    parser.add_argument("--siblings", type=int, default=3)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    task_id = next(iter(config))
    task = config[task_id]
    agent = load_agent_module()
    results = []
    for arm in (args.arm or list(ARMS)):
        result = run_arm(
            agent, copy.deepcopy(task), arm,
            budget=args.sibling_budget, siblings=args.siblings,
        )
        print(
            f"{task_id} {arm}: steps={result['steps']} "
            f"placed={result['evaluation'].get('num_placed_items')} "
            f"fill={result['evaluation'].get('fill_score')}",
            file=sys.stderr, flush=True,
        )
        results.append(result)
    output = {
        "schema_version": 1,
        "task_id": task_id,
        "config": str(args.config),
        "sibling_budget": args.sibling_budget,
        "siblings": args.siblings,
        "arms": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
