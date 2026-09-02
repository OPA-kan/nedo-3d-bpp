"""Compare policy heads over hundreds of cells instead of six.

The Cup course is six cells, and six cells cannot resolve the size of
difference our changes produce: the advantage-distilled head beat the
shipped champion by +0.652 mean fill with a paired standard deviation of
4.632, which is a t of 0.34 and needs about 396 cells for 80% power
(`reports/value/advantage-distillation-20260831.md`). Every "is this
model better" verdict the season has recorded rests on six.

The fix is not a better statistic -- pairing already removes the
between-cell variance, and what is left is genuine divergence between
two policies on the same board. The fix is n. That is affordable because
a Cup cell is expensive for a reason that does not apply here: it runs
six horses AND the teacher's physical terminal rollouts. Comparing two
frozen policy heads needs neither. One measured episode averages 28
seconds, so four hundred cells across two arms is a few CPU-hours.

Cells are (scenario, stream) pairs drawn from the arena band added to
``build_scenario_matrix.STREAM_VARIANTS`` -- primes 809 and up, disjoint
from the frozen eval variants, the season-1 wave primes and the Cup
pool, and deliberately re-usable, because an arena run measures two
frozen policies rather than drawing a single-use corpus.

Runs are resumable: a cell whose manifest already exists is skipped, so
n can be grown by re-running with a larger ``--streams``.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import pathlib
import random
import re
import statistics
import subprocess
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_scenario_matrix import SCENARIOS, STREAM_VARIANTS

CONTRACT = "policy_arena_v1"
# Streams reserved for the arena. Cup primes (401-799), the frozen eval
# variants (<= 197) and the season-1 wave primes (<= 379) are all below
# this floor and must stay out: see the band comment in
# build_scenario_matrix.
ARENA_PRIME_FLOOR = 809


def arena_streams() -> list[str]:
    found = []
    for variant in STREAM_VARIANTS:
        match = re.fullmatch(r"permute-(000|001)-(\d+)", variant)
        if match and int(match.group(2)) >= ARENA_PRIME_FLOOR:
            found.append((int(match.group(2)), match.group(1), variant))
    # interleave the two sources so a truncated run stays balanced
    return [variant for _prime, _source, variant in sorted(found)]


def build_configs(
    variant: str, config_root: pathlib.Path, python: str,
) -> pathlib.Path:
    target = config_root / variant
    if (target / "manifest.json").is_file():
        return target
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [python, str(ROOT / "scripts" / "build_scenario_matrix.py"),
         "--stream-variant", variant, "--output-dir", str(target)],
        check=True, capture_output=True,
    )
    return target


MODIFIERS = {
    # C(s) = C_generic(s) | C_rule-alpha(s) on the INFERENCE side. The
    # same ranker, a wider choice set: the one arm that separates "the
    # learner ranks badly" from "the learner is never offered the board".
    "union": ["--union-rule-alpha", "--rule-alpha-union-limit", "4"],
    # Expert advisors: their move is offered, they never execute.
    "expert-agent": ["--union-expert", "current-agent"],
    "expert-alpha": ["--union-expert", "rule-alpha"],
}


def arm_command(spec: str) -> list[str]:
    """Policy flags for one arm.

    An arm is a learned head (a model directory) or one of the runner's
    own policies, written `policy:<name>`, optionally followed by
    comma-separated modifiers. The hand-coded actors have to be
    enterable: without them the arena only compares learned heads to
    each other, and at 200 cells the champion sits 17.70 fill points
    below `current-agent`, which generates its own moves.
    """
    head, *modifiers = spec.split(",")
    for modifier in modifiers:
        if modifier not in MODIFIERS:
            raise ValueError(f"unknown arm modifier: {modifier!r}")
    extra = [flag for modifier in modifiers for flag in MODIFIERS[modifier]]
    if head.startswith("policy:"):
        return ["--policy", head.split(":", 1)[1]] + extra
    return [
        "--policy", "learned",
        "--model-dir", str(pathlib.Path(head).resolve()),
    ] + extra


def run_cell(
    *, python: str, config_dir: pathlib.Path, scenario: str,
    arm_spec: str, output_dir: pathlib.Path, max_steps: int,
) -> dict[str, Any]:
    manifest = output_dir / "manifest.json"
    if manifest.is_file():
        return {"status": "cached", "manifest": manifest}
    output_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [python, str(ROOT / "scripts" / "run_terminal_rollout_policy.py"),
         "--config", str(config_dir / f"{scenario}.json"),
         "--case", f"m-{scenario}",
         "--environment-seed", "42",
         "--attempt-budget", "128",
         "--top-k", "3", "--rollout-top-k", "3",
         "--rollout-max-steps", str(max_steps),
         "--max-steps", str(max_steps),
         *arm_command(arm_spec),
         "--output-dir", str(output_dir)],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not manifest.is_file():
        return {
            "status": "failed",
            "returncode": result.returncode,
            "stderr": result.stderr[-2000:],
        }
    return {"status": "ran", "manifest": manifest}


def read_cell(manifest_path: pathlib.Path) -> dict[str, Any]:
    episode = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )["episodes"][0]
    metrics = episode["final_metrics"]
    return {
        "fill": float(metrics["fill_score_proxy"]),
        "placed": int(metrics["placed_count"]),
        "steps": int(episode["steps"]),
        "termination": episode["termination"],
    }


def _sign_test(wins: int, losses: int) -> float | None:
    """Exact two-sided binomial p for wins vs losses, ties dropped."""
    trials = wins + losses
    if trials == 0:
        return None
    extreme = min(wins, losses)
    tail = sum(
        math.comb(trials, k) for k in range(0, extreme + 1)
    ) / 2 ** trials
    return min(1.0, 2 * tail)


def _bootstrap_ci(
    differences: list[float], *, draws: int = 10000, seed: int = 20260831,
) -> tuple[float, float] | None:
    if len(differences) < 2:
        return None
    rng = random.Random(seed)
    means = []
    size = len(differences)
    for _ in range(draws):
        means.append(sum(
            differences[rng.randrange(size)] for _ in range(size)
        ) / size)
    means.sort()
    return means[int(0.025 * draws)], means[int(0.975 * draws) - 1]


def compare(
    baseline: str, arm: str, cells: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    """Paired over the cells where both arms produced an episode."""
    differences = []
    wins = losses = ties = 0
    for _cell, arms in sorted(cells.items()):
        if baseline not in arms or arm not in arms:
            continue
        delta = arms[arm]["fill"] - arms[baseline]["fill"]
        differences.append(delta)
        if delta > 1e-9:
            wins += 1
        elif delta < -1e-9:
            losses += 1
        else:
            ties += 1
    if not differences:
        return {"cells": 0}
    mean = statistics.mean(differences)
    sd = statistics.stdev(differences) if len(differences) > 1 else 0.0
    se = sd / math.sqrt(len(differences)) if sd else 0.0
    interval = _bootstrap_ci(differences)
    return {
        "cells": len(differences),
        "mean_difference": mean,
        "sd": sd,
        "se": se,
        "t": mean / se if se else None,
        "ci95": list(interval) if interval else None,
        "wins": wins, "losses": losses, "ties": ties,
        "sign_test_p": _sign_test(wins, losses),
        # what this n could have detected at 80% power, two-sided 0.05
        "mde_at_this_n": 2.8 * sd / math.sqrt(len(differences)) if sd else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--arm", action="append", required=True, metavar="NAME=MODEL_DIR",
        help="policy head to enter; repeat for each arm (at least two)",
    )
    parser.add_argument("--baseline", default=None)
    parser.add_argument(
        "--scenarios", default=None,
        help="comma-separated; default is every scenario in the matrix",
    )
    parser.add_argument("--streams", type=int, default=25)
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--work-dir", type=pathlib.Path, required=True)
    parser.add_argument("--report", type=pathlib.Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()

    arms: dict[str, str] = {}
    for entry in args.arm:
        name, _, spec = entry.partition("=")
        if not name or not spec:
            raise SystemExit(
                f"--arm needs NAME=MODEL_DIR or NAME=policy:<name>,"
                f" got {entry!r}"
            )
        head = spec.split(",")[0]
        if not head.startswith("policy:") and not pathlib.Path(head).is_dir():
            raise SystemExit(f"--arm {name}: no such model directory: {head}")
        try:
            arm_command(spec)
        except ValueError as error:
            raise SystemExit(f"--arm {name}: {error}")
        arms[name] = spec
    if len(arms) < 2:
        raise SystemExit("an arena needs at least two arms")
    baseline = args.baseline or next(iter(arms))
    if baseline not in arms:
        raise SystemExit(f"baseline {baseline!r} is not one of the arms")

    scenarios = (
        [name.strip() for name in args.scenarios.split(",")]
        if args.scenarios else [name for name, _spec in SCENARIOS]
    )
    known = {name for name, _spec in SCENARIOS}
    for scenario in scenarios:
        if scenario not in known:
            raise SystemExit(f"unknown scenario: {scenario}")
    streams = arena_streams()[:args.streams]
    if not streams:
        raise SystemExit("no arena streams available")

    config_root = args.work_dir / "configs"
    for variant in streams:
        build_configs(variant, config_root, args.python)

    jobs = []
    for variant in streams:
        for scenario in scenarios:
            for name, spec in arms.items():
                jobs.append((variant, scenario, name, spec))
    print(f"arena: {len(streams)} streams x {len(scenarios)} scenarios"
          f" x {len(arms)} arms = {len(jobs)} runs", flush=True)

    failures = []
    done = 0
    with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
        futures = {
            pool.submit(
                run_cell,
                python=args.python,
                config_dir=config_root / variant,
                scenario=scenario,
                arm_spec=spec,
                output_dir=(
                    args.work_dir / "episodes" / name / scenario / variant
                ),
                max_steps=args.max_steps,
            ): (variant, scenario, name)
            for variant, scenario, name, spec in jobs
        }
        for future in concurrent.futures.as_completed(futures):
            variant, scenario, name = futures[future]
            outcome = future.result()
            done += 1
            if outcome["status"] == "failed":
                failures.append({
                    "cell": f"{scenario}:{variant}", "arm": name,
                    "stderr": outcome["stderr"],
                })
            if done % 25 == 0:
                print(f"  {done}/{len(jobs)} runs, {len(failures)} failed",
                      flush=True)

    cells: dict[str, dict[str, dict[str, Any]]] = {}
    for variant in streams:
        for scenario in scenarios:
            for name in arms:
                manifest = (
                    args.work_dir / "episodes" / name / scenario / variant
                    / "manifest.json"
                )
                if manifest.is_file():
                    cells.setdefault(f"{scenario}:{variant}", {})[name] = (
                        read_cell(manifest)
                    )

    report: dict[str, Any] = {
        "contract": CONTRACT,
        "arms": dict(arms),
        "baseline": baseline,
        "scenarios": scenarios,
        "streams": streams,
        "cells_attempted": len(streams) * len(scenarios),
        "cells_complete": sum(
            1 for arms_seen in cells.values() if len(arms_seen) == len(arms)
        ),
        "failures": failures[:20],
        "failure_count": len(failures),
        "per_arm": {
            name: {
                "cells": sum(1 for a in cells.values() if name in a),
                "mean_fill": statistics.mean(
                    [a[name]["fill"] for a in cells.values() if name in a]
                ),
                "mean_placed": statistics.mean(
                    [a[name]["placed"] for a in cells.values() if name in a]
                ),
            }
            for name in arms
            if any(name in a for a in cells.values())
        },
        "paired": {
            name: compare(baseline, name, cells)
            for name in arms if name != baseline
        },
        "per_scenario": {
            scenario: {
                name: compare(
                    baseline, name,
                    {k: v for k, v in cells.items()
                     if k.startswith(f"{scenario}:")},
                )
                for name in arms if name != baseline
            }
            for scenario in scenarios
        },
        "cells": cells,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = {
        key: report[key]
        for key in ("cells_complete", "failure_count", "per_arm", "paired")
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
