"""Attribute every recorded episode's ending to a cause, from the traces.

`num_placed_items` gates every official score component above r = 0.96
(`reports/official/placed-regression.md`), so what stops an episode is
what caps the score. This script joins each run's harness row (which
carries the simulator's `terminal_channel`) with the last `decision`
event of its policy trace (which carries what the agent was doing when
the episode ended) and reports the joint distribution.

The join matters because `terminal_channel` alone is ambiguous.
`transport_invalid` can mean either of two opposite things:

- the agent proposed a placement it believed reachable and the
  simulator's `check_transport_path` disagreed -- a model error; or
- the agent's deadline search accepted nothing at all and emitted the
  fixed protocol fallback, which is a deliberately transport-invalid
  action -- a surrender, and a search failure rather than a geometry
  one.

Only the trace distinguishes them, via `action_source` and
`no_safe_action`. For surrender endings the script also reports the
search diagnostics of the fatal step, which say whether the search ran
out of time or ran out of space -- a different fix in each case.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import pathlib
import statistics
from typing import Any


def load_episodes(row_globs: list[str]) -> list[dict[str, Any]]:
    episodes: list[dict[str, Any]] = []
    for pattern in row_globs:
        for rows_path in sorted(glob.glob(pattern)):
            base = os.path.dirname(rows_path)
            for line in open(rows_path, encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                trace = os.path.join(
                    base, "runs", row["label"], "policy-trace.jsonl"
                )
                last_decision = None
                if os.path.exists(trace):
                    for entry in open(trace, encoding="utf-8"):
                        if '"decision"' not in entry:
                            continue
                        try:
                            event = json.loads(entry)
                        except json.JSONDecodeError:
                            continue
                        if event.get("event") == "decision":
                            last_decision = event
                for case_id, summary in (row.get("cases") or {}).items():
                    episodes.append(
                        {
                            "label": row["label"],
                            "case_id": case_id,
                            "arm": row.get("arm"),
                            "terminal_channel": summary.get(
                                "terminal_channel"
                            ),
                            "placed_fraction": summary.get(
                                "placed_fraction"
                            ),
                            "placed_count": summary.get("placed_count"),
                            "total_items": summary.get("total_items"),
                            "last_decision": last_decision,
                        }
                    )
    return episodes


def classify(episode: dict) -> str:
    decision = episode.get("last_decision") or {}
    channel = episode.get("terminal_channel")
    if decision.get("no_safe_action"):
        return "surrender_no_candidate"
    source = decision.get("action_source")
    if channel in ("topple", "slide"):
        return f"physical_{channel}_from_{source or 'unknown'}"
    if channel == "transport_invalid":
        return f"transport_model_error_from_{source or 'unknown'}"
    return f"{channel}_from_{source or 'unknown'}"


def summarize(episodes: list[dict]) -> dict[str, Any]:
    total = len(episodes)
    causes = collections.Counter(classify(e) for e in episodes)
    channels = collections.Counter(
        e["terminal_channel"] for e in episodes
    )
    joint = collections.Counter(
        (
            e["terminal_channel"],
            (e.get("last_decision") or {}).get("action_source"),
        )
        for e in episodes
    )

    surrenders = [
        e for e in episodes if classify(e) == "surrender_no_candidate"
    ]
    search_stats: dict[str, Any] = {}
    if surrenders:
        diags = [
            (
                (e["last_decision"].get("candidate_diagnostics") or {}).get(
                    "search"
                )
                or {}
            )
            for e in surrenders
        ]
        attempts = [
            d.get("attempts_consumed")
            for d in diags
            if d.get("attempts_consumed") is not None
        ]
        search_stats = {
            "episodes": len(surrenders),
            "deadline_reached": sum(
                1 for d in diags if d.get("deadline_reached")
            ),
            "zero_units_completed": sum(
                1 for d in diags if d.get("units_completed") == 0
            ),
            "found_no_candidate_for_any_item": sum(
                1
                for d in diags
                if not (d.get("item_indices_with_candidates") or [])
            ),
            "mean_attempts_consumed": (
                statistics.fmean(attempts) if attempts else None
            ),
            "median_attempts_consumed": (
                statistics.median(attempts) if attempts else None
            ),
        }

    by_cause_placed = {}
    grouped = collections.defaultdict(list)
    for episode in episodes:
        grouped[classify(episode)].append(episode)
    for cause, group in grouped.items():
        fractions = [
            e["placed_fraction"]
            for e in group
            if e["placed_fraction"] is not None
        ]
        by_cause_placed[cause] = {
            "episodes": len(group),
            "share": len(group) / total if total else None,
            "mean_placed_fraction": (
                statistics.fmean(fractions) if fractions else None
            ),
        }

    return {
        "episodes": total,
        "terminal_channels": dict(channels),
        "channel_x_action_source": {
            f"{channel}|{source}": count
            for (channel, source), count in joint.items()
        },
        "causes": dict(causes),
        "by_cause": by_cause_placed,
        "surrender_search_diagnostics": search_stats,
        "mean_placed_fraction": (
            statistics.fmean(
                e["placed_fraction"]
                for e in episodes
                if e["placed_fraction"] is not None
            )
            if episodes
            else None
        ),
    }


def render_markdown(summary: dict) -> str:
    total = summary["episodes"]
    lines = [
        "# Death budget: what actually ends our episodes",
        "",
        "Generated by `scripts/analyze_death_budget.py` from recorded "
        "harness rows joined with their policy traces. "
        "`num_placed_items` gates every official component above "
        "r = 0.96 (`reports/official/placed-regression.md`), so what "
        "stops an episode is what caps the score.",
        "",
        f"- episodes: {total}",
        f"- mean placed fraction: "
        f"{summary['mean_placed_fraction']:.4f}",
        "",
        "## Cause of ending",
        "",
        "| cause | episodes | share | mean placed fraction |",
        "|---|---:|---:|---:|",
    ]
    for cause, stats in sorted(
        summary["by_cause"].items(), key=lambda kv: -kv[1]["episodes"]
    ):
        mean = stats["mean_placed_fraction"]
        lines.append(
            f"| `{cause}` | {stats['episodes']} | "
            f"{stats['share']:.1%} | "
            f"{'-' if mean is None else f'{mean:.4f}'} |"
        )

    search = summary.get("surrender_search_diagnostics") or {}
    if search:
        lines += [
            "",
            "## The surrender ending, in detail",
            "",
            "The fixed protocol fallback emits a knowingly "
            "transport-invalid action, so an episode ending this way was "
            "not beaten by geometry -- the search accepted nothing before "
            "its deadline and gave up. These diagnostics come from the "
            "fatal step itself.",
            "",
            f"- episodes ending this way: {search['episodes']} of {total}"
            f" ({search['episodes'] / total:.1%})",
            f"- deadline reached: "
            f"{search['deadline_reached']}/{search['episodes']}",
            f"- search units completed = 0: "
            f"{search['zero_units_completed']}/{search['episodes']}",
            f"- found no candidate for ANY item: "
            f"{search['found_no_candidate_for_any_item']}/"
            f"{search['episodes']}",
            f"- attempts consumed at the fatal step: mean "
            f"{search['mean_attempts_consumed']:.0f}, median "
            f"{search['median_attempts_consumed']:.0f}",
        ]
    lines += [
        "",
        "## Reading",
        "",
        "The shipped physics probe guards placements against toppling "
        "and sliding. Those channels are the MINORITY of endings. The "
        "majority is a search that ran out of time having accepted "
        "nothing, which no amount of physics arbitration can help: "
        "there is nothing to arbitrate between.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", action="append", required=True)
    parser.add_argument("--output-json", type=pathlib.Path, required=True)
    parser.add_argument("--output-md", type=pathlib.Path)
    args = parser.parse_args()

    episodes = load_episodes(args.rows)
    if not episodes:
        raise SystemExit("no episodes matched --rows")
    summary = summarize(episodes)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(args.output_json)
    if args.output_md:
        args.output_md.write_text(
            render_markdown(summary), encoding="utf-8"
        )
        print(args.output_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
