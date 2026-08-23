"""Audit the paired exogenous-world contract on a real physical run.

The paired round-robin allocation promises, per searched root:

- every root candidate receives the same number of physical rollouts,
- replica ``r`` of every sibling shares one ``exogenous_world_id``,
- the (candidate, world) block is complete with no duplicates,
- no root Dirichlet noise is injected,
- no policy target is emitted and the executed action stays rank-0.

This script checks those invariants against the run manifest produced by
``run_self_play_packing.py`` and then computes the confidence-Pareto
frontier per root from the raw joint outcome vectors, so the contract is
exercised end to end on physical data rather than only in unit tests.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
from typing import Any

try:
    from scripts.self_play_packing_search import MULTI_HEAD_SPECS
    from scripts.vector_search import confidence_pareto_frontier
except ModuleNotFoundError:
    from self_play_packing_search import MULTI_HEAD_SPECS
    from vector_search import confidence_pareto_frontier


# Post-shake stability heads are not measured inside bounded branch
# rollouts (their values are None by construction), so requiring them in
# the joint objective would censor every physical sample. They stay out of
# the audit's Pareto set and are reported as unmeasured instead.
UNMEASURED_BRANCH_HEADS = frozenset({
    "stability_max_shift",
    "stability_peak_kinetic_energy",
    "stability_items_toppled",
})

PARETO_OBJECTIVES = {
    name: direction
    for name, direction in MULTI_HEAD_SPECS.items()
    if direction in {"maximize", "minimize"}
    and name not in UNMEASURED_BRANCH_HEADS
}


def _audit_search_record(record: dict[str, Any]) -> dict[str, Any]:
    search = record["search"]
    violations: list[str] = []
    if search.get("root_allocation_mode") != "paired_round_robin":
        violations.append("root_allocation_mode is not paired_round_robin")
    if search.get("policy_target_eligible") is not False:
        violations.append("paired search must not be policy-target eligible")
    if search.get("policy_target"):
        violations.append("paired search emitted a policy target")
    if search.get("execution_policy") != (
        "baseline_rank0_not_search_improvement"
    ):
        violations.append("execution policy is not the rank-0 baseline")
    if search.get("root_dirichlet_epsilon") or search.get("root_dirichlet_alpha"):
        violations.append("paired search configured root Dirichlet noise")
    if search.get("root_dirichlet_noise") is not None:
        violations.append("paired search injected root Dirichlet noise")
    selection = record.get("selection") or {}
    if int(selection.get("rank", -1)) != 0:
        violations.append(
            f"executed action rank {selection.get('rank')} is not rank-0"
        )

    samples = search.get("multi_head_branch_samples") or []
    simulations = int(search.get("simulations", 0))
    candidate_ids = sorted({
        str(row["candidate_id"])
        for row in search.get("candidate_outcome_summaries") or []
    })
    if len(samples) != simulations:
        violations.append(
            f"{len(samples)} branch samples for {simulations} simulations"
        )

    by_candidate: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    world_by_replica: dict[int, set[str]] = collections.defaultdict(set)
    block: collections.Counter[tuple[str, str]] = collections.Counter()
    candidate_set_ids = set()
    world_contract_versions = set()
    for sample in samples:
        candidate = str(sample["root_candidate_id"])
        world = str(sample["exogenous_world_id"])
        replica = int(sample["exogenous_world_sample_index"])
        by_candidate[candidate].append(sample)
        world_by_replica[replica].add(world)
        block[(candidate, world)] += 1
        candidate_set_ids.add(sample.get("candidate_set_id"))
        world_contract_versions.add(
            (sample.get("exogenous_world") or {}).get("contract_version")
        )
        if int(sample.get("schema_version", 0)) != 2:
            violations.append(f"sample schema_version is not 2: {sample.get('schema_version')}")
        if "raw_outcome_vector" not in sample or "head_eligibility" not in sample:
            violations.append("sample is missing the raw joint outcome contract")
        identity = sample.get("exogenous_world") or {}
        if identity.get("sample_index") != replica:
            violations.append("world identity sample_index disagrees with sample")

    if candidate_ids and sorted(by_candidate) != candidate_ids:
        violations.append(
            "sampled candidates differ from the root candidate set: "
            f"{sorted(by_candidate)} vs {candidate_ids}"
        )
    counts = sorted({len(rows) for rows in by_candidate.values()})
    if len(counts) > 1:
        violations.append(f"unequal per-candidate allocation: {counts}")
    replicas = len(counts) == 1 and counts[0] or 0
    for replica, worlds in sorted(world_by_replica.items()):
        if len(worlds) != 1:
            violations.append(
                f"replica {replica} spans {len(worlds)} exogenous worlds"
            )
    duplicates = sorted(
        key for key, count in block.items() if count > 1
    )
    if duplicates:
        violations.append(f"duplicate (candidate, world) cells: {duplicates}")
    expected_cells = len(by_candidate) * replicas
    if replicas and len(block) != expected_cells:
        violations.append(
            f"incomplete candidate/world block: {len(block)} of {expected_cells}"
        )
    if len(candidate_set_ids) > 1:
        violations.append(f"multiple candidate_set_ids in one root: {sorted(candidate_set_ids)}")
    if candidate_set_ids and candidate_set_ids != {search.get("candidate_set_id")}:
        violations.append("sample candidate_set_id disagrees with the search record")

    pareto = None
    if samples:
        try:
            pareto = confidence_pareto_frontier(
                samples, objectives=PARETO_OBJECTIVES,
                minimum_pairs=1, minimum_probability_lcb=0.8,
            )
        except ValueError as error:
            violations.append(f"confidence Pareto rejected the block: {error}")
    eligible_samples = sum(
        1 for sample in samples
        if all(
            (sample.get("head_eligibility") or {}).get(head) is True
            for head in PARETO_OBJECTIVES
        )
    )
    return {
        "step": record.get("step"),
        "candidate_count": len(candidate_ids),
        "simulations": simulations,
        "replicas_per_candidate": replicas,
        "distinct_worlds": len({
            world for worlds in world_by_replica.values() for world in worlds
        }),
        "world_contract_versions": sorted(
            version for version in world_contract_versions if version is not None
        ),
        "pareto_eligible_samples": eligible_samples,
        "censored_samples": len(samples) - eligible_samples,
        "confidence_pareto": (
            {
                "frontier_candidate_ids": pareto["frontier_candidate_ids"],
                "dominated_candidate_ids": pareto["dominated_candidate_ids"],
                "dominated_by": pareto["dominated_by"],
                "minimum_pairs": pareto["minimum_pairs"],
                "minimum_probability_lcb": pareto["minimum_probability_lcb"],
                "comparison_count": len(pareto["comparisons"]),
            }
            if pareto is not None else None
        ),
        "violations": violations,
    }


def audit_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    mcts = (manifest.get("selection") or {}).get("mcts") or {}
    if mcts.get("root_allocation_mode") != "paired_round_robin":
        raise ValueError(
            "manifest was not produced under paired_round_robin allocation"
        )
    roots = []
    for game_index, game in enumerate(manifest.get("games") or []):
        for record in game.get("records") or []:
            if "search" not in record:
                continue
            row = _audit_search_record(record)
            row["game"] = game_index
            roots.append(row)
    if not roots:
        raise ValueError("manifest contains no searched roots to audit")
    violations = [
        {"game": row["game"], "step": row["step"], "violations": row["violations"]}
        for row in roots
        if row["violations"]
    ]
    return {
        "schema_version": 1,
        "contract": "paired_exogenous_world_physical_audit_v1",
        "case_id": manifest.get("case_id"),
        "policy_generation": manifest.get("policy_generation"),
        "root_allocation_mode": mcts.get("root_allocation_mode"),
        "pareto_objectives": PARETO_OBJECTIVES,
        "unmeasured_branch_heads": sorted(UNMEASURED_BRANCH_HEADS),
        "searched_roots": len(roots),
        "roots_with_violations": len(violations),
        "violations": violations,
        "roots": roots,
        "passed": not violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = audit_manifest(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"searched_roots={report['searched_roots']} "
        f"violations={report['roots_with_violations']} "
        f"passed={report['passed']}"
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
