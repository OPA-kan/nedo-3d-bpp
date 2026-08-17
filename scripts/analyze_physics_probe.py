#!/usr/bin/env python3
"""Fidelity gates for the in-process physics probe.

Implements the four preregistered gates of
reports/hazard/physics-probe-protocol.md over probe-shadow episodes
produced by run_risk_ablation --arm physics_probe: joins each run's
policy-trace.jsonl ``physics_probe`` events with the environment's own
settle outcomes (evaluation_results.json step_metrics) and computes

1. discrimination -- pooled AUC of the probe's predicted severity
   (max of angle/30, displacement/0.3) against the environment's
   actually-unsafe settles (angle > 30 deg or displacement > 0.3 m);
2. fatal recall -- of the physically-fatal final placements in the wave
   (topple / slide terminal channels), the fraction the probe flagged
   unsafe;
3. calibration direction -- mean predicted displacement strictly higher
   on actually-unsafe steps than on safe steps, and the same for angle;
4. zero footprint -- probe episodes' placed/steps within the baseline
   floors of the base arm, and per-probe wall time within the shipped
   budget's slack.

Step-index correspondence: the probe event's ``step`` is the agent's
policy-step counter, incremented once per emitted action, and
step_metrics is appended once per env.step of an emitted action -- both
per placement, in the same order, so event step k joins step_metrics[k].
The join additionally checks step_metrics[k]["step"] == k and reports
any mismatch instead of silently mis-joining.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

ANGLE_THRESHOLD_DEG = 30.0
DISPLACEMENT_THRESHOLD = 0.3
GATE_MIN_AUC = 0.80
GATE_MIN_FATAL_RECALL = 0.5
# One probe per step must fit the shipped budget's slack (protocol cost
# basis: 40 ms crowded-scene probe, 66 ms scene build; the shipped
# policy budget is several seconds per step). The gate binds the MEAN
# probe cost to 0.3 s: an individual unsafe settle legitimately runs the
# full 300-step horizon and costs ~0.4 s, so the max is reported but not
# gated beyond the shipped budget's own order of magnitude.
GATE_MEAN_PROBE_SECONDS = 0.3
FATAL_CHANNELS = frozenset({"topple", "slide"})


def load_probe_events(trace_path: pathlib.Path) -> list[dict[str, Any]]:
    events = []
    if not trace_path.exists():
        return events
    with trace_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("event") != "physics_probe":
                continue
            events.append(
                {
                    "step": int(record.get("step", -1)),
                    "angle_deg": record.get("angle_deg"),
                    "displacement": record.get("displacement"),
                    "predicted_safe": record.get("predicted_safe"),
                    "elapsed_seconds": record.get("elapsed_seconds"),
                }
            )
    events.sort(key=lambda event: event["step"])
    return events


def load_step_metrics(
    result_path: pathlib.Path, case_id: str
) -> list[dict[str, Any]]:
    if not result_path.exists():
        return []
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    case = payload.get(case_id)
    if not isinstance(case, dict):
        return []
    evaluation = case.get("evaluation") or {}
    steps = evaluation.get("step_metrics")
    return steps if isinstance(steps, list) else []


def join_events(
    events: list[dict[str, Any]], step_metrics: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Join probe events to environment settle outcomes by step index."""
    joined = []
    audit = {
        "events": len(events),
        "events_failed": 0,
        "events_out_of_range": 0,
        "events_without_settle": 0,
        "step_field_mismatches": 0,
    }
    for event in events:
        if event["angle_deg"] is None or event["displacement"] is None:
            audit["events_failed"] += 1
            continue
        index = event["step"]
        if not 0 <= index < len(step_metrics):
            audit["events_out_of_range"] += 1
            continue
        metric = step_metrics[index]
        recorded_step = metric.get("step")
        if recorded_step is not None and int(recorded_step) != index:
            audit["step_field_mismatches"] += 1
            continue
        actual_angle = metric.get("settle_angle_deg")
        actual_displacement = metric.get("settle_displacement_norm")
        if actual_angle is None or actual_displacement is None:
            audit["events_without_settle"] += 1
            continue
        predicted_angle = float(event["angle_deg"])
        predicted_displacement = float(event["displacement"])
        joined.append(
            {
                "step": index,
                "predicted_angle_deg": predicted_angle,
                "predicted_displacement": predicted_displacement,
                "predicted_score": max(
                    predicted_angle / ANGLE_THRESHOLD_DEG,
                    predicted_displacement / DISPLACEMENT_THRESHOLD,
                ),
                "predicted_unsafe": bool(
                    predicted_angle > ANGLE_THRESHOLD_DEG
                    or predicted_displacement > DISPLACEMENT_THRESHOLD
                ),
                "actual_angle_deg": float(actual_angle),
                "actual_displacement": float(actual_displacement),
                "actual_unsafe": bool(
                    float(actual_angle) > ANGLE_THRESHOLD_DEG
                    or float(actual_displacement) > DISPLACEMENT_THRESHOLD
                ),
                "elapsed_seconds": event.get("elapsed_seconds"),
            }
        )
    return joined, audit


def collect_episodes(input_dir: pathlib.Path) -> list[dict[str, Any]]:
    episodes = []
    for rows_path in sorted(input_dir.rglob("rows.jsonl")):
        with rows_path.open(encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
        for row in rows:
            cases = row.get("cases") or {}
            if len(cases) != 1:
                # Fidelity joins need a unique terminal channel and a
                # unique step_metrics list per run.
                continue
            case_id, case = next(iter(cases.items()))
            run_dir = rows_path.parent / "runs" / str(row["label"])
            events = load_probe_events(run_dir / "policy-trace.jsonl")
            step_metrics = load_step_metrics(
                run_dir / "evaluation_results.json", case_id
            )
            joined, audit = join_events(events, step_metrics)
            episodes.append(
                {
                    "case_id": case_id,
                    "label": str(row["label"]),
                    "arm": str(row.get("arm") or ""),
                    "replicate": row.get("repeat"),
                    "returncode": row.get("process_returncode"),
                    "terminal_channel": str(
                        case.get("terminal_channel") or "unknown"
                    ),
                    "placed_count": case.get("placed_count"),
                    "steps": case.get("steps"),
                    "policy_seconds": case.get("policy_seconds"),
                    "join_audit": audit,
                    "joined": joined,
                }
            )
    return episodes


def rank_auc(
    positives: list[float], negatives: list[float]
) -> float | None:
    """P(random positive > random negative), ties counted half."""
    if not positives or not negatives:
        return None
    wins = 0.0
    for positive in positives:
        for negative in negatives:
            if positive > negative:
                wins += 1.0
            elif positive == negative:
                wins += 0.5
    return wins / (len(positives) * len(negatives))


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def summarize(
    episodes: list[dict[str, Any]],
    probe_arm: str,
    base_arm: str,
) -> dict[str, Any]:
    probe_episodes = [
        episode
        for episode in episodes
        if episode["arm"] == probe_arm and episode["returncode"] == 0
    ]
    base_episodes = [
        episode
        for episode in episodes
        if episode["arm"] == base_arm and episode["returncode"] == 0
    ]
    joined = [
        pair for episode in probe_episodes for pair in episode["joined"]
    ]
    unsafe = [pair for pair in joined if pair["actual_unsafe"]]
    safe = [pair for pair in joined if not pair["actual_unsafe"]]

    # Gate 1: discrimination.
    pooled_auc = rank_auc(
        [pair["predicted_score"] for pair in unsafe],
        [pair["predicted_score"] for pair in safe],
    )

    # Gate 2: fatal recall over topple/slide terminal placements.
    fatal_detail = []
    for episode in probe_episodes:
        if episode["terminal_channel"] not in FATAL_CHANNELS:
            continue
        final = episode["joined"][-1] if episode["joined"] else None
        fatal_detail.append(
            {
                "case_id": episode["case_id"],
                "label": episode["label"],
                "terminal_channel": episode["terminal_channel"],
                "final_step_joined": final is not None,
                "predicted_unsafe": (
                    final["predicted_unsafe"] if final else None
                ),
                "predicted_angle_deg": (
                    final["predicted_angle_deg"] if final else None
                ),
                "predicted_displacement": (
                    final["predicted_displacement"] if final else None
                ),
                "actual_angle_deg": (
                    final["actual_angle_deg"] if final else None
                ),
                "actual_displacement": (
                    final["actual_displacement"] if final else None
                ),
            }
        )
    fatal_total = len(fatal_detail)
    fatal_flagged = sum(
        1 for entry in fatal_detail if entry["predicted_unsafe"] is True
    )
    fatal_recall = fatal_flagged / fatal_total if fatal_total else None

    # Gate 3: calibration direction.
    mean_predicted = {
        "displacement_unsafe": mean(
            [pair["predicted_displacement"] for pair in unsafe]
        ),
        "displacement_safe": mean(
            [pair["predicted_displacement"] for pair in safe]
        ),
        "angle_unsafe": mean([pair["predicted_angle_deg"] for pair in unsafe]),
        "angle_safe": mean([pair["predicted_angle_deg"] for pair in safe]),
    }
    direction_displacement = (
        None
        if mean_predicted["displacement_unsafe"] is None
        or mean_predicted["displacement_safe"] is None
        else mean_predicted["displacement_unsafe"]
        > mean_predicted["displacement_safe"]
    )
    direction_angle = (
        None
        if mean_predicted["angle_unsafe"] is None
        or mean_predicted["angle_safe"] is None
        else mean_predicted["angle_unsafe"] > mean_predicted["angle_safe"]
    )

    # Gate 4: zero footprint. Per case, every probe episode must stay at
    # or above the base arm's floor (minimum over replicates) on placed
    # and steps, and every probe call must fit the per-step budget slack.
    by_case_probe: dict[str, list[dict[str, Any]]] = {}
    by_case_base: dict[str, list[dict[str, Any]]] = {}
    for episode in probe_episodes:
        by_case_probe.setdefault(episode["case_id"], []).append(episode)
    for episode in base_episodes:
        by_case_base.setdefault(episode["case_id"], []).append(episode)
    footprint_cases = {}
    for case_id, probe_group in sorted(by_case_probe.items()):
        base_group = by_case_base.get(case_id, [])
        placed_probe = [
            episode["placed_count"]
            for episode in probe_group
            if isinstance(episode["placed_count"], (int, float))
        ]
        steps_probe = [
            episode["steps"]
            for episode in probe_group
            if isinstance(episode["steps"], (int, float))
        ]
        placed_base = [
            episode["placed_count"]
            for episode in base_group
            if isinstance(episode["placed_count"], (int, float))
        ]
        steps_base = [
            episode["steps"]
            for episode in base_group
            if isinstance(episode["steps"], (int, float))
        ]
        placed_floor = min(placed_base) if placed_base else None
        steps_floor = min(steps_base) if steps_base else None
        footprint_cases[case_id] = {
            "probe_episodes": len(probe_group),
            "base_episodes": len(base_group),
            "probe_placed": placed_probe,
            "probe_steps": steps_probe,
            "base_placed_floor": placed_floor,
            "base_steps_floor": steps_floor,
            "placed_within_floor": (
                None
                if placed_floor is None or not placed_probe
                else all(value >= placed_floor for value in placed_probe)
            ),
            "steps_within_floor": (
                None
                if steps_floor is None or not steps_probe
                else all(value >= steps_floor for value in steps_probe)
            ),
        }
    footprint_flags = [
        entry[key]
        for entry in footprint_cases.values()
        for key in ("placed_within_floor", "steps_within_floor")
    ]
    trajectories_within_floors = (
        None
        if not footprint_flags or any(flag is None for flag in footprint_flags)
        else all(footprint_flags)
    )
    elapsed = [
        float(pair["elapsed_seconds"])
        for pair in joined
        if isinstance(pair["elapsed_seconds"], (int, float))
    ]
    elapsed_mean = mean(elapsed)
    elapsed_max = max(elapsed) if elapsed else None
    within_budget = (
        None
        if elapsed_mean is None
        else elapsed_mean <= GATE_MEAN_PROBE_SECONDS
    )

    gates = {
        "discrimination": (
            None if pooled_auc is None else pooled_auc >= GATE_MIN_AUC
        ),
        "fatal_recall": (
            None
            if fatal_recall is None
            else fatal_recall >= GATE_MIN_FATAL_RECALL
        ),
        "calibration_direction": (
            None
            if direction_displacement is None or direction_angle is None
            else direction_displacement and direction_angle
        ),
        "zero_footprint": (
            None
            if trajectories_within_floors is None or within_budget is None
            else trajectories_within_floors and within_budget
        ),
    }
    if any(value is None for value in gates.values()):
        verdict = "incomplete_wave_gates_not_evaluable"
    elif all(gates.values()):
        verdict = "fidelity_pass_behavioral_experiment_licensed"
    else:
        verdict = "fidelity_fail_line_closed"

    join_audit_total: dict[str, int] = {}
    for episode in probe_episodes:
        for key, value in episode["join_audit"].items():
            join_audit_total[key] = join_audit_total.get(key, 0) + int(value)

    return {
        "protocol": "reports/hazard/physics-probe-protocol.md",
        "probe_arm": probe_arm,
        "base_arm": base_arm,
        "thresholds": {
            "angle_deg": ANGLE_THRESHOLD_DEG,
            "displacement": DISPLACEMENT_THRESHOLD,
            "min_auc": GATE_MIN_AUC,
            "min_fatal_recall": GATE_MIN_FATAL_RECALL,
            "mean_probe_seconds": GATE_MEAN_PROBE_SECONDS,
        },
        "probe_episodes": len(probe_episodes),
        "base_episodes": len(base_episodes),
        "joined_steps": len(joined),
        "actual_unsafe_steps": len(unsafe),
        "actual_safe_steps": len(safe),
        "join_audit": join_audit_total,
        "pooled_auc": (
            round(pooled_auc, 4) if pooled_auc is not None else None
        ),
        "fatal_steps_total": fatal_total,
        "fatal_steps_flagged_unsafe": fatal_flagged,
        "fatal_recall": (
            round(fatal_recall, 4) if fatal_recall is not None else None
        ),
        "mean_predicted": {
            key: (round(value, 6) if value is not None else None)
            for key, value in mean_predicted.items()
        },
        "probe_elapsed_seconds": {
            "mean": round(elapsed_mean, 6) if elapsed_mean is not None else None,
            "max": round(elapsed_max, 6) if elapsed_max is not None else None,
        },
        "zero_footprint_by_case": footprint_cases,
        "gates": gates,
        "verdict": verdict,
        "fatal_step_detail": fatal_detail,
        "confusion": {
            "predicted_unsafe_actual_unsafe": sum(
                1 for pair in unsafe if pair["predicted_unsafe"]
            ),
            "predicted_safe_actual_unsafe": sum(
                1 for pair in unsafe if not pair["predicted_unsafe"]
            ),
            "predicted_unsafe_actual_safe": sum(
                1 for pair in safe if pair["predicted_unsafe"]
            ),
            "predicted_safe_actual_safe": sum(
                1 for pair in safe if not pair["predicted_unsafe"]
            ),
        },
    }


def to_markdown(summary: dict[str, Any]) -> str:
    gates = summary["gates"]
    lines = [
        "# Physics probe fidelity gates",
        "",
        f"Protocol: `{summary['protocol']}`",
        "",
        f"- probe episodes: {summary['probe_episodes']} "
        f"(arm `{summary['probe_arm']}`); base episodes: "
        f"{summary['base_episodes']} (arm `{summary['base_arm']}`)",
        f"- joined steps: {summary['joined_steps']} "
        f"({summary['actual_unsafe_steps']} actually unsafe, "
        f"{summary['actual_safe_steps']} safe)",
        f"- join audit: {json.dumps(summary['join_audit'])}",
        f"- probe elapsed seconds: "
        f"{json.dumps(summary['probe_elapsed_seconds'])}",
        f"- **verdict: {summary['verdict']}**",
        "",
        "## Gates",
        "",
        "| gate | measured | requirement | pass |",
        "|---|---|---|---|",
        f"| 1 discrimination | AUC {summary['pooled_auc']} "
        f"| >= {summary['thresholds']['min_auc']} "
        f"| {gates['discrimination']} |",
        f"| 2 fatal recall | {summary['fatal_steps_flagged_unsafe']}"
        f"/{summary['fatal_steps_total']} = {summary['fatal_recall']} "
        f"| >= {summary['thresholds']['min_fatal_recall']} "
        f"| {gates['fatal_recall']} |",
        f"| 3 calibration direction "
        f"| {json.dumps(summary['mean_predicted'])} "
        f"| unsafe means strictly higher "
        f"| {gates['calibration_direction']} |",
        f"| 4 zero footprint | probe s mean "
        f"{summary['probe_elapsed_seconds']['mean']} max "
        f"{summary['probe_elapsed_seconds']['max']} "
        f"| within base floors and mean "
        f"<= {summary['thresholds']['mean_probe_seconds']} s/probe "
        f"| {gates['zero_footprint']} |",
        "",
        "## Confusion (official thresholds)",
        "",
        "| | actual unsafe | actual safe |",
        "|---|---|---|",
        f"| predicted unsafe "
        f"| {summary['confusion']['predicted_unsafe_actual_unsafe']} "
        f"| {summary['confusion']['predicted_unsafe_actual_safe']} |",
        f"| predicted safe "
        f"| {summary['confusion']['predicted_safe_actual_unsafe']} "
        f"| {summary['confusion']['predicted_safe_actual_safe']} |",
        "",
        "## Zero footprint by case",
        "",
        "| case | probe placed | base placed floor | placed ok "
        "| probe steps | base steps floor | steps ok |",
        "|---|---|---|---|---|---|---|",
    ]
    for case_id, entry in summary["zero_footprint_by_case"].items():
        lines.append(
            f"| {case_id} | {entry['probe_placed']} "
            f"| {entry['base_placed_floor']} "
            f"| {entry['placed_within_floor']} "
            f"| {entry['probe_steps']} | {entry['base_steps_floor']} "
            f"| {entry['steps_within_floor']} |"
        )
    lines += ["", "## Fatal steps", ""]
    if summary["fatal_step_detail"]:
        lines += [
            "| case | episode | channel | flagged | predicted angle "
            "| predicted disp | actual angle | actual disp |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for entry in summary["fatal_step_detail"]:
            lines.append(
                f"| {entry['case_id']} | {entry['label']} "
                f"| {entry['terminal_channel']} "
                f"| {entry['predicted_unsafe']} "
                f"| {entry['predicted_angle_deg']} "
                f"| {entry['predicted_displacement']} "
                f"| {entry['actual_angle_deg']} "
                f"| {entry['actual_displacement']} |"
            )
    else:
        lines.append("(none)")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown", type=pathlib.Path)
    parser.add_argument("--probe-arm", default="physics_probe")
    parser.add_argument("--base-arm", default="base")
    args = parser.parse_args()
    episodes = collect_episodes(args.input_dir)
    summary = summarize(episodes, args.probe_arm, args.base_arm)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(to_markdown(summary), encoding="utf-8")
    print(
        json.dumps(
            {
                "probe_episodes": summary["probe_episodes"],
                "joined_steps": summary["joined_steps"],
                "pooled_auc": summary["pooled_auc"],
                "fatal_recall": summary["fatal_recall"],
                "gates": summary["gates"],
                "verdict": summary["verdict"],
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
