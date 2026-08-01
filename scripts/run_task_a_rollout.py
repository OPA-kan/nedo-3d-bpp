"""Run and aggregate the Task A bounded-rollout transfer experiment."""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_checks import load_json, run  # noqa: E402
from scripts.run_risk_ablation import (  # noqa: E402
    SIMULATOR,
    case_summary,
    sync_agent_into_simulator,
)


def configure_task_a_arm(
    env: dict[str, str],
    arm: str,
    *,
    offline_seconds: float,
    macro_seconds: float,
) -> None:
    for name in (
        "OFFLINE_SEARCH_BUDGET_SECONDS",
        "OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM",
        "OFFLINE_PAIR_MACRO_BUDGET_SECONDS",
    ):
        env.pop(name, None)
    env["OFFLINE_SEARCH_BUDGET_SECONDS"] = str(float(offline_seconds))
    if arm == "base":
        return
    if not arm.startswith("bounded"):
        raise ValueError(f"unknown Task A arm: {arm}")
    attempts = int(arm.removeprefix("bounded"))
    if attempts <= 0:
        raise ValueError("bounded attempt budget must be positive")
    env["OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM"] = str(attempts)
    env["OFFLINE_PAIR_MACRO_BUDGET_SECONDS"] = str(
        float(macro_seconds)
    )


def read_offline_trace(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record.get("event") == "offline_optimization":
                return record
    return {}


def run_episode(args: argparse.Namespace) -> dict:
    sync_agent_into_simulator()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    case_id = next(iter(config))
    run_dir = args.output_dir / (
        f"{case_id}-{args.arm}-r{args.repeat}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = run_dir / "evaluation_results.json"
    trace_path = run_dir / "policy-trace.jsonl"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(SIMULATOR)
    env["NEDO_POLICY_TRACE_PATH"] = str(trace_path.resolve())
    configure_task_a_arm(
        env,
        args.arm,
        offline_seconds=args.offline_seconds,
        macro_seconds=args.macro_seconds,
    )
    result = run(
        [
            sys.executable,
            "scripts/run_test.py",
            "--config-path",
            str(args.config.resolve()),
            "--module-path",
            "",
            "--result-dir",
            str(run_dir.resolve()),
            "--result-fname",
            result_path.name,
        ],
        SIMULATOR,
        env,
    )
    (run_dir / "simulator.log").write_text(
        result["stdout"] + result["stderr"], encoding="utf-8"
    )
    evaluation = load_json(result_path) if result_path.exists() else {}
    raw_case = evaluation.get(case_id, {})
    row = {
        "source_case": args.source_case,
        "case_id": case_id,
        "arm": args.arm,
        "repeat": int(args.repeat),
        "process_returncode": int(result["returncode"]),
        "process_seconds": float(result["seconds"]),
        "optimization_seconds": float(
            (raw_case.get("time_results") or {}).get("optimization", 0.0)
        ),
        "case": case_summary(evaluation, config).get(case_id, {}),
        "offline": read_offline_trace(trace_path),
    }
    (run_dir / "row.json").write_text(
        json.dumps(row, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return row


def metric(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": round(statistics.fmean(values), 6),
        "min": min(values),
        "max": max(values),
    }


def summarize(root: pathlib.Path) -> dict:
    rows = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(root.rglob("row.json"))
    ]
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        groups.setdefault((row["source_case"], row["arm"]), []).append(row)
    results = []
    for (source_case, arm), group in sorted(groups.items()):
        good = [row for row in group if row["process_returncode"] == 0]
        results.append(
            {
                "source_case": source_case,
                "arm": arm,
                "episodes": len(good),
                "placed": metric(
                    [float(row["case"]["placed_count"]) for row in good]
                ),
                "fill": metric(
                    [float(row["case"]["fill_score"]) for row in good]
                ),
                "optimization_seconds": metric(
                    [float(row["optimization_seconds"]) for row in good]
                ),
                "offline_evaluations": metric(
                    [float(row["offline"].get("evaluations", 0)) for row in good]
                ),
                "offline_proxy_placed": metric(
                    [
                        float(
                            (row["offline"].get("best_result") or {}).get(
                                "placed_count", 0
                            )
                        )
                        for row in good
                    ]
                ),
            }
        )
    return {"rows": len(rows), "results": results}


def render_markdown(summary: dict) -> str:
    lines = [
        "# Task A bounded-rollout transfer",
        "",
        f"Rows: {summary['rows']}",
        "",
        "| source | arm | episodes | placed mean [min,max] | fill mean "
        "| optimization s | offline evaluations | offline proxy placed |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for result in summary["results"]:
        placed = result["placed"]
        lines.append(
            f"| {result['source_case']} | {result['arm']} "
            f"| {result['episodes']} "
            f"| {placed['mean']} [{placed['min']},{placed['max']}] "
            f"| {result['fill']['mean']} "
            f"| {result['optimization_seconds']['mean']} "
            f"| {result['offline_evaluations']['mean']} "
            f"| {result['offline_proxy_placed']['mean']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--source-case")
    parser.add_argument("--arm")
    parser.add_argument("--repeat", type=int, default=0)
    parser.add_argument("--offline-seconds", type=float, default=30.0)
    parser.add_argument("--macro-seconds", type=float, default=0.5)
    parser.add_argument("--output-dir", type=pathlib.Path)
    parser.add_argument("--summarize-root", type=pathlib.Path)
    parser.add_argument("--summary-output", type=pathlib.Path)
    args = parser.parse_args()

    if args.summarize_root is not None:
        summary = summarize(args.summarize_root)
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.with_suffix(".json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        args.summary_output.with_suffix(".md").write_text(
            render_markdown(summary), encoding="utf-8"
        )
        return 0

    required = (args.config, args.source_case, args.arm, args.output_dir)
    if any(value is None for value in required):
        parser.error("episode mode requires config/source-case/arm/output-dir")
    run_episode(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
