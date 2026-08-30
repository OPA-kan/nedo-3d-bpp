"""Execute a V-free single-agent terminal-rollout improvement policy.

At each live state, every bounded legacy root candidate is physically forced
and then continued by the frozen rank-0 policy to a genuine terminal.  The
incumbent rank-0 action is replaced only when it is absent from the complete
terminal Pareto frontier.  No component weights and no learned value are used.
Any censored terminal comparison fails safe to the incumbent.

The ``learned`` policy executes a distilled allocator ensemble directly:
the network picks among the physically safe root candidates from the
current snapshot alone (measured one-step safety screen, no terminal
rollouts), which makes its per-decision cost trivially inside the SLA.
It still uses no learned value function.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import platform
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "simulator") not in sys.path:
    sys.path.insert(0, str(ROOT / "simulator"))

from scripts.build_counterfactual_graph import (  # noqa: E402
    build_candidate_provider,
    cumulative_metrics,
)
from scripts.build_replay_dataset import (  # noqa: E402
    json_safe,
    load_agent_module,
    policy_observation,
    require_supported_python,
    state_snapshot,
)
from scripts.counterfactual_graph import (  # noqa: E402
    BranchCandidate,
    board_fingerprint,
    canonical_action,
    item_symmetry_board_fingerprint,
    stable_id,
)
from scripts.run_self_play_packing import (  # noqa: E402
    _candidate_action,
    _candidate_record,
    _candidate_selection,
    _compact_evaluation,
    _safe,
    _status,
)
from scripts.run_single_agent_packing import _fresh_env  # noqa: E402
from scripts.run_vector_mcts import vector_search_root  # noqa: E402
from scripts.single_agent_packing import GENUINE_TERMINATIONS  # noqa: E402

RULE_POLICIES = {"rule-grid", "rule-lowcog", "rule-edge"}
CURRENT_AGENT_POLICY = "current-agent"
RULE_ALPHA_POLICY = "rule-alpha"
EXACT_AGENT_POLICIES = {CURRENT_AGENT_POLICY, RULE_ALPHA_POLICY}
MINING_POLICIES = RULE_POLICIES | EXACT_AGENT_POLICIES
LEARNED_POLICIES = {"learned", "online"}
POLICIES = (
    {"legacy", "terminal-rollout"}
    | EXACT_AGENT_POLICIES
    | LEARNED_POLICIES | RULE_POLICIES
)
BEHAVIOR_CONTRACT = "single_agent_terminal_rollout_policy_v3_wall_clock"
TIMING_CONTRACT = "decision_wall_clock_v1"
RULE_GRID_PITCH = 0.25


def rule_heuristic_key(
    policy: str, action: dict[str, Any], one_step: dict[str, Any],
) -> tuple:
    """Deterministic ranking key for the rule-based diversity actors.

    Each actor re-ranks the SAME physically screened safe candidates —
    only the inductive bias differs.  Ties break toward fewer measured
    one-step violations, then more fill, for determinism and decency.
    """
    x = float(action["place_pos"][0])
    y = float(action["place_pos"][1])
    violations = (
        float(one_step.get("soft_violation_gain", 0.0))
        + float(one_step.get("priority_covered_gain", 0.0))
        + float(one_step.get("priority_misrouted_gain", 0.0))
    )
    fill = float(one_step.get("fill_gain", 0.0))
    if policy == "rule-grid":
        snap = (
            abs(x / RULE_GRID_PITCH - round(x / RULE_GRID_PITCH))
            + abs(y / RULE_GRID_PITCH - round(y / RULE_GRID_PITCH))
        )
        primary = (round(snap, 9), 0 if int(action.get("orientation", 0)) == 0 else 1)
    elif policy == "rule-lowcog":
        primary = (round(float(one_step.get("center_of_mass_z_delta", 0.0)), 9),)
    elif policy == "rule-edge":
        primary = (round(-(abs(x) + abs(y)), 9),)
    else:
        raise ValueError(f"unsupported rule policy: {policy}")
    return primary + (round(violations, 9), round(-fill, 9))


def _rank_key(candidate: Any) -> tuple[int, str]:
    return (
        int(_candidate_selection(candidate).get("rank", 10**9)),
        str(_candidate_record(candidate)["candidate_id"]),
    )


def pair_fork_winner(
    fork: dict[str, Any], pair_ids: set[str],
) -> str | None:
    """Strict winner of a two-candidate fork, or None if there is no verdict.

    A pair verdict requires BOTH sides to have reached a genuine terminal.
    ``build_resurrection_audit`` builds its comparison set from root
    candidates that were physically *safe*, so a side whose action turns
    out unsafe inside the fork leaves the set entirely rather than being
    censored: the survivor is then alone on a one-candidate terminal
    frontier with ``terminal_truth_complete`` still True.  Reading a winner
    off that would score a one-horse race as strict dominance, so the
    eligibility of both ids is checked explicitly here.
    """
    if not bool(fork.get("terminal_truth_complete")):
        return None
    eligible = {
        str(value)
        for value in fork.get("terminal_eligible_candidates") or []
    }
    if not pair_ids <= eligible:
        return None
    frontier = {
        str(value)
        for value in fork.get("terminal_pareto_candidates") or []
    }
    if len(frontier) != 1:
        return None
    winner = next(iter(frontier))
    return winner if winner in pair_ids else None


def exact_agent_action(solver: Any, observation: dict[str, Any]):
    """Return an exact actor command, preserving an honest decline."""
    action = solver.policy(observation)
    return None if action is None else canonical_action(action)


def add_exact_agent_candidate(
    candidates: list[Any], action: dict[str, Any],
    observation: dict[str, Any], *, policy: str,
) -> tuple[list[Any], str, bool]:
    """Union an exact stateful agent action into Cup candidate support.

    The actor owns its own generator, rescue and guard stack.  Its
    action may therefore be absent from the item-stratified Cup provider.
    Reuse an exact command match when present; otherwise add one auditable
    root candidate so PyBullet, the champion scorer and the paired terminal
    fork all see the same action.
    """
    if policy not in EXACT_AGENT_POLICIES:
        raise ValueError(f"unsupported exact agent policy: {policy}")
    command = canonical_action(action)
    for candidate in candidates:
        if canonical_action(_candidate_action(candidate)) == command:
            return list(candidates), str(
                _candidate_record(candidate)["candidate_id"]
            ), True
    pool = observation.get("pool_list") or []
    pool_index = int(command["item_idx"])
    stable_item_index = (
        int(pool[pool_index].get("index", pool_index))
        if 0 <= pool_index < len(pool) else None
    )
    candidate_id = stable_id("candidate", {
        "action": command,
        "kind": f"{policy.replace('-', '_')}_policy",
        "stable_item_index": stable_item_index,
    })
    current = BranchCandidate(
        candidate_id=candidate_id,
        command_action=command,
        selection={
            "provider": f"exact_{policy.replace('-', '_')}_policy",
            "rank": -1,
            "pool_index": pool_index,
            "stable_item_index": stable_item_index,
            "candidate_kind": f"{policy.replace('-', '_')}_policy",
            "candidate_support_hit": False,
        },
    )
    return list(candidates) + [current], candidate_id, False


def add_current_agent_candidate(
    candidates: list[Any], action: dict[str, Any],
    observation: dict[str, Any],
) -> tuple[list[Any], str, bool]:
    """Backward-compatible wrapper for the shipped current agent."""
    return add_exact_agent_candidate(
        candidates, action, observation, policy=CURRENT_AGENT_POLICY,
    )


def choose_root_candidate(
    candidates: list[Any], search_result: dict[str, Any], *, policy: str,
    learned_scorer: Any | None = None,
    forced_candidate_id: str | None = None,
) -> tuple[Any | None, dict[str, Any]]:
    """Choose conservatively from physically safe root candidates."""
    if policy not in POLICIES:
        raise ValueError(f"unsupported policy: {policy}")
    if policy in LEARNED_POLICIES and learned_scorer is None:
        raise ValueError("learned policy requires a candidate scorer")
    safe_ids = {
        str(row["root_candidate_id"])
        for row in search_result.get("root_candidates") or []
        if row.get("safe")
    }
    ranked = sorted(
        (
            candidate for candidate in candidates
            if str(_candidate_record(candidate)["candidate_id"]) in safe_ids
        ),
        key=_rank_key,
    )
    if policy in EXACT_AGENT_POLICIES:
        if forced_candidate_id is None:
            raise ValueError(f"{policy} policy requires its exact candidate id")
        exact = next(
            (
                candidate for candidate in candidates
                if str(_candidate_record(candidate)["candidate_id"])
                == str(forced_candidate_id)
            ),
            None,
        )
        if exact is None:
            raise ValueError(f"{policy} exact candidate is absent from union")
        incumbent_id = (
            str(_candidate_record(ranked[0])["candidate_id"])
            if ranked else None
        )
        exact_id = str(forced_candidate_id)
        return exact, {
            "policy": policy,
            "reason": f"{policy.replace('-', '_')}_policy",
            "switched": exact_id != incumbent_id,
            "incumbent_candidate_id": incumbent_id,
            "selected_candidate_id": exact_id,
            "selected_safe": exact_id in safe_ids,
            "candidate_support_hit": bool(
                _candidate_selection(exact).get(
                    "candidate_support_hit", True
                )
            ),
        }
    if not ranked:
        return None, {
            "policy": policy,
            "reason": "no_safe_candidate",
            "switched": False,
            "incumbent_candidate_id": None,
            "selected_candidate_id": None,
        }
    incumbent = ranked[0]
    incumbent_id = str(_candidate_record(incumbent)["candidate_id"])
    chosen = incumbent
    reason = "legacy_rank0"
    learned_scores: dict[str, float] | None = None
    if policy in RULE_POLICIES:
        rows = {
            str(row["root_candidate_id"]): row
            for row in search_result.get("root_candidates") or []
        }
        def _heuristic(candidate):
            record = _candidate_record(candidate)
            candidate_id = str(record["candidate_id"])
            row = rows.get(candidate_id) or {}
            return rule_heuristic_key(
                policy, record["command_action"],
                row.get("one_step_vector") or {},
            ) + (candidate_id,)
        chosen = min(ranked, key=_heuristic)
        reason = "rule_heuristic_argmin"
    elif policy in LEARNED_POLICIES:
        learned_scores = dict(learned_scorer(incumbent_id) or {})
        scored = [
            candidate for candidate in ranked
            if str(_candidate_record(candidate)["candidate_id"])
            in learned_scores
        ]
        if not scored:
            reason = "learned_scores_missing"
        else:
            chosen = max(
                scored,
                key=lambda candidate: learned_scores[
                    str(_candidate_record(candidate)["candidate_id"])
                ],
            )
            reason = (
                "learned_argmax_keep_incumbent"
                if str(_candidate_record(chosen)["candidate_id"])
                == incumbent_id
                else "learned_argmax_switch"
            )
    elif policy == "terminal-rollout":
        if not search_result.get("terminal_truth_complete"):
            reason = "terminal_truth_censored"
        else:
            frontier = {
                str(value)
                for value in search_result.get("terminal_pareto_candidates") or []
            }
            if incumbent_id in frontier:
                reason = "incumbent_terminal_pareto"
            else:
                alternatives = [
                    candidate for candidate in ranked
                    if str(_candidate_record(candidate)["candidate_id"])
                    in frontier
                ]
                if alternatives:
                    chosen = alternatives[0]
                    reason = "terminal_dominance_switch"
                else:
                    reason = "terminal_frontier_empty"
    selected_id = str(_candidate_record(chosen)["candidate_id"])
    audit = {
        "policy": policy,
        "reason": reason,
        "switched": selected_id != incumbent_id,
        "incumbent_candidate_id": incumbent_id,
        "selected_candidate_id": selected_id,
    }
    if learned_scores is not None:
        audit["learned_scores"] = {
            key: float(value) for key, value in learned_scores.items()
        }
    return chosen, audit


def _search_record(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "leaf_eval": result.get("leaf_eval"),
        "terminal_truth_complete": bool(
            result.get("terminal_truth_complete")
        ),
        "terminal_censored_candidates": result.get(
            "terminal_censored_candidates"
        ),
        "terminal_pareto_candidates": result.get(
            "terminal_pareto_candidates"
        ),
        "physical_steps": int(result.get("physical_steps", 0)),
        "physical_step_equivalents": int(
            result.get("physical_step_equivalents", 0)
        ),
        "terminal_rollout_physical_steps": int(
            result.get("terminal_rollout_physical_steps", 0)
        ),
        "terminal_rollout_physical_step_equivalents": int(
            result.get(
                "terminal_rollout_physical_step_equivalents", 0
            )
        ),
        "terminal_rollout_legal_filter_symmetry_reused": int(
            result.get(
                "terminal_rollout_legal_filter_symmetry_reused", 0
            )
        ),
        "item_symmetry_cache_shadow": result.get(
            "item_symmetry_cache_shadow"
        ),
        "item_symmetry_terminal_cache": result.get(
            "item_symmetry_terminal_cache"
        ),
        "timing": result.get("timing"),
        "root_candidates": [
            {
                key: row.get(key)
                for key in (
                    "root_candidate_id", "command_action",
                    "stable_item_index", "safe",
                    "one_step_vector", "terminal_genuine",
                    "terminal_termination", "terminal_continuation_steps",
                    "terminal_vector",
                    "terminal_checkpoint_vector",
                    "terminal_continuation_actions",
                    "terminal_physical_step_equivalents",
                    "terminal_legal_filter_symmetry_reused",
                    "terminal_symmetry_cache_hit",
                    "terminal_symmetry_cache_source",
                )
            }
            for row in result.get("root_candidates") or []
        ],
    }


def run_episode(
    agent_module, task_config: dict[str, Any], *, case_id: str,
    environment_seed: int, attempt_budget: int, top_k: int,
    rollout_top_k: int, rollout_max_steps: int, max_steps: int,
    policy: str, output_dir: pathlib.Path,
    model_dir: pathlib.Path | None = None,
    online_fork_budget: int = 4, online_band: float = 0.15,
    online_learning_rate: float = 0.05, online_update_steps: int = 2,
    online_trust_radius: float = 1.0,
    mine_model_dir: pathlib.Path | None = None,
    mine_fork_budget: int = 12,
) -> dict[str, Any]:
    if policy not in POLICIES:
        raise ValueError(f"unsupported policy: {policy}")
    mining_policy = None
    if mine_model_dir is not None:
        if policy not in MINING_POLICIES:
            raise ValueError(
                "counterfactual mining requires a diversity actor: the actor"
                " executes its own action and forks the champion's"
            )
        from scripts.learned_allocator_policy import LearnedAllocatorPolicy

        mining_policy = LearnedAllocatorPolicy(mine_model_dir)
    learned_policy = None
    if policy in LEARNED_POLICIES:
        if model_dir is None:
            raise ValueError("learned policy requires --model-dir")
        if policy == "online":
            from scripts.learned_allocator_policy import OnlineAdapterPolicy

            learned_policy = OnlineAdapterPolicy(
                model_dir,
                learning_rate=online_learning_rate,
                update_steps=online_update_steps,
                trust_radius=online_trust_radius,
            )
        else:
            from scripts.learned_allocator_policy import (
                LearnedAllocatorPolicy,
            )

            learned_policy = LearnedAllocatorPolicy(model_dir)
    provider = build_candidate_provider(
        agent_module, attempt_budget=attempt_budget,
        scan_all_visible_items=True,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    env = _fresh_env(task_config)
    try:
        env.reset_settings()
        exact_solver = None
        if policy == CURRENT_AGENT_POLICY:
            exact_solver = agent_module.Agent("")
        elif policy == RULE_ALPHA_POLICY:
            from rule_alpha.agent import RuleAlphaAgent

            exact_solver = RuleAlphaAgent()
        if exact_solver is not None:
            exact_solver.get_init_states(env.get_init_states())
        env.reset_item_stream()
        observation, _info = env.reset(seed=environment_seed)
        executed: list[Any] = []
        records = []
        termination = None
        online_forks_used = 0
        online_updates = 0
        mining_forks_used = 0
        mining_disagreements = 0
        mining_pairs = 0
        mining_fork_step_equivalents = 0
        for step in range(max_steps):
            decision_started = time.perf_counter()
            phase_started = time.perf_counter()
            observed = policy_observation(env, observation)
            snapshot = state_snapshot(
                env, observed, case_id=case_id, step=step,
            )
            fingerprint = board_fingerprint(snapshot)
            symmetry_fingerprint = item_symmetry_board_fingerprint(snapshot)
            root_id = stable_id("terminal-rollout-policy-root", {
                "board": fingerprint,
                "placements": len(executed),
            })
            snapshot_path = output_dir / f"step-{step:03d}-state.json"
            snapshot["behavior_contract"] = BEHAVIOR_CONTRACT
            snapshot["item_symmetry_fingerprint"] = symmetry_fingerprint
            snapshot_path.write_text(
                json.dumps(json_safe(snapshot), ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )
            state_capture_seconds = time.perf_counter() - phase_started
            actor_policy_seconds = 0.0
            current_candidate_id = None
            current_support_hit = None
            current_action = None
            if exact_solver is not None:
                phase_started = time.perf_counter()
                current_action = exact_agent_action(exact_solver, observed)
                actor_policy_seconds = time.perf_counter() - phase_started
                if current_action is None:
                    termination = f"{policy.replace('-', '_')}_declined"
                    break
            phase_started = time.perf_counter()
            candidates = list(provider(env, observation, int(top_k)))
            if current_action is not None:
                (
                    candidates,
                    current_candidate_id,
                    current_support_hit,
                ) = add_exact_agent_candidate(
                    candidates, current_action, observed, policy=policy,
                )
            provider_seconds = time.perf_counter() - phase_started
            if not candidates:
                termination = "no_retained_candidate"
                break
            leaf_eval = "rollout" if policy == "terminal-rollout" else "measured"
            phase_started = time.perf_counter()
            search = vector_search_root(
                agent_module, task_config, case_id=case_id,
                environment_seed=environment_seed,
                prefix_actions=list(executed),
                root_candidates=candidates,
                attempt_budget=attempt_budget,
                deep_top_k=top_k,
                expansions=0,
                max_depth=1,
                step=step,
                leaf_eval=leaf_eval,
                rollout_top_k=rollout_top_k,
                rollout_max_steps=rollout_max_steps,
                allocation="frontier",
                item_symmetry_cache_shadow=True,
                item_symmetry_terminal_cache=(
                    policy == "terminal-rollout"
                ),
            )
            search_seconds = time.perf_counter() - phase_started
            phase_started = time.perf_counter()
            learned_scorer = None
            if learned_policy is not None:
                search_rows = search.get("root_candidates") or []
                current_snapshot = snapshot

                def learned_scorer(incumbent_id, _snapshot=current_snapshot,
                                   _rows=search_rows):
                    return learned_policy.score_candidates(
                        _snapshot, _rows, incumbent_id=incumbent_id,
                    )
            chosen, selection = choose_root_candidate(
                candidates, search, policy=policy,
                learned_scorer=learned_scorer,
                forced_candidate_id=current_candidate_id,
            )
            if current_support_hit is not None:
                selection["candidate_support_hit"] = bool(
                    current_support_hit
                )
            selection_seconds = time.perf_counter() - phase_started
            if chosen is None:
                termination = "no_safe_retained_candidate"
                break
            online_event = None
            if policy == "online" and learned_policy is not None:
                # gated counterfactual A/B fork: only when the adapted
                # model is genuinely uncertain, only within budget, and
                # only strict terminal dominance teaches anything
                scores = selection.get("learned_scores") or {}
                incumbent_id = selection["incumbent_candidate_id"]
                alternates = [
                    (candidate_id, probability)
                    for candidate_id, probability in scores.items()
                    if candidate_id != incumbent_id
                ]
                if alternates and online_forks_used < online_fork_budget:
                    alternate_id, alternate_p = max(
                        alternates, key=lambda pair: (pair[1], pair[0])
                    )
                    if abs(alternate_p - 0.5) <= online_band:
                        fork_started = time.perf_counter()
                        pair_ids = {incumbent_id, alternate_id}
                        pair = [
                            candidate for candidate in candidates
                            if str(_candidate_record(candidate)["candidate_id"])
                            in pair_ids
                        ]
                        fork = vector_search_root(
                            agent_module, task_config, case_id=case_id,
                            environment_seed=environment_seed,
                            prefix_actions=list(executed),
                            root_candidates=pair,
                            attempt_budget=attempt_budget,
                            deep_top_k=top_k,
                            expansions=0,
                            max_depth=1,
                            step=step,
                            leaf_eval="rollout",
                            rollout_top_k=rollout_top_k,
                            rollout_max_steps=rollout_max_steps,
                            allocation="frontier",
                            item_symmetry_cache_shadow=True,
                            item_symmetry_terminal_cache=True,
                        )
                        online_forks_used += 1
                        complete = bool(fork.get("terminal_truth_complete"))
                        frontier = {
                            str(value) for value in
                            fork.get("terminal_pareto_candidates") or []
                        }
                        winner = pair_fork_winner(fork, pair_ids)
                        update = None
                        if winner is not None:
                            update = learned_policy.update_from_fork(
                                snapshot,
                                search.get("root_candidates") or [],
                                incumbent_id=incumbent_id,
                                alternate_id=alternate_id,
                                alternate_wins=(winner == alternate_id),
                            )
                            if update is not None:
                                online_updates += 1
                            # physics outranks the model at this state
                            if str(
                                _candidate_record(chosen)["candidate_id"]
                            ) != winner:
                                chosen = next(
                                    candidate for candidate in pair
                                    if str(_candidate_record(candidate)[
                                        "candidate_id"
                                    ]) == winner
                                )
                                selection["selected_candidate_id"] = winner
                                selection["switched"] = (
                                    winner != incumbent_id
                                )
                                selection["reason"] = "online_fork_winner"
                        online_event = {
                            "incumbent_candidate_id": incumbent_id,
                            "alternate_candidate_id": alternate_id,
                            "alternate_probability": float(alternate_p),
                            "terminal_truth_complete": complete,
                            "terminal_pareto_candidates": sorted(frontier),
                            "winner_candidate_id": winner,
                            "update": update,
                            "fork_physical_steps": int(
                                fork.get("physical_steps", 0)
                            ),
                            "fork_physical_step_equivalents": int(
                                fork.get("physical_step_equivalents", 0)
                            ),
                            "fork_terminal_rollout_physical_steps": int(
                                fork.get(
                                    "terminal_rollout_physical_steps", 0
                                )
                            ),
                            "fork_seconds": (
                                time.perf_counter() - fork_started
                            ),
                        }
            mining_event = None
            if mining_policy is not None:
                # counterfactual mining: fork the stud's action against
                # the frozen champion's choice at the SAME state. The
                # stud's own action is ALWAYS the one executed — mining
                # never bends its state distribution.
                actor_id = selection["selected_candidate_id"]
                incumbent_id = selection["incumbent_candidate_id"]
                scores = mining_policy.score_candidates(
                    snapshot, search.get("root_candidates") or [],
                    incumbent_id=incumbent_id,
                ) if incumbent_id else {}
                champion_id = (
                    max(scores, key=lambda cid: (scores[cid], cid))
                    if scores else None
                )
                if champion_id is not None and champion_id != actor_id:
                    mining_disagreements += 1
                    if mining_forks_used >= mine_fork_budget:
                        mining_event = {
                            "skipped": "fork_budget_exhausted",
                            "actor_policy": policy,
                            "actor_candidate_id": actor_id,
                            **(
                                {"rule_candidate_id": actor_id}
                                if policy in RULE_POLICIES else {}
                            ),
                            "champion_candidate_id": champion_id,
                        }
                    else:
                        fork_started = time.perf_counter()
                        pair_ids = {actor_id, champion_id}
                        pair = [
                            candidate for candidate in candidates
                            if str(_candidate_record(candidate)["candidate_id"])
                            in pair_ids
                        ]
                        fork = vector_search_root(
                            agent_module, task_config, case_id=case_id,
                            environment_seed=environment_seed,
                            prefix_actions=list(executed),
                            root_candidates=pair,
                            attempt_budget=attempt_budget,
                            deep_top_k=top_k,
                            expansions=0,
                            max_depth=1,
                            step=step,
                            leaf_eval="rollout",
                            rollout_top_k=rollout_top_k,
                            rollout_max_steps=rollout_max_steps,
                            allocation="frontier",
                            item_symmetry_cache_shadow=True,
                            item_symmetry_terminal_cache=True,
                        )
                        mining_forks_used += 1
                        mining_fork_step_equivalents += int(
                            fork.get("physical_step_equivalents", 0)
                        )
                        complete = bool(fork.get("terminal_truth_complete"))
                        frontier = {
                            str(value) for value in
                            fork.get("terminal_pareto_candidates") or []
                        }
                        winner = pair_fork_winner(fork, pair_ids)
                        if winner is not None:
                            mining_pairs += 1
                        mining_event = {
                            "actor_policy": policy,
                            "actor_candidate_id": actor_id,
                            **(
                                {"rule_candidate_id": actor_id}
                                if policy in RULE_POLICIES else {}
                            ),
                            "champion_candidate_id": champion_id,
                            "champion_probability": float(
                                scores[champion_id]
                            ),
                            "terminal_truth_complete": complete,
                            "terminal_pareto_candidates": sorted(frontier),
                            "winner_candidate_id": winner,
                            "pair_rows": [
                                {
                                    key: row.get(key)
                                    for key in (
                                        "root_candidate_id",
                                        "terminal_genuine",
                                        "terminal_termination",
                                        "terminal_vector",
                                    )
                                }
                                for row in fork.get("root_candidates") or []
                            ],
                            "fork_physical_steps": int(
                                fork.get("physical_steps", 0)
                            ),
                            "fork_physical_step_equivalents": int(
                                fork.get("physical_step_equivalents", 0)
                            ),
                            "fork_terminal_rollout_physical_steps": int(
                                fork.get(
                                    "terminal_rollout_physical_steps", 0
                                )
                            ),
                            "fork_seconds": (
                                time.perf_counter() - fork_started
                            ),
                        }
            before = cumulative_metrics(env)
            action = _candidate_action(chosen)
            phase_started = time.perf_counter()
            observation, _reward, terminated, truncated, info = env.step(action)
            live_action_seconds = time.perf_counter() - phase_started
            executed.append(action)
            status = _status(info)
            timing = {
                "contract": TIMING_CONTRACT,
                "state_capture_seconds": state_capture_seconds,
                "actor_policy_seconds": actor_policy_seconds,
                "provider_seconds": provider_seconds,
                "search_seconds": search_seconds,
                "selection_seconds": selection_seconds,
                "live_action_seconds": live_action_seconds,
                "decision_total_seconds": (
                    time.perf_counter() - decision_started
                ),
            }
            records.append({
                "step": int(step),
                "root_id": root_id,
                "snapshot_path": snapshot_path.name,
                "board_fingerprint": fingerprint,
                "item_symmetry_fingerprint": symmetry_fingerprint,
                "selection": selection,
                "action": json_safe(action),
                "metrics_before": before,
                "search": _search_record(search),
                "timing": timing,
                "status": status,
                **({"online": online_event} if online_event else {}),
                **({"mining": mining_event} if mining_event else {}),
            })
            if not _safe(status):
                termination = "selected_action_failure"
                break
            if truncated:
                termination = "simulator_truncated"
                break
            if terminated:
                termination = "stream_exhausted"
                break
        else:
            termination = "max_steps"
        final_metrics = cumulative_metrics(env)
        evaluation = None
        if termination in GENUINE_TERMINATIONS:
            evaluation = _compact_evaluation(env.evaluate())
            shake = (evaluation or {}).get("shake_response") or {}
            for source, target in (
                ("shake_max_shift", "post_shake_max_shift"),
                ("shake_peak_kinetic_energy", "post_shake_peak_kinetic_energy"),
                ("shake_items_toppled", "post_shake_items_toppled"),
            ):
                if source in shake:
                    final_metrics[target] = shake[source]
        return {
            "behavior_contract": BEHAVIOR_CONTRACT,
            "policy": policy,
            "steps": len(records),
            "termination": termination,
            "genuine_termination": termination in GENUINE_TERMINATIONS,
            "records": records,
            "final_metrics": final_metrics,
            "evaluation": evaluation,
            "executed_actions": [json_safe(action) for action in executed],
            "online_forks": (
                online_forks_used if policy == "online" else None
            ),
            "online_updates": (
                online_updates if policy == "online" else None
            ),
            "online_adapter_norms": (
                learned_policy.adapter_norms()
                if policy == "online" else None
            ),
            "mining_disagreements": (
                mining_disagreements if mining_policy is not None else None
            ),
            "mining_forks": (
                mining_forks_used if mining_policy is not None else None
            ),
            "mining_strict_pairs": (
                mining_pairs if mining_policy is not None else None
            ),
            "mining_fork_physical_step_equivalents": (
                mining_fork_step_equivalents
                if mining_policy is not None else None
            ),
            "current_agent_support_misses": (
                sum(
                    not bool(record["selection"].get(
                        "candidate_support_hit", True
                    ))
                    for record in records
                )
                if policy == CURRENT_AGENT_POLICY else None
            ),
            "rule_alpha_support_misses": (
                sum(
                    not bool(record["selection"].get(
                        "candidate_support_hit", True
                    ))
                    for record in records
                )
                if policy == RULE_ALPHA_POLICY else None
            ),
            "terminal_dominance_switches": sum(
                bool(record["selection"]["switched"])
                for record in records
            ),
            "terminal_truth_complete_roots": sum(
                bool(record["search"]["terminal_truth_complete"])
                for record in records
            ),
            "terminal_truth_censored_roots": sum(
                not bool(record["search"]["terminal_truth_complete"])
                for record in records
                if policy == "terminal-rollout"
            ),
            "search_physical_steps": sum(
                int(record["search"]["physical_steps"])
                for record in records
            ),
            "search_physical_step_equivalents": sum(
                int(record["search"]["physical_step_equivalents"])
                for record in records
            ),
            "terminal_rollout_physical_steps": sum(
                int(record["search"]["terminal_rollout_physical_steps"])
                for record in records
            ),
            "terminal_rollout_physical_step_equivalents": sum(
                int(record["search"][
                    "terminal_rollout_physical_step_equivalents"
                ])
                for record in records
            ),
            "terminal_rollout_legal_filter_symmetry_reused": sum(
                int(record["search"][
                    "terminal_rollout_legal_filter_symmetry_reused"
                ])
                for record in records
            ),
            "terminal_symmetry_cache_hits": sum(
                int((record["search"].get(
                    "item_symmetry_terminal_cache"
                ) or {}).get("hits", 0))
                for record in records
            ),
            "terminal_symmetry_cache_saved_physical_steps": sum(
                int((record["search"].get(
                    "item_symmetry_terminal_cache"
                ) or {}).get("saved_physical_steps", 0))
                for record in records
            ),
            "terminal_symmetry_cache_saved_physical_step_equivalents": sum(
                int((record["search"].get(
                    "item_symmetry_terminal_cache"
                ) or {}).get("saved_physical_step_equivalents", 0))
                for record in records
            ),
        }
    finally:
        env.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--environment-seed", type=int, default=42)
    parser.add_argument("--attempt-budget", type=int, default=128)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--rollout-top-k", type=int, default=3)
    parser.add_argument("--rollout-max-steps", type=int, default=40)
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--policy", choices=sorted(POLICIES), required=True)
    parser.add_argument(
        "--model-dir", type=pathlib.Path, default=None,
        help="frozen allocator ensemble directory (learned/online policies)",
    )
    parser.add_argument("--online-fork-budget", type=int, default=4)
    parser.add_argument("--online-band", type=float, default=0.15)
    parser.add_argument("--online-learning-rate", type=float, default=0.05)
    parser.add_argument("--online-update-steps", type=int, default=2)
    parser.add_argument("--online-trust-radius", type=float, default=1.0)
    parser.add_argument(
        "--mine-against-model", type=pathlib.Path, default=None,
        help="rule studs only: fork the stud's action against this"
             " frozen champion ensemble's choice at every disagreement"
             " (the stud still executes its own action)",
    )
    parser.add_argument("--mine-fork-budget", type=int, default=12)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if (args.policy in LEARNED_POLICIES) != (args.model_dir is not None):
        raise SystemExit(
            "--model-dir is required for --policy learned/online and"
            " forbidden otherwise"
        )
    if args.mine_against_model is not None and (
        args.policy not in MINING_POLICIES
    ):
        raise SystemExit(
            "--mine-against-model is valid only with current-agent/rule-*"
        )
    require_supported_python()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    task_config = config[args.case] if args.case in config else config
    episode = run_episode(
        load_agent_module(), task_config, case_id=args.case,
        environment_seed=args.environment_seed,
        attempt_budget=args.attempt_budget,
        top_k=args.top_k,
        rollout_top_k=args.rollout_top_k,
        rollout_max_steps=args.rollout_max_steps,
        max_steps=args.max_steps,
        policy=args.policy,
        output_dir=args.output_dir / "episode-000",
        model_dir=args.model_dir,
        online_fork_budget=args.online_fork_budget,
        online_band=args.online_band,
        online_learning_rate=args.online_learning_rate,
        online_update_steps=args.online_update_steps,
        online_trust_radius=args.online_trust_radius,
        mine_model_dir=args.mine_against_model,
        mine_fork_budget=args.mine_fork_budget,
    )
    policy_model = None
    if args.policy in LEARNED_POLICIES:
        policy_model = json.loads(
            (args.model_dir / "model.json").read_text(encoding="utf-8")
        )
        policy_model.pop("members", None)
        policy_model["model_dir"] = str(args.model_dir)
    manifest = {
        "schema_version": 1,
        "experiment": "single-agent terminal rollout policy",
        "behavior_contract": BEHAVIOR_CONTRACT,
        "case_id": args.case,
        "environment_seed": args.environment_seed,
        "policy": args.policy,
        "selection_contract": {
            "terminal-rollout": (
                "terminal_pareto_dominance_switch_else_legacy_rank0"
            ),
            "learned": "learned_allocator_argmax_over_safe_candidates",
            "online": (
                "adapted_argmax_with_gated_ab_terminal_fork;"
                " fork winner executed; adapter discarded at episode end"
            ),
            "current-agent": (
                "exact_stateful_agent_policy; action unioned into physical"
                " candidate support before champion comparison"
            ),
            "rule-alpha": (
                "exact_stateful_rule_alpha_policy; fixed stream; action"
                " unioned into physical candidate support before champion"
                " comparison"
            ),
            "legacy": "legacy_safe_rank0",
            "rule-grid": "rule_heuristic_argmin_over_safe_candidates",
            "rule-lowcog": "rule_heuristic_argmin_over_safe_candidates",
            "rule-edge": "rule_heuristic_argmin_over_safe_candidates",
        }[args.policy],
        "value_model": None,
        "policy_model": policy_model,
        "timing_contract": {
            "decision": TIMING_CONTRACT,
            "search": "vector_search_wall_clock_v1",
            "sla_seconds": 10.0,
            "clock": "time.perf_counter",
            "platform": platform.platform(),
            "python": platform.python_version(),
            "sample_scope": (
                "decisions_that_execute_a_live_action; terminal provider-empty "
                "checks without an action are not episode records"
            ),
        },
        "candidate_contract": {
            "provider": "placement_core_item_stratified_fixed_attempts",
            "attempt_budget": args.attempt_budget,
            "top_k": args.top_k,
        },
        "rollout_contract": {
            "policy": "frozen_rank0_exact_physical_filter",
            "top_k": args.rollout_top_k,
            "max_continuation_steps": args.rollout_max_steps,
            "censor_on_cap": True,
            "identical_item_terminal_cache": True,
        } if args.policy == "terminal-rollout" else {
            "policy": "gated_pairwise_terminal_fork",
            "fork_budget": args.online_fork_budget,
            "uncertainty_band": args.online_band,
            "top_k": args.rollout_top_k,
            "max_continuation_steps": args.rollout_max_steps,
            "censor_on_cap": True,
            "identical_item_terminal_cache": True,
            "online_update": {
                "objective": "pairwise_logistic_on_head_adapter",
                "teacher": "strict_terminal_dominance_only",
                "learning_rate": args.online_learning_rate,
                "steps": args.online_update_steps,
                "trust_radius": args.online_trust_radius,
                "adapter_lifetime": "single_episode",
            },
        } if args.policy == "online" else None,
        "mining_contract": {
            "champion_model_dir": str(args.mine_against_model),
            "fork_budget": args.mine_fork_budget,
            "actor_policy": args.policy,
            "rule": (
                "actor_executes_own_action;"
                " fork_champion_argmax_on_disagreement;"
                " strict_terminal_dominance_pairs_only"
            ),
        } if args.mine_against_model is not None else None,
        "episodes": [episode],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / "manifest.json"
    output.write_text(
        json.dumps(json_safe(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"policy={args.policy} steps={episode['steps']} "
        f"termination={episode['termination']} "
        f"switches={episode['terminal_dominance_switches']} "
        f"rollout_physical_steps={episode['terminal_rollout_physical_steps']}"
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
