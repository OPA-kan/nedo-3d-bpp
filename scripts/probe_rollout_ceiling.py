"""How far does the rollout get before it declares the board finished?

Cup 009's mining forks ran 108 terminal rollouts on one cell. Not one
ended by exhausting the item stream: 96.3% ended `no_retained_candidate`
and 3.7% `no_safe_retained_candidate`. Both are listed in
GENUINE_TERMINATIONS, so "the generator ran out of proposals" is
recorded as "the board is full".

That makes the teacher an n-step estimate with the bootstrap term pinned
to zero,

    V(s_t) ~= sum_{k<n} r_{t+k} + gamma^n * V(s_{t+n}),  V(s_{t+n}) := 0

and today's measurement puts that zero two to four times below what the
board actually still holds.

The candidate union was built to fix a train/inference mismatch, but it
should also push `no_retained_candidate` further out: a provider with
more to propose runs out later. This measures whether it does -- how
many steps the continuation survives, and how much fill it books --
against the same continuation on the generic provider alone, and
against rule-alpha's own play as a reference ceiling.

Nothing here is learned. It asks how far the zero-bootstrap estimate can
be carried by widening the candidate set alone.
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

from rule_alpha.config import DEFAULT_CONFIG  # noqa: E402
from scripts.build_counterfactual_graph import (  # noqa: E402
    build_candidate_provider,
    cumulative_metrics,
)
from scripts.build_replay_dataset import (  # noqa: E402
    json_safe,
    load_agent_module,
    policy_observation,
    require_supported_python,
)
from scripts.run_self_play_packing import (  # noqa: E402
    _candidate_action,
    _safe,
    _status,
)
from scripts.run_single_agent_packing import _fresh_env  # noqa: E402
from scripts.sweep_rule_alpha_config import episode as rule_alpha_episode  # noqa: E402

CONTRACT = "rollout_ceiling_probe_v1"


def rank0(task, *, agent_module, seed, attempt_budget, max_steps,
          union: bool, union_limit: int) -> dict[str, Any]:
    """The teacher's own continuation: provider rank-0 to termination."""
    started = time.perf_counter()
    provider = build_candidate_provider(
        agent_module, attempt_budget=attempt_budget,
        scan_all_visible_items=True,
    )
    env = _fresh_env(task)
    proposer = None
    try:
        env.reset_settings()
        if union:
            from scripts.rule_alpha_proposals import (
                RuleAlphaProposer,
                union_provider,
            )

            proposer = RuleAlphaProposer(max_proposals=int(union_limit))
            proposer.get_init_states(env.get_init_states())
            provider = union_provider(
                provider, proposer, observation_fn=policy_observation,
            )
        env.reset_item_stream()
        observation, _info = env.reset(seed=seed)
        termination, steps = None, 0
        for _ in range(max_steps):
            candidates = list(provider(env, observation, 3))
            if not candidates:
                termination = "no_retained_candidate"
                break
            observation, _r, terminated, truncated, info = env.step(
                _candidate_action(candidates[0])
            )
            steps += 1
            if not _safe(_status(info)):
                termination = "selected_action_failure"
                break
            if terminated or truncated:
                termination = "stream_exhausted" if terminated else "truncated"
                break
        else:
            termination = "continuation_cap"
        metrics = cumulative_metrics(env)
    finally:
        env.close()
    return {
        "termination": termination,
        "steps": steps,
        "placed_count": int(metrics.get("placed_count") or 0),
        "fill": round(float(metrics.get("fill_score_proxy") or 0.0), 3),
        "seconds": round(time.perf_counter() - started, 1),
        "proposer_seconds": (
            round(float(proposer.seconds), 1) if proposer else None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=pathlib.Path, required=True)
    parser.add_argument("--cases", nargs="+", required=True)
    parser.add_argument("--environment-seed", type=int, default=42)
    parser.add_argument("--attempt-budget", type=int, default=128)
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--union-limit", type=int, default=4)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    require_supported_python()
    agent_module = load_agent_module()

    rows = []
    for case in args.cases:
        config = json.loads(
            (args.config_dir / f"{case}.json").read_text(encoding="utf-8")
        )
        task = next(
            v for v in config.values()
            if isinstance(v, dict) and "containers" in v
        )
        plain = rank0(
            task, agent_module=agent_module, seed=args.environment_seed,
            attempt_budget=args.attempt_budget, max_steps=args.max_steps,
            union=False, union_limit=args.union_limit,
        )
        unioned = rank0(
            task, agent_module=agent_module, seed=args.environment_seed,
            attempt_budget=args.attempt_budget, max_steps=args.max_steps,
            union=True, union_limit=args.union_limit,
        )
        reference = rule_alpha_episode(
            task, config=DEFAULT_CONFIG, seed=args.environment_seed,
            max_steps=args.max_steps,
        )
        rows.append({
            "case": case, "generic": plain, "unioned": unioned,
            "rule_alpha_reference": {
                "termination": reference["termination"],
                "steps": reference["steps"],
                "placed_count": reference["placed_count"],
                "fill": round(reference["fill_score_proxy"], 3),
            },
        })
        print(
            f"{case}\n"
            f"  generic   n={plain['steps']:2d} fill={plain['fill']:7.3f}"
            f"  {plain['termination']}\n"
            f"  unioned   n={unioned['steps']:2d} fill={unioned['fill']:7.3f}"
            f"  {unioned['termination']}  (+{unioned['fill']-plain['fill']:.3f})\n"
            f"  rule-alpha n={reference['steps']:2d}"
            f" fill={reference['fill_score_proxy']:7.3f}"
            f"  {reference['termination']}",
            flush=True,
        )

    def mean(key, arm):
        values = [float(r[arm][key]) for r in rows]
        return round(sum(values) / len(values), 3) if values else None

    summary = {
        "cells": len(rows),
        "mean_steps": {
            "generic": mean("steps", "generic"),
            "unioned": mean("steps", "unioned"),
            "rule_alpha": mean("steps", "rule_alpha_reference"),
        },
        "mean_fill": {
            "generic": mean("fill", "generic"),
            "unioned": mean("fill", "unioned"),
            "rule_alpha": mean("fill", "rule_alpha_reference"),
        },
        "generic_no_retained_candidate": sum(
            1 for r in rows
            if r["generic"]["termination"] == "no_retained_candidate"
        ),
        "unioned_no_retained_candidate": sum(
            1 for r in rows
            if r["unioned"]["termination"] == "no_retained_candidate"
        ),
    }
    payload = {
        "schema_version": 1, "contract": CONTRACT,
        "question": (
            "does widening the candidate set push out the rollout's"
            " no_retained_candidate, and how much of rule-alpha's ceiling"
            " does that recover?"
        ),
        "summary": summary, "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(json_safe(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("\n=== summary ===")
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
