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
    reference = conditions[reference_label]["policy_target"]
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
        "reference_condition": reference_label,
        "reference_signature": policy_signature(reference),
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
    consistent_state_groups = sum(
        len({
            json.dumps(row["reference_signature"], sort_keys=True)
            for row in group
        }) == 1
        for group in state_groups.values()
    )
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
        "reference_consistent_game_state_groups": consistent_state_groups,
        "bounded_search_stable_game_state_groups": stable_state_groups,
        "deterministic_repeat_roots": deterministic,
        "instrument_deterministic": deterministic == len(rows),
        "base_budget_stable_roots": sum(row["base_budget_stable"] for row in rows),
        "base_horizon_stable_roots": sum(row["base_horizon_stable"] for row in rows),
        "promoted_roots": promoted,
        "bounded_search_stable_roots": stable,
        "bounded_search_stable_fraction": stable / len(rows) if rows else 0.0,
        "caveat": (
            "Stability means agreement inside the measured bounded PUCT schedule; "
            "it does not establish convergence to Q* or an unbounded-search oracle."
        ),
        "roots": rows,
    }


def render_markdown(result: dict[str, Any]) -> str:
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
        f"- stable unique game-state groups: {result['bounded_search_stable_game_state_groups']} / {result['game_state_group_count']}",
        f"- duplicate groups with one reference answer: {result['reference_consistent_game_state_groups']} / {result['game_state_group_count']}",
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
