"""Aggregate provider-zero rescue shards and report recall/cost/attributes."""

from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
from typing import Any


def wilson_interval(successes: int, total: int) -> list[float]:
    if total == 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    p = successes / total
    denominator = 1.0 + z * z / total
    centre = (p + z * z / (2.0 * total)) / denominator
    half = z * math.sqrt(
        p * (1.0 - p) / total + z * z / (4.0 * total * total)
    ) / denominator
    return [max(0.0, centre - half), min(1.0, centre + half)]


def _attribute_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    keys = (
        "priority_routing_violation",
        "priority_violations_direct",
        "soft_violations_direct",
        "priority_violations_stack",
        "soft_violations_stack",
    )
    result = {}
    for key in keys:
        values = [
            row.get("selection", {}).get(key) for row in candidates
            if row.get("selection", {}).get(key) is not None
        ]
        result[f"{key}_candidates"] = sum(int(value) > 0 for value in values)
        result[f"{key}_events"] = sum(int(value) for value in values)
    return result


ATTRIBUTE_KEYS = (
    "priority_routing_violation",
    "priority_violations_direct",
    "soft_violations_direct",
    "priority_violations_stack",
    "soft_violations_stack",
)


def _is_clean(candidate: dict[str, Any]) -> bool:
    selection = candidate.get("selection", {})
    return all(selection.get(key) == 0 for key in ATTRIBUTE_KEYS)


def _first_safe_rank(row: dict[str, Any], name: str) -> int | None:
    ranks = [
        candidate.get("selection", {}).get("rank")
        for candidate in row["strategies"][name]["safe_candidates"]
    ]
    numeric = [int(rank) for rank in ranks if rank is not None]
    return min(numeric) if numeric else None


def evaluate(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    incomplete = [
        payload.get("shard_index") for payload in payloads
        if payload.get("complete") is not True
    ]
    if incomplete:
        raise ValueError(f"incomplete provider rescue shards: {incomplete}")
    states = [row for payload in payloads for row in payload.get("states", [])]
    boards = [str(row["board_fingerprint"]) for row in states]
    if len(set(boards)) != len(boards):
        raise ValueError("duplicate board_fingerprint across rescue shards")
    strategy_names = sorted({
        name for row in states for name in row.get("strategies", {})
    })
    strategies = {}
    for name in strategy_names:
        rows = [row for row in states if name in row.get("strategies", {})]
        rescued = [row for row in rows if row["strategies"][name]["rescued"]]
        occurrence_total = sum(int(row["occurrence_count"]) for row in rows)
        occurrence_rescued = sum(
            int(row["occurrence_count"]) for row in rescued
        )
        candidates = [
            candidate
            for row in rows
            for candidate in row["strategies"][name]["safe_candidates"]
        ]
        first_safe_ranks = {
            str(row["board_fingerprint"]): _first_safe_rank(row, name)
            for row in rows
        }
        rank0_safe_boards = sum(
            rank == 0 for rank in first_safe_ranks.values()
        )
        lazy_checks = sum(
            (
                int(first_safe_ranks[str(row["board_fingerprint"])]) + 1
                if first_safe_ranks[str(row["board_fingerprint"])] is not None
                else int(row["strategies"][name]["proposal_count"])
            )
            for row in rows
        )
        clean_candidates = [row for row in candidates if _is_clean(row)]
        clean_boards = sum(
            any(_is_clean(candidate) for candidate in row["strategies"][name]["safe_candidates"])
            for row in rows
        )
        by_case = {}
        for case_id in sorted({str(row["case_id"]) for row in rows}):
            case_rows = [row for row in rows if row["case_id"] == case_id]
            case_rescued = sum(
                row["strategies"][name]["rescued"] for row in case_rows
            )
            by_case[case_id] = {
                "boards": len(case_rows),
                "rescued_boards": int(case_rescued),
                "board_recall": case_rescued / len(case_rows),
            }
        strategies[name] = {
            "boards": len(rows),
            "rescued_boards": len(rescued),
            "board_recall": len(rescued) / len(rows) if rows else 0.0,
            "board_recall_wilson95": wilson_interval(len(rescued), len(rows)),
            "weighted_node_occurrences": occurrence_total,
            "rescued_node_occurrences": occurrence_rescued,
            "node_weighted_recall": (
                occurrence_rescued / occurrence_total
                if occurrence_total else 0.0
            ),
            "proposal_count": sum(
                row["strategies"][name]["proposal_count"] for row in rows
            ),
            "safe_candidate_count": len(candidates),
            "rank0_safe_boards": int(rank0_safe_boards),
            "rank0_safe_board_rate": (
                rank0_safe_boards / len(rows) if rows else 0.0
            ),
            "lazy_physical_checks_to_first_safe": int(lazy_checks),
            "mean_lazy_physical_checks_per_board": (
                lazy_checks / len(rows) if rows else 0.0
            ),
            "clean_safe_candidate_count": len(clean_candidates),
            "clean_safe_candidate_rate": (
                len(clean_candidates) / len(candidates)
                if candidates else 0.0
            ),
            "boards_with_clean_safe_candidate": int(clean_boards),
            "mean_generation_seconds": (
                sum(row["strategies"][name]["generation_seconds"] for row in rows)
                / len(rows) if rows else 0.0
            ),
            "mean_physical_filter_seconds": (
                sum(
                    row["strategies"][name]["physical_filter_seconds"]
                    for row in rows
                ) / len(rows) if rows else 0.0
            ),
            "attribute_heads": _attribute_counts(candidates),
            "by_case": by_case,
        }
    ranked = sorted(
        strategy_names,
        key=lambda name: (
            -strategies[name]["board_recall"],
            strategies[name]["mean_generation_seconds"],
            name,
        ),
    )
    return {
        "schema_version": 1,
        "experiment": "provider_zero_rescue_evaluation",
        "board_count": len(states),
        "node_occurrence_count": sum(
            int(row["occurrence_count"]) for row in states
        ),
        "all_baselines_confirmed_empty": all(
            row.get("baseline_provider_confirmed_empty") is True
            for row in states
        ),
        "strategy_ranking": ranked,
        "promising_strategies_at_20pct_point_recall": [
            name for name in ranked if strategies[name]["board_recall"] >= 0.20
        ],
        "strategies": strategies,
        "caveat": (
            "This is a stratified provider-zero capability sample. Recall is "
            "not an on-policy score gain, and soft/priority heads are reported "
            "separately rather than collapsed into a local exchange rate."
        ),
    }


def markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Provider-zero rescue benchmark",
        "",
        f"- unique boards: {result['board_count']}",
        f"- represented exhausted nodes: {result['node_occurrence_count']}",
        "- baseline provider empty on every replay: "
        f"{result['all_baselines_confirmed_empty']}",
        "",
        "| strategy | rescued boards | board recall | node-weighted recall | "
        "rank-0 safe | lazy checks | clean safe rate | safe candidates | "
        "mean generation s | mean physics-filter s |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in result["strategy_ranking"]:
        row = result["strategies"][name]
        lines.append(
            f"| {name} | {row['rescued_boards']}/{row['boards']} | "
            f"{row['board_recall']:.3f} | {row['node_weighted_recall']:.3f} | "
            f"{row['rank0_safe_boards']}/{row['boards']} | "
            f"{row['lazy_physical_checks_to_first_safe']} | "
            f"{row['clean_safe_candidate_rate']:.3f} | "
            f"{row['safe_candidate_count']} | "
            f"{row['mean_generation_seconds']:.3f} | "
            f"{row['mean_physical_filter_seconds']:.3f} |"
        )
    lines.extend(["", f"> {result['caveat']}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    paths = sorted(args.root.glob("provider-rescue-shard-*.json"))
    if not paths:
        raise SystemExit(f"no provider rescue shards below {args.root}")
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    result = evaluate(payloads)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.markdown_output.write_text(markdown(result), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
