"""League evaluation for policy generations (pure logic, no simulator).

The promotion structure is deliberately asymmetric (design review
2026-08-25, `expert-iteration-loop-contract.md`):

- **Main gate** — challenger vs the current champion only: paired Pareto
  wins must exceed losses on the frozen eval episodes, and the
  aggregate hard heads (rule violations, completion) must not regress.
- **League** — the anchor pi_0, the previous champion and a few
  milestones act only as a **catastrophic-regression detector**:
  aggregate collapse thresholds, never per-episode vetoes.  "Beat every
  member on every episode" would make promotion impossible as the
  league grows, because the verdict is a partial order.
- **Benchmarks** — SLA-noncompliant oracle-ish arms (pi_0 + expensive
  terminal search) sit outside the production line entirely (design
  review 2026-08-25, second round): they never gate and never veto.
  Each match reports the challenger's standing against them so that
  "new generation beats the production champion" (promotion), "matches
  the search teacher" (compression) and "beats the search teacher"
  (major breakthrough) stay distinguishable.

Paired episodes share scenario, stream and seed, and the simulator is
deterministic under those, so paired comparisons carry no sampling
noise and use a strict epsilon.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

EPS = 1e-9

# Official-aligned heads only.  Diagnostic telemetry (surface total
# variation, peak shake kinetic energy) is reported elsewhere but never
# decides a match.
LEAGUE_HEADS = {
    "placed_count": +1.0,
    "fill_score_proxy": +1.0,
    "soft_covered_by_other": -1.0,
    "priority_covered_by_other": -1.0,
    "priority_misrouted": -1.0,
    "center_of_mass_z": -1.0,
    "post_shake_max_shift": -1.0,
    "post_shake_items_toppled": -1.0,
}
HARD_VIOLATION_HEADS = (
    "soft_covered_by_other", "priority_covered_by_other",
    "priority_misrouted",
)
COMPLETION_HEAD = "placed_count"

DEFAULT_PARAMS = {
    # main gate (vs champion): strict
    "champion_violation_slack": 0.0,
    "champion_completion_slack": 0.0,
    # league detector (vs anchor/milestones): aggregate collapse only
    "league_violation_slack": 0.0,
    "league_completion_slack": 1.0,
    "league_collapse_fraction": 1.0 / 3.0,
}


def episode_outcome(manifest: dict[str, Any]) -> dict[str, Any]:
    episodes = manifest.get("episodes") or []
    if len(episodes) != 1:
        raise ValueError("league episodes must contain exactly one episode")
    episode = episodes[0]
    final = episode.get("final_metrics") or {}
    heads = {}
    for head in LEAGUE_HEADS:
        value = final.get(head)
        if not isinstance(value, (int, float)):
            raise ValueError(f"final metric {head} missing or non-numeric")
        heads[head] = float(value)
    return {
        "case_id": str(manifest.get("case_id")),
        "environment_seed": int(manifest.get("environment_seed")),
        "policy": manifest.get("policy"),
        "steps": int(episode.get("steps", 0)),
        "termination": episode.get("termination"),
        "genuine_termination": bool(episode.get("genuine_termination")),
        "heads": heads,
    }


def paired_relation(
    challenger: dict[str, float], member: dict[str, float],
) -> str:
    """challenger_wins / member_wins / equal / incomparable."""
    differences = [
        sign * (float(challenger[head]) - float(member[head]))
        for head, sign in LEAGUE_HEADS.items()
    ]
    challenger_non_worse = all(value >= -EPS for value in differences)
    member_non_worse = all(value <= EPS for value in differences)
    challenger_strict = any(value > EPS for value in differences)
    member_strict = any(value < -EPS for value in differences)
    if challenger_non_worse and challenger_strict:
        return "challenger_wins"
    if member_non_worse and member_strict:
        return "member_wins"
    if challenger_non_worse and member_non_worse:
        return "equal"
    return "incomparable"


def match(
    challenger: dict[str, dict[str, Any]],
    member: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Compare two arms over identical eval cells (paired by cell)."""
    cells = sorted(challenger)
    if cells != sorted(member):
        raise ValueError("challenger and member eval cells differ")
    relations = {}
    counts = {"challenger_wins": 0, "member_wins": 0, "equal": 0,
              "incomparable": 0}
    aggregate = {"challenger": {}, "member": {}}
    for side, outcomes in (("challenger", challenger), ("member", member)):
        for head in LEAGUE_HEADS:
            aggregate[side][head] = sum(
                outcomes[cell]["heads"][head] for cell in cells
            )
    for cell in cells:
        for side, outcomes in (
            ("challenger", challenger), ("member", member),
        ):
            row = outcomes[cell]
            if (row["case_id"], row["environment_seed"]) != (
                challenger[cell]["case_id"],
                challenger[cell]["environment_seed"],
            ):
                raise ValueError(f"{cell}: pairing mismatch")
        relation = paired_relation(
            challenger[cell]["heads"], member[cell]["heads"]
        )
        relations[cell] = relation
        counts[relation] += 1
    violation_delta = sum(
        aggregate["challenger"][head] - aggregate["member"][head]
        for head in HARD_VIOLATION_HEADS
    )
    completion_delta = (
        aggregate["challenger"][COMPLETION_HEAD]
        - aggregate["member"][COMPLETION_HEAD]
    )
    return {
        "episodes": len(cells),
        "relations": relations,
        "counts": counts,
        "aggregate": aggregate,
        "aggregate_violation_delta": violation_delta,
        "aggregate_completion_delta": completion_delta,
    }


def champion_gate(
    result: dict[str, Any], params: dict[str, float],
) -> dict[str, Any]:
    reasons = []
    wins = result["counts"]["challenger_wins"]
    losses = result["counts"]["member_wins"]
    if wins <= losses:
        reasons.append(
            f"paired Pareto wins {wins} do not exceed losses {losses}"
        )
    if result["aggregate_violation_delta"] > (
        params["champion_violation_slack"] + EPS
    ):
        reasons.append(
            "aggregate rule violations regress by "
            f"{result['aggregate_violation_delta']:+g}"
        )
    if result["aggregate_completion_delta"] < -(
        params["champion_completion_slack"] + EPS
    ):
        reasons.append(
            "aggregate completion regresses by "
            f"{result['aggregate_completion_delta']:+g}"
        )
    return {"passed": not reasons, "reasons": reasons}


def benchmark_standing(
    result: dict[str, Any], params: dict[str, float],
) -> dict[str, Any]:
    """Classify the challenger against an oracle-ish benchmark arm.

    Benchmarks never gate and never veto; this is reporting only.
    """
    wins = result["counts"]["challenger_wins"]
    losses = result["counts"]["member_wins"]
    hard_ok = result["aggregate_violation_delta"] <= (
        params["champion_violation_slack"] + EPS
    ) and result["aggregate_completion_delta"] >= -(
        params["champion_completion_slack"] + EPS
    )
    if wins > losses and hard_ok:
        standing = "beats_benchmark"
    elif wins >= losses and hard_ok:
        standing = "at_benchmark"
    else:
        standing = "below_benchmark"
    return {
        "standing": standing,
        "wins": wins,
        "losses": losses,
        "hard_heads_non_worse": hard_ok,
    }


def collapse_check(
    result: dict[str, Any], params: dict[str, float],
) -> dict[str, Any]:
    """Catastrophic-regression detector: aggregate thresholds only."""
    reasons = []
    wins = result["counts"]["challenger_wins"]
    losses = result["counts"]["member_wins"]
    allowed = params["league_collapse_fraction"] * result["episodes"]
    if losses - wins > allowed + EPS:
        reasons.append(
            f"loses to member by {losses - wins} episodes "
            f"(> {allowed:.2f} allowed)"
        )
    if result["aggregate_violation_delta"] > (
        params["league_violation_slack"] + EPS
    ):
        reasons.append(
            "aggregate rule violations regress by "
            f"{result['aggregate_violation_delta']:+g}"
        )
    if result["aggregate_completion_delta"] < -(
        params["league_completion_slack"] + EPS
    ):
        reasons.append(
            "aggregate completion collapses by "
            f"{result['aggregate_completion_delta']:+g}"
        )
    return {"collapsed": bool(reasons), "reasons": reasons}


def promotion_decision(
    challenger: dict[str, dict[str, Any]],
    registry: dict[str, Any],
    params: dict[str, float] | None = None,
) -> dict[str, Any]:
    params = {**DEFAULT_PARAMS, **(params or {})}
    members = registry.get("members") or []
    champion = next(
        (m for m in members if m["role"] == "champion"), None
    )
    if champion is None:
        raise ValueError("registry has no champion")
    matches = {}
    champion_result = match(challenger, champion["outcomes"])
    matches[champion["name"]] = champion_result
    gate = champion_gate(champion_result, params)
    league_checks = {}
    benchmarks = {}
    for member in members:
        if member["role"] == "benchmark":
            # oracle-ish teacher arm: reported, never gating or vetoing
            member_result = match(challenger, member["outcomes"])
            matches[member["name"]] = member_result
            benchmarks[member["name"]] = benchmark_standing(
                member_result, params
            )
            continue
        if member["name"] == champion["name"]:
            continue
        member_result = match(challenger, member["outcomes"])
        matches[member["name"]] = member_result
        league_checks[member["name"]] = collapse_check(member_result, params)
    collapsed = {
        name: check for name, check in league_checks.items()
        if check["collapsed"]
    }
    promoted = gate["passed"] and not collapsed
    return {
        "contract": "league_promotion_decision_v2",
        "params": params,
        "champion": champion["name"],
        "main_gate": gate,
        "league_checks": league_checks,
        "benchmarks": benchmarks,
        "matches": matches,
        "promoted": promoted,
    }


def load_registry(path: pathlib.Path) -> dict[str, Any]:
    registry = json.loads(path.read_text(encoding="utf-8"))
    if registry.get("contract") != "policy_league_registry_v1":
        raise ValueError("unsupported league registry contract")
    return registry


def new_registry(
    anchor_name: str, outcomes: dict[str, dict[str, Any]],
    *, source: str,
) -> dict[str, Any]:
    member = {
        "name": anchor_name,
        "role": "anchor",
        "generation": 0,
        "source": source,
        "outcomes": outcomes,
    }
    # the anchor starts as champion too, until a challenger dethrones it
    champion = {**member, "role": "champion"}
    return {
        "contract": "policy_league_registry_v1",
        "generation_counter": 0,
        "eval_cells": sorted(outcomes),
        "members": [member, champion],
    }


def promote(
    registry: dict[str, Any], name: str,
    outcomes: dict[str, dict[str, Any]], *, source: str,
    milestone_every: int = 3,
) -> dict[str, Any]:
    generation = int(registry["generation_counter"]) + 1
    members = [dict(member) for member in registry["members"]]
    for member in members:
        if member["role"] == "previous":
            # the outgoing "recent champion" slot: keep as milestone
            # every N generations (generation 0 is already the anchor),
            # otherwise retire
            if member["generation"] != 0 and (
                member["generation"] % milestone_every == 0
            ):
                member["role"] = "milestone"
            else:
                member["role"] = "retired"
    for member in members:
        if member["role"] == "champion":
            # the dethroned champion stays in the league one more
            # generation as the recent-champion slot
            member["role"] = "retired" if member["generation"] == 0 \
                else "previous"
    members = [m for m in members if m["role"] != "retired"]
    members.append({
        "name": name,
        "role": "champion",
        "generation": generation,
        "source": source,
        "outcomes": outcomes,
    })
    return {
        **registry,
        "generation_counter": generation,
        "members": members,
    }
