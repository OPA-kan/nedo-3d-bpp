"""Replay an adaptive no-NN PUCT stopping rule over measured convergence roots.

This evaluator changes no search result. It treats the existing H/S matrix as
an offline trace and asks how early a root could have stopped using only the
Q-top and visit-top decisions available at that point.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_self_play_puct_convergence import policy_signature


CONDITION_COST = {
    "h2-s24": 2 * 24,
    "h2-s48": 2 * 48,
    "h3-s48": 3 * 48,
    "h5-s48": 5 * 48,
    "h2-s96": 2 * 96,
    "h3-s96": 3 * 96,
    "h5-s96": 5 * 96,
}


def _top_signature(condition: dict[str, Any]) -> tuple[str | None, str | None]:
    signature = policy_signature(condition["policy_target"])
    return signature["q_top"], signature["visit_top"]


def _adaptive_choice(root: dict[str, Any]) -> tuple[str, str, list[str]]:
    conditions = root["conditions"]
    required = ("h2-s24", "h2-s48", "h3-s48", "h5-s48")
    missing = [label for label in required if label not in conditions]
    if missing:
        raise ValueError(f"root {root['root_id']} missing conditions: {missing}")
    used = ["h2-s24", "h2-s48"]
    if _top_signature(conditions["h2-s24"]) == _top_signature(
        conditions["h2-s48"]
    ):
        return "h2-s48", "budget_top_confirmed", used

    used.append("h3-s48")
    if _top_signature(conditions["h2-s48"]) == _top_signature(
        conditions["h3-s48"]
    ):
        return "h3-s48", "h3_top_confirmed", used

    used.append("h5-s48")
    if _top_signature(conditions["h3-s48"]) == _top_signature(
        conditions["h5-s48"]
    ):
        return "h5-s48", "h5_top_confirmed", used

    promoted = ("h2-s96", "h3-s96", "h5-s96")
    missing = [label for label in promoted if label not in conditions]
    if missing:
        raise ValueError(
            f"root {root['root_id']} needs unmeasured high-budget conditions: "
            f"{missing}"
        )
    used.extend(promoted)
    return "h5-s96", "high_budget_reference", used


def _horizon_confirmed_choice(
    root: dict[str, Any],
) -> tuple[str, str, list[str]]:
    conditions = root["conditions"]
    used = ["h2-s24", "h2-s48", "h3-s48"]
    if _top_signature(conditions["h2-s48"]) == _top_signature(
        conditions["h3-s48"]
    ):
        return "h3-s48", "h3_top_confirmed", used
    used.append("h5-s48")
    if _top_signature(conditions["h3-s48"]) == _top_signature(
        conditions["h5-s48"]
    ):
        return "h5-s48", "h5_top_confirmed", used
    promoted = ("h2-s96", "h3-s96", "h5-s96")
    missing = [label for label in promoted if label not in conditions]
    if missing:
        raise ValueError(
            f"root {root['root_id']} needs unmeasured high-budget conditions: "
            f"{missing}"
        )
    used.extend(promoted)
    return "h5-s96", "high_budget_reference", used


def _full_order_guarded_choice(
    root: dict[str, Any],
) -> tuple[str, str, list[str]]:
    conditions = root["conditions"]
    base = ["h2-s24", "h2-s48", "h3-s48", "h5-s48"]
    signatures = [
        policy_signature(conditions[label]["policy_target"])
        for label in base
    ]
    if all(signature == signatures[0] for signature in signatures[1:]):
        return "h5-s48", "full_order_base_stable", base
    promoted = ["h2-s96", "h3-s96", "h5-s96"]
    missing = [label for label in promoted if label not in conditions]
    if missing:
        raise ValueError(
            f"root {root['root_id']} needs unmeasured high-budget conditions: "
            f"{missing}"
        )
    return "h5-s96", "full_order_guard_promoted", base + promoted


RULES = {
    "aggressive_budget_top": _adaptive_choice,
    "horizon_top_confirmed": _horizon_confirmed_choice,
    "full_order_guarded": _full_order_guarded_choice,
}


def evaluate_adaptive_schedule(
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

    rows = []
    selected_counts: collections.Counter[str] = collections.Counter()
    rule_rows: dict[str, list[dict[str, Any]]] = {
        name: [] for name in RULES
    }
    for root in sorted(roots, key=lambda row: str(row["root_id"])):
        selected_label, stop_reason, used = _adaptive_choice(root)
        reference_label = "h5-s96" if root.get("promoted") else "h5-s48"
        selected = policy_signature(
            root["conditions"][selected_label]["policy_target"]
        )
        reference = policy_signature(
            root["conditions"][reference_label]["policy_target"]
        )
        reference_shadow = root["conditions"][reference_label].get(
            "candidate_exhaustion_shadow_summary", {}
        )
        selected_counts[selected_label] += 1
        for rule_name, choose in RULES.items():
            rule_label, rule_stop, rule_used = choose(root)
            rule_signature = policy_signature(
                root["conditions"][rule_label]["policy_target"]
            )
            rule_rows[rule_name].append({
                "selected_condition": rule_label,
                "stop_reason": rule_stop,
                "conditions_evaluated": rule_used,
                "q_top_matches_reference": (
                    rule_signature["q_top"] == reference["q_top"]
                ),
                "visit_top_matches_reference": (
                    rule_signature["visit_top"] == reference["visit_top"]
                ),
                "both_tops_match_reference": (
                    rule_signature["q_top"] == reference["q_top"]
                    and rule_signature["visit_top"] == reference["visit_top"]
                ),
                "rollout_step_budget_upper_bound": sum(
                    CONDITION_COST[label] for label in rule_used
                ),
            })
        rows.append({
            "root_id": root["root_id"],
            "case_id": root.get("case_id"),
            "step": root.get("step"),
            "selected_condition": selected_label,
            "stop_reason": stop_reason,
            "conditions_evaluated": used,
            "reference_condition": reference_label,
            "selected_signature": selected,
            "reference_signature": reference,
            "q_top_matches_reference": selected["q_top"] == reference["q_top"],
            "visit_top_matches_reference": (
                selected["visit_top"] == reference["visit_top"]
            ),
            "both_tops_match_reference": (
                selected["q_top"] == reference["q_top"]
                and selected["visit_top"] == reference["visit_top"]
            ),
            "rollout_step_budget_upper_bound": sum(
                CONDITION_COST[label] for label in used
            ),
            "reference_wider_safe_recovered_nodes": int(
                reference_shadow.get("wider_safe_recovered_nodes", 0)
            ),
        })

    count = len(rows)
    q_matches = sum(row["q_top_matches_reference"] for row in rows)
    visit_matches = sum(row["visit_top_matches_reference"] for row in rows)
    both_matches = sum(row["both_tops_match_reference"] for row in rows)
    total_cost = sum(row["rollout_step_budget_upper_bound"] for row in rows)
    rule_comparison = {}
    for rule_name, outcomes in rule_rows.items():
        rule_cost = sum(
            row["rollout_step_budget_upper_bound"] for row in outcomes
        )
        condition_counts = collections.Counter(
            row["selected_condition"] for row in outcomes
        )
        rule_comparison[rule_name] = {
            "both_top_matches_roots": sum(
                row["both_tops_match_reference"] for row in outcomes
            ),
            "q_top_matches_roots": sum(
                row["q_top_matches_reference"] for row in outcomes
            ),
            "visit_top_matches_roots": sum(
                row["visit_top_matches_reference"] for row in outcomes
            ),
            "mean_rollout_step_budget_upper_bound": (
                rule_cost / count if count else 0.0
            ),
            "selected_condition_counts": {
                label: int(condition_counts.get(label, 0))
                for label in CONDITION_COST
            },
        }
    return {
        "schema_version": 1,
        "experiment": "offline_adaptive_no_nn_puct_schedule",
        "root_count": count,
        "rule": (
            "confirm consecutive (q_top, visit_top), escalating "
            "H2/S24 -> H2/S48 -> H3/S48 -> H5/S48 -> full S96 ladder"
        ),
        "selected_condition_counts": {
            label: int(selected_counts.get(label, 0))
            for label in CONDITION_COST
        },
        "q_top_matches_reference_roots": q_matches,
        "visit_top_matches_reference_roots": visit_matches,
        "both_tops_match_reference_roots": both_matches,
        "q_top_match_fraction": q_matches / count if count else 0.0,
        "visit_top_match_fraction": visit_matches / count if count else 0.0,
        "both_top_match_fraction": both_matches / count if count else 0.0,
        "total_rollout_step_budget_upper_bound": total_cost,
        "mean_rollout_step_budget_upper_bound": total_cost / count if count else 0.0,
        "rule_comparison": rule_comparison,
        "reference_wider_safe_recovered_nodes": sum(
            row["reference_wider_safe_recovered_nodes"] for row in rows
        ),
        "caveats": [
            "All three stopping rules are posthoc development diagnostics on these same 58 roots; none is a preregistered or independently confirmed policy.",
            "The full-order guarded rule reproduces 58/58 by construction because it uses the promotion rule that defines the measured deep reference.",
            "The 58 roots are a Q-discriminating capability set, not an unbiased on-policy evaluation set.",
            "Horizon times simulations is an upper bound on rollout steps; candidate proposal and physical-filter cost is not included.",
            "The existing width-64 audit is shadow-only at exhausted Top-3 nodes, so it can identify rescue opportunities but cannot measure action changes from adaptive K.",
            "Agreement is measured against the deepest bounded condition, not Q*.",
        ],
        "roots": rows,
    }


def render_markdown(result: dict[str, Any]) -> str:
    counts = result["selected_condition_counts"]
    lines = [
        "# Offline adaptive no-NN PUCT schedule",
        "",
        f"- roots: {result['root_count']}",
        f"- Q-top matches deep bounded reference: {result['q_top_matches_reference_roots']} / {result['root_count']}",
        f"- visit-top matches deep bounded reference: {result['visit_top_matches_reference_roots']} / {result['root_count']}",
        f"- both tops match: {result['both_tops_match_reference_roots']} / {result['root_count']}",
        f"- mean rollout-step upper bound: {result['mean_rollout_step_budget_upper_bound']:.1f}",
        f"- reference wider-safe rescue nodes: {result['reference_wider_safe_recovered_nodes']}",
        "",
        "## Rule comparison",
        "",
        "| rule | both tops match | mean rollout-step upper bound |",
        "|---|---:|---:|",
    ]
    for name, row in result["rule_comparison"].items():
        lines.append(
            f"| {name} | {row['both_top_matches_roots']} / "
            f"{result['root_count']} | "
            f"{row['mean_rollout_step_budget_upper_bound']:.1f} |"
        )
    lines.extend([
        "",
        "## Stop conditions",
        "",
        "| condition | roots |",
        "|---|---:|",
    ])
    for label in CONDITION_COST:
        lines.append(f"| {label} | {counts[label]} |")
    lines.extend(["", "## Caveats", ""])
    lines.extend(f"- {item}" for item in result["caveats"])
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
    result = evaluate_adaptive_schedule(
        payloads, expected_roots=args.expected_roots
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
