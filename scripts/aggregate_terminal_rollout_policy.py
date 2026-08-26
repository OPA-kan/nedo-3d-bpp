"""Aggregate paired legacy versus V-free terminal-rollout policy episodes."""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
from typing import Any

# surface_total_variation stays out of the win/loss decision (it is
# still tracked below in REPORT_METRICS/REPORT_DIRECTIONS) — see the
# matching comment on DOMINANCE_HEADS in run_vector_mcts.py.
OBJECTIVE_METRICS = {
    "fill_score_proxy": +1.0,
    "soft_covered_by_other": -1.0,
    "priority_covered_by_other": -1.0,
    "priority_misrouted": -1.0,
}
REPORT_METRICS = (
    "placed_count",
    "fill_score_proxy",
    "center_of_mass_z",
    "soft_covered_by_other",
    "priority_covered_by_other",
    "priority_misrouted",
    "surface_total_variation",
    "post_shake_max_shift",
    "post_shake_peak_kinetic_energy",
    "post_shake_items_toppled",
)
REPORT_DIRECTIONS = {
    "placed_count": +1.0,
    "fill_score_proxy": +1.0,
    "center_of_mass_z": -1.0,
    "soft_covered_by_other": -1.0,
    "priority_covered_by_other": -1.0,
    "priority_misrouted": -1.0,
    "surface_total_variation": -1.0,
    "post_shake_max_shift": -1.0,
    "post_shake_peak_kinetic_energy": -1.0,
    "post_shake_items_toppled": -1.0,
}
EPS = 1e-9
BEHAVIOR_CONTRACTS = {
    "single_agent_terminal_rollout_policy_v2_item_symmetry",
    "single_agent_terminal_rollout_policy_v3_wall_clock",
}
TIMING_PHASES = (
    "state_capture_seconds",
    "provider_seconds",
    "search_seconds",
    "selection_seconds",
    "live_action_seconds",
)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(
        ordered[lower] * (1.0 - weight) + ordered[upper] * weight,
        12,
    )


def summarize_decision_timings(
    records: list[dict[str, Any]], *, sla_seconds: float = 10.0,
) -> dict[str, Any]:
    timings = [
        record.get("timing") or {} for record in records
        if isinstance((record.get("timing") or {}).get(
            "decision_total_seconds"
        ), (int, float))
    ]
    values = [float(row["decision_total_seconds"]) for row in timings]
    within = sum(value <= sla_seconds for value in values)
    return {
        "contract": "decision_wall_clock_summary_v1",
        "decision_count": len(values),
        "sla_seconds": float(sla_seconds),
        "mean_seconds": sum(values) / len(values) if values else None,
        "p50_seconds": _percentile(values, 0.50),
        "p90_seconds": _percentile(values, 0.90),
        "p95_seconds": _percentile(values, 0.95),
        "max_seconds": max(values) if values else None,
        "within_sla_count": within,
        "within_sla_rate": within / len(values) if values else None,
        "phase_total_seconds": {
            phase: sum(float(row.get(phase, 0.0)) for row in timings)
            for phase in TIMING_PHASES
        },
        "decision_seconds": values,
    }


def _episode(payload: dict[str, Any], *, policy: str, cell: str):
    if payload.get("behavior_contract") not in BEHAVIOR_CONTRACTS:
        raise ValueError(f"{cell}: invalid behavior contract")
    if payload.get("policy") != policy:
        raise ValueError(f"{cell}: expected {policy} manifest")
    if payload.get("value_model") is not None:
        raise ValueError(f"{cell}: rollout policy must not load V")
    episodes = payload.get("episodes") or []
    if len(episodes) != 1:
        raise ValueError(f"{cell}: expected exactly one episode per arm")
    return episodes[0]


def _relation(
    baseline: dict[str, Any], rollout: dict[str, Any],
) -> str:
    differences = []
    for metric, sign in OBJECTIVE_METRICS.items():
        left = baseline.get(metric)
        right = rollout.get(metric)
        if not isinstance(left, (int, float)) or not isinstance(
            right, (int, float)
        ):
            return "unmeasured"
        differences.append(sign * (float(right) - float(left)))
    rollout_non_worse = all(value >= -EPS for value in differences)
    baseline_non_worse = all(value <= EPS for value in differences)
    rollout_strict = any(value > EPS for value in differences)
    baseline_strict = any(value < -EPS for value in differences)
    if rollout_non_worse and rollout_strict:
        return "rollout_dominates"
    if baseline_non_worse and baseline_strict:
        return "baseline_dominates"
    if rollout_non_worse and baseline_non_worse:
        return "equal"
    return "incomparable"


def _arm(episode: dict[str, Any]) -> dict[str, Any]:
    return {
        "steps": int(episode.get("steps", 0)),
        "termination": episode.get("termination"),
        "genuine_termination": bool(episode.get("genuine_termination")),
        "switches": int(episode.get("terminal_dominance_switches", 0)),
        "terminal_truth_complete_roots": int(
            episode.get("terminal_truth_complete_roots", 0)
        ),
        "terminal_truth_censored_roots": int(
            episode.get("terminal_truth_censored_roots", 0)
        ),
        "search_physical_steps": int(
            episode.get("search_physical_steps", 0)
        ),
        "search_physical_step_equivalents": int(
            episode.get("search_physical_step_equivalents", 0)
        ),
        "terminal_rollout_physical_steps": int(
            episode.get("terminal_rollout_physical_steps", 0)
        ),
        "terminal_rollout_physical_step_equivalents": int(
            episode.get("terminal_rollout_physical_step_equivalents", 0)
        ),
        "terminal_rollout_legal_filter_symmetry_reused": int(
            episode.get(
                "terminal_rollout_legal_filter_symmetry_reused", 0
            )
        ),
        "terminal_symmetry_cache_hits": int(
            episode.get("terminal_symmetry_cache_hits", 0)
        ),
        "terminal_symmetry_cache_saved_physical_steps": int(
            episode.get(
                "terminal_symmetry_cache_saved_physical_steps", 0
            )
        ),
        "terminal_symmetry_cache_saved_physical_step_equivalents": int(
            episode.get(
                "terminal_symmetry_cache_saved_physical_step_equivalents",
                0,
            )
        ),
        "final_metrics": episode.get("final_metrics") or {},
        "decision_timing": summarize_decision_timings(
            episode.get("records") or []
        ),
    }


def _combined_timing(cells: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    records = []
    for cell in cells:
        for value in cell[arm]["decision_timing"]["decision_seconds"]:
            records.append({"timing": {"decision_total_seconds": value}})
    summary = summarize_decision_timings(records)
    summary["phase_total_seconds"] = {
        phase: sum(
            float(cell[arm]["decision_timing"]["phase_total_seconds"][phase])
            for cell in cells
        )
        for phase in TIMING_PHASES
    }
    return summary


def compare_pair(
    baseline_payload: dict[str, Any], rollout_payload: dict[str, Any], *,
    cell: str,
) -> dict[str, Any]:
    for field in ("case_id", "environment_seed"):
        if baseline_payload.get(field) != rollout_payload.get(field):
            raise ValueError(f"{cell}: paired {field} differs")
    baseline_episode = _episode(baseline_payload, policy="legacy", cell=cell)
    rollout_episode = _episode(
        rollout_payload, policy="terminal-rollout", cell=cell
    )
    baseline = _arm(baseline_episode)
    rollout = _arm(rollout_episode)
    metric_deltas = {}
    for metric in REPORT_METRICS:
        left = baseline["final_metrics"].get(metric)
        right = rollout["final_metrics"].get(metric)
        metric_deltas[metric] = (
            float(right) - float(left)
            if isinstance(left, (int, float))
            and isinstance(right, (int, float))
            else None
        )
    return {
        "cell": cell,
        "case_id": baseline_payload.get("case_id"),
        "environment_seed": baseline_payload.get("environment_seed"),
        "baseline": baseline,
        "rollout": rollout,
        "step_delta": rollout["steps"] - baseline["steps"],
        "metric_deltas": metric_deltas,
        "terminal_vector_relation": _relation(
            baseline["final_metrics"], rollout["final_metrics"]
        ),
    }


def aggregate(root: pathlib.Path) -> dict[str, Any]:
    cells = []
    for rollout_path in sorted(root.glob("*/rollout.json")):
        baseline_path = rollout_path.with_name("baseline.json")
        if not baseline_path.exists():
            raise FileNotFoundError(
                f"{rollout_path.parent.name}: missing baseline.json"
            )
        cells.append(compare_pair(
            json.loads(baseline_path.read_text(encoding="utf-8")),
            json.loads(rollout_path.read_text(encoding="utf-8")),
            cell=rollout_path.parent.name,
        ))
    if not cells:
        raise ValueError(f"no paired policy cells below {root}")
    relation_counts = collections.Counter(
        cell["terminal_vector_relation"] for cell in cells
    )
    metric_summaries = {}
    for metric in REPORT_METRICS:
        values = [
            cell["metric_deltas"][metric] for cell in cells
            if cell["metric_deltas"][metric] is not None
        ]
        direction = REPORT_DIRECTIONS[metric]
        oriented = [direction * value for value in values]
        metric_summaries[metric] = {
            "paired_cells": len(values),
            "mean_delta": sum(values) / len(values) if values else None,
            "higher_is_better": direction > 0.0,
            "wins": sum(value > EPS for value in oriented),
            "ties": sum(abs(value) <= EPS for value in oriented),
            "losses": sum(value < -EPS for value in oriented),
        }
    return {
        "schema_version": 3,
        "contract": "single_agent_terminal_rollout_policy_ablation_v3_timing",
        "value_model": None,
        "selection": "terminal_pareto_dominance_switch_else_legacy_rank0",
        "timing_sample_scope": (
            "decisions_that_execute_a_live_action"
        ),
        "scalar_utility": None,
        "cell_count": len(cells),
        "cells": cells,
        "relation_counts": dict(sorted(relation_counts.items())),
        "total_switches": sum(cell["rollout"]["switches"] for cell in cells),
        "total_terminal_truth_censored_roots": sum(
            cell["rollout"]["terminal_truth_censored_roots"]
            for cell in cells
        ),
        "total_terminal_rollout_physical_steps": sum(
            cell["rollout"]["terminal_rollout_physical_steps"]
            for cell in cells
        ),
        "total_search_physical_step_equivalents": sum(
            cell["rollout"]["search_physical_step_equivalents"]
            for cell in cells
        ),
        "total_terminal_rollout_physical_step_equivalents": sum(
            cell["rollout"][
                "terminal_rollout_physical_step_equivalents"
            ]
            for cell in cells
        ),
        "total_terminal_rollout_legal_filter_symmetry_reused": sum(
            cell["rollout"][
                "terminal_rollout_legal_filter_symmetry_reused"
            ]
            for cell in cells
        ),
        "total_terminal_symmetry_cache_hits": sum(
            cell["rollout"]["terminal_symmetry_cache_hits"]
            for cell in cells
        ),
        "total_terminal_symmetry_cache_saved_physical_steps": sum(
            cell["rollout"][
                "terminal_symmetry_cache_saved_physical_steps"
            ]
            for cell in cells
        ),
        "total_terminal_symmetry_cache_saved_physical_step_equivalents": sum(
            cell["rollout"][
                "terminal_symmetry_cache_saved_physical_step_equivalents"
            ]
            for cell in cells
        ),
        "mean_step_delta": sum(
            cell["step_delta"] for cell in cells
        ) / len(cells),
        "metric_summaries": metric_summaries,
        "timing_summaries": {
            arm: _combined_timing(cells, arm)
            for arm in ("baseline", "rollout")
        },
    }


def render_markdown(result: dict[str, Any]) -> str:
    rows = [
        "# V-free terminal-rollout policy ablation",
        "",
        f"- cells: **{result['cell_count']}**",
        f"- terminal dominance switches: **{result['total_switches']}**",
        "- terminal-truth censored roots: "
        f"**{result['total_terminal_truth_censored_roots']}**",
        "- terminal rollout physical steps: "
        f"**{result['total_terminal_rollout_physical_steps']}**",
        "- search replay-inclusive physical step equivalents: "
        f"**{result['total_search_physical_step_equivalents']}**",
        "- terminal replay-inclusive physical step equivalents: "
        "**"
        f"{result['total_terminal_rollout_physical_step_equivalents']}"
        "**",
        "- identical-item terminal cache hits: "
        f"**{result['total_terminal_symmetry_cache_hits']}**",
        "- legal-filter physical checks reused by item symmetry: "
        "**"
        f"{result['total_terminal_rollout_legal_filter_symmetry_reused']}"
        "**",
        "- estimated physical steps saved by terminal cache: "
        "**"
        f"{result['total_terminal_symmetry_cache_saved_physical_steps']}"
        "**",
        "- estimated replay-inclusive step equivalents saved by cache: "
        "**"
        f"{result['total_terminal_symmetry_cache_saved_physical_step_equivalents']}"
        "**",
        f"- mean placed-step delta: **{result['mean_step_delta']}**",
        "- V model: **none**",
        "- No scalar utility is constructed; final relations use the raw "
        "terminal component vector.",
        "",
        "## Decision wall-clock",
        "",
        "| arm | decisions | p50 s | p90 s | p95 s | max s | <=10.0s SLA |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for arm in ("baseline", "rollout"):
        timing = result["timing_summaries"][arm]
        rows.append(
            f"| {arm} | {timing['decision_count']} | "
            f"{timing['p50_seconds']} | {timing['p90_seconds']} | "
            f"{timing['p95_seconds']} | {timing['max_seconds']} | "
            f"{timing['within_sla_count']}/{timing['decision_count']} "
            f"({timing['within_sla_rate']}) |"
        )
    rows.extend([
        "",
        "| cell | baseline steps | rollout steps | delta | switches | "
        "terminal relation |",
        "|---|---:|---:|---:|---:|---|",
    ])
    rows.extend(
        f"| {cell['cell']} | {cell['baseline']['steps']} | "
        f"{cell['rollout']['steps']} | {cell['step_delta']} | "
        f"{cell['rollout']['switches']} | "
        f"{cell['terminal_vector_relation']} |"
        for cell in result["cells"]
    )
    rows.extend((
        "",
        "| metric | paired | mean rollout-baseline | wins | ties | losses |",
        "|---|---:|---:|---:|---:|---:|",
    ))
    for metric in REPORT_METRICS:
        summary = result["metric_summaries"][metric]
        rows.append(
            f"| {metric} | {summary['paired_cells']} | "
            f"{summary['mean_delta']} | {summary['wins']} | "
            f"{summary['ties']} | {summary['losses']} |"
        )
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--expected-cells", type=int, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    result = aggregate(args.root)
    if result["cell_count"] != args.expected_cells:
        raise ValueError(
            f"expected {args.expected_cells} cells, "
            f"found {result['cell_count']}"
        )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(render_markdown(result), encoding="utf-8")
    print(args.markdown_output.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
