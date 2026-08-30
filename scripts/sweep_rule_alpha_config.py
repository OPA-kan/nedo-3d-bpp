"""Decide rule-alpha's shelved config flags on Cup courses, not on n=2.

The rule-alpha branch keeps arriving at the same place: a mechanism is
traced, repaired, verified correct -- and then shipped **off**, because
enabling it lowers the score on one of the two official tasks and raises
it on the other.  Its own commit messages say why that is not a verdict:

    "Two items gained against four points of fill lost, on a sample of
     two, is not enough to ship a change that lowers the headline score."
    "part of that 29.484 was earned by the bug"

Sixteen booleans now sit off in `rule_alpha/config.py` for that reason.
The Cup side has the thing that decision needs and the branch does not:
six independent, never-reused course cells per cup, and nine cups of
them.  This harness spends that evidence on those flags.

It deliberately runs the actor ALONE -- no search, no forks, no
champion.  The quantity in dispute is placed-count and fill, which is
exactly what the branch measures, so this extends their own measurement
from n=2 to n=cells rather than substituting a different one.  Dropping
the search is also what makes it cheap enough to sweep: a bare
rule-alpha episode is about a minute, against the half hour a mining
cell costs.

Paired by construction: both arms see the identical course cell and
seed, so a cell that is simply hard cancels out of the delta.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import statistics
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "simulator") not in sys.path:
    sys.path.insert(0, str(ROOT / "simulator"))

from rule_alpha.config import DEFAULT_CONFIG  # noqa: E402
from scripts.build_counterfactual_graph import cumulative_metrics  # noqa: E402
from scripts.build_replay_dataset import (  # noqa: E402
    json_safe,
    policy_observation,
    require_supported_python,
)
from scripts.counterfactual_graph import canonical_action  # noqa: E402
from scripts.run_self_play_packing import _safe, _status  # noqa: E402
from scripts.run_single_agent_packing import _fresh_env  # noqa: E402

CONTRACT = "rule_alpha_config_sweep_v1"


def episode(task_config: dict[str, Any], *, config, seed: int,
            max_steps: int) -> dict[str, Any]:
    """One bare rule-alpha episode: its own policy, its own actions."""
    from rule_alpha.agent import RuleAlphaAgent

    started = time.perf_counter()
    env = _fresh_env(task_config)
    try:
        env.reset_settings()
        actor = RuleAlphaAgent(config=config)
        actor.get_init_states(env.get_init_states())
        env.reset_item_stream()
        observation, _info = env.reset(seed=seed)
        termination = None
        steps = 0
        for _step in range(max_steps):
            observed = policy_observation(env, observation)
            action = actor.policy(observed)
            if action is None:
                termination = "rule_alpha_declined"
                break
            observation, _reward, terminated, truncated, info = env.step(
                canonical_action(action)
            )
            steps += 1
            if not _safe(_status(info)):
                termination = "selected_action_failure"
                break
            if terminated or truncated:
                termination = "stream_exhausted" if terminated else "max_steps"
                break
        else:
            termination = "max_steps"
        metrics = cumulative_metrics(env)
    finally:
        env.close()
    return {
        "termination": termination,
        "steps": steps,
        "placed_count": int(metrics.get("placed_count") or 0),
        "fill_score_proxy": float(metrics.get("fill_score_proxy") or 0.0),
        "center_of_mass_z": metrics.get("center_of_mass_z"),
        "seconds": round(time.perf_counter() - started, 1),
    }


def flipped(flag: str):
    if not hasattr(DEFAULT_CONFIG, flag):
        raise ValueError(f"rule_alpha config has no flag {flag!r}")
    current = getattr(DEFAULT_CONFIG, flag)
    if not isinstance(current, bool):
        raise ValueError(f"{flag!r} is not a boolean flag")
    return dataclasses.replace(DEFAULT_CONFIG, **{flag: not current})


def paired_delta(base: list[dict], arm: list[dict]) -> dict[str, Any]:
    """Per-cell deltas, and how many cells each direction won.

    The mean is reported beside the win/loss counts on purpose: one cell
    swinging four points of fill is what "raises one task and lowers the
    other" looks like at n=2, and a mean alone would hide it again.
    """
    fills = [a["fill_score_proxy"] - b["fill_score_proxy"]
             for b, a in zip(base, arm)]
    placed = [a["placed_count"] - b["placed_count"] for b, a in zip(base, arm)]
    return {
        "cells": len(fills),
        "fill_delta_mean": round(statistics.fmean(fills), 4) if fills else None,
        "fill_delta_min": round(min(fills), 4) if fills else None,
        "fill_delta_max": round(max(fills), 4) if fills else None,
        "fill_cells_better": sum(1 for value in fills if value > 1e-9),
        "fill_cells_worse": sum(1 for value in fills if value < -1e-9),
        "fill_cells_identical": sum(1 for value in fills if abs(value) <= 1e-9),
        "placed_delta_mean": (
            round(statistics.fmean(placed), 4) if placed else None
        ),
        "placed_delta_sum": sum(placed),
        "per_cell_fill_delta": [round(value, 4) for value in fills],
        "per_cell_placed_delta": placed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config-dir", type=pathlib.Path, required=True,
        help="directory of built scenario json (build_scenario_matrix output)",
    )
    parser.add_argument(
        "--cases", nargs="+", required=True,
        help="scenario names within --config-dir, e.g. dual-empty",
    )
    parser.add_argument(
        "--flags", nargs="+", required=True,
        help="rule_alpha config booleans to flip, one arm each",
    )
    parser.add_argument("--environment-seed", type=int, default=42)
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    require_supported_python()

    tasks = []
    for case in args.cases:
        path = args.config_dir / f"{case}.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        # A Cup cell is a (scenario, stream) pair, so the file is named for
        # the cell while the key inside is the scenario. Resolve by exact
        # key, else by the file holding exactly one task -- never by
        # falling through to the whole map, which would silently hand the
        # env a dict of scenarios and make every arm identical.
        key = f"m-{case}"
        if key in config:
            task = config[key]
        else:
            cases = {
                name: value for name, value in config.items()
                if isinstance(value, dict) and "containers" in value
            }
            if len(cases) == 1:
                task = next(iter(cases.values()))
            elif "containers" in config:
                task = config
            else:
                raise SystemExit(
                    f"{path} holds {len(cases)} tasks; name the file for the"
                    " single scenario it should run"
                )
        tasks.append((case, task))

    print("baseline (shipped config)", flush=True)
    baseline = []
    for case, task in tasks:
        row = episode(
            task, config=DEFAULT_CONFIG, seed=args.environment_seed,
            max_steps=args.max_steps,
        )
        row["case"] = case
        baseline.append(row)
        print(
            f"  {case:28s} placed={row['placed_count']:3d}"
            f" fill={row['fill_score_proxy']:7.3f} {row['termination']}"
            f" ({row['seconds']}s)", flush=True,
        )

    arms = {}
    for flag in args.flags:
        config = flipped(flag)
        print(
            f"\n{flag} = {getattr(config, flag)}"
            f" (shipped {getattr(DEFAULT_CONFIG, flag)})", flush=True,
        )
        rows = []
        for case, task in tasks:
            row = episode(
                task, config=config, seed=args.environment_seed,
                max_steps=args.max_steps,
            )
            row["case"] = case
            rows.append(row)
            print(
                f"  {case:28s} placed={row['placed_count']:3d}"
                f" fill={row['fill_score_proxy']:7.3f} {row['termination']}"
                f" ({row['seconds']}s)", flush=True,
            )
        arms[flag] = {"episodes": rows, "delta": paired_delta(baseline, rows)}

    payload = {
        "schema_version": 1,
        "contract": CONTRACT,
        "experiment": "rule-alpha shelved config flags on Cup course cells",
        "why": (
            "the branch shelves these flags because one official task"
            " improves and the other regresses at n=2; the Cup has six"
            " independent never-reused cells per cup"
        ),
        "measurement": "bare actor, no search and no forks; placed and fill",
        "environment_seed": args.environment_seed,
        "cases": list(args.cases),
        "baseline": baseline,
        "arms": arms,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(json_safe(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("\n=== paired deltas vs shipped ===", flush=True)
    for flag, arm in arms.items():
        delta = arm["delta"]
        print(
            f"{flag:34s} fill {delta['fill_delta_mean']:+8.4f}"
            f"  better/worse/same"
            f" {delta['fill_cells_better']}/{delta['fill_cells_worse']}"
            f"/{delta['fill_cells_identical']}"
            f"  placed {delta['placed_delta_sum']:+d}", flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
