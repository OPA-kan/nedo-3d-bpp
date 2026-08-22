"""Compare two candidate-support PUCT convergence aggregates."""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any


def compare_rescue(
    baseline: dict[str, Any], rescue: dict[str, Any],
) -> dict[str, Any]:
    rescue_limits = [
        int(value)
        for value in rescue.get("reference_candidate_rescue_limits", [])
        if value is not None and int(value) > 0
    ]
    provider_zero_limits = [
        int(value)
        for value in rescue.get(
            "reference_provider_zero_rescue_limits", []
        )
        if value is not None and int(value) > 0
    ]
    if not rescue_limits and not provider_zero_limits:
        raise ValueError(
            "rescue aggregate does not declare a positive candidate rescue "
            "limit or provider-zero rescue limit"
        )
    baseline_roots = {
        str(row["root_id"]): row for row in baseline.get("roots", [])
    }
    rescue_roots = {
        str(row["root_id"]): row for row in rescue.get("roots", [])
    }
    if set(baseline_roots) != set(rescue_roots):
        missing = sorted(set(baseline_roots) - set(rescue_roots))
        extra = sorted(set(rescue_roots) - set(baseline_roots))
        raise ValueError(
            f"baseline/rescue root sets differ: missing={missing} extra={extra}"
        )

    rows = []
    for root_id in sorted(baseline_roots):
        left = baseline_roots[root_id]
        right = rescue_roots[root_id]
        left_signature = left["reference_signature"]
        right_signature = right["reference_signature"]
        rows.append({
            "root_id": root_id,
            "case_id": right.get("case_id") or left.get("case_id"),
            "step": right.get("step") if right.get("step") is not None else left.get("step"),
            "baseline_q_top": left_signature.get("q_top"),
            "rescue_q_top": right_signature.get("q_top"),
            "baseline_visit_top": left_signature.get("visit_top"),
            "rescue_visit_top": right_signature.get("visit_top"),
            "q_top_changed": (
                left_signature.get("q_top") != right_signature.get("q_top")
            ),
            "visit_top_changed": (
                left_signature.get("visit_top")
                != right_signature.get("visit_top")
            ),
            "baseline_q_top_stable": bool(left.get("bounded_q_top_stable")),
            "rescue_q_top_stable": bool(right.get("bounded_q_top_stable")),
        })

    rescue_summary = rescue.get("reference_candidate_rescue_summary", {})
    provider_zero_summary = rescue.get(
        "reference_provider_zero_rescue_summary", {}
    )
    result = {
        "schema_version": 1,
        "experiment": "searchable_candidate_support_comparison",
        "matched_roots": len(rows),
        "candidate_rescue_limits": sorted(set(rescue_limits)),
        "provider_zero_rescue_limits": sorted(set(provider_zero_limits)),
        "provider_zero_rescue_strides": [
            int(value) for value in rescue.get(
                "reference_provider_zero_rescue_strides", []
            )
        ],
        "baseline_censored_exhaustion_events": int(
            baseline.get("reference_censored_exhaustion_events", 0)
        ),
        "rescue_censored_exhaustion_events": int(
            rescue.get("reference_censored_exhaustion_events", 0)
        ),
        "censored_exhaustion_event_delta": int(
            rescue.get("reference_censored_exhaustion_events", 0)
        ) - int(baseline.get("reference_censored_exhaustion_events", 0)),
        "baseline_unique_exhausted_nodes": int(
            baseline.get("reference_exhaustion_unique_nodes", 0)
        ),
        "rescue_unique_exhausted_nodes": int(
            rescue.get("reference_exhaustion_unique_nodes", 0)
        ),
        "unique_exhausted_node_delta": int(
            rescue.get("reference_exhaustion_unique_nodes", 0)
        ) - int(baseline.get("reference_exhaustion_unique_nodes", 0)),
        "searchable_rescue_nodes": int(
            rescue_summary.get("applied_nodes", 0)
        ),
        "searchable_recovered_candidates": int(
            rescue_summary.get("recovered_candidates", 0)
        ),
        "provider_zero_rescue_nodes": int(
            provider_zero_summary.get("applied_nodes", 0)
        ),
        "provider_zero_recovered_candidates": int(
            provider_zero_summary.get("recovered_candidates", 0)
        ),
        "provider_zero_physical_checks": int(
            provider_zero_summary.get("physical_checks", 0)
        ),
        "provider_zero_physical_rejections": int(
            provider_zero_summary.get("physical_rejections", 0)
        ),
        "reference_q_top_changed_roots": sum(
            row["q_top_changed"] for row in rows
        ),
        "reference_visit_top_changed_roots": sum(
            row["visit_top_changed"] for row in rows
        ),
        "bounded_q_top_stable_root_delta": int(
            rescue.get("bounded_q_top_stable_roots", 0)
        ) - int(baseline.get("bounded_q_top_stable_roots", 0)),
        "bounded_visit_top_stable_root_delta": int(
            rescue.get("bounded_visit_top_stable_roots", 0)
        ) - int(baseline.get("bounded_visit_top_stable_roots", 0)),
        "bounded_q_order_stable_root_delta": int(
            rescue.get("bounded_q_order_stable_roots", 0)
        ) - int(baseline.get("bounded_q_order_stable_roots", 0)),
        "caveat": (
            "A changed root action is not automatically an improvement. Both "
            "arms are compared to bounded deep references under their own "
            "candidate support; fresh trajectory outcome remains required."
        ),
        "roots": rows,
    }
    return result


def render_markdown(result: dict[str, Any]) -> str:
    return "\n".join([
        "# Searchable candidate-support comparison",
        "",
        f"- matched roots: {result['matched_roots']}",
        f"- censored exhaustion events: {result['baseline_censored_exhaustion_events']} -> {result['rescue_censored_exhaustion_events']} ({result['censored_exhaustion_event_delta']:+d})",
        f"- unique exhausted nodes: {result['baseline_unique_exhausted_nodes']} -> {result['rescue_unique_exhausted_nodes']} ({result['unique_exhausted_node_delta']:+d})",
        f"- searchable rescue nodes: {result['searchable_rescue_nodes']}",
        f"- recovered candidates entering search: {result['searchable_recovered_candidates']}",
        f"- provider-zero stride rescue nodes: {result['provider_zero_rescue_nodes']}",
        f"- provider-zero rescue strides: {result['provider_zero_rescue_strides']}",
        f"- provider-zero lazy physical checks: {result['provider_zero_physical_checks']}",
        f"- provider-zero physical rejections: {result['provider_zero_physical_rejections']}",
        f"- deep-reference Q-top changed roots: {result['reference_q_top_changed_roots']}",
        f"- deep-reference visit-top changed roots: {result['reference_visit_top_changed_roots']}",
        f"- bounded Q-top stability delta: {result['bounded_q_top_stable_root_delta']:+d}",
        f"- bounded visit-top stability delta: {result['bounded_visit_top_stable_root_delta']:+d}",
        f"- bounded full Q-order stability delta: {result['bounded_q_order_stable_root_delta']:+d}",
        "",
        f"> {result['caveat']}",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=pathlib.Path, required=True)
    parser.add_argument("--rescue", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    result = compare_rescue(
        json.loads(args.baseline.read_text(encoding="utf-8")),
        json.loads(args.rescue.read_text(encoding="utf-8")),
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(render_markdown(result), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
