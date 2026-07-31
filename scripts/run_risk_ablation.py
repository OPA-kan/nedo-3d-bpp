"""
Online risk ablation: does Q - lambda*P_hat raise placed/fill?

Runs one full simulator episode for a task-b config under one arm
(risk off, or live mechanics rerank at a given lambda) and appends a
result row; --summarize aggregates all rows collected so far into
per-arm and per-config-paired tables. Rows accumulate across
invocations, so repeats can be added incrementally and scheduled with
run_queue.

Constraints (docs/RELEASE_RISK_PROTOCOL.md section 8): development
configurations only -- final_holdout cases (b001-k40, b001-k10) are
refused; the submission default stays risk-off.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_checks import load_json, run  # noqa: E402

SIMULATOR = ROOT / "simulator"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "risk-ablation"
FINAL_HOLDOUT_CASES = frozenset({"b001-k40", "b001-k10"})


def case_summary(
    evaluation: Any, config: dict[str, Any]
) -> dict[str, Any]:
    cases = {}
    if not isinstance(evaluation, dict):
        return cases
    for case_id, case in evaluation.items():
        if not isinstance(case, dict):
            continue
        item_list = (
            config.get(case_id, {})
            .get("item_stream", {})
            .get("item_list", [])
        )
        score = case.get("evaluation") or {}
        place_states = case.get("place_states") or {}
        placed_fraction = float(score.get("num_placed_items", 0.0))
        steps = score.get("step_metrics") or []
        cases[case_id] = {
            "status": case.get("status"),
            "fill_score": float(score.get("fill_score", 0.0)),
            "placed_fraction": placed_fraction,
            "placed_count": int(round(placed_fraction * len(item_list))),
            "total_items": len(item_list),
            "steps": len(steps),
            "is_placed_safe": place_states.get("is_placed_safe") is True,
            "policy_seconds": float(
                (case.get("time_results") or {}).get("policy", 0.0)
            ),
        }
    return cases


def run_episode(
    config_path: pathlib.Path,
    arm: str,
    risk_lambda: float,
    repeat: int,
    output_dir: pathlib.Path,
) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    case_ids = list(config)
    holdout = FINAL_HOLDOUT_CASES.intersection(case_ids)
    if holdout:
        raise SystemExit(
            f"refusing to run online ablation on final_holdout cases: "
            f"{sorted(holdout)} (protocol section 8)"
        )

    label = f"{'-'.join(case_ids)}-{arm}-r{repeat}"
    run_dir = output_dir / "runs" / label
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = run_dir / "evaluation_results.json"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(SIMULATOR)
    if arm == "off":
        env.pop("RELEASE_RISK_LIVE_RERANK", None)
    else:
        env["RELEASE_RISK_LIVE_RERANK"] = "1"
        env["RELEASE_RISK_P_MODEL"] = "mech"
        env["RELEASE_RISK_RERANK_LAMBDA"] = str(risk_lambda)
    # Ablation runs never do shadow reranking: it is suppressed under
    # live rerank anyway, and the off arm should match the submission
    # default exactly.
    env.pop("RELEASE_RISK_SHADOW_RERANK", None)

    result = run(
        [
            sys.executable,
            "scripts/run_test.py",
            "--config-path",
            str(config_path.resolve()),
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
    evaluation = load_json(result_path)
    row = {
        "label": label,
        "arm": arm,
        "risk_lambda": risk_lambda if arm != "off" else None,
        "repeat": repeat,
        "config": config_path.name,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(
            timespec="seconds"
        ),
        "process_returncode": result["returncode"],
        "process_seconds": result["seconds"],
        "cases": case_summary(evaluation, config),
    }
    rows_path = output_dir / "rows.jsonl"
    with rows_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def load_rows(output_dir: pathlib.Path) -> list[dict[str, Any]]:
    rows_path = output_dir / "rows.jsonl"
    if not rows_path.exists():
        return []
    rows = []
    with rows_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    per_arm: dict[str, dict[str, list[float]]] = {}
    per_case_arm: dict[tuple[str, str], dict[str, list[float]]] = {}
    for row in rows:
        if row["process_returncode"] != 0:
            continue
        for case_id, case in row["cases"].items():
            arm_bucket = per_arm.setdefault(
                row["arm"], {"placed": [], "fill": [], "steps": []}
            )
            arm_bucket["placed"].append(case["placed_count"])
            arm_bucket["fill"].append(case["fill_score"])
            arm_bucket["steps"].append(case["steps"])
            case_bucket = per_case_arm.setdefault(
                (case_id, row["arm"]),
                {"placed": [], "fill": []},
            )
            case_bucket["placed"].append(case["placed_count"])
            case_bucket["fill"].append(case["fill_score"])

    def stats(values: list[float]) -> dict[str, float]:
        if not values:
            return {"n": 0}
        mean = sum(values) / len(values)
        return {
            "n": len(values),
            "mean": round(mean, 3),
            "min": min(values),
            "max": max(values),
        }

    arms = {
        arm: {metric: stats(vals) for metric, vals in buckets.items()}
        for arm, buckets in per_arm.items()
    }
    cases: dict[str, Any] = {}
    for (case_id, arm), buckets in sorted(per_case_arm.items()):
        cases.setdefault(case_id, {})[arm] = {
            metric: stats(vals) for metric, vals in buckets.items()
        }
    paired = {}
    for case_id, arm_stats in cases.items():
        off = arm_stats.get("off")
        for arm, arm_stat in arm_stats.items():
            if arm == "off" or not off or off["placed"]["n"] == 0:
                continue
            if arm_stat["placed"]["n"] == 0:
                continue
            paired.setdefault(arm, {})[case_id] = {
                "placed_diff": round(
                    arm_stat["placed"]["mean"] - off["placed"]["mean"], 3
                ),
                "fill_diff": round(
                    arm_stat["fill"]["mean"] - off["fill"]["mean"], 3
                ),
            }
    return {"arms": arms, "cases": cases, "paired_vs_off": paired}


def render_markdown(summary: dict[str, Any], rows: int) -> str:
    lines = [
        "# Online risk ablation (development configurations only)",
        "",
        f"- episode rows: {rows}; arms compare the submission-default "
        "baseline (off) with live mechanics rerank "
        "(RELEASE_RISK_LIVE_RERANK=1, RELEASE_RISK_P_MODEL=mech).",
        "",
        "## Per arm",
        "",
        "| arm | episodes | placed mean | fill mean | steps mean |",
        "|---|---:|---:|---:|---:|",
    ]
    for arm, stats in sorted(summary["arms"].items()):
        lines.append(
            f"| {arm} | {stats['placed']['n']} "
            f"| {stats['placed'].get('mean', '-')} "
            f"| {stats['fill'].get('mean', '-')} "
            f"| {stats['steps'].get('mean', '-')} |"
        )
    lines += [
        "",
        "## Paired per-case difference vs off",
        "",
        "| arm | case | placed diff | fill diff |",
        "|---|---|---:|---:|",
    ]
    for arm, cases in sorted(summary["paired_vs_off"].items()):
        for case_id, diff in sorted(cases.items()):
            lines.append(
                f"| {arm} | {case_id} | {diff['placed_diff']} "
                f"| {diff['fill_diff']} |"
            )
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=pathlib.Path)
    parser.add_argument("--arm", default="off")
    parser.add_argument("--risk-lambda", type=float, default=2.0)
    parser.add_argument("--repeat", type=int, default=0)
    parser.add_argument(
        "--output-dir", type=pathlib.Path, default=DEFAULT_OUTPUT_DIR
    )
    parser.add_argument(
        "--summarize",
        action="store_true",
        help="Aggregate rows.jsonl into summary.md/json and exit.",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.summarize:
        rows = load_rows(args.output_dir)
        summary = summarize(rows)
        (args.output_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        markdown = render_markdown(summary, len(rows))
        (args.output_dir / "summary.md").write_text(
            markdown, encoding="utf-8"
        )
        print(args.output_dir / "summary.md")
        return 0

    if args.config is None:
        raise SystemExit("--config is required unless --summarize")
    row = run_episode(
        args.config,
        args.arm,
        args.risk_lambda,
        args.repeat,
        args.output_dir,
    )
    print(json.dumps({k: row[k] for k in ("label", "cases")}, indent=1))
    return 0 if row["process_returncode"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
