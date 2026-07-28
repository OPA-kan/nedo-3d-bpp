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


def load_policy_trace(
    path: pathlib.Path,
    case_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    by_case = {case_id: [] for case_id in case_ids}
    if not path.exists():
        return by_case
    case_iterator = iter(case_ids)
    current_case = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("event") == "init":
            current_case = next(case_iterator, None)
        elif event.get("event") == "decision" and current_case is not None:
            by_case[current_case].append(event)
    return by_case


def _mean_or_zero(values: list[float]) -> float:
    return mean(values) if values else 0.0


def summarize_evaluation(
    evaluation: Any,
    config: dict[str, Any],
    policy_trace: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    cases: dict[str, Any] = {}
    policy_trace = policy_trace or {}
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
            raw_metrics = score.get("step_metrics") or []
            policy_events = policy_trace.get(case_id, [])
            metric_history = []
            for index, metric in enumerate(raw_metrics):
                row = dict(metric)
                if index < len(policy_events):
                    event = policy_events[index]
                    row["predicted_feasible_remaining_items"] = event.get(
                        "feasible_remaining_items"
                    )
                    row["predicted_evaluated_remaining_items"] = event.get(
                        "evaluated_remaining_items"
                    )
                    row["predicted_feasible_remaining_ratio"] = event.get(
                        "feasible_remaining_ratio"
                    )
                    row["agent_immediate_score"] = event.get(
                        "immediate_score"
                    )
                    row["action_source"] = event.get("action_source")
                    row["candidate_kind"] = event.get("candidate_kind")
                    row["candidate_diagnostics"] = event.get(
                        "candidate_diagnostics"
                    )
                metric_history.append(row)
            final_metrics = metric_history[-1] if metric_history else {}
            feasible_ratios = [
                float(row["predicted_feasible_remaining_ratio"])
                for row in metric_history
                if row.get("predicted_feasible_remaining_ratio") is not None
            ]
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
                "final_placed_volume": float(
                    final_metrics.get("placed_volume", 0.0)
                ),
                "final_center_of_mass_z": float(
                    final_metrics.get("center_of_mass_z", 0.0)
                ),
                "final_surface_total_variation": float(
                    final_metrics.get("surface_total_variation", 0.0)
                ),
                "final_surface_height_std": float(
                    final_metrics.get("surface_height_std", 0.0)
                ),
                "final_flat_support_edge_ratio": float(
                    final_metrics.get("flat_support_edge_ratio", 0.0)
                ),
                "final_remaining_volume_ratio": float(
                    final_metrics.get("remaining_volume_ratio", 0.0)
                ),
                "final_occupied_depth_center_normalized": float(
                    final_metrics.get(
                        "occupied_depth_center_normalized",
                        0.0,
                    )
                ),
                "final_front_depth_occupancy_mean": float(
                    final_metrics.get("front_depth_occupancy_mean", 0.0)
                ),
                "final_back_depth_occupancy_mean": float(
                    final_metrics.get("back_depth_occupancy_mean", 0.0)
                ),
                "mean_predicted_feasible_remaining_ratio": (
                    _mean_or_zero(feasible_ratios)
                ),
                "predicted_feasible_observation_count": len(
                    feasible_ratios
                ),
                "metric_history": metric_history,
            }

    fill_scores = [case["fill_score"] for case in cases.values()]
    policy_seconds = [case["policy_seconds"] for case in cases.values()]
    feasible_ratios = [
        case["mean_predicted_feasible_remaining_ratio"]
        for case in cases.values()
        if case["predicted_feasible_observation_count"] > 0
    ]
    return {
        "cases": cases,
        "all_physics_valid": evaluation_passed(evaluation),
        "total_placed_count": sum(
            case["placed_count"] for case in cases.values()
        ),
        "mean_fill_score": mean(fill_scores) if fill_scores else 0.0,
        "max_policy_seconds": max(policy_seconds, default=0.0),
        "mean_predicted_feasible_remaining_ratio": _mean_or_zero(
            feasible_ratios
        ),
        "mean_final_center_of_mass_z": _mean_or_zero(
            [case["final_center_of_mass_z"] for case in cases.values()]
        ),
        "mean_final_surface_total_variation": _mean_or_zero(
            [
                case["final_surface_total_variation"]
                for case in cases.values()
            ]
        ),
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
        "| mode | process | physics | placed | mean fill | residual feasible | "
        "CoG z | surface TV | max policy |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for mode, result in payload["modes"].items():
        summary = result["summary"]
        lines.append(
            "| {mode} | {process} | {physics} | {placed} | {fill:.6f} | "
            "{feasible:.3f} | {cog:.3f} | {surface:.4f} | "
            "{policy:.3f}s |".format(
                mode=mode,
                process=result["process_returncode"],
                physics="PASS" if summary["all_physics_valid"] else "FAIL",
                placed=summary["total_placed_count"],
                fill=summary["mean_fill_score"],
                feasible=summary["mean_predicted_feasible_remaining_ratio"],
                cog=summary["mean_final_center_of_mass_z"],
                surface=summary["mean_final_surface_total_variation"],
                policy=summary["max_policy_seconds"],
            )
        )

    lines.extend(["", "## Case history", ""])
    for mode, result in payload["modes"].items():
        lines.extend(
            [
                f"### {mode}",
                "",
                "| case | fill | placed | volume | residual feasible | CoG z | "
                "surface TV | valid | safe |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for case_id, case in result["summary"]["cases"].items():
            feasible_text = (
                "-"
                if case.get("predicted_feasible_observation_count", 0) == 0
                else "{:.3f}".format(
                    case.get(
                        "mean_predicted_feasible_remaining_ratio",
                        0.0,
                    )
                )
            )
            lines.append(
                "| {case_id} | {fill:.6f} | {placed}/{total} | {volume:.4f} | "
                "{feasible} | {cog:.3f} | {surface:.4f} | "
                "{valid} | {safe} |".format(
                    case_id=case_id,
                    fill=case["fill_score"],
                    placed=case["placed_count"],
                    total=case["total_items"],
                    volume=case.get("final_placed_volume", 0.0),
                    feasible=feasible_text,
                    cog=case.get("final_center_of_mass_z", 0.0),
                    surface=case.get(
                        "final_surface_total_variation",
                        0.0,
                    ),
                    valid=case["is_valid"],
                    safe=case["is_placed_safe"],
                )
            )
        lines.append("")
        for case_id, case in result["summary"]["cases"].items():
            lines.extend(
                [
                    f"#### {mode} / {case_id} per-step diagnostics",
                    "",
                    "| step | placed | volume | empty ratio | residual feasible | "
                    "CoG z | depth center | front/back | kind | settle d/angle | "
                    "top rejection | physical |",
                    "|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|",
                ]
            )
            for row in case.get("metric_history", []):
                status = row.get("status") or {}
                physical = (
                    "PASS"
                    if all(
                        status.get(name) is True
                        for name in (
                            "is_included",
                            "is_valid",
                            "is_placed_safe",
                        )
                    )
                    else "FAIL"
                )
                feasible = row.get("predicted_feasible_remaining_ratio")
                feasible_text = (
                    "-"
                    if feasible is None
                    else f"{float(feasible):.3f}"
                )
                candidate_diagnostics = (
                    row.get("candidate_diagnostics") or {}
                )
                rejection_counts = (
                    candidate_diagnostics.get("total", {}).get(
                        "rejected",
                        {},
                    )
                )
                dominant_rejection = "-"
                dominant_count = 0
                if rejection_counts:
                    reason, count = max(
                        rejection_counts.items(),
                        key=lambda entry: entry[1],
                    )
                    if count:
                        dominant_rejection = f"{reason}:{count}"
                        dominant_count = int(count)
                envelope_pruned = int(
                    candidate_diagnostics.get("total", {}).get(
                        "envelope_pruned",
                        0,
                    )
                )
                if envelope_pruned > dominant_count:
                    dominant_rejection = f"envelope:{envelope_pruned}"
                settle_displacement = row.get("settle_displacement_norm")
                settle_angle = row.get("settle_angle_deg")
                settle_text = (
                    "-"
                    if settle_displacement is None or settle_angle is None
                    else (
                        f"{float(settle_displacement):.3f}m/"
                        f"{float(settle_angle):.1f}deg"
                    )
                )
                lines.append(
                    "| {step} | {placed} | {volume:.4f} | {empty:.3f} | "
                    "{feasible} | {cog:.3f} | {depth:.3f} | "
                    "{front:.3f}/{back:.3f} | {kind} | {settle} | {rejection} | "
                    "{physical} |".format(
                        step=row.get("step", 0),
                        placed=row.get("placed_count", 0),
                        volume=float(row.get("placed_volume", 0.0)),
                        empty=float(row.get("remaining_volume_ratio", 0.0)),
                        feasible=feasible_text,
                        cog=float(row.get("center_of_mass_z", 0.0)),
                        depth=float(
                            row.get(
                                "occupied_depth_center_normalized",
                                0.0,
                            )
                        ),
                        front=float(
                            row.get("front_depth_occupancy_mean", 0.0)
                        ),
                        back=float(
                            row.get("back_depth_occupancy_mean", 0.0)
                        ),
                        kind=row.get("candidate_kind") or "-",
                        settle=settle_text,
                        rejection=dominant_rejection,
                        physical=physical,
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
    trace_path = mode_dir / "agent_policy_trace.jsonl"
    if trace_path.exists():
        trace_path.unlink()
    env = os.environ.copy()
    env["LOOKAHEAD_SELECTION_MODE"] = mode
    env["NEDO_POLICY_TRACE_PATH"] = str(trace_path.resolve())
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
    policy_trace = load_policy_trace(trace_path, list(config))
    (mode_dir / "simulator.log").write_text(
        result["stdout"] + result["stderr"],
        encoding="utf-8",
    )
    return {
        "process_returncode": result["returncode"],
        "process_seconds": result["seconds"],
        "summary": summarize_evaluation(
            evaluation,
            config,
            policy_trace=policy_trace,
        ),
        "evaluation_path": str(result_path.relative_to(ROOT)),
        "log_path": str((mode_dir / "simulator.log").relative_to(ROOT)),
        "policy_trace_path": str(trace_path.relative_to(ROOT)),
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
