#!/usr/bin/env python3
"""Locate the choice-invariance freezing point and test the suicide mechanism.

Consumes schema-2+ ``branch-labels.json`` files. Per config it reports, at
each measured branch step, whether sibling choice still changes the final
outcome; the freezing step is the earliest measured step from which every
later measured step is choice-invariant. Before the freezing step it asks
two questions: did a sibling strictly better than the policy's own choice
exist (avoidability), and does the support-surface ledger separate the
better sibling from the worse one (mechanism)? A death is self-inflicted
exactly to the extent that both answers are yes.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import pathlib
from typing import Any

OUTCOMES = ("placed", "fill")
LEDGER_AXES = (
    "delta_usable_support",
    "forbidden_overlap",
    "plain_overlap",
    "footprint_area",
    "base_z",
)


def _exact_two_sided_binomial_p(successes: int, trials: int) -> float:
    if not trials:
        return 1.0
    tail = sum(
        math.comb(trials, value)
        for value in range(min(successes, trials - successes) + 1)
    ) / (2 ** trials)
    return min(1.0, 2.0 * tail)


def _ledger_value(branch: dict[str, Any], axis: str) -> float | None:
    ledger = branch.get("support_ledger")
    if not ledger:
        return None
    if axis == "forbidden_overlap":
        overlap = ledger["supporter_overlap"]
        return float(overlap["soft"]) + float(overlap["priority"])
    if axis == "plain_overlap":
        return float(ledger["supporter_overlap"]["plain"])
    return float(ledger[axis])


def load_config(path: pathlib.Path) -> dict[str, Any]:
    data = json.loads((path / "branch-labels.json").read_text(encoding="utf-8"))
    if int(data.get("schema_version", 0)) < 2:
        raise ValueError(f"branch labels require schema 2+: {path}")
    states = []
    for state in data["states"]:
        usable = []
        for branch in state["branches"]:
            reproducibility = branch["reproducibility"]
            if not reproducibility["prefix_reproduced_all"]:
                continue
            if not reproducibility["parent_state_matches_all"]:
                continue
            run = branch["runs"][0]
            usable.append({
                "q": float(branch["q"]),
                "is_control": bool(branch["is_control"]),
                "support_ledger": branch.get("support_ledger"),
                "placed": float(run["evaluation"].get("num_placed_items", 0.0)),
                "fill": float(run["evaluation"].get("fill_score", 0.0)),
            })
        if usable:
            states.append({
                "step": int(state["step"]),
                "board": state.get("board"),
                "branches": usable,
            })
    return {"task_id": data["task_id"], "states": sorted(states, key=lambda s: s["step"])}


def _per_step_rows(config: dict[str, Any], outcome: str) -> list[dict[str, Any]]:
    rows = []
    for state in config["states"]:
        values = [branch[outcome] for branch in state["branches"]]
        decided = sum(
            1 for left, right in itertools.combinations(state["branches"], 2)
            if left[outcome] != right[outcome]
        )
        control = next(
            (branch for branch in state["branches"] if branch["is_control"]), None
        )
        rows.append({
            "step": state["step"],
            "usable_branches": len(state["branches"]),
            "decided_pairs": decided,
            "outcome_min": min(values),
            "outcome_max": max(values),
            "control_outcome": control[outcome] if control else None,
            "control_is_best": (
                control[outcome] == max(values) if control else None
            ),
            "best_minus_control": (
                max(values) - control[outcome] if control else None
            ),
        })
    return rows


def _freezing_step(rows: list[dict[str, Any]]) -> int | None:
    """Earliest measured step from which every later step is invariant."""
    frozen_from = None
    for row in rows:
        if row["decided_pairs"] > 0:
            frozen_from = None
        elif frozen_from is None:
            frozen_from = row["step"]
    return frozen_from


def _mechanism(states: list[dict[str, Any]], outcome: str) -> dict[str, Any]:
    axes: dict[str, list[bool]] = {axis: [] for axis in LEDGER_AXES}
    q_flags: list[bool] = []
    for state in states:
        for left, right in itertools.combinations(state["branches"], 2):
            if left[outcome] == right[outcome]:
                continue
            better, worse = (
                (left, right) if left[outcome] > right[outcome] else (right, left)
            )
            if better["q"] != worse["q"]:
                q_flags.append(better["q"] > worse["q"])
            for axis in LEDGER_AXES:
                better_value = _ledger_value(better, axis)
                worse_value = _ledger_value(worse, axis)
                if better_value is None or worse_value is None:
                    continue
                if better_value != worse_value:
                    axes[axis].append(better_value > worse_value)
    def summarize(flags: list[bool]) -> dict[str, Any]:
        return {
            "decided_pairs": len(flags),
            "better_branch_higher": sum(flags),
            "exact_two_sided_p": _exact_two_sided_binomial_p(
                sum(flags), len(flags)
            ),
        }
    return {
        "q": summarize(q_flags),
        **{axis: summarize(flags) for axis, flags in axes.items() if flags},
    }


def analyze(dirs: list[pathlib.Path]) -> dict[str, Any]:
    configs = [load_config(path) for path in dirs]
    result: dict[str, Any] = {"schema_version": 1, "per_config": {}}
    for config in configs:
        block: dict[str, Any] = {}
        for outcome in OUTCOMES:
            rows = _per_step_rows(config, outcome)
            freeze = _freezing_step(rows)
            pre_freeze_states = [
                state for state in config["states"]
                if freeze is None or state["step"] < freeze
            ]
            avoidable = [
                row for row in rows
                if (freeze is None or row["step"] < freeze)
                and row["control_outcome"] is not None
                and row["outcome_max"] > row["control_outcome"]
            ]
            block[outcome] = {
                "per_step": rows,
                "freezing_step": freeze,
                "pre_freeze_states_with_better_sibling": len(avoidable),
                "pre_freeze_states": sum(
                    1 for row in rows if freeze is None or row["step"] < freeze
                ),
                "avoidable_gap_total": sum(
                    row["best_minus_control"] for row in avoidable
                ),
                "mechanism_pre_freeze": _mechanism(pre_freeze_states, outcome),
            }
        result["per_config"][config["task_id"]] = block
    pooled: dict[str, Any] = {}
    for outcome in OUTCOMES:
        all_states = [
            state for config in configs for state in config["states"]
        ]
        pooled[outcome] = _mechanism(all_states, outcome)
    result["pooled_mechanism_all_steps"] = pooled
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels-dir", action="append", type=pathlib.Path,
                        required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path)
    args = parser.parse_args()
    result = analyze(args.labels_dir)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    if args.markdown_output:
        lines = ["# Freezing point and suicide mechanism", ""]
        for task_id, block in result["per_config"].items():
            lines.append(f"## {task_id}")
            for outcome in OUTCOMES:
                data = block[outcome]
                lines += [
                    "",
                    f"### final {outcome}",
                    f"- freezing step: {data['freezing_step']}",
                    (
                        f"- pre-freeze states with a strictly better sibling: "
                        f"{data['pre_freeze_states_with_better_sibling']}/"
                        f"{data['pre_freeze_states']}"
                        f" (total avoidable gap {data['avoidable_gap_total']:.3f})"
                    ),
                ]
                for axis, stats in data["mechanism_pre_freeze"].items():
                    lines.append(
                        f"- {axis}: better branch higher in "
                        f"{stats['better_branch_higher']}/{stats['decided_pairs']}"
                        f" (p={stats['exact_two_sided_p']:.4g})"
                    )
            lines.append("")
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text("\n".join(lines), encoding="utf-8")
    print(args.json_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
