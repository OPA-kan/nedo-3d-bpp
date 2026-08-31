"""Collect (board, remaining-volume) pairs for a bootstrap value function.

The teacher's rollout stops when the generator runs dry -- 96.3% of Cup
009's terminal rollouts ended `no_retained_candidate` and none exhausted
the item stream -- and then books the tail as zero. That zero is the
defect, not the early stop: an n-step estimate is fine at any n, so long
as the bootstrap term is honest.

    V(s_t) ~= sum_{k<n} gamma^k r_{t+k} + gamma^n * V_theta(s_{t+n})

So no terminal is needed to start. Running ONE episode labels every
prefix state by telescoping, with r_t = the volume of the item placed at
t and gamma = 1:

    V(s_t) = sum of the volume placed from t onward

which is exactly the return that target uses. An episode that ends
`rule_alpha_declined` or `selected_action_failure` labels its states
just as well as one that packs the stream out.

**What this target is.** It is V^behaviour, not V*: the volume THIS
policy goes on to place, not the volume the board could hold. Regressing
on it approximates the behaviour policy and is bounded by it. That is
accepted deliberately for a first model, because the incumbent value at
those states is the constant 0 and V^behaviour beats 0 by two to four
times. Escaping the bound needs a max over policies or over candidate
continuations, which this collector is shaped to allow later: it records
the behaviour policy per row, so several can be pooled and a per-state
max taken over whichever continuations were run from the same prefix.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "simulator") not in sys.path:
    sys.path.insert(0, str(ROOT / "simulator"))

from scripts.build_counterfactual_graph import build_candidate_provider  # noqa: E402
from scripts.build_replay_dataset import (  # noqa: E402
    json_safe,
    load_agent_module,
    policy_observation,
    require_supported_python,
)
from scripts.counterfactual_graph import canonical_action  # noqa: E402
from scripts.probe_value_rankability import board_features, item_volume  # noqa: E402
from scripts.run_self_play_packing import (  # noqa: E402
    _candidate_action,
    _safe,
    _status,
)
from scripts.run_single_agent_packing import _fresh_env  # noqa: E402

CONTRACT = "value_target_collection_v1"
POLICIES = ("rule-alpha", "rank0", "rank0-union")


def _actor(policy: str, env, *, agent_module, attempt_budget, union_limit):
    """Return (choose, label) for one behaviour policy."""
    if policy == "rule-alpha":
        from rule_alpha.agent import RuleAlphaAgent

        solver = RuleAlphaAgent()
        solver.get_init_states(env.get_init_states())

        def choose(observed, _observation):
            action = solver.policy(observed)
            return None if action is None else canonical_action(action)

        return choose

    provider = build_candidate_provider(
        agent_module, attempt_budget=attempt_budget,
        scan_all_visible_items=True,
    )
    if policy == "rank0-union":
        from scripts.rule_alpha_proposals import (
            RuleAlphaProposer,
            union_provider,
        )

        proposer = RuleAlphaProposer(max_proposals=int(union_limit))
        proposer.get_init_states(env.get_init_states())
        provider = union_provider(
            provider, proposer, observation_fn=policy_observation,
        )

    def choose(_observed, observation):
        candidates = list(provider(env, observation, 3))
        return _candidate_action(candidates[0]) if candidates else None

    return choose


def trajectory(task, *, policy, agent_module, seed, max_steps,
               attempt_budget, union_limit) -> dict[str, Any]:
    started = time.perf_counter()
    env = _fresh_env(task)
    states: list[dict[str, Any]] = []
    try:
        env.reset_settings()
        choose = _actor(
            policy, env, agent_module=agent_module,
            attempt_budget=attempt_budget, union_limit=union_limit,
        )
        env.reset_item_stream()
        observation, _info = env.reset(seed=seed)
        termination = None
        for step in range(max_steps):
            observed = policy_observation(env, observation)
            action = choose(observed, observation)
            if action is None:
                termination = (
                    "rule_alpha_declined" if policy == "rule-alpha"
                    else "no_retained_candidate"
                )
                break
            states.append({
                "step": step,
                "features": board_features(observed),
                "reward": item_volume(observed, action),
            })
            observation, _r, terminated, truncated, info = env.step(action)
            if not _safe(_status(info)):
                termination = "selected_action_failure"
                break
            if terminated or truncated:
                termination = (
                    "stream_exhausted" if terminated else "simulator_truncated"
                )
                break
        else:
            termination = "max_steps"
    finally:
        env.close()
    # The telescoped return. Every state gets a label, whatever ended the
    # episode -- which is the point: no terminal is required.
    tail = 0.0
    for row in reversed(states):
        tail += float(row["reward"])
        row["remaining_volume"] = tail
    return {
        "policy": policy,
        "termination": termination,
        "states": states,
        "seconds": round(time.perf_counter() - started, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=pathlib.Path, required=True)
    parser.add_argument("--cases", nargs="+", required=True)
    parser.add_argument(
        "--policies", nargs="+", default=["rule-alpha", "rank0-union"],
        choices=list(POLICIES),
        help="behaviour policies to roll out; each labels its own states",
    )
    parser.add_argument("--environment-seed", type=int, default=42)
    parser.add_argument("--attempt-budget", type=int, default=128)
    parser.add_argument("--union-limit", type=int, default=4)
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    require_supported_python()
    agent_module = load_agent_module()

    rows: list[dict[str, Any]] = []
    trajectories: list[dict[str, Any]] = []
    for case in args.cases:
        config = json.loads(
            (args.config_dir / f"{case}.json").read_text(encoding="utf-8")
        )
        task = next(
            v for v in config.values()
            if isinstance(v, dict) and "containers" in v
        )
        for policy in args.policies:
            result = trajectory(
                task, policy=policy, agent_module=agent_module,
                seed=args.environment_seed, max_steps=args.max_steps,
                attempt_budget=args.attempt_budget,
                union_limit=args.union_limit,
            )
            for state in result["states"]:
                rows.append({
                    "case": case,
                    "policy": policy,
                    "step": state["step"],
                    "reward": state["reward"],
                    "remaining_volume": state["remaining_volume"],
                    "features": state["features"],
                })
            trajectories.append({
                "case": case, "policy": policy,
                "termination": result["termination"],
                "states": len(result["states"]),
                "total_volume": (
                    result["states"][0]["remaining_volume"]
                    if result["states"] else 0.0
                ),
                "seconds": result["seconds"],
            })
            print(
                f"{case:44s} {policy:12s} {len(result['states']):3d} states"
                f"  V(s0)={trajectories[-1]['total_volume']:.4f}"
                f"  {result['termination']} ({result['seconds']}s)",
                flush=True,
            )

    terminations: dict[str, int] = {}
    for row in trajectories:
        terminations[row["termination"]] = (
            terminations.get(row["termination"], 0) + 1
        )
    payload = {
        "schema_version": 1, "contract": CONTRACT,
        "target": (
            "V(s_t) = sum of placed volume from t onward, gamma=1;"
            " V^behaviour, not V*"
        ),
        "why_no_terminal_needed": (
            "an n-step estimate is valid at any n provided the bootstrap"
            " term is honest; the incumbent pins it to 0, which is 2-4x"
            " wrong. Telescoping labels every prefix state whatever ended"
            " the episode"
        ),
        "environment_seed": args.environment_seed,
        "policies": list(args.policies),
        "trajectories": trajectories,
        "termination_counts": terminations,
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(json_safe(payload), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"\n{len(rows)} labelled states from {len(trajectories)}"
        f" trajectories -> {args.output}", flush=True,
    )
    print("terminations:", json.dumps(terminations), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
