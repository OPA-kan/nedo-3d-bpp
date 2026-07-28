from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import sys
from statistics import mean
from typing import Any

try:
    from scripts.run_checks import evaluation_passed, git_sha, load_json, run
except ModuleNotFoundError:
    from run_checks import evaluation_passed, git_sha, load_json, run


ROOT = pathlib.Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / "reports" / "lookahead"
AGENT = ROOT / "agent" / "agent.py"
SIMULATOR = ROOT / "simulator"
DEFAULT_CONFIG = SIMULATOR / "configs" / "sample_config.json"
DEFAULT_MODES = ("weighted", "depth2", "pool_resilience")


def load_config(path: pathlib.Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def summarize_evaluation(
    evaluation: Any,
    config: dict[str, Any],
) -> dict[str, Any]:
    cases: dict[str, Any] = {}
    if isinstance(evaluation, dict):
        for case_id, case in evaluation.items():
            if not isinstance(case, dict):
                continue
            task_config = config.get(case_id, {})
            item_list = task_config.get("item_stream", {}).get("item_list", [])
            total_items = len(item_list)
            score = case.get("evaluation") or {}
            placed_fraction = float(score.get("num_placed_items", 0.0))
            place_states = case.get("place_states") or {}
            time_results = case.get("time_results") or {}
            cases[case_id] = {
                "status": case.get("status"),
                "fill_score": float(score.get("fill_score", 0.0)),
                "placed_fraction": placed_fraction,
                "placed_count": int(round(placed_fraction * total_items)),
                "total_items": total_items,
                "is_included": place_states.get("is_included") is True,
                "is_valid": place_states.get("is_valid") is True,
                "is_placed_safe": place_states.get("is_placed_safe") is True,
                "optimization_seconds": float(
                    time_results.get("optimization", 0.0)
                ),
                "policy_seconds": float(time_results.get("policy", 0.0)),
            }

    fill_scores = [case["fill_score"] for case in cases.values()]
    policy_seconds = [case["policy_seconds"] for case in cases.values()]
    return {
        "cases": cases,
        "all_physics_valid": evaluation_passed(evaluation),
        "total_placed_count": sum(
            case["placed_count"] for case in cases.values()
        ),
        "mean_fill_score": mean(fill_scores) if fill_scores else 0.0,
        "max_policy_seconds": max(policy_seconds, default=0.0),
    }


def comparison_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Lookahead sample-simulator comparison",
        "",
        f"- Timestamp: `{payload['timestamp']}`",
        f"- Git SHA: `{payload.get('git_sha') or 'unknown'}`",
        f"- Config: `{payload['config']}`",
        f"- Run ID: `{payload.get('run_id') or 'local'}`",
        "- Scope: bundled simulator proxy; not a SIGNATE leaderboard score",
        "",
        "## Mode summary",
        "",
        "| mode | process | physics | placed total | mean fill | max policy |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for mode, result in payload["modes"].items():
        summary = result["summary"]
        lines.append(
            "| {mode} | {process} | {physics} | {placed} | {fill:.6f} | "
            "{policy:.3f}s |".format(
                mode=mode,
                process=result["process_returncode"],
                physics="PASS" if summary["all_physics_valid"] else "FAIL",
                placed=summary["total_placed_count"],
                fill=summary["mean_fill_score"],
                policy=summary["max_policy_seconds"],
            )
        )

    lines.extend(["", "## Case history", ""])
    for mode, result in payload["modes"].items():
        lines.extend(
            [
                f"### {mode}",
                "",
                "| case | fill | placed | included | valid | safe | optimize | policy |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for case_id, case in result["summary"]["cases"].items():
            lines.append(
                "| {case_id} | {fill:.6f} | {placed}/{total} | {included} | "
                "{valid} | {safe} | {opt:.3f}s | {policy:.3f}s |".format(
                    case_id=case_id,
                    fill=case["fill_score"],
                    placed=case["placed_count"],
                    total=case["total_items"],
                    included=case["is_included"],
                    valid=case["is_valid"],
                    safe=case["is_placed_safe"],
                    opt=case["optimization_seconds"],
                    policy=case["policy_seconds"],
                )
            )
        lines.append("")

    if not all(
        result["summary"]["all_physics_valid"]
        for result in payload["modes"].values()
    ):
        lines.extend(
            [
                "## Interpretation",
                "",
                "At least one mode's physical validity failed. Fill and placed "
                "comparisons are diagnostic history, not a valid competition "
                "result.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## Interpretation",
                "",
                "All compared modes passed inclusion, validity, and placed-safely "
                "checks. Values can be compared as valid bundled-simulator "
                "results, but are not leaderboard scores.",
                "",
            ]
        )
    return "\n".join(lines)


def run_mode(
    mode: str,
    config_path: pathlib.Path,
    run_dir: pathlib.Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    mode_dir = run_dir / mode
    mode_dir.mkdir(parents=True, exist_ok=True)
    result_path = mode_dir / "evaluation_results.json"
    env = os.environ.copy()
    env["LOOKAHEAD_SELECTION_MODE"] = mode
    env["PYTHONPATH"] = str(SIMULATOR)
    result = run(
        [
            sys.executable,
            "scripts/run_test.py",
            "--config-path",
            str(config_path.resolve()),
            "--module-path",
            "",
            "--result-dir",
            str(mode_dir.resolve()),
            "--result-fname",
            result_path.name,
        ],
        SIMULATOR,
        env,
    )
    evaluation = load_json(result_path)
    (mode_dir / "simulator.log").write_text(
        result["stdout"] + result["stderr"],
        encoding="utf-8",
    )
    return {
        "process_returncode": result["returncode"],
        "process_seconds": result["seconds"],
        "summary": summarize_evaluation(evaluation, config),
        "evaluation_path": str(result_path.relative_to(ROOT)),
        "log_path": str((mode_dir / "simulator.log").relative_to(ROOT)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=pathlib.Path,
        default=DEFAULT_CONFIG,
    )
    parser.add_argument(
        "--modes",
        nargs="+",
        default=list(DEFAULT_MODES),
    )
    parser.add_argument("--run-id")
    args = parser.parse_args()

    timestamp = dt.datetime.now(dt.timezone.utc).astimezone()
    run_id = args.run_id or timestamp.strftime("%Y%m%d_%H%M%S")
    run_dir = REPORT_ROOT / "history" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(AGENT, SIMULATOR / "agent.py")
    config = load_config(args.config)

    payload: dict[str, Any] = {
        "timestamp": timestamp.isoformat(timespec="seconds"),
        "git_sha": git_sha(),
        "config": str(args.config),
        "run_id": run_id,
        "modes": {},
    }
    for mode in args.modes:
        payload["modes"][mode] = run_mode(
            mode,
            args.config,
            run_dir,
            config,
        )

    markdown = comparison_markdown(payload)
    summary_json = json.dumps(payload, ensure_ascii=False, indent=2)
    (run_dir / "summary.json").write_text(summary_json, encoding="utf-8")
    (run_dir / "summary.md").write_text(markdown, encoding="utf-8")
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    (REPORT_ROOT / "latest-summary.json").write_text(
        summary_json,
        encoding="utf-8",
    )
    (REPORT_ROOT / "latest-summary.md").write_text(
        markdown,
        encoding="utf-8",
    )

    print(REPORT_ROOT / "latest-summary.md")
    processes_ok = all(
        result["process_returncode"] == 0
        for result in payload["modes"].values()
    )
    return 0 if processes_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
