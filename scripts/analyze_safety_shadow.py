#!/usr/bin/env python3
"""Calibrate the live safety shadow against physical episode outcomes.

Joins each episode's ``safety_shadow`` policy-trace events with the
episode's terminal channel (run_risk_ablation rows) and asks the Gate 1
question of reports/state-model/calibration-protocol.md: do the logits
the shadow computed live, from the agent's own phi at decision time,
rank the placements that physically ended the episode (topple / slide /
unsafe_other) below the placements the episode survived?

Labeling is fixed by the protocol: in a physically-fatal episode the
LAST shadow event is fatal and every earlier one surviving; safe
episodes contribute only surviving events; transport_invalid endings
are fixed-fallback deaths with no candidate and hence no shadow event
for the fatal action, so they contribute no fatal label and are counted
separately.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
from typing import Any

PHYSICAL_FATAL_CHANNELS = frozenset({"topple", "slide", "unsafe_other"})
LOGIT_BANDS = (
    ("below_0", None, 0.0),
    ("0_to_2", 0.0, 2.0),
    ("2_to_5", 2.0, 5.0),
    ("5_to_10", 5.0, 10.0),
    ("10_up", 10.0, None),
)
STEP_BANDS = (("early_0_7", 0, 7), ("mid_8_15", 8, 15), ("late_16_up", 16, None))

GATE_MIN_COMPLETE_EPISODES = 15
GATE_MIN_FATAL_EVENTS = 5
GATE_MIN_AUC = 0.70


def load_shadow_events(trace_path: pathlib.Path) -> list[dict[str, Any]]:
    events = []
    if not trace_path.exists():
        return events
    with trace_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("event") != "safety_shadow":
                continue
            events.append(
                {
                    "step": int(record.get("step", -1)),
                    "logit": float(record["logit"]),
                    "candidate_kind": str(
                        record.get("candidate_kind") or "candidate"
                    ),
                }
            )
    events.sort(key=lambda event: event["step"])
    return events


def collect_episodes(input_dir: pathlib.Path) -> list[dict[str, Any]]:
    """One record per completed episode: labeled shadow events + outcome."""
    episodes = []
    for rows_path in sorted(input_dir.rglob("rows.jsonl")):
        with rows_path.open(encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
        for row in rows:
            cases = row.get("cases") or {}
            if len(cases) != 1:
                # The calibration matrix runs single-case configs; a
                # multi-case row has no unique terminal channel to join.
                continue
            case_id, case = next(iter(cases.items()))
            trace_path = (
                rows_path.parent / "runs" / str(row["label"]) /
                "policy-trace.jsonl"
            )
            events = load_shadow_events(trace_path)
            channel = str(case.get("terminal_channel") or "unknown")
            fatal_last = channel in PHYSICAL_FATAL_CHANNELS and bool(events)
            for index, event in enumerate(events):
                event["label"] = (
                    "fatal"
                    if fatal_last and index == len(events) - 1
                    else "surviving"
                )
            episodes.append(
                {
                    "case_id": case_id,
                    "label": str(row["label"]),
                    "replicate": row.get("repeat"),
                    "returncode": row.get("process_returncode"),
                    "terminal_channel": channel,
                    "steps": case.get("steps"),
                    "placed_count": case.get("placed_count"),
                    "events": events,
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


def band_of(value: float, bands) -> str:
    for name, low, high in bands:
        if (low is None or value >= low) and (high is None or value < high):
            return name
    return "unbanded"


def sigmoid(logit: float) -> float:
    return 1.0 / (1.0 + math.exp(-logit))


def summarize(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [
        episode
        for episode in episodes
        if episode.get("returncode") == 0 and episode["events"]
    ]
    surviving = [
        event["logit"]
        for episode in completed
        for event in episode["events"]
        if event["label"] == "surviving"
    ]
    fatal = [
        event["logit"]
        for episode in completed
        for event in episode["events"]
        if event["label"] == "fatal"
    ]

    def median(values: list[float]) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[middle]
        return (ordered[middle - 1] + ordered[middle]) / 2.0

    calibration = {}
    for name, _low, _high in LOGIT_BANDS:
        calibration[name] = {"surviving": 0, "fatal": 0}
    splits: dict[str, dict[str, dict[str, list[float]]]] = {
        "candidate_kind": {},
        "step_band": {},
    }
    per_case: dict[str, dict[str, list[float]]] = {}
    for episode in completed:
        case_bucket = per_case.setdefault(
            episode["case_id"], {"surviving": [], "fatal": []}
        )
        for event in episode["events"]:
            label = event["label"]
            calibration[band_of(event["logit"], LOGIT_BANDS)][label] += 1
            case_bucket[label].append(event["logit"])
            kind_bucket = splits["candidate_kind"].setdefault(
                event["candidate_kind"], {"surviving": [], "fatal": []}
            )
            kind_bucket[label].append(event["logit"])
            step_bucket = splits["step_band"].setdefault(
                band_of(float(event["step"]), STEP_BANDS),
                {"surviving": [], "fatal": []},
            )
            step_bucket[label].append(event["logit"])

    for band in calibration.values():
        total = band["surviving"] + band["fatal"]
        band["n"] = total
        band["empirical_survival"] = (
            round(band["surviving"] / total, 4) if total else None
        )
        band["mean_predicted_survival"] = None
    # Mean predicted survival per band, from the events themselves.
    predicted: dict[str, list[float]] = {}
    for episode in completed:
        for event in episode["events"]:
            predicted.setdefault(
                band_of(event["logit"], LOGIT_BANDS), []
            ).append(sigmoid(event["logit"]))
    for name, values in predicted.items():
        calibration[name]["mean_predicted_survival"] = round(
            sum(values) / len(values), 4
        )

    def split_table(buckets):
        table = {}
        for key, bucket in sorted(buckets.items()):
            table[key] = {
                "surviving_n": len(bucket["surviving"]),
                "fatal_n": len(bucket["fatal"]),
                "auc": (
                    round(auc, 4)
                    if (auc := rank_auc(bucket["surviving"], bucket["fatal"]))
                    is not None
                    else None
                ),
                "median_surviving": median(bucket["surviving"]),
                "median_fatal": median(bucket["fatal"]),
            }
        return table

    channels: dict[str, int] = {}
    for episode in episodes:
        channels[episode["terminal_channel"]] = (
            channels.get(episode["terminal_channel"], 0) + 1
        )
    b_complete = any(
        episode["case_id"].startswith("b") for episode in completed
    )
    c_complete = any(
        episode["case_id"].startswith("c") for episode in completed
    )
    pooled_auc = rank_auc(surviving, fatal)
    median_surviving = median(surviving)
    median_fatal = median(fatal)
    gates = {
        "coverage": (
            len(completed) >= GATE_MIN_COMPLETE_EPISODES
            and b_complete
            and c_complete
        ),
        "power": len(fatal) >= GATE_MIN_FATAL_EVENTS,
        "discrimination": (
            pooled_auc is not None and pooled_auc >= GATE_MIN_AUC
        ),
        "direction": (
            median_fatal is not None
            and median_surviving is not None
            and median_fatal < median_surviving
        ),
    }
    if not gates["power"]:
        verdict = "underpowered_extend_wave"
    elif all(gates.values()):
        verdict = "calibration_pass_gate2_licensed"
    else:
        verdict = "calibration_fail_shadow_only"
    return {
        "protocol": "reports/state-model/calibration-protocol.md",
        "episodes_total": len(episodes),
        "episodes_completed_with_shadow": len(completed),
        "terminal_channels": dict(sorted(channels.items())),
        "surviving_events": len(surviving),
        "fatal_events": len(fatal),
        "pooled_auc_surviving_over_fatal": (
            round(pooled_auc, 4) if pooled_auc is not None else None
        ),
        "median_surviving_logit": median_surviving,
        "median_fatal_logit": median_fatal,
        "gates": gates,
        "verdict": verdict,
        "calibration_by_logit_band": calibration,
        "split_by_candidate_kind": split_table(splits["candidate_kind"]),
        "split_by_step_band": split_table(splits["step_band"]),
        "per_case": split_table(per_case),
        "fatal_event_detail": [
            {
                "case_id": episode["case_id"],
                "label": episode["label"],
                "terminal_channel": episode["terminal_channel"],
                "step": episode["events"][-1]["step"],
                "logit": episode["events"][-1]["logit"],
                "candidate_kind": episode["events"][-1]["candidate_kind"],
            }
            for episode in completed
            if episode["events"] and episode["events"][-1]["label"] == "fatal"
        ],
    }


def to_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Safety shadow calibration (Gate 1)",
        "",
        f"Protocol: `{summary['protocol']}`",
        "",
        f"- episodes: {summary['episodes_completed_with_shadow']} completed "
        f"with shadow of {summary['episodes_total']} total",
        f"- terminal channels: "
        f"{json.dumps(summary['terminal_channels'])}",
        f"- events: {summary['surviving_events']} surviving, "
        f"{summary['fatal_events']} fatal",
        f"- pooled AUC (surviving over fatal): "
        f"{summary['pooled_auc_surviving_over_fatal']}",
        f"- median logit: surviving {summary['median_surviving_logit']}, "
        f"fatal {summary['median_fatal_logit']}",
        f"- gates: {json.dumps(summary['gates'])}",
        f"- **verdict: {summary['verdict']}**",
        "",
        "## Calibration by logit band",
        "",
        "| band | n | empirical survival | mean predicted survival |",
        "|---|---|---|---|",
    ]
    for name, _low, _high in LOGIT_BANDS:
        band = summary["calibration_by_logit_band"][name]
        lines.append(
            f"| {name} | {band['n']} | {band['empirical_survival']} "
            f"| {band['mean_predicted_survival']} |"
        )
    for title, key in (
        ("Split by candidate kind", "split_by_candidate_kind"),
        ("Split by step band", "split_by_step_band"),
        ("Per case", "per_case"),
    ):
        lines += [
            "",
            f"## {title}",
            "",
            "| group | surviving n | fatal n | AUC | median surviving "
            "| median fatal |",
            "|---|---|---|---|---|---|",
        ]
        for group, stats in summary[key].items():
            lines.append(
                f"| {group} | {stats['surviving_n']} | {stats['fatal_n']} "
                f"| {stats['auc']} | {stats['median_surviving']} "
                f"| {stats['median_fatal']} |"
            )
    lines += ["", "## Fatal events", ""]
    if summary["fatal_event_detail"]:
        lines += [
            "| case | episode | channel | step | logit | kind |",
            "|---|---|---|---|---|---|",
        ]
        for event in summary["fatal_event_detail"]:
            lines.append(
                f"| {event['case_id']} | {event['label']} "
                f"| {event['terminal_channel']} | {event['step']} "
                f"| {round(event['logit'], 3)} "
                f"| {event['candidate_kind']} |"
            )
    else:
        lines.append("(none)")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown", type=pathlib.Path)
    args = parser.parse_args()
    episodes = collect_episodes(args.input_dir)
    summary = summarize(episodes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(to_markdown(summary), encoding="utf-8")
    print(json.dumps({
        "episodes": summary["episodes_completed_with_shadow"],
        "surviving_events": summary["surviving_events"],
        "fatal_events": summary["fatal_events"],
        "pooled_auc": summary["pooled_auc_surviving_over_fatal"],
        "verdict": summary["verdict"],
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
