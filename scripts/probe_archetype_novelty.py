"""Stage 0b: does rule-alpha's archetype ladder order actually matter?

`choose_for_item` generates candidates, vetoes them physically, then
walks `archetype_ladder` and takes the best candidate of the FIRST
archetype that has survivors.  That ladder is a hand-tuned artifact --
its comments read as a changelog of manual reordering ("growth before
ground was the original call", "it has to come before the foundation
archetypes") -- and it sits exactly where an AlphaGo-style policy head
would sit: a finite, semantically meaningful action space of
(item, archetype) pairs whose geometry the rules still materialise.

Before training anything to reorder that ladder, the precondition has
to hold:

    if the ladder had picked a DIFFERENT archetype, would the terminal
    outcome differ at all?

If every archetype swap comes back incomparable or identical, there is
no gradient for a policy head to follow, and the architecture is not
worth building however good it looks.  This probe answers that, and it
answers it in the same currency the Cup scores -- plus a scalar fill
comparison, because a four-head partial order that is mostly silent
does not by itself mean the outcomes were the same.

Same discipline as scripts/probe_perturbation_novelty.py: the actor
always executes its own action, so the state distribution is untouched.
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

import numpy as np  # noqa: E402

from rule_alpha import classify as cls  # noqa: E402
from rule_alpha import layer1  # noqa: E402
from scripts.build_counterfactual_graph import cumulative_metrics  # noqa: E402
from scripts.build_replay_dataset import (  # noqa: E402
    json_safe,
    load_agent_module,
    policy_observation,
    require_supported_python,
)
from scripts.counterfactual_graph import (  # noqa: E402
    BranchCandidate,
    canonical_action,
    stable_id,
)
from scripts.probe_perturbation_novelty import screen  # noqa: E402
from scripts.rule_alpha_proposals import _action_key, _ordered_pool  # noqa: E402
from scripts.run_self_play_packing import _safe, _status  # noqa: E402
from scripts.run_single_agent_packing import _fresh_env  # noqa: E402
from scripts.run_vector_mcts import (  # noqa: E402
    _dominates,
    _oriented,
    vector_search_root,
)

CONTRACT = "archetype_ladder_novelty_probe_v1"
EQUAL_EPS = 1e-9


def archetype_alternatives(
    solver, observation: dict[str, Any],
) -> dict[str, Any] | None:
    """One placement per ladder archetype for the item rule-alpha plays.

    Returns the chosen archetype's command plus, for every OTHER
    archetype the ladder had survivors for, the command that archetype
    would have played.  These are the arms of the discrete action the
    policy head would choose among.
    """
    config = solver.config
    solver.board = layer1.Board(
        observation.get("container_list") or [], config
    )
    solver._reapply_zone_scales()
    solver._resize_zones_for_what_is_left()
    for pool_index, profile in _ordered_pool(observation, config):
        captured: dict[str, Any] = {}

        def observer(payload, _sink=captured):
            _sink.update(payload)

        decision = layer1.choose_for_item(
            solver.board, profile, config, ranked_observer=observer,
        )
        if decision is None:
            continue
        board = solver.board
        container_idx = int(decision.placement.container_idx)
        model = board.model(container_idx)
        container = board.container(container_idx)

        def command_for(candidate):
            box = candidate.box
            if config.compaction_iterations > 0 and candidate.surface in (
                ("floor", "item") if config.compact_raised else ("floor",)
            ):
                box = layer1.compact_backwards(
                    box, board, candidate.container_idx, candidate.role,
                    config,
                )
            centre = layer1.action_center(
                box, board.model(candidate.container_idx),
                board.container(candidate.container_idx), config,
            )
            return canonical_action({
                "item_idx": int(pool_index),
                "container_idx": int(candidate.container_idx),
                "place_pos": np.asarray(centre, dtype=np.float32),
                "orientation": int(candidate.orientation.index),
            })

        chosen_archetype = captured.get("chosen_archetype")
        ranked = captured.get("ranked_by_archetype") or {}
        chosen = canonical_action({
            "item_idx": int(pool_index),
            "container_idx": container_idx,
            "place_pos": np.asarray(
                layer1.action_center(
                    decision.placement.box, model, container, config,
                ),
                dtype=np.float32,
            ),
            "orientation": int(decision.placement.orientation.index),
        })
        alternatives = []
        seen = {_action_key(chosen)}
        for name, candidates in ranked.items():
            if name == chosen_archetype or not candidates:
                continue
            command = command_for(candidates[0])
            key = _action_key(command)
            if key in seen:
                # The skipped archetype's best IS the chosen move: the
                # ladder order made no difference for this item, which is
                # itself the answer for this step and not a comparison.
                continue
            seen.add(key)
            alternatives.append({"archetype": name, "action": command})
        return {
            "pool_index": int(pool_index),
            "chosen_archetype": chosen_archetype,
            "chosen": chosen,
            "ladder": list(captured.get("ladder") or []),
            "archetypes_with_survivors": sorted(ranked),
            "alternatives": alternatives,
        }
    return None


def candidate_for(action, observation, *, archetype, rank):
    command = canonical_action(action)
    pool = observation.get("pool_list") or []
    pool_index = int(command["item_idx"])
    stable_item_index = (
        int(pool[pool_index].get("index", pool_index))
        if 0 <= pool_index < len(pool) else None
    )
    return BranchCandidate(
        candidate_id=stable_id("candidate", {
            "action": command,
            "kind": "archetype_arm",
            "stable_item_index": stable_item_index,
        }),
        command_action=command,
        selection={
            "provider": "rule_alpha_archetype_arm",
            "rank": int(rank),
            "pool_index": pool_index,
            "stable_item_index": stable_item_index,
            "candidate_kind": "archetype_arm",
            "archetype": archetype,
        },
    )


def compare(fork, base_id, arms):
    """Four-head verdicts AND the scalar fill delta for every arm.

    Both are reported because a partial order that answers
    "incomparable" is not evidence the outcomes matched -- it is the
    absence of an answer, and the fill column says whether there was
    anything to answer about.
    """
    rows = {
        str(r["root_candidate_id"]): r
        for r in fork.get("root_candidates") or []
    }
    base = rows.get(base_id)
    base_vector = (
        _oriented(base.get("terminal_vector") or {})
        if base and base.get("terminal_genuine") is True else None
    )
    base_fill = (
        float((base.get("terminal_vector") or {}).get("fill_gain"))
        if base_vector is not None else None
    )
    out = {"base_genuine": base_vector is not None, "base_fill": base_fill,
           "arms": []}
    if base_vector is None:
        return out
    for candidate_id, archetype in arms.items():
        row = rows.get(candidate_id)
        entry = {"archetype": archetype}
        if row is None or row.get("terminal_genuine") is not True:
            entry["verdict"] = "not_genuine"
            out["arms"].append(entry)
            continue
        vector = _oriented(row.get("terminal_vector") or {})
        if vector is None:
            entry["verdict"] = "not_genuine"
            out["arms"].append(entry)
            continue
        fill = float((row.get("terminal_vector") or {}).get("fill_gain"))
        entry["fill"] = fill
        entry["fill_delta"] = fill - base_fill
        if _dominates(vector, base_vector):
            entry["verdict"] = "beats_base"
        elif _dominates(base_vector, vector):
            entry["verdict"] = "loses_to_base"
        elif all(
            abs(x - y) <= EQUAL_EPS for x, y in zip(vector, base_vector)
        ):
            entry["verdict"] = "identical"
        else:
            entry["verdict"] = "incomparable"
        out["arms"].append(entry)
    return out


def run(agent_module, task_config, *, case_id, environment_seed,
        attempt_budget, top_k, rollout_top_k, rollout_max_steps, max_steps,
        fork_width, fork_budget, first_step):
    from rule_alpha.agent import RuleAlphaAgent

    env = _fresh_env(task_config)
    records: list[dict[str, Any]] = []
    executed: list[Any] = []
    forks_used = 0
    try:
        env.reset_settings()
        actor = RuleAlphaAgent()
        actor.get_init_states(env.get_init_states())
        env.reset_item_stream()
        observation, _info = env.reset(seed=environment_seed)
        termination = None
        for step in range(max_steps):
            observed = policy_observation(env, observation)
            plan = archetype_alternatives(actor, observed)
            if plan is None:
                termination = "rule_alpha_declined"
                break
            record: dict[str, Any] = {
                "step": int(step),
                "chosen_archetype": plan["chosen_archetype"],
                "archetypes_with_survivors": plan["archetypes_with_survivors"],
                "distinct_alternatives": len(plan["alternatives"]),
            }
            if (
                step >= first_step and forks_used < fork_budget
                and plan["alternatives"]
            ):
                record.update(probe_step(
                    agent_module, task_config, env, observed, plan,
                    case_id=case_id, environment_seed=environment_seed,
                    executed=executed, step=step,
                    attempt_budget=attempt_budget, top_k=top_k,
                    rollout_top_k=rollout_top_k,
                    rollout_max_steps=rollout_max_steps,
                    fork_width=fork_width,
                ))
                if record.get("forked"):
                    forks_used += 1
            action = plan["chosen"]
            observation, _reward, terminated, truncated, info = env.step(action)
            executed.append(action)
            records.append(record)
            if not _safe(_status(info)):
                termination = "selected_action_failure"
                break
            if terminated or truncated:
                termination = "stream_exhausted" if terminated else "max_steps"
                break
        else:
            termination = "max_steps"
        final_metrics = cumulative_metrics(env)
    finally:
        env.close()
    return {
        "contract": CONTRACT, "case_id": case_id,
        "environment_seed": environment_seed, "termination": termination,
        "steps": len(records), "forks_used": forks_used,
        "final_metrics": final_metrics, "records": records,
    }


def probe_step(agent_module, task_config, env, observed, plan, *, case_id,
               environment_seed, executed, step, attempt_budget, top_k,
               rollout_top_k, rollout_max_steps, fork_width):
    started = time.perf_counter()
    rows = [
        {"action": alt["action"], "archetype": alt["archetype"]}
        for alt in plan["alternatives"]
    ]
    feasible = screen(env, rows)
    picked = feasible[:fork_width]
    out: dict[str, Any] = {
        "alternatives_screened": len(rows),
        "alternatives_feasible": len(feasible),
        "forked_alternatives": len(picked),
        "screen_seconds": round(time.perf_counter() - started, 3),
        "forked": False,
    }
    if not picked:
        return out
    base = candidate_for(
        plan["chosen"], observed,
        archetype=plan["chosen_archetype"], rank=0,
    )
    arms = {}
    roots = [base]
    for index, row in enumerate(picked):
        candidate = candidate_for(
            row["action"], observed, archetype=row["archetype"],
            rank=index + 1,
        )
        arms[str(candidate.candidate_id)] = row["archetype"]
        roots.append(candidate)
    fork_started = time.perf_counter()
    fork = vector_search_root(
        agent_module, task_config, case_id=case_id,
        environment_seed=environment_seed, prefix_actions=list(executed),
        root_candidates=roots, attempt_budget=attempt_budget,
        deep_top_k=top_k, expansions=0, max_depth=1, step=step,
        leaf_eval="rollout", rollout_top_k=rollout_top_k,
        rollout_max_steps=rollout_max_steps, allocation="frontier",
        item_symmetry_cache_shadow=True, item_symmetry_terminal_cache=True,
    )
    out.update({
        "forked": True,
        "fork_seconds": round(time.perf_counter() - fork_started, 3),
        "fork_physical_step_equivalents": int(
            fork.get("physical_step_equivalents", 0)
        ),
        **compare(fork, str(base.candidate_id), arms),
    })
    return out


def summarize(episode):
    forked = [r for r in episode["records"] if r.get("forked")]
    arms = [a for r in forked for a in r.get("arms", [])]
    tally: dict[str, int] = {}
    for arm in arms:
        tally[arm["verdict"]] = tally.get(arm["verdict"], 0) + 1
    deltas = [
        arm["fill_delta"] for arm in arms if arm.get("fill_delta") is not None
    ]
    by_archetype: dict[str, dict[str, int]] = {}
    for arm in arms:
        bucket = by_archetype.setdefault(arm["archetype"], {})
        bucket[arm["verdict"]] = bucket.get(arm["verdict"], 0) + 1
    chosen = {}
    for record in episode["records"]:
        name = record.get("chosen_archetype")
        chosen[name] = chosen.get(name, 0) + 1
    return {
        "forked_steps": len(forked),
        "comparisons": len(arms),
        "verdict_tally": tally,
        "steps_with_a_winning_arm": sum(
            1 for r in forked
            if any(a["verdict"] == "beats_base" for a in r.get("arms", []))
        ),
        "verdict_by_archetype": by_archetype,
        "chosen_archetype_counts": chosen,
        "mean_distinct_alternatives": round(
            sum(
                int(r.get("distinct_alternatives", 0))
                for r in episode["records"]
            ) / max(len(episode["records"]), 1), 2,
        ),
        # A four-head "incomparable" is the absence of an answer. The fill
        # spread says whether the arms actually led anywhere different.
        "fill_delta": {
            "n": len(deltas),
            "min": round(min(deltas), 4) if deltas else None,
            "max": round(max(deltas), 4) if deltas else None,
            "mean_abs": (
                round(sum(abs(d) for d in deltas) / len(deltas), 4)
                if deltas else None
            ),
            "exactly_zero": sum(1 for d in deltas if abs(d) <= EQUAL_EPS),
            "arm_better": sum(1 for d in deltas if d > EQUAL_EPS),
            "arm_worse": sum(1 for d in deltas if d < -EQUAL_EPS),
        },
        "fork_physical_step_equivalents": sum(
            int(r.get("fork_physical_step_equivalents", 0)) for r in forked
        ),
    }


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
    parser.add_argument("--fork-width", type=int, default=4)
    parser.add_argument("--fork-budget", type=int, default=10)
    parser.add_argument("--first-step", type=int, default=4)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    require_supported_python()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    task_config = config[args.case] if args.case in config else config
    episode = run(
        load_agent_module(), task_config, case_id=args.case,
        environment_seed=args.environment_seed,
        attempt_budget=args.attempt_budget, top_k=args.top_k,
        rollout_top_k=args.rollout_top_k,
        rollout_max_steps=args.rollout_max_steps, max_steps=args.max_steps,
        fork_width=args.fork_width, fork_budget=args.fork_budget,
        first_step=args.first_step,
    )
    payload = {
        "schema_version": 1,
        "experiment": "stage 0b archetype ladder novelty probe",
        "question": (
            "if rule-alpha's ladder had picked a different archetype,"
            " would the terminal outcome differ?"
        ),
        "why": (
            "the ladder is where an AlphaGo-style policy head would sit;"
            " a policy cannot be trained over an action space whose arms"
            " all lead to the same terminal"
        ),
        "summary": summarize(episode),
        "episode": episode,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(json_safe(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
