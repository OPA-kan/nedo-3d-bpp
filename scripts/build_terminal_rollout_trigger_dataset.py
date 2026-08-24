"""Build an auditable adaptive-rollout trigger dataset from rollout episodes.

The label is deliberately narrow: whether the terminal physical oracle changed
the live action away from the incumbent.  Shallow H1 vectors are features; no
learned value or scalar utility is introduced.  Rule results on the same small
corpus are capability diagnostics, not held-out performance estimates.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any, Callable

DOMINANCE_HEADS = {
    "fill_gain": +1.0,
    "soft_violation_gain": -1.0,
    "priority_covered_gain": -1.0,
    "priority_misrouted_gain": -1.0,
    "surface_total_variation_delta": -1.0,
}
EPS = 1e-9


def _oriented(vector: dict[str, Any] | None) -> tuple[float, ...] | None:
    if not vector:
        return None
    values = []
    for head, direction in DOMINANCE_HEADS.items():
        value = vector.get(head)
        if not isinstance(value, (int, float)):
            return None
        values.append(direction * float(value))
    return tuple(values)


def _dominates(left: tuple[float, ...], right: tuple[float, ...]) -> bool:
    return all(a >= b - EPS for a, b in zip(left, right)) and any(
        a > b + EPS for a, b in zip(left, right)
    )


def pareto_ids(
    candidates: list[dict[str, Any]], vector_field: str,
) -> list[str]:
    vectors = {
        str(row["root_candidate_id"]): oriented
        for row in candidates
        if row.get("safe")
        and (oriented := _oriented(row.get(vector_field))) is not None
    }
    return sorted(
        candidate for candidate, vector in vectors.items()
        if not any(
            _dominates(other_vector, vector)
            for other, other_vector in vectors.items()
            if other != candidate
        )
    )


def _distinct_h1_vectors(candidates: list[dict[str, Any]]) -> int:
    return len({
        oriented for row in candidates
        if row.get("safe")
        and (oriented := _oriented(row.get("one_step_vector"))) is not None
    })


def row_from_record(
    record: dict[str, Any], *, cell: str, case_id: str,
    environment_seed: int, snapshot_root: pathlib.Path,
    dataset_root: pathlib.Path,
) -> dict[str, Any]:
    search = record.get("search") or {}
    candidates = search.get("root_candidates") or []
    safe_candidates = [row for row in candidates if row.get("safe")]
    h1 = pareto_ids(safe_candidates, "one_step_vector")
    terminal = sorted(
        str(value) for value in search.get("terminal_pareto_candidates") or []
    )
    selection = record.get("selection") or {}
    incumbent = selection.get("incumbent_candidate_id")
    selected = selection.get("selected_candidate_id")
    terminal_set = set(terminal)
    h1_set = set(h1)
    symmetry = search.get("item_symmetry_terminal_cache") or {}
    snapshot_path = snapshot_root / str(record.get("snapshot_path"))
    return {
        "contract": "terminal_rollout_trigger_row_v1",
        "cell": cell,
        "case_id": case_id,
        "environment_seed": int(environment_seed),
        "step": int(record.get("step", 0)),
        "root_id": record.get("root_id"),
        "board_fingerprint": record.get("board_fingerprint"),
        "item_symmetry_fingerprint": record.get(
            "item_symmetry_fingerprint"
        ),
        "snapshot_path": snapshot_path.relative_to(dataset_root).as_posix(),
        "incumbent_candidate_id": incumbent,
        "selected_candidate_id": selected,
        "terminal_intervention": bool(selection.get("switched")),
        "terminal_truth_complete": bool(
            search.get("terminal_truth_complete")
        ),
        "candidate_count": len(candidates),
        "safe_candidate_count": len(safe_candidates),
        "h1_pareto_candidates": h1,
        "h1_frontier_size": len(h1),
        "h1_distinct_vector_count": _distinct_h1_vectors(safe_candidates),
        "h1_incumbent_pareto": incumbent in h1_set,
        "h1_all_safe_candidates_pareto": (
            bool(safe_candidates) and len(h1) == len(safe_candidates)
        ),
        "terminal_pareto_candidates": terminal,
        "terminal_frontier_size": len(terminal),
        "terminal_incumbent_pareto": incumbent in terminal_set,
        "terminal_resurrection_candidates": sorted(terminal_set - h1_set),
        "terminal_resurrection_present": bool(terminal_set - h1_set),
        "h1_terminal_frontier_equal": h1_set == terminal_set,
        "terminal_rollout_physical_steps": int(
            search.get("terminal_rollout_physical_steps", 0)
        ),
        "terminal_rollout_physical_step_equivalents": int(
            search.get("terminal_rollout_physical_step_equivalents", 0)
        ),
        "terminal_rollout_calls": int(symmetry.get("misses", 0)),
        "terminal_rollout_cache_hits": int(symmetry.get("hits", 0)),
        "candidates": candidates,
    }


RULES: dict[str, Callable[[dict[str, Any]], bool]] = {
    "always": lambda row: True,
    "h1_incumbent_dominated": lambda row: not row["h1_incumbent_pareto"],
    "h1_frontier_ambiguous": lambda row: row["h1_frontier_size"] > 1,
    "h1_all_candidates_pareto": lambda row: row[
        "h1_all_safe_candidates_pareto"
    ],
    "h1_all_vectors_tied": lambda row: (
        row["safe_candidate_count"] > 1
        and row["h1_distinct_vector_count"] == 1
    ),
    "at_least_three_safe_candidates": lambda row: (
        row["safe_candidate_count"] >= 3
    ),
}


def audit_rules(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    positives = sum(row["terminal_intervention"] for row in rows)
    total_equivalents = sum(
        row["terminal_rollout_physical_step_equivalents"] for row in rows
    )
    results = []
    for name, rule in RULES.items():
        triggered = [row for row in rows if rule(row)]
        true_positives = sum(row["terminal_intervention"] for row in triggered)
        retained = sum(
            row["terminal_rollout_physical_step_equivalents"]
            for row in triggered
        )
        results.append({
            "rule": name,
            "triggered_roots": len(triggered),
            "trigger_rate": len(triggered) / len(rows) if rows else None,
            "true_positive_roots": true_positives,
            "intervention_recall": (
                true_positives / positives if positives else None
            ),
            "false_trigger_roots": len(triggered) - true_positives,
            "retained_physical_step_equivalents": retained,
            "saved_physical_step_equivalents_upper_bound": (
                total_equivalents - retained
            ),
            "retained_compute_rate": (
                retained / total_equivalents if total_equivalents else None
            ),
        })
    return results


def build_dataset(root: pathlib.Path) -> dict[str, Any]:
    rows = []
    for path in sorted(root.rglob("rollout.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        episodes = payload.get("episodes") or []
        if len(episodes) != 1:
            raise ValueError(f"{path}: expected exactly one episode")
        snapshot_root = path.parent / "rollout" / "episode-000"
        for record in episodes[0].get("records") or []:
            rows.append(row_from_record(
                record, cell=path.parent.name,
                case_id=str(payload.get("case_id")),
                environment_seed=int(payload.get("environment_seed", 0)),
                snapshot_root=snapshot_root,
                dataset_root=root,
            ))
    if not rows:
        raise ValueError(f"no rollout records below {root}")
    positives = sum(row["terminal_intervention"] for row in rows)
    complete = sum(row["terminal_truth_complete"] for row in rows)
    resurrection = sum(row["terminal_resurrection_present"] for row in rows)
    return {
        "schema_version": 1,
        "contract": "terminal_rollout_trigger_dataset_v1",
        "label": "terminal_oracle_changes_incumbent_action",
        "feature_horizon": "H1_physical",
        "value_model": None,
        "scalar_utility": None,
        "root_count": len(rows),
        "terminal_truth_complete_roots": complete,
        "terminal_intervention_roots": positives,
        "terminal_resurrection_roots": resurrection,
        "positive_prevalence": positives / len(rows),
        "rule_audit_scope": (
            "same-corpus capability diagnostic; not held-out performance"
        ),
        "rule_audits": audit_rules(rows),
        "rows": rows,
    }


def render_markdown(dataset: dict[str, Any]) -> str:
    rows = [
        "# Adaptive terminal-rollout trigger dataset",
        "",
        f"- roots: **{dataset['root_count']}**",
        "- complete terminal truth: "
        f"**{dataset['terminal_truth_complete_roots']}**",
        f"- terminal interventions: **{dataset['terminal_intervention_roots']}**",
        "- terminal frontier resurrection roots: "
        f"**{dataset['terminal_resurrection_roots']}**",
        "- learned V: **none**",
        "- Rule results below are same-corpus diagnostics, not held-out "
        "performance estimates.",
        "",
        "| rule | triggers | intervention recall | false triggers | "
        "compute retained | saved equivalents (upper bound) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for result in dataset["rule_audits"]:
        rows.append(
            f"| {result['rule']} | {result['triggered_roots']} | "
            f"{result['intervention_recall']} | "
            f"{result['false_trigger_roots']} | "
            f"{result['retained_compute_rate']} | "
            f"{result['saved_physical_step_equivalents_upper_bound']} |"
        )
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    dataset = build_dataset(args.root)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(
        render_markdown(dataset), encoding="utf-8"
    )
    print(args.markdown_output.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
