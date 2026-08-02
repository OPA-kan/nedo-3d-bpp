"""
Paired arm comparison across permuted arrival streams.

The design this encodes, and why each part of it is not optional:

- **Paired within stream.** The development suite's noise floor is large and
  is NOT reachable by repeats: permuting one multiset moves placed by up to
  7 (sd 2.315), while re-running one configuration is bit-identical on most
  configs. So the variance that matters is `omega` (arrival order), and the
  only way to see through it is to compare arms on the SAME stream.
- **Sequential.** The search is deadline-limited; running episodes in
  parallel changes what each can reach, which is the quantity under test.
- **Alternating arm order.** Stream j runs base-first on even j and
  arm-first on odd j. Runtime variance `xi` is config-dependent and nonzero
  on some configurations (up to 5 placed), so running all of one arm and
  then all of the other would let any slow drift in machine state load onto
  one arm. Alternating cancels the linear component.

Output matches reports/stream-variance/base-vs-item-cap16.json so results
across source cases are directly comparable.

    python3 scripts/run_stream_paired.py \\
        --streams-dir reports/stream-variance/case001 \\
        --arm item_cap16 \\
        --output reports/stream-variance/case001-base-vs-item-cap16.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_risk_ablation import (  # noqa: E402
    SIMULATOR,
    case_summary,
    configure_arm_environment,
    sync_agent_into_simulator,
)
from scripts.run_checks import load_json, run  # noqa: E402


def run_episode(config_path: pathlib.Path, arm: str,
                out_dir: pathlib.Path) -> dict:
    import os

    sync_agent_into_simulator()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    case_id = next(iter(config))
    run_dir = out_dir / f"{case_id}-{arm}"
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = run_dir / "evaluation_results.json"
    trace_path = run_dir / "policy-trace.jsonl"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(SIMULATOR)
    env["NEDO_POLICY_TRACE_PATH"] = str(trace_path.resolve())
    for name in ("MAX_POOL_ITEMS_EVALUATED", "LIVE_SEARCH_INTERLEAVE",
                 "VISIBLE_POOL_ROLLOUT_STRIDE", "VISIBLE_POOL_ROLLOUT_MODE",
                 "RESCUE_SCAN_ENABLED", "CROSS_STEP_INCUMBENT_MODE"):
        env.pop(name, None)
    configure_arm_environment(env, arm, risk_lambda=1.0, slide_lambda=0.5)

    result = run(
        [sys.executable, "scripts/run_test.py",
         "--config-path", str(config_path.resolve()),
         "--module-path", "",
         "--result-dir", str(run_dir.resolve()),
         "--result-fname", result_path.name],
        SIMULATOR, env,
    )
    (run_dir / "simulator.log").write_text(
        result["stdout"] + result["stderr"], encoding="utf-8"
    )
    evaluation = load_json(result_path) if result_path.exists() else {}
    summary = case_summary(evaluation, config).get(case_id, {})
    fallbacks = 0
    deadline_hits = 0
    decisions = 0
    if trace_path.exists():
        for line in trace_path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record.get("event") != "decision":
                continue
            decisions += 1
            search = record.get("candidate_diagnostics", {}).get("search", {})
            if search.get("deadline_reached"):
                deadline_hits += 1
            if record.get("candidate_kind") == "unsafe_protocol_fallback":
                fallbacks += 1
    return {
        "case_id": case_id,
        "arm": arm,
        "returncode": int(result["returncode"]),
        "placed": int(summary.get("placed_count", 0)),
        "fill": round(float(summary.get("fill_score", 0.0)), 3),
        "steps": int(summary.get("steps", 0)),
        "is_valid": bool(summary.get("is_valid")),
        "is_placed_safe": bool(summary.get("is_placed_safe")),
        "policy_seconds": round(float(summary.get("policy_seconds", 0.0)), 3),
        "decisions": decisions,
        "deadline_reached": deadline_hits,
        "ended_in_fallback": fallbacks > 0,
    }


def sign_test_p(wins: int, losses: int) -> float:
    """
    Two-sided exact sign test; ties are dropped, as is conventional.

    NOTE for comparison with reports/stream-variance/base-vs-item-cap16.json:
    that file's 0.00391 for 8/0 is the ONE-sided value (0.5**8). This
    function returns the two-sided 0.00781 for the same counts. Do not read
    the two numbers as a difference in evidence strength -- it is a
    difference in convention, and the conservative one is used here.
    """
    from math import comb

    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(comb(n, i) for i in range(k + 1)) / (2 ** n)
    return round(min(1.0, 2 * tail), 5)


def summarise(pairs: list[dict], arm: str, design: dict) -> dict:
    def stat(values):
        return {
            "mean": round(statistics.fmean(values), 3),
            "sd": round(statistics.stdev(values), 3) if len(values) > 1 else 0.0,
            "min": min(values), "max": max(values),
            "range": round(max(values) - min(values), 3),
        }

    base_placed = [p["base"]["placed"] for p in pairs]
    base_fill = [p["base"]["fill"] for p in pairs]
    dp = [p["delta_placed"] for p in pairs]
    df = [p["delta_fill"] for p in pairs]

    def effect(deltas):
        wins = sum(1 for d in deltas if d > 0)
        losses = sum(1 for d in deltas if d < 0)
        return {
            "mean_diff": round(statistics.fmean(deltas), 3),
            "sd": round(statistics.stdev(deltas), 3) if len(deltas) > 1 else 0.0,
            "wins": wins, "losses": losses,
            "ties": len(deltas) - wins - losses,
            "sign_test_p": sign_test_p(wins, losses),
        }

    def pressure(key):
        eps = [p[key] for p in pairs]
        decisions = sum(e["decisions"] for e in eps)
        return {
            "decisions": decisions,
            "mean_steps": round(statistics.fmean([e["steps"] for e in eps]), 2),
            "deadline_reached_rate": round(
                sum(e["deadline_reached"] for e in eps) / decisions, 3
            ) if decisions else None,
            "episodes_ending_in_fallback": sum(
                1 for e in eps if e["ended_in_fallback"]
            ),
        }

    return {
        "schema_version": 1,
        "design": design,
        "noise_floor_base": {
            "placed": stat(base_placed), "fill": stat(base_fill),
            "interpretation": (
                "Spread of the unchanged algorithm on an unchanged item "
                "multiset. Any effect smaller than it cannot be read from "
                "unpaired per-configuration deltas."
            ),
        },
        f"paired_effect_{arm}": {"placed": effect(dp), "fill": effect(df)},
        "search_pressure": {"base": pressure("base"), arm: pressure(arm)},
        "per_stream": pairs,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--streams-dir", type=pathlib.Path, required=True)
    parser.add_argument("--arm", default="item_cap16")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--run-dir", type=pathlib.Path)
    args = parser.parse_args()

    manifest = json.loads(
        (args.streams_dir / "manifest.json").read_text(encoding="utf-8")
    )
    run_dir = args.run_dir or (args.streams_dir / "runs")
    pairs = []
    for index, variant in enumerate(manifest["variants"]):
        config_path = args.streams_dir / variant["path"]
        # Alternate which arm goes first so slow drift in machine state
        # cannot load onto one arm.
        order = ["base", args.arm] if index % 2 == 0 else [args.arm, "base"]
        episodes = {}
        for arm in order:
            print(f"[{index}] {variant['task_id']} {arm}", flush=True)
            episodes[arm] = run_episode(
                config_path, arm, run_dir / variant["task_id"]
            )
        pairs.append({
            "stream": variant["task_id"],
            "arm_order": order,
            "base": episodes["base"],
            args.arm: episodes[args.arm],
            "delta_placed": episodes[args.arm]["placed"] - episodes["base"]["placed"],
            "delta_fill": round(
                episodes[args.arm]["fill"] - episodes["base"]["fill"], 3
            ),
        })

    design = dict(manifest.get("design", {}))
    design.update({
        "mode": manifest.get("mode"),
        "source_case": manifest.get("source_case"),
        "look_ahead": manifest.get("look_ahead"),
        "variants": len(manifest["variants"]),
        "arm_order": "alternating (base-first on even streams)",
        "note": (
            "Permutations of one multiset: content, class mix, total volume "
            "and difficulty identical across variants; only arrival order "
            "differs. Arms are paired within each stream and run "
            "sequentially, because the search is deadline-limited and "
            "parallel execution would change what it can reach."
        ),
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summarise(pairs, args.arm, design), ensure_ascii=False,
                   indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
