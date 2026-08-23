"""Evaluate multi-head suffix V without collapsing axes into one reward.

For every bounded physical branch this composes the observed root-to-leaf
component delta with a group-excluded ensemble prediction of the remaining
leaf-to-terminal component return.  It preserves the locally measurable
official component vector: fill, CoG, priority placement and soft.  Placed is
only the published activation gate; surface variation is diagnostic.  The
currently unlearned stability component is deferred to paired physical shake.
This is a proposal/capability audit, not an on-policy score claim.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import sys
from typing import Any, Callable

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


COMPONENTS = {
    "fill": ("fill_gain", "fill_return", "maximize", "official"),
    "placed_gate": ("placed_gain", "placed_return", "maximize", "gate"),
    "soft_violation": (
        "soft_violation_gain", "soft_violation_return", "minimize", "official",
    ),
    "priority_covered": (
        "priority_covered_gain", "priority_covered_return", "minimize", "official",
    ),
    "priority_misrouted": (
        "priority_misrouted_gain", "priority_misrouted_return", "minimize", "official",
    ),
    "center_of_mass_z": (
        "center_of_mass_z_delta", "center_of_mass_z_return", "minimize", "official",
    ),
    "surface_total_variation": (
        "surface_total_variation_delta", "surface_total_variation_return",
        "minimize_proxy", "diagnostic",
    ),
}


def _moments(values: list[float]) -> dict[str, float]:
    if not values:
        raise ValueError("component estimate has no samples")
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return {"mean": mean, "std": math.sqrt(variance), "samples": len(values)}


def _component_summary(
    member_samples: list[list[float]], branch_means: list[float],
) -> dict[str, Any]:
    if not member_samples or any(not values for values in member_samples):
        raise ValueError("component estimate has an incomplete ensemble")
    member_means = [
        sum(values) / len(values) for values in member_samples
    ]
    epistemic = _moments(member_means)
    chance = _moments(branch_means)
    return {
        "mean": epistemic["mean"],
        "member_means": member_means,
        "epistemic_std": epistemic["std"],
        "chance_standard_error": (
            chance["std"] / math.sqrt(len(branch_means))
        ),
        "branches": len(branch_means),
    }


def _incumbent(policy: list[dict[str, Any]]) -> str:
    eligible = [row for row in policy if int(row.get("visits") or 0) > 0]
    if not eligible:
        raise ValueError("policy row has no visited incumbent")
    best = max(
        eligible,
        key=lambda row: (
            int(row.get("visits") or 0),
            float(row.get("search_q") or 0.0),
            -int(row.get("rank") or 0),
        ),
    )
    return str(best["candidate_id"])


def estimate_candidates(
    row: dict[str, Any],
    predictor: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    *,
    ensemble_size: int,
) -> dict[str, dict[str, Any]]:
    """Compose branch deltas and suffix predictions per root candidate."""
    if ensemble_size < 3:
        raise ValueError("component confidence requires at least 3 members")
    values: dict[str, dict[str, dict[str, Any]]] = collections.defaultdict(
        lambda: collections.defaultdict(
            lambda: {
                "member_samples": [[] for _ in range(ensemble_size)],
                "branch_means": [],
            }
        )
    )
    branch_counts: collections.Counter[str] = collections.Counter()
    censored_counts: collections.Counter[str] = collections.Counter()
    for branch in row.get("bounded_branch_outcomes", []):
        candidate_id = str(branch["root_candidate_id"])
        if branch.get("continuation_censored"):
            censored_counts[candidate_id] += 1
            continue
        branch_counts[candidate_id] += 1
        if branch.get("termination") == "stream_exhausted":
            prediction = {
                suffix: {"members": [0.0] * ensemble_size}
                for _name, (_delta, suffix, _objective, _role) in COMPONENTS.items()
            }
        else:
            prediction = predictor(
                branch["leaf_state"], branch["leaf_game_state"]
            )
        for name, (delta_head, suffix_head, _objective, _role) in COMPONENTS.items():
            delta = branch["heads"].get(delta_head) or {}
            if not delta.get("target_eligible"):
                continue
            members = list(prediction[suffix_head]["members"])
            if len(members) != ensemble_size:
                raise ValueError(
                    f"expected {ensemble_size} members for {suffix_head}"
                )
            observed = float(delta["value"])
            totals = [observed + float(member) for member in members]
            for index, total in enumerate(totals):
                values[candidate_id][name]["member_samples"][index].append(total)
            values[candidate_id][name]["branch_means"].append(
                sum(totals) / len(totals)
            )
    result = {}
    for candidate_id, heads in values.items():
        if set(heads) != set(COMPONENTS):
            continue
        result[candidate_id] = {
            "branches": int(branch_counts[candidate_id]),
            "censored_branches": int(censored_counts[candidate_id]),
            "components": {
                name: _component_summary(
                    samples["member_samples"], samples["branch_means"]
                )
                for name, samples in heads.items()
            },
        }
    return result


def dominance(
    candidate: dict[str, Any], incumbent: dict[str, Any], *, beta: float,
) -> dict[str, Any]:
    """Return an axis-wise confidence dominance decision."""
    axes = {}
    nonworse = True
    strict = False
    official_strict = False
    for name, (_delta, _suffix, objective, role) in COMPONENTS.items():
        left = candidate["components"][name]
        right = incumbent["components"][name]
        delta = float(left["mean"]) - float(right["mean"])
        member_deltas = [
            float(mine) - float(theirs)
            for mine, theirs in zip(
                left["member_means"], right["member_means"], strict=True
            )
        ]
        epistemic_delta_std = _moments(member_deltas)["std"]
        chance_delta_se = math.sqrt(
            float(left["chance_standard_error"]) ** 2
            + float(right["chance_standard_error"]) ** 2
        )
        delta_uncertainty = math.sqrt(
            epistemic_delta_std ** 2 + chance_delta_se ** 2
        )
        if role == "diagnostic":
            axes[name] = {
                "objective": objective,
                "role": role,
                "mean_delta": delta,
                "epistemic_delta_std": epistemic_delta_std,
                "chance_delta_standard_error": chance_delta_se,
                "delta_uncertainty": delta_uncertainty,
            }
            continue
        if objective == "maximize":
            bound = delta - beta * delta_uncertainty
            axis_nonworse = bound >= -1e-12
            axis_strict = bound > 1e-12
            bound_name = "lower_delta"
        else:
            bound = delta + beta * delta_uncertainty
            axis_nonworse = bound <= 1e-12
            axis_strict = bound < -1e-12
            bound_name = "upper_delta"
        nonworse = nonworse and axis_nonworse
        strict = strict or axis_strict
        if role == "official":
            official_strict = official_strict or axis_strict
        axes[name] = {
            "objective": objective,
            "role": role,
            "mean_delta": delta,
            "epistemic_delta_std": epistemic_delta_std,
            "chance_delta_standard_error": chance_delta_se,
            "delta_uncertainty": delta_uncertainty,
            bound_name: bound,
            "nonworse": axis_nonworse,
            "strict": axis_strict,
        }
    return {
        "dominates": bool(nonworse and official_strict),
        "official_component_improves": bool(official_strict),
        "any_strict_axis": bool(strict),
        "axes": axes,
    }


def analyze_row(
    row: dict[str, Any],
    predictor: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    *,
    ensemble_size: int,
    beta: float,
) -> dict[str, Any]:
    if not row.get("policy_target_eligible", True) or not row.get("policy_target"):
        return {
            "eligible": False,
            "reason": "state_has_no_search_policy_target",
            "incumbent_candidate_id": None,
        }
    estimates = estimate_candidates(
        row, predictor, ensemble_size=ensemble_size
    )
    incumbent_id = _incumbent(row["policy_target"])
    if incumbent_id not in estimates:
        return {
            "eligible": False,
            "reason": "incumbent_has_no_uncensored_complete_component_estimate",
            "incumbent_candidate_id": incumbent_id,
        }
    selection = select_candidate(
        estimates, incumbent_id=incumbent_id, beta=beta
    )
    return {
        "eligible": True,
        "incumbent_candidate_id": incumbent_id,
        "candidate_estimates": estimates,
        **selection,
    }


def select_candidate(
    estimates: dict[str, dict[str, Any]], *, incumbent_id: str, beta: float,
) -> dict[str, Any]:
    """Select only an unambiguously dominating candidate without weights."""
    if incumbent_id not in estimates:
        raise ValueError("incumbent is absent from component estimates")
    comparisons = {}
    dominating = []
    for candidate_id, estimate in estimates.items():
        if candidate_id == incumbent_id:
            continue
        comparison = dominance(
            estimate, estimates[incumbent_id], beta=beta
        )
        comparisons[candidate_id] = comparison
        if comparison["dominates"]:
            dominating.append(candidate_id)
    selected = incumbent_id
    abstained_tradeoff = False
    if dominating:
        # Never invent a cross-component tie-break.  Select only a unique
        # candidate that also dominates every other incumbent-dominator.
        winners = [
            identifier for identifier in dominating
            if all(
                other == identifier or dominance(
                    estimates[identifier], estimates[other], beta=beta
                )["dominates"]
                for other in dominating
            )
        ]
        if len(winners) == 1:
            selected = winners[0]
        elif len(dominating) == 1:
            selected = dominating[0]
        else:
            abstained_tradeoff = True
    return {
        "selected_candidate_id": selected,
        "changed": selected != incumbent_id,
        "abstained_due_to_incomparable_dominators": abstained_tradeoff,
        "dominating_candidate_ids": sorted(dominating),
        "comparisons_to_incumbent": comparisons,
    }


def summarize(rows: list[dict[str, Any]], *, beta: float) -> dict[str, Any]:
    eligible = [row for row in rows if row.get("eligible")]
    changed = [row for row in eligible if row.get("changed")]
    by_case = collections.Counter(row["case_id"] for row in changed)
    return {
        "schema_version": 1,
        "experiment": "group_excluded_partial_official_vector_value_shadow",
        "scalarization": False,
        "beta": float(beta),
        "axes": {
            name: {"objective": objective, "role": role}
            for name, (_delta, _suffix, objective, role) in COMPONENTS.items()
        },
        "rows": len(rows),
        "eligible_rows": len(eligible),
        "changed_rows": len(changed),
        "changed_rate": len(changed) / len(eligible) if eligible else 0.0,
        "changed_by_case": dict(sorted(by_case.items())),
        "tradeoff_abstentions": sum(
            bool(row.get("abstained_due_to_incomparable_dominators"))
            for row in eligible
        ),
        "unmodeled_official_components": ["stability"],
        "next_gate": (
            "paired physical continuation for changed roots; no live policy claim"
        ),
        "records": rows,
    }


def render_markdown(result: dict[str, Any]) -> str:
    cases = ", ".join(
        f"{name}={count}"
        for name, count in result["changed_by_case"].items()
    ) or "none"
    return "\n".join([
        "# Partial official-vector value shadow",
        "",
        f"- rows / eligible: {result['rows']} / {result['eligible_rows']}",
        f"- confidence beta: {result['beta']}",
        f"- changed roots: {result['changed_rows']} ({result['changed_rate']:.3%})",
        f"- changed by case: {cases}",
        "- modeled official axes: fill, CoG, priority placement, soft",
        "- placed: activation gate, not a score term",
        "- surface variation: diagnostic proxy only",
        "- stability: unmodeled; requires paired physical shake",
        f"- incomparable-dominator abstentions: {result['tradeoff_abstentions']}",
        "- cross-axis scalarization: **disabled**",
        "",
        "> A change is only a candidate for paired continuation. It is not an on-policy score claim.",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=pathlib.Path, required=True)
    parser.add_argument("--model-dir", type=pathlib.Path, required=True)
    parser.add_argument("--beta", type=float, default=1.0)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if args.beta < 0.0:
        raise SystemExit("beta must be non-negative")

    from scripts.train_self_play_set_value import BehaviorValueEnsemble

    dataset = [
        json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    manifest = json.loads(
        (args.model_dir / "manifest.json").read_text(encoding="utf-8")
    )
    ensemble_size = len(manifest.get("members", []))
    fold_for_group = {}
    for fold in manifest.get("group_excluded_ensembles", []):
        for group in fold.get("excluded_groups", []):
            if group in fold_for_group:
                raise ValueError(f"trajectory group appears in two folds: {group}")
            fold_for_group[group] = int(fold["fold"])
    ensembles = {}
    output_rows = []
    for row in dataset:
        group = str(row["trajectory_group"])
        if group not in fold_for_group:
            raise ValueError(f"no group-excluded ensemble for {group}")
        fold = fold_for_group[group]
        if fold not in ensembles:
            ensembles[fold] = BehaviorValueEnsemble(
                args.model_dir, excluded_group=group
            )
        if not row.get("policy_target_eligible") or not row.get("policy_target"):
            analyzed = {
                "eligible": False,
                "reason": "state_has_no_search_policy_target",
                "incumbent_candidate_id": None,
            }
        else:
            analyzed = analyze_row(
                row, ensembles[fold].predict,
                ensemble_size=ensemble_size, beta=args.beta,
            )
        output_rows.append({
            "trajectory_group": group,
            "pair_id": row["pair_id"],
            "case_id": row["case_id"],
            "step": row["step"],
            "model_visible_state_signature": row["model_visible_state_signature"],
            **analyzed,
        })
    result = summarize(output_rows, beta=args.beta)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.markdown_output.write_text(render_markdown(result), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
