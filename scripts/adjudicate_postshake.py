"""Adjudicate the direct post-shake instrument's gates, and report its payload.

Protocol: reports/hazard/post-shake-direct-protocol.md (G1 amended
2026-08-18 before any G1 datum existed; the amendment and its reason are
recorded in the protocol itself).

Gates adjudicated here:

  G1a  in-process no-op. For each captured episode the recorder ran the
       official shake_test wrapped and then again unwrapped on the same
       terminal state; the two responses must be equal, and exactly two
       _live_poses calls must have occurred inside the wrapped one.
       Compared on the same state, so wall-clock nondeterminism cannot
       confound it.

  G2   pre-shake self-consistency. Nothing steps the simulation between
       the last placement's settle and evaluate(), so the recorder's
       pre-shake capture must reproduce the last SAFE step's recorded
       attribute counts exactly. Episodes whose final step is unsafe do
       not qualify (the validator removes the item, which moves the
       world after the last recorded settle).

  G3   structural, adjudicated in tests/test_postshake_capture.py.

The payload -- the pre-to-post change in soft/priority coverage, which
is the axis official feedback says we are blind on -- is computed and
reported here, but it is reported only, and it is marked as carrying no
verdict weight unless every gate passes.
"""

from __future__ import annotations

import argparse
import glob
import json
import pathlib
import statistics
from typing import Any

import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.postshake_capture import (  # noqa: E402
    ATTRIBUTE_KEYS,
    attribute_counts,
)

G2_THRESHOLD = 0.95
G1_MIN_EPISODES = 6
G1_MIN_CONFIGS = 3
STREAM_MIN_EPISODES = 40
STREAM_MIN_CONFIGS = 5


def load_run(run_dir: pathlib.Path) -> list[dict[str, Any]]:
    """Join one run directory's capture with its evaluation report."""
    capture_path = run_dir / "post-shake-capture.json"
    result_path = run_dir / "evaluation_results.json"
    if not capture_path.exists() or not result_path.exists():
        return []
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    results = json.loads(result_path.read_text(encoding="utf-8"))
    episodes = capture.get("episodes", [])

    # The capture file accumulates one record per shake_test call, in
    # the order EvaluationApp iterates the config's cases, which is the
    # order evaluation_results.json preserves.
    case_ids = list(results)
    rows = []
    for case_id, record in zip(case_ids, episodes):
        evaluation = (results[case_id] or {}).get("evaluation")
        if not evaluation:
            continue
        rows.append(
            {
                "run_dir": str(run_dir),
                "label": run_dir.name,
                "case_id": case_id,
                "record": record,
                "evaluation": evaluation,
            }
        )
    return rows


def last_safe_step(evaluation: dict) -> dict | None:
    for step in reversed(evaluation.get("step_metrics", []) or []):
        if (step.get("status") or {}).get("is_placed_safe"):
            return step
    return None


def adjudicate_g1a(rows: list[dict]) -> dict[str, Any]:
    checked = []
    for row in rows:
        check = row["record"].get("noop_check") or {}
        checked.append(
            {
                "label": row["label"],
                "case_id": row["case_id"],
                "control_matches": bool(check.get("control_matches")),
                "live_poses_calls": check.get("live_poses_calls"),
                "calls_as_expected": check.get("live_poses_calls")
                == check.get("expected_live_poses_calls"),
            }
        )
    matched = sum(1 for c in checked if c["control_matches"])
    calls_ok = sum(1 for c in checked if c["calls_as_expected"])
    total = len(checked)
    # The protocol asks for >= 6 episodes "spanning >= 3 configs and
    # both arms", so the span is part of the gate, not a description of
    # the data. A recorder verified on one config proves less.
    configs = sorted({row["case_id"] for row in rows})
    arms = sorted(
        {
            "quiet_guard"
            if "quiet_guard" in row["label"]
            else ("base" if "-base-" in row["label"] else "other")
            for row in rows
        }
    )
    span_ok = len(configs) >= G1_MIN_CONFIGS and {"base", "quiet_guard"} <= set(
        arms
    )
    return {
        "episodes": total,
        "control_matches": matched,
        "live_poses_calls_as_expected": calls_ok,
        "min_episodes": G1_MIN_EPISODES,
        "configs": configs,
        "min_configs": G1_MIN_CONFIGS,
        "arms": arms,
        "span_ok": span_ok,
        "pass": (
            total >= G1_MIN_EPISODES
            and span_ok
            and matched == total
            and calls_ok == total
        ),
        "detail": checked,
    }


def adjudicate_g2(rows: list[dict]) -> dict[str, Any]:
    qualifying = []
    for row in rows:
        step = last_safe_step(row["evaluation"])
        if step is None:
            continue
        recorded = {k: step[k] for k in ATTRIBUTE_KEYS if k in step}
        captured = attribute_counts(row["record"].get("pre_shake"))
        qualifying.append(
            {
                "label": row["label"],
                "case_id": row["case_id"],
                "equal": recorded == captured,
                "recorded": recorded,
                "captured": captured,
            }
        )
    equal = sum(1 for q in qualifying if q["equal"])
    total = len(qualifying)
    rate = (equal / total) if total else 0.0
    return {
        "qualifying_episodes": total,
        "exact_matches": equal,
        "match_rate": rate,
        "threshold": G2_THRESHOLD,
        "pass": total > 0 and rate >= G2_THRESHOLD,
        "mismatches": [q for q in qualifying if not q["equal"]],
    }


def payload(rows: list[dict]) -> dict[str, Any]:
    """Pre-to-post coverage change, by arm. Reported, never a verdict."""
    per_episode = []
    for row in rows:
        pre = attribute_counts(row["record"].get("pre_shake"))
        post = attribute_counts(row["record"].get("post_shake"))
        if not pre or not post:
            continue
        label = row["label"]
        arm = "quiet_guard" if "quiet_guard" in label else (
            "base" if "-base-" in label else "other"
        )
        per_episode.append(
            {
                "label": label,
                "case_id": row["case_id"],
                "arm": arm,
                "soft_clean_pre": pre.get("soft_clean_ratio"),
                "soft_clean_post": post.get("soft_clean_ratio"),
                "priority_clean_pre": pre.get("priority_clean_ratio"),
                "priority_clean_post": post.get("priority_clean_ratio"),
                "soft_changed": pre.get("soft_clean_ratio")
                != post.get("soft_clean_ratio"),
                "priority_changed": pre.get("priority_clean_ratio")
                != post.get("priority_clean_ratio"),
            }
        )

    def mean_of(key: str, arm: str | None = None) -> float | None:
        values = [
            e[key]
            for e in per_episode
            if e[key] is not None and (arm is None or e["arm"] == arm)
        ]
        return statistics.fmean(values) if values else None

    by_arm = {}
    for arm in sorted({e["arm"] for e in per_episode}):
        by_arm[arm] = {
            "episodes": sum(1 for e in per_episode if e["arm"] == arm),
            "soft_clean_pre": mean_of("soft_clean_pre", arm),
            "soft_clean_post": mean_of("soft_clean_post", arm),
            "priority_clean_pre": mean_of("priority_clean_pre", arm),
            "priority_clean_post": mean_of("priority_clean_post", arm),
        }
    return {
        "episodes": len(per_episode),
        "soft_changed_by_shake": sum(
            1 for e in per_episode if e["soft_changed"]
        ),
        "priority_changed_by_shake": sum(
            1 for e in per_episode if e["priority_changed"]
        ),
        "by_arm": by_arm,
        "per_episode": per_episode,
    }


def render_markdown(report: dict) -> str:
    g1 = report["g1a"]
    g2 = report["g2"]
    suf = report["stream_sufficiency"]
    pay = report["payload"]
    lines = [
        "# Direct post-shake instrument: gate adjudication",
        "",
        "Protocol: `reports/hazard/post-shake-direct-protocol.md`. "
        "Instrument: `scripts/postshake_capture.py` (recorder) and "
        "`scripts/run_test_capture.py` (entry point). No clone, no "
        "reconstruction: these are the numbers the bundled shake itself "
        "produced.",
        "",
        "## Gates",
        "",
        "| gate | threshold | measured | result |",
        "|---|---|---|---|",
        f"| G1a wrapped-vs-unwrapped shake equal | all episodes | "
        f"{g1['control_matches']}/{g1['episodes']} | "
        f"{'pass' if g1['control_matches'] == g1['episodes'] else '**fail**'}"
        " |",
        f"| G1a exactly two `_live_poses` calls per shake | all episodes | "
        f"{g1['live_poses_calls_as_expected']}/{g1['episodes']} | "
        f"{'pass' if g1['live_poses_calls_as_expected'] == g1['episodes'] else '**fail**'}"
        " |",
        f"| G1a span | >= {g1['min_episodes']} episodes, >= "
        f"{g1['min_configs']} configs, both arms | "
        f"{g1['episodes']} episodes, {len(g1['configs'])} configs, "
        f"arms {g1['arms']} | "
        f"{'pass' if g1['episodes'] >= g1['min_episodes'] and g1['span_ok'] else '**fail**'}"
        " |",
        f"| G2 pre-shake capture == last safe step counts | >= "
        f"{int(G2_THRESHOLD * 100)}% | "
        f"{g2['exact_matches']}/{g2['qualifying_episodes']} = "
        f"{g2['match_rate']:.1%} | "
        f"{'pass' if g2['pass'] else '**fail**'} |",
        "| G3 no reimplementation of the attribute contract | structural"
        " | `tests/test_postshake_capture.py` | see test run |",
        f"| stream sufficiency | >= {suf['min_episodes']} episodes, >= "
        f"{suf['min_configs']} configs, both arms | "
        f"{suf['episodes']} episodes, {len(suf['configs'])} configs, "
        f"arms {suf['arms']} | "
        f"{'pass' if suf['pass'] else '**fail**'} |",
        "",
        f"## Verdict: **{report['verdict']}**",
        "",
    ]
    if report["verdict"] != "pass":
        lines += [
            "Gates failed, so the instrument is not adopted, the payload "
            "below carries no verdict weight, and rung-3 label "
            "generation stays blocked.",
            "",
        ]
    lines += [
        "## Payload: what the shake does to attribute coverage",
        "",
        f"- episodes with pre and post capture: {pay['episodes']}",
        f"- episodes whose soft coverage changed across the shake: "
        f"{pay['soft_changed_by_shake']}",
        f"- episodes whose priority coverage changed across the shake: "
        f"{pay['priority_changed_by_shake']}",
        "",
        "| arm | episodes | soft clean pre | soft clean post | "
        "priority clean pre | priority clean post |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for arm, stats in pay["by_arm"].items():

        def fmt(value):
            return "-" if value is None else f"{value:.4f}"

        lines.append(
            f"| {arm} | {stats['episodes']} | "
            f"{fmt(stats['soft_clean_pre'])} | "
            f"{fmt(stats['soft_clean_post'])} | "
            f"{fmt(stats['priority_clean_pre'])} | "
            f"{fmt(stats['priority_clean_post'])} |"
        )
    if g2["mismatches"]:
        lines += ["", "## G2 mismatches", ""]
        for m in g2["mismatches"][:20]:
            lines.append(f"- `{m['label']}` / {m['case_id']}")
            lines.append(f"  - recorded: `{m['recorded']}`")
            lines.append(f"  - captured: `{m['captured']}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", action="append", required=True)
    parser.add_argument("--output-json", type=pathlib.Path, required=True)
    parser.add_argument("--output-md", type=pathlib.Path)
    args = parser.parse_args()

    run_dirs = sorted(
        {path for pattern in args.runs for path in glob.glob(pattern)}
    )
    if not run_dirs:
        raise SystemExit("no run directories matched --runs")

    rows: list[dict] = []
    for run_dir in run_dirs:
        rows.extend(load_run(pathlib.Path(run_dir)))
    if not rows:
        raise SystemExit("no captured episodes found in the matched runs")

    g1a = adjudicate_g1a(rows)
    g2 = adjudicate_g2(rows)
    # The protocol sizes the stream as well as the gates: ">= 40
    # episodes across >= 5 configs and both arms for G2 and for the
    # payload". A gate that passes on a thin stream has not been tested.
    stream_configs = sorted({row["case_id"] for row in rows})
    stream_arms = sorted(
        {
            "quiet_guard"
            if "quiet_guard" in row["label"]
            else ("base" if "-base-" in row["label"] else "other")
            for row in rows
        }
    )
    sufficiency = {
        "episodes": len(rows),
        "min_episodes": STREAM_MIN_EPISODES,
        "configs": stream_configs,
        "min_configs": STREAM_MIN_CONFIGS,
        "arms": stream_arms,
        "pass": (
            len(rows) >= STREAM_MIN_EPISODES
            and len(stream_configs) >= STREAM_MIN_CONFIGS
            and {"base", "quiet_guard"} <= set(stream_arms)
        ),
    }
    report = {
        "run_dirs": run_dirs,
        "episodes": len(rows),
        "stream_sufficiency": sufficiency,
        "g1a": g1a,
        "g2": g2,
        "payload": payload(rows),
        "verdict": (
            "pass"
            if (g1a["pass"] and g2["pass"] and sufficiency["pass"])
            else "fail"
        ),
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(args.output_json)
    if args.output_md:
        args.output_md.write_text(
            render_markdown(report), encoding="utf-8"
        )
        print(args.output_md)
    print(
        json.dumps(
            {
                "episodes": report["episodes"],
                "g1a_pass": g1a["pass"],
                "g2_pass": g2["pass"],
                "g2_match_rate": g2["match_rate"],
                "verdict": report["verdict"],
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
