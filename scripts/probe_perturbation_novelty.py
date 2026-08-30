"""Stage 0: can a mechanical perturbation of a rule's move beat that move?

The candidate union closed the train/inference mismatch, but both sides
of every fork still come from a hand-coded generator
(`reports/candidate-support/rule-alpha-union-20260830.md`).  A learned
proposer trained on that corpus would compress the existing generators,
not escape them -- imitation moved one level up.  Escaping needs a source
of novelty that is not the rules, and the terminal-rollout teacher can
*evaluate* anything but *invent* nothing.

So the cheapest thing that can kill the whole idea is asked first:

    perturb the rule's own executed action, physically screen the
    perturbations, and fork the survivors against it.
    Does a perturbation ever strictly dominate the move it came from?

If the rules are locally optimal the answer is never, there is nothing
for a proposer to learn in this neighbourhood, and no model is trained.
If some perturbations win, they are the first actions in this project
that no generator proposed, and their statistics say what a proposer
would have to predict.

This probe trains nothing and changes no shipped behaviour.  The actor
always executes its own action -- perturbations are scored and thrown
away, so the state distribution is untouched.
"""

from __future__ import annotations

import argparse
import itertools
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

from scripts import env_checkpoint  # noqa: E402
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
    canonical_action,
    stable_id,
)
from scripts.run_self_play_packing import _candidate_action, _safe, _status  # noqa: E402
from scripts.run_single_agent_packing import _fresh_env  # noqa: E402
# The dominance rule is imported, never restated: a probe that decided
# "wins" by its own copy of the four-head test would be measuring
# something the Cup does not score.
from scripts.run_vector_mcts import (  # noqa: E402
    _dominates,
    _oriented,
    vector_search_root,
)

CONTRACT = "perturbation_novelty_probe_v2"
# Below this the four heads are treated as the same terminal rather
# than as an unadjudicated trade-off.
EQUAL_EPS = 1e-9
ORIENTATION_COUNT = 6


def translation_offsets(magnitudes: list[float]) -> list[tuple[str, tuple]]:
    """Axis-aligned nudges in the container-local plane, both signs."""
    out = []
    for magnitude in magnitudes:
        for axis, name in ((0, "x"), (1, "y")):
            for sign in (+1.0, -1.0):
                delta = [0.0, 0.0, 0.0]
                delta[axis] = sign * float(magnitude)
                out.append((
                    f"translate_{name}{'+' if sign > 0 else '-'}"
                    f"_{magnitude:.3f}",
                    tuple(delta),
                ))
    return out


def perturbations(
    action: dict[str, Any], *, magnitudes: list[float],
    orientation_swaps: int,
) -> list[dict[str, Any]]:
    """Mechanical neighbours of one command. No rule knowledge is used."""
    base = canonical_action(action)
    out = []
    for label, delta in translation_offsets(magnitudes):
        position = [
            float(base["place_pos"][index]) + delta[index]
            for index in range(3)
        ]
        out.append({
            "kind": "translate",
            "label": label,
            "magnitude": float(max(abs(value) for value in delta)),
            "action": canonical_action({**base, "place_pos": position}),
        })
    current = int(base["orientation"])
    swaps = [
        index for index in range(ORIENTATION_COUNT) if index != current
    ][:max(0, int(orientation_swaps))]
    for index in swaps:
        out.append({
            "kind": "orientation",
            "label": f"orientation_{current}->{index}",
            "magnitude": 0.0,
            "action": canonical_action({**base, "orientation": index}),
        })
    return out


def perturbation_candidate(
    action: dict[str, Any], observation: dict[str, Any], *,
    label: str, rank: int,
) -> BranchCandidate:
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
            "kind": "perturbation",
            "stable_item_index": stable_item_index,
        }),
        command_action=command,
        selection={
            "provider": "mechanical_perturbation",
            "rank": int(rank),
            "pool_index": pool_index,
            "stable_item_index": stable_item_index,
            "candidate_kind": "perturbation",
            "perturbation_label": label,
        },
    )


def screen(env, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One-step physical feasibility, by checkpoint and restore.

    scripts/env_checkpoint.py exists for exactly this: force an action,
    read the status the simulator reports, and put the world back. A
    perturbation that cannot be placed safely is not evidence about the
    rule's quality, so it must not consume a terminal rollout.
    """
    checkpoint = env_checkpoint.capture(env)
    try:
        for row in candidates:
            _obs, _reward, _term, _trunc, info = env.step(row["action"])
            status = _status(info)
            row["one_step_status"] = status
            row["feasible"] = bool(_safe(status))
            env_checkpoint.restore(checkpoint, env)
    finally:
        env_checkpoint.release(checkpoint, env)
    return [row for row in candidates if row["feasible"]]


def verdicts(fork: dict[str, Any], base_id: str) -> dict[str, Any]:
    """Pairwise four-head verdicts of every root against the base move.

    One fork over {base} u {perturbations} is run rather than a fork per
    pair: the terminal vectors are the expensive part and they are the
    same either way, so N-1 verdicts come out for the price of one.
    """
    rows = {
        str(row["root_candidate_id"]): row
        for row in fork.get("root_candidates") or []
    }
    base = rows.get(base_id)
    base_vector = (
        _oriented(base.get("terminal_vector") or {})
        if base and base.get("terminal_genuine") is True else None
    )
    out: dict[str, Any] = {
        "base_genuine": base_vector is not None,
        "base_terminal_vector": (
            base.get("terminal_vector") if base else None
        ),
        "per_candidate": {},
    }
    if base_vector is None:
        return out
    for candidate_id, row in rows.items():
        if candidate_id == base_id:
            continue
        # The raw vectors are kept, not just the verdict. "Incomparable"
        # covers two completely different worlds -- a terminal the
        # perturbation reached identically, and a genuine trade-off the
        # four-head rule declines to adjudicate -- and a probe that
        # records only the label cannot tell them apart afterwards.
        entry: dict[str, Any] = {
            "terminal_vector": row.get("terminal_vector"),
            "terminal_genuine": row.get("terminal_genuine"),
            "terminal_termination": row.get("terminal_termination"),
        }
        if row.get("terminal_genuine") is not True:
            entry["verdict"] = "not_genuine"
            out["per_candidate"][candidate_id] = entry
            continue
        vector = _oriented(row.get("terminal_vector") or {})
        if vector is None:
            entry["verdict"] = "not_genuine"
            out["per_candidate"][candidate_id] = entry
            continue
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
        out["per_candidate"][candidate_id] = entry
    return out


def run(
    agent_module, task_config: dict[str, Any], *, case_id: str,
    environment_seed: int, attempt_budget: int, top_k: int,
    rollout_top_k: int, rollout_max_steps: int, max_steps: int,
    magnitudes: list[float], orientation_swaps: int,
    fork_width: int, fork_budget: int, first_step: int,
) -> dict[str, Any]:
    from rule_alpha.agent import RuleAlphaAgent

    provider = build_candidate_provider(
        agent_module, attempt_budget=attempt_budget,
        scan_all_visible_items=True,
    )
    env = _fresh_env(task_config)
    records: list[dict[str, Any]] = []
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
            action = actor.policy(observed)
            if action is None:
                termination = "rule_alpha_declined"
                break
            action = canonical_action(action)
            record: dict[str, Any] = {"step": int(step)}
            if step >= first_step and forks_used < fork_budget:
                record.update(
                    probe_step(
                        agent_module, task_config, env, observed, action,
                        case_id=case_id,
                        environment_seed=environment_seed,
                        executed=[r["action"] for r in records],
                        step=step, attempt_budget=attempt_budget,
                        top_k=top_k, rollout_top_k=rollout_top_k,
                        rollout_max_steps=rollout_max_steps,
                        magnitudes=magnitudes,
                        orientation_swaps=orientation_swaps,
                        fork_width=fork_width,
                    )
                )
                if record.get("forked"):
                    forks_used += 1
            record["action"] = action
            observation, _reward, terminated, truncated, info = env.step(action)
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
        "contract": CONTRACT,
        "case_id": case_id,
        "environment_seed": environment_seed,
        "termination": termination,
        "steps": len(records),
        "forks_used": forks_used,
        "final_metrics": final_metrics,
        "records": records,
    }


def pick_spanning(rows: list[dict[str, Any]], width: int) -> list[dict[str, Any]]:
    """Keep a spread across magnitudes rather than the first few found.

    Taking the head of the list would fill the fork with the smallest
    nudges on one axis, and the question is whether ANY neighbourhood
    scale beats the rule, so each magnitude and each kind gets a slot
    before any of them gets a second.
    """
    buckets: dict[tuple, list] = {}
    for row in rows:
        buckets.setdefault((row["kind"], row["magnitude"]), []).append(row)
    picked: list[dict[str, Any]] = []
    for cycle in itertools.count():
        added = False
        for key in sorted(buckets):
            group = buckets[key]
            if cycle < len(group) and len(picked) < width:
                picked.append(group[cycle])
                added = True
        if not added or len(picked) >= width:
            break
    return picked[:width]


def probe_step(
    agent_module, task_config, env, observed, action, *, case_id,
    environment_seed, executed, step, attempt_budget, top_k,
    rollout_top_k, rollout_max_steps, magnitudes, orientation_swaps,
    fork_width,
) -> dict[str, Any]:
    started = time.perf_counter()
    generated = perturbations(
        action, magnitudes=magnitudes, orientation_swaps=orientation_swaps,
    )
    feasible = screen(env, generated)
    picked = pick_spanning(feasible, fork_width)
    out: dict[str, Any] = {
        "generated": len(generated),
        "feasible": len(feasible),
        "forked_perturbations": len(picked),
        "screen_seconds": round(time.perf_counter() - started, 3),
        "forked": False,
    }
    if not picked:
        return out
    base = perturbation_candidate(
        action, observed, label="base", rank=0,
    )
    # The base carries the rule's own command, so it must not be built by
    # the perturbation recipe under a different kind or the two would get
    # different candidate ids for the same action.
    roots = [base] + [
        perturbation_candidate(
            row["action"], observed, label=row["label"], rank=index + 1,
        )
        for index, row in enumerate(picked)
    ]
    by_id = {
        str(candidate.candidate_id): label
        for candidate, label in zip(
            roots, ["base"] + [row["label"] for row in picked]
        )
    }
    fork_started = time.perf_counter()
    fork = vector_search_root(
        agent_module, task_config, case_id=case_id,
        environment_seed=environment_seed,
        prefix_actions=list(executed),
        root_candidates=roots,
        attempt_budget=attempt_budget,
        deep_top_k=top_k, expansions=0, max_depth=1, step=step,
        leaf_eval="rollout", rollout_top_k=rollout_top_k,
        rollout_max_steps=rollout_max_steps, allocation="frontier",
        item_symmetry_cache_shadow=True,
        item_symmetry_terminal_cache=True,
    )
    result = verdicts(fork, str(base.candidate_id))
    out.update({
        "forked": True,
        "fork_seconds": round(time.perf_counter() - fork_started, 3),
        "fork_physical_step_equivalents": int(
            fork.get("physical_step_equivalents", 0)
        ),
        "base_genuine": result["base_genuine"],
        "base_terminal_vector": result.get("base_terminal_vector"),
        "verdicts": [
            {
                "label": by_id[candidate_id],
                "kind": next(
                    row["kind"] for row in picked
                    if row["label"] == by_id[candidate_id]
                ),
                "magnitude": next(
                    row["magnitude"] for row in picked
                    if row["label"] == by_id[candidate_id]
                ),
                **entry,
            }
            for candidate_id, entry in result["per_candidate"].items()
        ],
    })
    return out


def summarize(episode: dict[str, Any]) -> dict[str, Any]:
    forked = [r for r in episode["records"] if r.get("forked")]
    rows = [v for r in forked for v in r.get("verdicts", [])]
    tally: dict[str, int] = {}
    for row in rows:
        tally[row["verdict"]] = tally.get(row["verdict"], 0) + 1
    by_magnitude: dict[str, dict[str, int]] = {}
    for row in rows:
        key = f"{row['kind']}@{row['magnitude']:.3f}"
        bucket = by_magnitude.setdefault(key, {})
        bucket[row["verdict"]] = bucket.get(row["verdict"], 0) + 1
    winning_steps = sum(
        1 for r in forked
        if any(v["verdict"] == "beats_base" for v in r.get("verdicts", []))
    )
    generated = sum(int(r.get("generated", 0)) for r in episode["records"])
    feasible = sum(int(r.get("feasible", 0)) for r in episode["records"])
    return {
        "forked_steps": len(forked),
        "steps_with_a_winning_perturbation": winning_steps,
        "comparisons": len(rows),
        "verdict_tally": tally,
        "verdict_by_perturbation": by_magnitude,
        "perturbations_generated": generated,
        "perturbations_feasible": feasible,
        "feasible_rate": (
            round(feasible / generated, 4) if generated else None
        ),
        "base_non_genuine_forks": sum(
            1 for r in forked if r.get("base_genuine") is False
        ),
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
    parser.add_argument(
        "--magnitudes", type=float, nargs="+", default=[0.02, 0.05, 0.10],
        help="axis-aligned nudge sizes in metres; span small refinements"
             " through structurally different placements",
    )
    parser.add_argument("--orientation-swaps", type=int, default=2)
    parser.add_argument(
        "--fork-width", type=int, default=4,
        help="perturbations forked per probed step, chosen to span"
             " magnitudes rather than to take the first few feasible",
    )
    parser.add_argument(
        "--fork-budget", type=int, default=8,
        help="probed steps per episode; each fork terminal-rolls out"
             " every root, so this is the dominant cost",
    )
    parser.add_argument(
        "--first-step", type=int, default=4,
        help="skip the opening moves, where an empty container makes"
             " almost any placement feasible and nothing is contested",
    )
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
        rollout_max_steps=args.rollout_max_steps,
        max_steps=args.max_steps, magnitudes=list(args.magnitudes),
        orientation_swaps=args.orientation_swaps,
        fork_width=args.fork_width, fork_budget=args.fork_budget,
        first_step=args.first_step,
    )
    payload = {
        "schema_version": 1,
        "experiment": "stage 0 perturbation novelty probe",
        "question": (
            "does a mechanical perturbation of the rule's own executed"
            " action ever strictly dominate it under the four-head"
            " terminal rule?"
        ),
        "actor": "rule-alpha",
        "dominance_rule": "imported from run_vector_mcts (four heads)",
        "perturbation_contract": {
            "magnitudes_m": list(args.magnitudes),
            "orientation_swaps": args.orientation_swaps,
            "fork_width": args.fork_width,
            "fork_budget": args.fork_budget,
            "first_step": args.first_step,
            "screen": "one-step physical safety via env_checkpoint",
            "state_distribution": "untouched; the actor executes its own action",
        },
        "summary": summarize(episode),
        "episode": episode,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(json_safe(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
