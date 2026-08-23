"""Shadow-compare H1+V composite vectors against H2 physical measurement.

V-MCTS-0 gate: on the same roots, the same exogenous worlds and the same
rank-0 trajectory, does one physical step plus the frozen V^pi_behavior
leaf bootstrap reproduce the candidate ordering, dominance relations and
Pareto membership that two physical steps measure — at half the physical
budget?

Both arms stay shadow-only: execution is rank-0 in each, so root states
and world blocks align cell by cell. Dominance on the H1+V arm is decided
by a member-wise vote: each ensemble member forms its own composite
vectors and its own same-world paired dominance table, and a relation
holds only when at least ``--vote-threshold`` members agree. No variance
model is invented.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
from typing import Any

# measured branch head at the cut + predicted leaf->terminal suffix head
COMPOSITE_HEADS = {
    "game": ("game_reward", "game_return", "maximize"),
    "fill": ("fill_gain", "fill_return", "maximize"),
    "soft_violation": (
        "soft_violation_gain", "soft_violation_return", "minimize"
    ),
    "priority_covered": (
        "priority_covered_gain", "priority_covered_return", "minimize"
    ),
    "priority_misrouted": (
        "priority_misrouted_gain", "priority_misrouted_return", "minimize"
    ),
}
# predicted-only heads that H2 cannot measure; reported, never compared
STABILITY_HEADS = {
    "terminal_stability_max_shift": "minimize",
    "terminal_stability_peak_kinetic_energy": "minimize",
    "terminal_stability_items_toppled": "minimize",
}
DOMINANCE_POINT_THRESHOLD = 0.75


def _load_roots(run_dir: pathlib.Path) -> dict[str, dict[str, Any]]:
    manifest = json.loads(
        (run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    mcts = (manifest.get("selection") or {}).get("mcts") or {}
    if mcts.get("root_allocation_mode") != "paired_round_robin":
        raise ValueError(f"{run_dir} is not a paired_round_robin run")
    roots: dict[str, dict[str, Any]] = {}
    for game in manifest.get("games") or []:
        for record in game.get("records") or []:
            search = record.get("search")
            if not search:
                continue
            roots[str(record["candidate_set_id"])] = {
                "step": int(record["step"]),
                "candidate_set_id": str(record["candidate_set_id"]),
                "samples": list(
                    search.get("multi_head_branch_samples") or []
                ),
                "simulations": int(search.get("simulations", 0)),
                "horizon": int(search.get("horizon", 0)),
            }
    if not roots:
        raise ValueError(f"{run_dir} contains no searched roots")
    return roots


def _measured_vectors(
    samples: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, float]]]:
    """candidate -> world -> {composite head: measured branch value}."""
    result: dict[str, dict[str, dict[str, float]]] = {}
    for sample in samples:
        eligibility = sample.get("head_eligibility") or {}
        vector = sample.get("raw_outcome_vector") or {}
        if not all(
            eligibility.get(branch) is True
            for branch, _suffix, _d in COMPOSITE_HEADS.values()
        ):
            continue
        candidate = str(sample["root_candidate_id"])
        world = str(sample["exogenous_world_id"])
        result.setdefault(candidate, {})[world] = {
            head: float(vector[branch])
            for head, (branch, _suffix, _d) in COMPOSITE_HEADS.items()
        }
    return result


def _composite_vectors(
    samples: list[dict[str, Any]], member: int,
) -> dict[str, dict[str, dict[str, float]]]:
    """Composite = measured H1 branch delta + member's predicted suffix."""
    result: dict[str, dict[str, dict[str, float]]] = {}
    for sample in samples:
        predicted = sample.get("predicted_leaf_value") or {}
        heads = predicted.get("heads")
        if not heads:
            continue
        eligibility = sample.get("head_eligibility") or {}
        vector = sample.get("raw_outcome_vector") or {}
        if not all(
            eligibility.get(branch) is True
            for branch, _suffix, _d in COMPOSITE_HEADS.values()
        ):
            continue
        candidate = str(sample["root_candidate_id"])
        world = str(sample["exogenous_world_id"])
        result.setdefault(candidate, {})[world] = {
            head: float(vector[branch])
            + float(heads[suffix]["members"][member])
            for head, (branch, suffix, _d) in COMPOSITE_HEADS.items()
        }
    return result


def _ensemble_size(samples: list[dict[str, Any]]) -> int:
    for sample in samples:
        predicted = sample.get("predicted_leaf_value") or {}
        if predicted.get("heads"):
            return int(predicted["ensemble_size"])
    raise ValueError("no predicted leaf vectors found in the H1+V arm")


def _dominates(
    vectors: dict[str, dict[str, dict[str, float]]],
    challenger: str, target: str,
) -> float | None:
    """Same-world joint strict dominance share on the composite heads."""
    left = vectors.get(challenger, {})
    right = vectors.get(target, {})
    shared = sorted(set(left) & set(right))
    if not shared:
        return None
    wins = 0
    for world in shared:
        nonworse = True
        strict = False
        for head, (_b, _s, direction) in COMPOSITE_HEADS.items():
            a, b = left[world][head], right[world][head]
            if direction == "minimize":
                a, b = -a, -b
            nonworse = nonworse and a >= b
            strict = strict or a > b
        wins += int(nonworse and strict)
    return wins / len(shared)


def _relations(
    vectors: dict[str, dict[str, dict[str, float]]],
) -> dict[tuple[str, str], bool]:
    names = sorted(vectors)
    result = {}
    for challenger in names:
        for target in names:
            if challenger == target:
                continue
            share = _dominates(vectors, challenger, target)
            result[(challenger, target)] = (
                share is not None and share >= DOMINANCE_POINT_THRESHOLD
            )
    return result


def _candidate_means(
    vectors: dict[str, dict[str, dict[str, float]]], head: str,
) -> dict[str, float]:
    return {
        name: sum(row[head] for row in worlds.values()) / len(worlds)
        for name, worlds in vectors.items()
        if worlds
    }


def _kendall_tau(left: dict[str, float], right: dict[str, float]) -> float | None:
    names = sorted(set(left) & set(right))
    pairs = [
        (a, b)
        for i, a in enumerate(names) for b in names[i + 1:]
        if left[a] != left[b] and right[a] != right[b]
    ]
    if not pairs:
        return None
    agree = sum(
        1 for a, b in pairs
        if (left[a] - left[b]) * (right[a] - right[b]) > 0
    )
    return (2.0 * agree - len(pairs)) / len(pairs)


def compare_cell(
    h2_roots: dict[str, dict[str, Any]],
    h1v_roots: dict[str, dict[str, Any]], *,
    vote_threshold: int,
) -> dict[str, Any]:
    shared_roots = sorted(set(h2_roots) & set(h1v_roots))
    rows = []
    for key in shared_roots:
        h2 = _measured_vectors(h2_roots[key]["samples"])
        members = _ensemble_size(h1v_roots[key]["samples"])
        member_vectors = [
            _composite_vectors(h1v_roots[key]["samples"], member)
            for member in range(members)
        ]
        h2_relations = _relations(h2)
        member_relations = [_relations(v) for v in member_vectors]
        voted = {
            pair: sum(rel.get(pair, False) for rel in member_relations)
            >= vote_threshold
            for pair in h2_relations
        }
        relation_matches = sum(
            1 for pair, held in h2_relations.items() if voted[pair] == held
        )
        h2_dominated = {pair[1] for pair, held in h2_relations.items() if held}
        h1v_dominated = {pair[1] for pair, held in voted.items() if held}
        candidates = sorted(h2)
        h1_measured = _measured_vectors(h1v_roots[key]["samples"])
        taus = {}
        measured_only_taus = {}
        for head in COMPOSITE_HEADS:
            h2_means = _candidate_means(h2, head)
            ensemble_means: dict[str, float] = {}
            for name in h2_means:
                values = [
                    mean[name]
                    for vectors in member_vectors
                    if name in (mean := _candidate_means(vectors, head))
                ]
                if values:
                    ensemble_means[name] = sum(values) / len(values)
            tau = _kendall_tau(h2_means, ensemble_means)
            if tau is not None:
                taus[head] = tau
            # Ablation baseline: does the measured H1 delta alone already
            # reproduce the H2 ordering? Separates the value of the second
            # physical step from the value (or damage) of the V bootstrap.
            baseline = _kendall_tau(
                h2_means, _candidate_means(h1_measured, head)
            )
            if baseline is not None:
                measured_only_taus[head] = baseline
        rows.append({
            "candidate_set_id": key,
            "step": h2_roots[key]["step"],
            "candidates": len(candidates),
            "relation_pairs": len(h2_relations),
            "relation_matches": relation_matches,
            "h2_dominated": sorted(h2_dominated),
            "h1v_dominated": sorted(h1v_dominated),
            "pareto_agree": h2_dominated == h1v_dominated,
            "ordering_tau": taus,
            "ordering_tau_measured_only": measured_only_taus,
            "h2_physical_steps": (
                h2_roots[key]["simulations"] * h2_roots[key]["horizon"]
            ),
            "h1v_physical_steps": (
                h1v_roots[key]["simulations"] * h1v_roots[key]["horizon"]
            ),
        })
    return {
        "shared_roots": len(shared_roots),
        "h2_only_roots": len(set(h2_roots) - set(h1v_roots)),
        "h1v_only_roots": len(set(h1v_roots) - set(h2_roots)),
        "roots": rows,
    }


def summarize(cells: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = [row for cell in cells.values() for row in cell["roots"]]
    if not rows:
        raise ValueError("no shared roots between the two arms")
    tau_by_head = collections.defaultdict(list)
    baseline_by_head = collections.defaultdict(list)
    for row in rows:
        for head, tau in row["ordering_tau"].items():
            tau_by_head[head].append(tau)
        for head, tau in row.get("ordering_tau_measured_only", {}).items():
            baseline_by_head[head].append(tau)
    relation_pairs = sum(row["relation_pairs"] for row in rows)
    relation_matches = sum(row["relation_matches"] for row in rows)
    h2_positive = sum(len(row["h2_dominated"]) for row in rows)
    recovered = sum(
        len(set(row["h2_dominated"]) & set(row["h1v_dominated"]))
        for row in rows
    )
    flagged = sum(len(row["h1v_dominated"]) for row in rows)
    return {
        "roots": len(rows),
        "ordering_tau": {
            head: {
                "mean": sum(values) / len(values),
                "count": len(values),
            }
            for head, values in sorted(tau_by_head.items())
        },
        "ordering_tau_measured_only": {
            head: {
                "mean": sum(values) / len(values),
                "count": len(values),
            }
            for head, values in sorted(baseline_by_head.items())
        },
        "dominance_relation_agreement": (
            relation_matches / relation_pairs if relation_pairs else None
        ),
        "dominated_recall": recovered / h2_positive if h2_positive else None,
        "dominated_precision": recovered / flagged if flagged else None,
        "pareto_exact_agreement": (
            sum(row["pareto_agree"] for row in rows) / len(rows)
        ),
        "physical_steps": {
            "h2": sum(row["h2_physical_steps"] for row in rows),
            "h1v": sum(row["h1v_physical_steps"] for row in rows),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--h2-run", action="append", required=True, metavar="CELL=DIR",
    )
    parser.add_argument(
        "--h1v-run", action="append", required=True, metavar="CELL=DIR",
    )
    parser.add_argument("--vote-threshold", type=int, default=3)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    def parse(specs):
        result = {}
        for spec in specs:
            cell, _, run_dir = spec.partition("=")
            if not run_dir:
                raise SystemExit(f"expected CELL=DIR, got: {spec}")
            result[cell] = pathlib.Path(run_dir)
        return result

    h2_runs, h1v_runs = parse(args.h2_run), parse(args.h1v_run)
    shared_cells = sorted(set(h2_runs) & set(h1v_runs))
    if not shared_cells:
        raise SystemExit("the two arms share no cells")
    cells = {
        cell: compare_cell(
            _load_roots(h2_runs[cell]), _load_roots(h1v_runs[cell]),
            vote_threshold=args.vote_threshold,
        )
        for cell in shared_cells
    }
    report = {
        "schema_version": 1,
        "contract": "h1_plus_v_vs_h2_physical_shadow_v1",
        "composite_heads": {
            head: {"measured": branch, "predicted": suffix, "objective": d}
            for head, (branch, suffix, d) in COMPOSITE_HEADS.items()
        },
        "stability_heads_reported_not_compared": dict(STABILITY_HEADS),
        "dominance_point_threshold": DOMINANCE_POINT_THRESHOLD,
        "vote_threshold": args.vote_threshold,
        "cells": cells,
        "summary": summarize(cells),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = report["summary"]
    print(
        f"roots={summary['roots']} "
        f"relation_agreement={summary['dominance_relation_agreement']} "
        f"dominated_recall={summary['dominated_recall']} "
        f"physical_steps={summary['physical_steps']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
