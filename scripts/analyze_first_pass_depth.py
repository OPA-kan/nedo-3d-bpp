"""
Read a first-pass depth ablation on the six things that decide it.

`ANCHOR_FIRST_PASS_ATTEMPTS` trades breadth for depth at fixed time: a
deeper first pass reaches the depth at which an item's candidates start
appearing, and reaches fewer items before the deadline. The probe in
`reports/same-class-stacking` located that depth between 64 and 256
attempts per item at the terminal states, so 128 is measured too -- a
cliff bracketed by two points is not a located cliff.

placed and fill alone cannot separate the two effects, because a deeper
pass can rescue the endgame and damage the opening in the same episode
and net to nothing. So this reports, per arm:

* **fallback deaths** -- episodes ending at `unsafe_protocol_fallback`,
  the failure the change is aimed at;
* **items with candidates** -- split early / late, because breadth loss
  shows up in the opening and depth gain in the endgame, and pooling
  them hides both;
* **units completed** and **deadline reached** -- whether the scan is
  finishing its units or being cut off;
* **attempts to first candidate** -- how deep the scan actually had to
  go before anything was placeable. This is the quantity the change is
  named after, and it is the one that says whether 256 is buying depth
  that was needed or depth that was already there.

The early/late split is by step index against each episode's own length,
so a short episode is not counted as all-endgame.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
EARLY_FRACTION = 0.5


def load_steps(run_dir: pathlib.Path):
    trace = run_dir / "policy-trace.jsonl"
    if not trace.exists():
        return []
    rows = [
        json.loads(line)
        for line in trace.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [row for row in rows if row.get("event") == "decision"]


def parse_run_name(name: str):
    """`b000-k40-first_pass256-r0` -> case, arm, repeat."""
    case, _, rest = name.partition("-")
    section, _, rest = rest.partition("-")
    case = f"{case}-{section}"
    arm, _, repeat = rest.rpartition("-r")
    return case, arm, repeat


def episode_metrics(steps):
    if not steps:
        return None
    cut = max(1, int(len(steps) * EARLY_FRACTION))
    early, late = steps[:cut], steps[cut:]

    def with_candidates(rows):
        return [
            len(
                (row.get("candidate_diagnostics", {}).get("search", {}) or {})
                .get("item_indices_with_candidates")
                or []
            )
            for row in rows
        ]

    def search_field(rows, field):
        values = [
            (row.get("candidate_diagnostics", {}).get("search", {}) or {}).get(
                field
            )
            for row in rows
        ]
        return [value for value in values if value is not None]

    first_candidate = search_field(steps, "attempts_to_first_candidate")
    completed = search_field(steps, "units_completed")
    reached = search_field(steps, "deadline_reached")
    return {
        "steps": len(steps),
        "fallback_deaths": int(
            steps[-1].get("action_source") == "unsafe_protocol_fallback"
        ),
        "fallback_steps": sum(
            1
            for row in steps
            if row.get("action_source") == "unsafe_protocol_fallback"
        ),
        "items_with_candidates_early": (
            statistics.fmean(with_candidates(early)) if early else 0.0
        ),
        "items_with_candidates_late": (
            statistics.fmean(with_candidates(late)) if late else 0.0
        ),
        "units_completed_mean": (
            statistics.fmean(completed) if completed else 0.0
        ),
        "deadline_reached_rate": (
            statistics.fmean([1.0 if value else 0.0 for value in reached])
            if reached
            else 0.0
        ),
        "attempts_to_first_candidate_median": (
            statistics.median(first_candidate) if first_candidate else None
        ),
        "steps_with_no_candidate_at_all": len(steps) - len(first_candidate),
    }


def collect(run_root: pathlib.Path):
    episodes: list[dict[str, Any]] = []
    for run_dir in sorted(run_root.iterdir()):
        if not run_dir.is_dir():
            continue
        metrics = episode_metrics(load_steps(run_dir))
        if metrics is None:
            continue
        case, arm, repeat = parse_run_name(run_dir.name)
        metrics.update({"case": case, "arm": arm, "repeat": repeat})
        result = run_dir / "evaluation_results.json"
        if result.exists():
            payload = json.loads(result.read_text(encoding="utf-8"))
            for case_payload in payload.values():
                evaluation = case_payload.get("evaluation", {})
                steps_metrics = evaluation.get("step_metrics") or [{}]
                metrics["placed"] = int(
                    steps_metrics[-1].get("placed_count", 0)
                )
                metrics["fill"] = float(evaluation.get("fill_score", 0.0))
        episodes.append(metrics)
    return episodes


NUMERIC = (
    "placed",
    "fill",
    "steps",
    "fallback_deaths",
    "items_with_candidates_early",
    "items_with_candidates_late",
    "units_completed_mean",
    "deadline_reached_rate",
    "steps_with_no_candidate_at_all",
)


def by_arm(episodes):
    arms: dict[str, dict[str, Any]] = {}
    for episode in episodes:
        bucket = arms.setdefault(episode["arm"], {"episodes": 0, "values": {}})
        bucket["episodes"] += 1
        for field in NUMERIC:
            bucket["values"].setdefault(field, []).append(
                float(episode.get(field) or 0.0)
            )
        median = episode.get("attempts_to_first_candidate_median")
        if median is not None:
            bucket["values"].setdefault("attempts_to_first", []).append(
                float(median)
            )
    return {
        arm: {
            "episodes": bucket["episodes"],
            **{
                field: round(statistics.fmean(values), 3)
                for field, values in bucket["values"].items()
                if values
            },
        }
        for arm, bucket in arms.items()
    }


def paired(episodes, baseline_arm):
    base = {
        (e["case"], e["repeat"]): e
        for e in episodes
        if e["arm"] == baseline_arm
    }
    rows = []
    for episode in episodes:
        if episode["arm"] == baseline_arm:
            continue
        reference = base.get((episode["case"], episode["repeat"])) or base.get(
            (episode["case"], "0")
        )
        if reference is None:
            continue
        rows.append(
            {
                "arm": episode["arm"],
                "case": episode["case"],
                "repeat": episode["repeat"],
                "placed_diff": episode.get("placed", 0)
                - reference.get("placed", 0),
                "fill_diff": round(
                    episode.get("fill", 0.0) - reference.get("fill", 0.0), 3
                ),
                "fallback_diff": episode["fallback_deaths"]
                - reference["fallback_deaths"],
                "early_candidate_items_diff": round(
                    episode["items_with_candidates_early"]
                    - reference["items_with_candidates_early"],
                    3,
                ),
                "late_candidate_items_diff": round(
                    episode["items_with_candidates_late"]
                    - reference["items_with_candidates_late"],
                    3,
                ),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=ROOT / "reports" / "first-pass-depth",
    )
    parser.add_argument("--baseline-arm", default="base")
    args = parser.parse_args()

    episodes = collect(args.output_dir / "runs")
    payload = {
        "episodes": len(episodes),
        "baseline_arm": args.baseline_arm,
        "per_arm": by_arm(episodes),
        "paired_vs_baseline": paired(episodes, args.baseline_arm),
        "per_episode": episodes,
    }
    (args.output_dir / "depth_summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["per_arm"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
