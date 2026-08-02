"""
Long-horizon paired labels: run each sibling branch to the end of the episode.

Every short-horizon label this project has tried is now known to be unusable
for a board-value question:

* `placed-to-go` is confounded by step and occupied volume (Stage A, and the
  step correlations in Stage A');
* immediate settle survival is unrelated to option counts (Stage B, sign
  agreement exactly 0.500);
* 95.2% of Q-band sibling pairs tie on any short-horizon outcome at all.

So the label has to come from actually finishing the episode. For one state
`s` and siblings `a_1..a_K` drawn from the SAME candidate set, this forces
each `a_i` at its step and lets the shipped policy run free afterwards,
recording the final placed count and fill. The result is a genuinely paired
`Y(T_{a_i}(s))` that a board functional can later be scored against.

Three properties the design depends on, in order of how badly they would
break it:

1. **The prefix must be reproducible.** Branch labels are only comparable if
   every branch shares the same history. The control branch - forcing the
   action the unforced policy chose anyway - must reproduce the plain
   episode exactly. That is checked and reported per state rather than
   assumed; the search is deadline-limited, so reproducibility is an
   empirical property of the machine, not a guarantee.
2. **The agent is untouched.** Injection lives entirely in this driver's
   loop, so no shipped code path differs between the labelled run and a
   normal one.
3. **Siblings are selected offline** from the captured observation with a
   fixed attempt budget, using the same class-diverse rule as the rollout
   Top-K. Selecting them from a live deadline-limited search would make the
   sibling set itself depend on machine timing.

A forced action that the environment rejects is a legitimate outcome, not an
error: the branch simply ends there and its label is the placed count it
reached.
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

from scripts.measure_anchor_recall import (  # noqa: E402
    load_agent_module,
    policy_indexed_items,
    policy_observation,
)

SCHEMA_VERSION = 1


def reconstruct_siblings(agent, observation, *, budget, limit):
    """
    Class-diverse Top-K from a fixed attempt budget.

    Deterministic by construction: no deadline is involved, so the sibling
    set does not depend on how fast this machine happens to be.
    """
    containers = observation.get("container_list", [])
    has_priority = any(
        bool(c.get("is_prioritized", False)) for c in containers
    )
    risk_lambda = (
        agent.RELEASE_RISK_RERANK_LAMBDA
        if agent.RELEASE_RISK_LIVE_RERANK
        else None
    )
    collector = agent.VisiblePoolRolloutCollector()
    indexed = policy_indexed_items(agent, observation)
    stream = agent.iter_prioritized_candidates(
        observation, indexed, attempt_budget=int(budget)
    )
    for item_idx, item, container_idx, orientation, candidate in stream:
        container = containers[container_idx]
        score = agent.Ranker.score(candidate, item, container, has_priority)
        score, _p = agent.risk_adjusted_score(
            score, candidate, item, container, orientation, risk_lambda
        )
        decision = agent.PlacementDecision(
            action={
                "item_idx": int(item_idx),
                "container_idx": int(container_idx),
                "place_pos": np.asarray(
                    agent.simulator_action_center(candidate, container),
                    dtype=np.float32,
                ),
                "orientation": int(orientation),
            },
            candidate=candidate,
            score=float(score),
        )
        collector.observe(item_idx, item, container_idx, orientation, decision)
    return collector.snapshot(max(1, int(limit)))


def action_signature(action):
    return {
        "item_idx": int(action["item_idx"]),
        "container_idx": int(action["container_idx"]),
        "orientation": int(action["orientation"]),
        "place_pos": [round(float(v), 6) for v in action["place_pos"]],
    }


def run_episode(agent, task, *, force=None, capture_steps=()):
    """
    One episode driven directly, mirroring the reference driver's call order.

    `force` is {step: action}, applied instead of the policy's own. The policy
    is still called on a forced step, so its internal per-step state advances
    exactly as in an unforced run - only the emitted action is replaced.
    """
    from src.ground_handling.env import GroundHandlingEnv

    env = GroundHandlingEnv(config=task, verbose=False, render_mode=None)
    solver = agent.Agent("")
    captured: dict[int, Any] = {}
    chosen: dict[int, Any] = {}
    step = 0
    try:
        env.reset_settings()
        solver.get_init_states(env.get_init_states())
        env.reset_item_stream()
        raw_observation, _info = env.reset(seed=42)
        terminated = truncated = False
        while not terminated and not truncated:
            observation = policy_observation(env, raw_observation)
            if step in capture_steps:
                captured[step] = copy.deepcopy(observation)
            action = solver.policy(observation)
            chosen[step] = action_signature(action)
            if force and step in force:
                action = force[step]
            raw_observation, _reward, terminated, truncated, _info = env.step(
                action
            )
            step += 1
        evaluation = env.evaluate()
    finally:
        env.close()
    return {
        "steps": step,
        "captured": captured,
        "chosen": chosen,
        "evaluation": {
            key: value
            for key, value in evaluation.items()
            if key != "step_metrics"
        },
        "terminated": bool(terminated),
        "truncated": bool(truncated),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument(
        "--step", type=int, action="append", default=[],
        help="branch point; repeatable",
    )
    parser.add_argument("--siblings", type=int, default=3)
    parser.add_argument("--sibling-budget", type=int, default=4096)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    task_id = next(iter(config))
    task = config[task_id]
    agent = load_agent_module()
    steps = sorted(set(args.step or [6, 8, 10, 12]))

    print("pass 1: unforced reference episode", file=sys.stderr, flush=True)
    reference = run_episode(agent, task, capture_steps=set(steps))
    reference_eval = reference["evaluation"]

    results = []
    for step in steps:
        observation = reference["captured"].get(step)
        if observation is None:
            print(f"  step {step} unreached", file=sys.stderr)
            continue
        siblings = reconstruct_siblings(
            agent, observation,
            budget=args.sibling_budget, limit=args.siblings,
        )
        for index, decision in enumerate(siblings):
            forced = {
                "item_idx": int(decision.action["item_idx"]),
                "container_idx": int(decision.action["container_idx"]),
                "place_pos": np.asarray(
                    decision.action["place_pos"], dtype=np.float32
                ),
                "orientation": int(decision.action["orientation"]),
            }
            branch = run_episode(agent, task, force={step: forced})
            is_control = (
                action_signature(forced) == reference["chosen"].get(step)
            )
            prefix_matches = all(
                branch["chosen"].get(k) == reference["chosen"].get(k)
                for k in range(step)
            )
            results.append({
                "step": step,
                "sibling_index": index,
                "is_control": is_control,
                "prefix_reproduced": prefix_matches,
                "action": action_signature(forced),
                "q": float(decision.score),
                "kind": str(decision.candidate.name),
                "candidate_center": [
                    round(float(v), 6) for v in decision.candidate.center
                ],
                "candidate_size": [
                    round(float(v), 6) for v in decision.candidate.size
                ],
                "label": {
                    "steps": branch["steps"],
                    "evaluation": branch["evaluation"],
                },
            })
            print(
                f"  step {step} sibling {index} "
                f"{'(control)' if is_control else ''} "
                f"prefix_ok={prefix_matches} steps={branch['steps']}",
                file=sys.stderr, flush=True,
            )

    controls = [r for r in results if r["is_control"]]
    report = {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "config": args.config.as_posix(),
        "branch_steps": steps,
        "siblings_per_step": args.siblings,
        "sibling_budget": args.sibling_budget,
        "validity": {
            "prefix_reproduced_all": all(
                r["prefix_reproduced"] for r in results
            ),
            "control_branches": len(controls),
            "control_matches_reference": [
                r["label"]["evaluation"] == reference_eval for r in controls
            ],
            "note": (
                "Branch labels are only comparable if every branch shares the "
                "same history. A false here invalidates the labels for that "
                "state rather than merely adding noise."
            ),
        },
        "reference": {
            "steps": reference["steps"],
            "evaluation": reference_eval,
        },
        "branches": results,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "branch-labels.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["validity"], indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
