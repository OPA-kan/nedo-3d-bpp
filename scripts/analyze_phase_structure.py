#!/usr/bin/env python3
"""Classify feasibility phases across all committed anchor-recall oracles.

Every schema-2 anchor-recall summary carries both the ground truth (dual
settled oracles with per-generator counts, all physically verified) and the
live policy's decision-time telemetry (`policy_log`). Crossing them sorts
each measured board into one of four phases:

- P0 FOUND: the live search accepted at least one settled candidate.
- P1 DEADLINE-MISS: settled candidates reachable by the live generator
  exist, but the deadline-limited search accepted none.
- P2 GENERATOR-HOLE: settled candidates exist only outside the live
  generator's reach.
- P3 TRUE-EMPTY: no settled candidate exists under either generator.

The detection question is whether P3 can be told from P1 *from inside the
search*, using only decision-time observables. The candidate rule measured
here: a search that accepted zero settled candidates AND completed at
least one third of its scan units is calling a truly empty settled phase
(near the collapse the candidate space itself implodes, so the scan
finishes; drowning states have huge spaces that eat the deadline first).
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

COMPLETION_THRESHOLD = 1.0 / 3.0


def load_states(root: pathlib.Path) -> list[dict[str, Any]]:
    states = []
    for path in sorted(root.rglob("step-*-summary.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if int(data.get("schema_version", 1)) < 2:
            continue
        policy_log = data.get("policy_log") or {}
        search = policy_log.get("search") or {}
        generator_counts = (
            (data.get("oracle_stats") or {}).get("generator_counts") or {}
        )
        if not data.get("oracle_complete") or not data.get("physics_complete"):
            continue
        states.append({
            "run": path.parts[len(root.parts)],
            "case": str(data.get("case_id")),
            "step": int(data.get("step")),
            "oracle_union": int(data.get("oracle_settled_count", 0)),
            "support_plane": generator_counts.get("support_plane"),
            "cartesian": generator_counts.get("cartesian"),
            "accepted_settled": policy_log.get("accepted_settled_count"),
            "accepted_release": policy_log.get("accepted_release_count"),
            "units_completed": search.get("units_completed"),
            "units_total": search.get("units_total"),
            "deadline_reached": search.get("deadline_reached"),
        })
    return states


def classify(state: dict[str, Any]) -> str:
    if state["oracle_union"] == 0:
        return "P3_true_empty"
    if state["support_plane"] is not None and state["support_plane"] == 0:
        return "P2_generator_hole"
    if not state["accepted_settled"]:
        return "P1_deadline_miss"
    return "P0_found"


def _completion(state: dict[str, Any]) -> float | None:
    done, total = state["units_completed"], state["units_total"]
    if done is None or not total:
        return None
    return done / total


def detector_fires(state: dict[str, Any]) -> bool | None:
    """Zero settled accepted plus a mostly-finished scan calls true-empty."""
    if state["accepted_settled"] is None:
        return None
    if state["accepted_settled"] > 0:
        return False
    completion = _completion(state)
    if completion is None:
        return None
    return completion >= COMPLETION_THRESHOLD


def _board_key(state: dict[str, Any]) -> tuple:
    # Distinct physical boards at the same (case, step) coordinate are
    # separated by their exact oracle census; identical censuses across
    # runs are replicate measurements of one board.
    return (
        state["case"], state["step"], state["oracle_union"],
        state["support_plane"], state["cartesian"],
    )


def evaluate(states: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for state in states:
        rows.append({
            **state,
            "phase": classify(state),
            "unit_completion": _completion(state),
            "detector_true_empty": detector_fires(state),
        })
    def confusion(selected: list[dict[str, Any]]) -> dict[str, Any]:
        fired = [r for r in selected if r["detector_true_empty"]]
        empty = [r for r in selected if r["phase"] == "P3_true_empty"]
        true_pos = sum(1 for r in fired if r["phase"] == "P3_true_empty")
        return {
            "states": len(selected),
            "true_empty": len(empty),
            "detector_fired": len(fired),
            "true_positives": true_pos,
            "false_positives": len(fired) - true_pos,
            "missed_true_empty": len(empty) - true_pos,
            "precision": true_pos / len(fired) if fired else None,
            "recall": true_pos / len(empty) if empty else None,
        }
    measurable = [r for r in rows if r["detector_true_empty"] is not None]
    boards: dict[tuple, dict[str, Any]] = {}
    for row in measurable:
        boards.setdefault(_board_key(row), row)
    phase_counts: dict[str, int] = {}
    for row in rows:
        phase_counts[row["phase"]] = phase_counts.get(row["phase"], 0) + 1
    board_phases: dict[str, int] = {}
    for row in boards.values():
        board_phases[row["phase"]] = board_phases.get(row["phase"], 0) + 1
    return {
        "schema_version": 1,
        "completion_threshold": COMPLETION_THRESHOLD,
        "phase_counts_raw_states": phase_counts,
        "phase_counts_distinct_boards": board_phases,
        "detector_raw_states": confusion(measurable),
        "detector_distinct_boards": confusion(list(boards.values())),
        "states": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--history-root", type=pathlib.Path,
        default=pathlib.Path("reports/anchor-recall/history"),
    )
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path)
    args = parser.parse_args()
    result = evaluate(load_states(args.history_root))
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    if args.markdown_output:
        raw = result["detector_raw_states"]
        board = result["detector_distinct_boards"]
        lines = [
            "# Feasibility phase structure across anchor-recall oracles", "",
            f"- raw states by phase: {result['phase_counts_raw_states']}",
            f"- distinct boards by phase: {result['phase_counts_distinct_boards']}",
            "",
            "## True-empty detector (zero settled accepted + scan completion >= 1/3)",
            "",
            (
                f"- raw states: precision {raw['precision']}, recall "
                f"{raw['recall']} ({raw['true_positives']}/{raw['detector_fired']}"
                f" fired, {raw['missed_true_empty']} missed)"
            ),
            (
                f"- distinct boards: precision {board['precision']}, recall "
                f"{board['recall']} ({board['true_positives']}/"
                f"{board['detector_fired']} fired, "
                f"{board['missed_true_empty']} missed)"
            ),
        ]
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
    print(args.json_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
