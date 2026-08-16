#!/usr/bin/env python3
"""Adjudicate the Gate 2 safety-rerank A/B against its preregistration.

Implements reports/state-model/gate2-rerank-protocol.md exactly: five
predeclared gates over the {base, safety_null, safety_rerank} matrix,
with per-config no-harm floors taken from the committed benchmark
baseline (2 sd where sd > 0, one placement where sd = 0). The verdict
comes out of this script, not out of a narrative reading of the
tables; anything not gated here is descriptive.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

PHYSICAL_GAMBLE_CHANNELS = ("topple", "slide")
ENFORCE_ARM = "safety_rerank"
NULL_ARM = "safety_null"
BASE_ARM = "base"


def load_rows(path: pathlib.Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return [row for row in rows if row.get("process_returncode") == 0]


def placed_floor(baseline_case: dict[str, Any] | None) -> float:
    if not baseline_case:
        return 1.0
    sd = float(baseline_case.get("placed_sd") or 0.0)
    return 2.0 * sd if sd > 0.0 else 1.0


def collect(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Index single-case rows by (case_id, arm, replicate)."""
    episodes: dict[tuple[str, str, int], dict[str, Any]] = {}
    for row in rows:
        cases = row.get("cases") or {}
        if len(cases) != 1:
            continue
        case_id, case = next(iter(cases.items()))
        trace = row.get("policy_trace") or {}
        episodes[(case_id, str(row["arm"]), int(row["repeat"]))] = {
            "placed": int(case.get("placed_count") or 0),
            "fill": float(case.get("fill_score") or 0.0),
            "channel": str(case.get("terminal_channel") or "unknown"),
            "triggered": int(
                trace.get("safety_rerank_triggered_count") or 0
            ),
            "would_swap": int(
                trace.get("safety_rerank_would_swap_count") or 0
            ),
            "enforced": int(
                trace.get("safety_rerank_enforced_count") or 0
            ),
        }
    return episodes


def adjudicate(
    rows: list[dict[str, Any]], baseline: dict[str, Any]
) -> dict[str, Any]:
    episodes = collect(rows)
    case_ids = sorted({key[0] for key in episodes})
    arms = sorted({key[1] for key in episodes})

    def arm_episodes(arm: str) -> list[dict[str, Any]]:
        return [
            value for key, value in episodes.items() if key[1] == arm
        ]

    def pooled_placed(arm: str) -> int:
        return sum(episode["placed"] for episode in arm_episodes(arm))

    def pooled_channel(arm: str, channels) -> int:
        return sum(
            1
            for episode in arm_episodes(arm)
            if episode["channel"] in channels
        )

    def case_mean_placed(case_id: str, arm: str) -> float | None:
        values = [
            value["placed"]
            for key, value in episodes.items()
            if key[0] == case_id and key[1] == arm
        ]
        return sum(values) / len(values) if values else None

    pairs = []
    for case_id in case_ids:
        replicates = sorted(
            {
                key[2]
                for key in episodes
                if key[0] == case_id and key[1] == BASE_ARM
            }
        )
        for replicate in replicates:
            base = episodes.get((case_id, BASE_ARM, replicate))
            enforce = episodes.get((case_id, ENFORCE_ARM, replicate))
            if base is None or enforce is None:
                continue
            pairs.append(
                {
                    "case_id": case_id,
                    "replicate": replicate,
                    "base_placed": base["placed"],
                    "rerank_placed": enforce["placed"],
                    "diff": enforce["placed"] - base["placed"],
                }
            )
    wins = sum(1 for pair in pairs if pair["diff"] > 0)
    losses = sum(1 for pair in pairs if pair["diff"] < 0)

    baseline_cases = baseline.get("cases") or {}
    no_harm = {}
    control = {}
    for case_id in case_ids:
        floor = placed_floor(baseline_cases.get(case_id))
        base_mean = case_mean_placed(case_id, BASE_ARM)
        rerank_mean = case_mean_placed(case_id, ENFORCE_ARM)
        null_mean = case_mean_placed(case_id, NULL_ARM)
        no_harm[case_id] = {
            "floor": round(floor, 3),
            "base_mean": base_mean,
            "rerank_mean": rerank_mean,
            "ok": (
                base_mean is None
                or rerank_mean is None
                or rerank_mean >= base_mean - floor
            ),
        }
        control[case_id] = {
            "floor": round(floor, 3),
            "base_mean": base_mean,
            "null_mean": null_mean,
            "ok": (
                base_mean is None
                or null_mean is None
                or abs(null_mean - base_mean) <= floor
            ),
        }

    gamble_base = pooled_channel(BASE_ARM, PHYSICAL_GAMBLE_CHANNELS)
    gamble_rerank = pooled_channel(ENFORCE_ARM, PHYSICAL_GAMBLE_CHANNELS)
    transport_base = pooled_channel(BASE_ARM, ("transport_invalid",))
    transport_rerank = pooled_channel(
        ENFORCE_ARM, ("transport_invalid",)
    )
    placed_base = pooled_placed(BASE_ARM)
    placed_rerank = pooled_placed(ENFORCE_ARM)
    enforced_total = sum(
        episode["enforced"] for episode in arm_episodes(ENFORCE_ARM)
    )

    gates = {
        "mechanism_topple_slide_lower": gamble_rerank < gamble_base,
        "direction_pooled_placed_higher": (
            placed_rerank > placed_base and wins >= losses
        ),
        "no_harm_per_config": all(
            entry["ok"] for entry in no_harm.values()
        ),
        "fallback_conservation": transport_rerank <= transport_base,
        "negative_control_within_floor": all(
            entry["ok"] for entry in control.values()
        ),
    }
    if enforced_total == 0:
        verdict = "inert_arm_closed"
    elif all(gates.values()):
        verdict = "development_pass_gate3_required"
    else:
        verdict = "development_fail_arm_closed"

    per_arm_channels: dict[str, dict[str, int]] = {}
    for arm in arms:
        bucket: dict[str, int] = {}
        for episode in arm_episodes(arm):
            bucket[episode["channel"]] = (
                bucket.get(episode["channel"], 0) + 1
            )
        per_arm_channels[arm] = dict(sorted(bucket.items()))

    swap_activity = {
        arm: {
            "episodes": len(arm_episodes(arm)),
            "triggered": sum(
                episode["triggered"] for episode in arm_episodes(arm)
            ),
            "would_swap": sum(
                episode["would_swap"] for episode in arm_episodes(arm)
            ),
            "enforced": sum(
                episode["enforced"] for episode in arm_episodes(arm)
            ),
        }
        for arm in arms
    }

    return {
        "protocol": "reports/state-model/gate2-rerank-protocol.md",
        "episodes": len(episodes),
        "arms": arms,
        "pooled_placed": {
            arm: pooled_placed(arm) for arm in arms
        },
        "pooled_channels": per_arm_channels,
        "paired_placed": {
            "pairs": len(pairs),
            "wins": wins,
            "losses": losses,
            "detail": pairs,
        },
        "no_harm": no_harm,
        "negative_control": control,
        "swap_activity": swap_activity,
        "gates": gates,
        "verdict": verdict,
    }


def to_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Safety rerank development adjudication (Gate 2)",
        "",
        f"Protocol: `{result['protocol']}`",
        "",
        f"- episodes: {result['episodes']} across arms "
        f"{result['arms']}",
        f"- pooled placed: {json.dumps(result['pooled_placed'])}",
        f"- pooled channels: "
        f"{json.dumps(result['pooled_channels'])}",
        f"- paired placed: {result['paired_placed']['wins']} wins / "
        f"{result['paired_placed']['losses']} losses over "
        f"{result['paired_placed']['pairs']} pairs",
        f"- swap activity: {json.dumps(result['swap_activity'])}",
        f"- gates: {json.dumps(result['gates'])}",
        f"- **verdict: {result['verdict']}**",
        "",
        "## No-harm per config",
        "",
        "| case | floor | base mean | rerank mean | ok |",
        "|---|---|---|---|---|",
    ]
    for case_id, entry in sorted(result["no_harm"].items()):
        lines.append(
            f"| {case_id} | {entry['floor']} | {entry['base_mean']} "
            f"| {entry['rerank_mean']} | {entry['ok']} |"
        )
    lines += [
        "",
        "## Negative control per config",
        "",
        "| case | floor | base mean | null mean | ok |",
        "|---|---|---|---|---|",
    ]
    for case_id, entry in sorted(result["negative_control"].items()):
        lines.append(
            f"| {case_id} | {entry['floor']} | {entry['base_mean']} "
            f"| {entry['null_mean']} | {entry['ok']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=pathlib.Path, required=True)
    parser.add_argument("--baseline", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown", type=pathlib.Path)
    args = parser.parse_args()
    rows = load_rows(args.rows)
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    result = adjudicate(rows, baseline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(to_markdown(result), encoding="utf-8")
    print(json.dumps({
        "episodes": result["episodes"],
        "pooled_placed": result["pooled_placed"],
        "gates": result["gates"],
        "verdict": result["verdict"],
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
