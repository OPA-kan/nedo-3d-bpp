"""Generate replayable roots under deliberately diverse behavior policies.

The shipped agent is not modified.  Every trajectory still calls its policy
at every step; this offline driver may replace the emitted action with a
fixed-budget, settled Top-K action.  This tests whether the narrow H3 state
distribution is caused by the incumbent behavior policy rather than by the
problem itself.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import pathlib
import random
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
SIMULATOR = ROOT / "simulator"
for path in (ROOT, SIMULATOR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.build_counterfactual_graph import (  # noqa: E402
    build_candidate_provider,
    cumulative_metrics,
    transition_outcomes,
)
from scripts.build_replay_dataset import (  # noqa: E402
    json_safe,
    load_agent_module,
    policy_observation,
    require_supported_python,
    state_snapshot,
)
from scripts.counterfactual_graph import (  # noqa: E402
    board_fingerprint,
    capture_replay_contract,
    canonical_action,
    stable_id,
    state_tensor_from_snapshot,
)
from scripts.evaluate_budgeted_dag_search import (  # noqa: E402
    edge_passes_hard_constraints,
)


BEHAVIOR_MODES = ("baseline", "safe-temperature", "force-rank1", "force-rank2")


def _action_key(action: dict[str, Any]) -> str:
    normalized = canonical_action(action)
    normalized["place_pos"] = [round(value, 6) for value in normalized["place_pos"]]
    return json.dumps(normalized, sort_keys=True)


def behavior_frontier(
    baseline_action: dict[str, Any], decisions: list[Any], *, top_k: int,
    is_safe=None,
) -> list[dict[str, Any]]:
    """Put the live action first, then unique fixed-budget settled actions."""
    frontier = [{
        "action": canonical_action(baseline_action),
        "score": None,
        "source": "live_rank0",
    }]
    seen = {_action_key(baseline_action)}
    def score(row: Any) -> float:
        if hasattr(row, "selection"):
            return float(row.selection["score"])
        return float(row.score)

    for decision in sorted(decisions, key=lambda row: -score(row)):
        candidate_kind = (
            decision.selection.get("candidate_kind")
            if hasattr(decision, "selection")
            else getattr(decision.candidate, "name", None)
        )
        if candidate_kind == "release_candidate":
            continue
        action = canonical_action(
            decision.command_action if hasattr(decision, "command_action") else decision.action
        )
        key = _action_key(action)
        if key in seen:
            continue
        if is_safe is not None and not is_safe(action):
            continue
        seen.add(key)
        frontier.append({
            "action": action,
            "score": score(decision),
            "source": "fixed_budget_settled",
        })
        if len(frontier) >= int(top_k):
            break
    return frontier


def candidate_passes_hard_constraints(
    task_config: dict[str, Any], action_prefix: list[dict[str, Any]],
    action: dict[str, Any], *, environment_seed: int,
) -> bool:
    """Physically replay and reject transport, settle, soft, or priority harm."""
    from src.ground_handling.env import GroundHandlingEnv

    def fresh_env():
        return GroundHandlingEnv(
            config=copy.deepcopy(task_config), verbose=False, render_mode=None
        )

    def replay_prefix(env) -> bool:
        env.reset_settings()
        env.reset_item_stream()
        _observation, _info = env.reset(seed=int(environment_seed))
        for prefix_action in action_prefix:
            _observation, _reward, terminated, truncated, _info = env.step(
                canonical_action(prefix_action)
            )
            if terminated or truncated:
                return False
        return True

    parent_env = fresh_env()
    try:
        if not replay_prefix(parent_env):
            return False
        # Post-shake deltas must be relative to the parent's own measured
        # post-shake condition.  Measuring only the child would incorrectly
        # attribute a pre-existing covered soft item to this candidate.
        parent = cumulative_metrics(parent_env, include_post_shake=True)
    finally:
        parent_env.close()

    env = fresh_env()
    try:
        if not replay_prefix(env):
            return False
        _observation, _reward, _terminated, _truncated, info = env.step(
            canonical_action(action)
        )
        outcomes = transition_outcomes(
            env, info, parent, include_post_shake=True
        )
        return edge_passes_hard_constraints(
            {"immediate_outcomes": outcomes}, hard_attributes=True
        )
    finally:
        env.close()


def choose_behavior_action(
    frontier: list[dict[str, Any]], *, mode: str, step: int,
    divergence_step: int, temperature: float, rng: random.Random,
) -> tuple[dict[str, Any], int]:
    if mode == "baseline":
        rank = 0
    elif mode.startswith("force-rank"):
        requested = int(mode.removeprefix("force-rank"))
        rank = requested if step == divergence_step and requested < len(frontier) else 0
    elif mode == "safe-temperature":
        if temperature <= 0:
            raise ValueError("temperature must be positive")
        weights = [math.exp(-rank / temperature) for rank in range(len(frontier))]
        rank = rng.choices(range(len(frontier)), weights=weights, k=1)[0]
    else:
        raise ValueError(f"unknown behavior mode: {mode}")
    return copy.deepcopy(frontier[rank]["action"]), rank


def model_visible_signature(snapshot: dict[str, Any]) -> str:
    return stable_id("model-state", state_tensor_from_snapshot(snapshot))


def run_trajectory(
    agent_module, task_config: dict[str, Any], *, case_id: str, mode: str,
    target_steps: set[int], divergence_step: int, environment_seed: int,
    behavior_seed: int, attempt_budget: int, top_k: int,
    temperature: float, output_dir: pathlib.Path,
) -> dict[str, Any]:
    from src.ground_handling.env import GroundHandlingEnv

    env = GroundHandlingEnv(config=copy.deepcopy(task_config), verbose=False, render_mode=None)
    solver = agent_module.Agent("")
    rng = random.Random(int(behavior_seed))
    action_prefix: list[dict[str, Any]] = []
    captures = []
    selections = []
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        env.reset_settings()
        solver.get_init_states(env.get_init_states())
        env.reset_item_stream()
        raw_observation, _info = env.reset(seed=int(environment_seed))
        terminated = truncated = False
        step = 0
        final_step = max(target_steps)
        while not terminated and not truncated and step <= final_step:
            observation = policy_observation(env, raw_observation)
            baseline_action = canonical_action(solver.policy(observation))
            needs_frontier = mode == "safe-temperature" or (
                mode.startswith("force-rank") and step == divergence_step
            )
            decisions = []
            if needs_frontier:
                decisions = build_candidate_provider(
                    agent_module, attempt_budget=int(attempt_budget)
                )(env, raw_observation, max(int(top_k) * 4, int(top_k)))
            frontier = behavior_frontier(
                baseline_action,
                decisions,
                top_k=top_k,
                is_safe=(
                    lambda candidate: candidate_passes_hard_constraints(
                        task_config, action_prefix, candidate,
                        environment_seed=environment_seed,
                    )
                ) if needs_frontier else None,
            )
            action, selected_rank = choose_behavior_action(
                frontier, mode=mode, step=step,
                divergence_step=int(divergence_step),
                temperature=float(temperature), rng=rng,
            )
            if step in target_steps:
                snapshot = state_snapshot(env, observation, case_id=case_id, step=step)
                snapshot_id = f"behavior:{case_id}:{mode}:step-{step:03d}"
                snapshot["snapshot_id"] = snapshot_id
                snapshot["replay_contract"] = capture_replay_contract(
                    env, action_prefix, seed=int(environment_seed)
                )
                snapshot["board_fingerprint"] = board_fingerprint(snapshot)
                snapshot["model_visible_state_signature"] = model_visible_signature(snapshot)
                snapshot["behavior_policy"] = {
                    "mode": mode,
                    "behavior_seed": int(behavior_seed),
                    "environment_seed": int(environment_seed),
                    "divergence_step": int(divergence_step),
                    "attempt_budget": int(attempt_budget),
                    "top_k": int(top_k),
                    "temperature": float(temperature),
                    "alternative_action_constraint": (
                        "physical_status_and_postshake_attribute_nonregression"
                    ),
                }
                path = output_dir / f"step-{step:03d}-state.json"
                path.write_text(json.dumps(json_safe(snapshot), ensure_ascii=False, indent=2), encoding="utf-8")
                captures.append({
                    "step": step, "snapshot_path": path.name,
                    "board_fingerprint": snapshot["board_fingerprint"],
                    "model_visible_state_signature": snapshot["model_visible_state_signature"],
                })
            raw_observation, _reward, terminated, truncated, info = env.step(action)
            selections.append({
                "step": step,
                "selected_rank": selected_rank,
                "frontier_size": len(frontier),
                "action_changed": _action_key(action) != _action_key(baseline_action),
                "accepted": bool(isinstance(info, dict) and info.get("is_included")),
            })
            action_prefix.append(action)
            step += 1
    finally:
        env.close()
    return {
        "mode": mode,
        "captures": captures,
        "selections": selections,
        "changed_action_count": sum(row["action_changed"] for row in selections),
        "reached_steps": [row["step"] for row in captures],
        "missing_steps": sorted(target_steps - {row["step"] for row in captures}),
        "terminated": bool(terminated),
        "truncated": bool(truncated),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--steps", type=int, nargs="+", required=True)
    parser.add_argument("--divergence-step", type=int, default=6)
    parser.add_argument("--environment-seed", type=int, default=42)
    parser.add_argument("--behavior-seed", type=int, default=1729)
    parser.add_argument("--attempt-budget", type=int, default=512)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--behavior", action="append", choices=BEHAVIOR_MODES)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    require_supported_python()
    if min(args.steps) <= args.divergence_step:
        raise SystemExit("all capture steps must be after --divergence-step")
    if args.top_k < 3:
        raise SystemExit("--top-k must be at least 3 for rank-2 divergence")
    os.environ["NEDO_CANDIDATE_AUDIT"] = "1"
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.case not in config:
        raise SystemExit(f"unknown case: {args.case}")
    modes = args.behavior or list(BEHAVIOR_MODES)
    agent_module = load_agent_module()
    trajectories = []
    for offset, mode in enumerate(modes):
        trajectories.append(run_trajectory(
            agent_module, config[args.case], case_id=args.case, mode=mode,
            target_steps=set(args.steps), divergence_step=args.divergence_step,
            environment_seed=args.environment_seed,
            behavior_seed=args.behavior_seed + offset,
            attempt_budget=args.attempt_budget, top_k=args.top_k,
            temperature=args.temperature, output_dir=args.output_dir / mode,
        ))
    payload = {
        "schema_version": 1,
        "experiment": "behavior-policy state-distribution diversity",
        "case_id": args.case,
        "environment_seed": args.environment_seed,
        "target_steps": sorted(args.steps),
        "trajectories": trajectories,
    }
    manifest = args.output_dir / "manifest.json"
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(manifest)
    return 1 if any(row["missing_steps"] for row in trajectories) else 0


if __name__ == "__main__":
    raise SystemExit(main())
