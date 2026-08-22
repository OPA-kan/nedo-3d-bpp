"""Measure bounded physical-PUCT stability across search budgets and horizons."""

from __future__ import annotations

import argparse
import json
import math
import pathlib
from typing import Any


Q_TOLERANCE = 1e-12


def _sign(value: float) -> int:
    if abs(value) <= Q_TOLERANCE:
        return 0
    return 1 if value > 0.0 else -1


def policy_signature(policy_target: list[dict[str, Any]]) -> dict[str, Any]:
    """Return coefficient-free order statistics for one root policy."""
    rows = sorted(policy_target, key=lambda row: str(row["candidate_id"]))
    visited = [row for row in rows if row.get("q") is not None]
    q_top = None
    if visited:
        q_top = max(
            visited,
            key=lambda row: (
                float(row["q"]),
                int(row.get("visits", 0)),
                -int(row.get("rank", 10**9)),
                str(row["candidate_id"]),
            ),
        )["candidate_id"]
    visit_top = None
    if rows:
        visit_top = max(
            rows,
            key=lambda row: (
                int(row.get("visits", 0)),
                float(row["q"]) if row.get("q") is not None else -math.inf,
                -int(row.get("rank", 10**9)),
                str(row["candidate_id"]),
            ),
        )["candidate_id"]
    relations = {}
    for index, left in enumerate(rows):
        for right in rows[index + 1:]:
            key = f"{left['candidate_id']}|{right['candidate_id']}"
            if left.get("q") is None or right.get("q") is None:
                relations[key] = None
            else:
                relations[key] = _sign(float(left["q"]) - float(right["q"]))
    return {
        "q_top": q_top,
        "visit_top": visit_top,
        "q_relations": relations,
    }


def _canonical_policy(policy_target: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = ("candidate_id", "rank", "base_prior", "prior", "visits", "probability", "q")
    return [
        {key: row.get(key) for key in keys}
        for row in sorted(policy_target, key=lambda row: str(row["candidate_id"]))
    ]


def _same_signature(conditions: dict[str, dict[str, Any]], labels: tuple[str, ...]) -> bool:
    signatures = [
        policy_signature(conditions[label]["policy_target"])
        for label in labels
    ]
    return all(signature == signatures[0] for signature in signatures[1:])


def _same_component(
    conditions: dict[str, dict[str, Any]], labels: tuple[str, ...], key: str,
) -> bool:
    values = [
        policy_signature(conditions[label]["policy_target"])[key]
        for label in labels
    ]
    return all(value == values[0] for value in values[1:])


def _distribution(policy_target: list[dict[str, Any]]) -> dict[str, float]:
    rows = {str(row["candidate_id"]): float(row.get("probability", 0.0)) for row in policy_target}
    total = sum(rows.values())
    if total <= 0.0:
        return {key: 0.0 for key in rows}
    return {key: value / total for key, value in rows.items()}


def _js_distance(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> float:
    p = _distribution(left)
    q = _distribution(right)
    identifiers = sorted(set(p) | set(q))
    midpoint = {key: 0.5 * (p.get(key, 0.0) + q.get(key, 0.0)) for key in identifiers}

    def divergence(source: dict[str, float]) -> float:
        return sum(
            value * math.log(value / midpoint[key])
            for key, value in source.items()
            if value > 0.0 and midpoint[key] > 0.0
        )

    return math.sqrt(max(0.0, 0.5 * (divergence(p) + divergence(q))))


def _max_q_delta(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> float | None:
    p = {str(row["candidate_id"]): row.get("q") for row in left}
    q = {str(row["candidate_id"]): row.get("q") for row in right}
    deltas = [
        abs(float(p[key]) - float(q[key]))
        for key in sorted(set(p) & set(q))
        if p[key] is not None and q[key] is not None
    ]
    return max(deltas) if deltas else None


def _root_result(root: dict[str, Any]) -> dict[str, Any]:
    conditions = root["conditions"]
    deterministic = _canonical_policy(conditions["h2-s12-a"]["policy_target"]) == _canonical_policy(
        conditions["h2-s12-b"]["policy_target"]
    )
    base_budget_stable = _same_signature(conditions, ("h2-s24", "h2-s48"))
    base_horizon_stable = _same_signature(conditions, ("h2-s48", "h3-s48", "h5-s48"))
    promoted = bool(root.get("promoted"))
    if promoted:
        high_horizon_stable = _same_signature(
            conditions, ("h2-s96", "h3-s96", "h5-s96")
        )
        deepest_budget_stable = _same_signature(conditions, ("h5-s48", "h5-s96"))
        bounded_search_stable = high_horizon_stable and deepest_budget_stable
        reference_label = "h5-s96"
    else:
        high_horizon_stable = None
        deepest_budget_stable = None
        bounded_search_stable = base_budget_stable and base_horizon_stable
        reference_label = "h5-s48"
    if promoted:
        bounded_labels = ("h2-s96", "h3-s96", "h5-s96")
        deepest_labels = ("h5-s48", "h5-s96")
    else:
        bounded_labels = ("h2-s24", "h2-s48", "h3-s48", "h5-s48")
        deepest_labels = ()
    bounded_components = {}
    for key in ("q_top", "visit_top", "q_relations"):
        bounded_components[key] = _same_component(
            conditions, bounded_labels, key
        ) and (
            not deepest_labels
            or _same_component(conditions, deepest_labels, key)
        )
    reference = conditions[reference_label]["policy_target"]
    reference_search = conditions[reference_label]
    reference_terminal_reasons = reference_search.get(
        "simulation_terminal_reasons", {}
    )
    reference_shadow = reference_search.get(
        "candidate_exhaustion_shadow_summary", {}
    )
    reference_rescue = reference_search.get("candidate_rescue_summary", {})
    reference_provider_zero = reference_search.get(
        "provider_zero_rescue_summary", {}
    )
    reference_signature = policy_signature(reference)
    reference_q_values = {
        round(float(row["q"]), 12)
        for row in reference
        if row.get("q") is not None and int(row.get("visits", 0)) > 0
    }
    comparisons = {}
    for label, condition in sorted(conditions.items()):
        if label == reference_label:
            continue
        comparisons[label] = {
            "visit_js_distance_to_reference": _js_distance(
                condition["policy_target"], reference
            ),
            "max_abs_q_delta_to_reference": _max_q_delta(
                condition["policy_target"], reference
            ),
            "signature_matches_reference": (
                policy_signature(condition["policy_target"])
                == policy_signature(reference)
            ),
        }
    return {
        "root_id": root["root_id"],
        "case_id": root.get("case_id"),
        "trajectory_id": root.get("trajectory_id"),
        "step": root.get("step"),
        "model_visible_state_signature": root.get("model_visible_state_signature"),
        "game_state_signature": root.get("game_state_signature"),
        "deterministic_repeat": deterministic,
        "base_budget_stable": base_budget_stable,
        "base_horizon_stable": base_horizon_stable,
        "promoted": promoted,
        "high_budget_horizon_stable": high_horizon_stable,
        "deepest_horizon_budget_stable": deepest_budget_stable,
        "bounded_search_stable": bounded_search_stable,
        "bounded_q_top_stable": bounded_components["q_top"],
        "bounded_visit_top_stable": bounded_components["visit_top"],
        "bounded_q_order_stable": bounded_components["q_relations"],
        "reference_condition": reference_label,
        "reference_signature": reference_signature,
        "reference_q_discriminating": len(reference_q_values) > 1,
        "reference_q_top_matches_visit_top": (
            reference_signature["q_top"] == reference_signature["visit_top"]
        ),
        "original_q_top_matches_reference": (
            policy_signature(root["original_search"]["policy_target"])["q_top"]
            == reference_signature["q_top"]
        ),
        "reference_censored_exhaustion_events": int(
            reference_terminal_reasons.get(
                "bounded_candidate_exhaustion_censored", 0
            )
        ),
        "reference_exhaustion_unique_nodes": int(
            reference_search.get("candidate_exhaustion_unique_nodes", 0)
        ),
        "reference_exhaustion_shadow_summary": {
            key: int(reference_shadow.get(key, 0))
            for key in (
                "audited_nodes",
                "top_k_proposal_empty_nodes",
                "top_k_all_rejected_nodes",
                "wider_safe_recovered_nodes",
                "wider_proposal_empty_nodes",
                "wider_all_rejected_nodes",
                "prefix_mismatch_nodes",
            )
        },
        "reference_candidate_rescue_summary": {
            key: int(reference_rescue.get(key, 0))
            for key in ("applied_nodes", "recovered_candidates")
        },
        "reference_candidate_rescue_limit": (
            int(reference_search["candidate_rescue_limit"])
            if reference_search.get("candidate_rescue_limit") is not None
            else None
        ),
        "reference_provider_zero_rescue_summary": {
            key: int(reference_provider_zero.get(key, 0))
            for key in (
                "attempted_nodes",
                "applied_nodes",
                "generated_candidates",
                "recovered_candidates",
                "physical_checks",
                "physical_rejections",
            )
        },
        "reference_provider_zero_rescue_limit": (
            int(reference_search["provider_zero_rescue_limit"])
            if reference_search.get("provider_zero_rescue_limit") is not None
            else None
        ),
        "reference_provider_zero_rescue_safe_limit": (
            int(reference_search["provider_zero_rescue_safe_limit"])
            if reference_search.get("provider_zero_rescue_safe_limit") is not None
            else None
        ),
        "reference_provider_zero_rescue_stride": (
            int(reference_search["provider_zero_rescue_stride"])
            if reference_search.get("provider_zero_rescue_stride") is not None
            else None
        ),
        "comparisons": comparisons,
    }


def aggregate_convergence(
    payloads: list[dict[str, Any]], *, expected_roots: int | None = None,
) -> dict[str, Any]:
    incomplete = [
        payload.get("shard_index")
        for payload in payloads if payload.get("complete") is not True
    ]
    if incomplete:
        raise ValueError(f"incomplete convergence shards: {incomplete}")
    roots = [root for payload in payloads for root in payload.get("roots", [])]
    identifiers = [str(root["root_id"]) for root in roots]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("duplicate convergence root_id across shards")
    if expected_roots is not None and len(roots) != expected_roots:
        raise ValueError(f"expected {expected_roots} roots, got {len(roots)}")
    rows = [_root_result(root) for root in sorted(roots, key=lambda row: row["root_id"])]
    deterministic = sum(row["deterministic_repeat"] for row in rows)
    promoted = sum(row["promoted"] for row in rows)
    stable = sum(row["bounded_search_stable"] for row in rows)
    state_groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get("game_state_signature") or row["root_id"])
        state_groups.setdefault(key, []).append(row)
    stable_state_groups = sum(
        all(row["bounded_search_stable"] for row in group)
        for group in state_groups.values()
    )
    shadow_keys = (
        "audited_nodes",
        "top_k_proposal_empty_nodes",
        "top_k_all_rejected_nodes",
        "wider_safe_recovered_nodes",
        "wider_proposal_empty_nodes",
        "wider_all_rejected_nodes",
        "prefix_mismatch_nodes",
    )
    reference_shadow_summary = {
        key: sum(
            row["reference_exhaustion_shadow_summary"][key]
            for row in rows
        )
        for key in shadow_keys
    }
    reference_candidate_rescue_summary = {
        key: sum(
            row["reference_candidate_rescue_summary"][key]
            for row in rows
        )
        for key in ("applied_nodes", "recovered_candidates")
    }
    reference_candidate_rescue_limits = sorted({
        row["reference_candidate_rescue_limit"]
        for row in rows
        if row["reference_candidate_rescue_limit"] is not None
    })
    provider_zero_keys = (
        "attempted_nodes",
        "applied_nodes",
        "generated_candidates",
        "recovered_candidates",
        "physical_checks",
        "physical_rejections",
    )
    reference_provider_zero_rescue_summary = {
        key: sum(
            row["reference_provider_zero_rescue_summary"][key]
            for row in rows
        )
        for key in provider_zero_keys
    }
    reference_provider_zero_rescue_limits = sorted({
        row["reference_provider_zero_rescue_limit"]
        for row in rows
        if row["reference_provider_zero_rescue_limit"] is not None
    })
    reference_provider_zero_rescue_safe_limits = sorted({
        row["reference_provider_zero_rescue_safe_limit"]
        for row in rows
        if row["reference_provider_zero_rescue_safe_limit"] is not None
    })
    reference_provider_zero_rescue_strides = sorted({
        row["reference_provider_zero_rescue_stride"]
        for row in rows
        if row["reference_provider_zero_rescue_stride"] is not None
    })
    return {
        "schema_version": 1,
        "experiment": "targeted_physical_puct_convergence",
        "root_count": len(rows),
        "unique_model_visible_states": len({
            row["model_visible_state_signature"]
            for row in rows if row.get("model_visible_state_signature")
        }),
        "unique_game_states": len({
            row["game_state_signature"]
            for row in rows if row.get("game_state_signature")
        }),
        "game_state_group_count": len(state_groups),
        "bounded_search_stable_game_state_groups": stable_state_groups,
        "deterministic_repeat_roots": deterministic,
        "instrument_deterministic": deterministic == len(rows),
        "base_budget_stable_roots": sum(row["base_budget_stable"] for row in rows),
        "base_horizon_stable_roots": sum(row["base_horizon_stable"] for row in rows),
        "promoted_roots": promoted,
        "bounded_search_stable_roots": stable,
        "bounded_q_top_stable_roots": sum(
            row["bounded_q_top_stable"] for row in rows
        ),
        "bounded_visit_top_stable_roots": sum(
            row["bounded_visit_top_stable"] for row in rows
        ),
        "bounded_q_order_stable_roots": sum(
            row["bounded_q_order_stable"] for row in rows
        ),
        "reference_q_discriminating_roots": sum(
            row["reference_q_discriminating"] for row in rows
        ),
        "reference_q_top_matches_visit_top_roots": sum(
            row["reference_q_top_matches_visit_top"] for row in rows
        ),
        "original_q_top_matches_reference_roots": sum(
            row["original_q_top_matches_reference"] for row in rows
        ),
        "reference_censored_exhaustion_events": sum(
            row["reference_censored_exhaustion_events"] for row in rows
        ),
        "reference_exhaustion_unique_nodes": sum(
            row["reference_exhaustion_unique_nodes"] for row in rows
        ),
        "reference_exhaustion_shadow_summary": reference_shadow_summary,
        "reference_candidate_rescue_summary": (
            reference_candidate_rescue_summary
        ),
        "reference_candidate_rescue_limits": (
            reference_candidate_rescue_limits
        ),
        "reference_provider_zero_rescue_summary": (
            reference_provider_zero_rescue_summary
        ),
        "reference_provider_zero_rescue_limits": (
            reference_provider_zero_rescue_limits
        ),
        "reference_provider_zero_rescue_safe_limits": (
            reference_provider_zero_rescue_safe_limits
        ),
        "reference_provider_zero_rescue_strides": (
            reference_provider_zero_rescue_strides
        ),
        "bounded_search_stable_fraction": stable / len(rows) if rows else 0.0,
        "caveat": (
            "Stability means agreement inside the measured bounded PUCT schedule; "
            "it does not establish convergence to Q* or an unbounded-search oracle."
        ),
        "roots": rows,
    }


def render_markdown(result: dict[str, Any]) -> str:
    shadow = result["reference_exhaustion_shadow_summary"]
    rescue = result["reference_candidate_rescue_summary"]
    provider_zero = result["reference_provider_zero_rescue_summary"]
    lines = [
        "# Targeted physical-PUCT convergence",
        "",
        f"- roots: {result['root_count']}",
        f"- unique model-visible states: {result['unique_model_visible_states']}",
        f"- unique game-state signatures: {result['unique_game_states']}",
        f"- deterministic repeats: {result['deterministic_repeat_roots']} / {result['root_count']}",
        f"- stable at H2 S24→S48: {result['base_budget_stable_roots']} / {result['root_count']}",
        f"- stable across H2/H3/H5 at S48: {result['base_horizon_stable_roots']} / {result['root_count']}",
        f"- promoted to S96: {result['promoted_roots']}",
        f"- bounded-search stable after schedule: {result['bounded_search_stable_roots']} / {result['root_count']}",
        f"- bounded Q-top stable: {result['bounded_q_top_stable_roots']} / {result['root_count']}",
        f"- bounded visit-top stable: {result['bounded_visit_top_stable_roots']} / {result['root_count']}",
        f"- bounded full Q-order stable: {result['bounded_q_order_stable_roots']} / {result['root_count']}",
        f"- still Q-discriminating at reference: {result['reference_q_discriminating_roots']} / {result['root_count']}",
        f"- original Q-top agrees with reference: {result['original_q_top_matches_reference_roots']} / {result['root_count']}",
        f"- stable unique game-state groups: {result['bounded_search_stable_game_state_groups']} / {result['game_state_group_count']}",
        f"- censored exhaustion visits at reference: {result['reference_censored_exhaustion_events']}",
        f"- unique exhausted nodes at reference: {result['reference_exhaustion_unique_nodes']}",
        f"- shadow-audited exhausted nodes: {shadow['audited_nodes']}",
        f"- wider safe candidate recovered: {shadow['wider_safe_recovered_nodes']}",
        f"- wider provider still empty: {shadow['wider_proposal_empty_nodes']}",
        f"- wider proposals all physically rejected: {shadow['wider_all_rejected_nodes']}",
        f"- shadow prefix mismatches: {shadow['prefix_mismatch_nodes']}",
        f"- searchable rescue nodes at reference: {rescue['applied_nodes']}",
        f"- provider-zero stride rescue nodes: {provider_zero['applied_nodes']}",
        f"- provider-zero lazy physical checks: {provider_zero['physical_checks']}",
        f"- provider-zero physical rejections before first safe: {provider_zero['physical_rejections']}",
        f"- searchable recovered candidates: {rescue['recovered_candidates']}",
        "",
        f"> {result['caveat']}",
        "",
        "## Unstable roots",
        "",
        "| root | case | step | promoted | deterministic | reference |",
        "|---|---|---:|---:|---:|---|",
    ]
    unstable = [row for row in result["roots"] if not row["bounded_search_stable"]]
    for row in unstable:
        lines.append(
            f"| `{row['root_id']}` | {row.get('case_id') or ''} | "
            f"{row.get('step', '')} | {row['promoted']} | "
            f"{row['deterministic_repeat']} | {row['reference_condition']} |"
        )
    if not unstable:
        lines.append("| — | — | — | — | — | — |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--expected-roots", type=int)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    paths = sorted(args.root.rglob("convergence-shard-*.json"))
    if not paths:
        raise SystemExit(f"no convergence shard files below {args.root}")
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    result = aggregate_convergence(payloads, expected_roots=args.expected_roots)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.markdown_output.write_text(render_markdown(result), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
