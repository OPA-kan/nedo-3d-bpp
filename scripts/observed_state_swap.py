"""Paired-control-seeded observed-state swap optimizer.

The safe-split construction that this replaces maximized semantic coverage
first and then greedily maximized the *minimum* observed nearest-neighbour
distance, while the acceptance guard compares the *mean* nearest-neighbour
distance against an independently drawn safe-random control.  Optimizing one
statistic and being judged on another is the objective mismatch that left two
single-container steps with a negative mean-distance delta even though their
minimum distance and semantic coverage did not regress.

This module removes the mismatch instead of tuning around it:

* the paired control portfolio itself is the initial feasible point, so the
  search starts from the portfolio the guard measures against;
* every move is an intra-stratum swap, so the stratum counts, the forced
  rows, and the safe-only population are invariants rather than hopes;
* a move is accepted only when semantic coverage does not fall and the
  *measured* paired mean-nearest-neighbour delta strictly rises.

The search is therefore monotone in the reported objective.  It is still a
local search: it does not certify that a better admissible portfolio does not
exist, and it cannot manufacture a positive delta when the seed itself starts
below zero and no admissible swap improves it.  Both facts are recorded in
the trace rather than hidden behind a verdict.
"""
from __future__ import annotations

import collections
from typing import Any

from scripts.measure_anchor_recall import candidate_key
from scripts.residual_diversity import (
    ProxyVector,
    feature_vector_distance,
    paired_component_objective,
    paired_mean_nn_objective,
    proxy_feature_vector,
    residual_proxy_features,
    scale_vector,
)


SWAP_DESIGN = "paired_control_seed_then_observed_state_swap"
# What the portfolio is when the optimizer is switched off. The trace has to
# name the construction that actually ran, or the ablation arm files itself in
# history under the name of the thing it is the control for.
UNSEEDED_DESIGN = (
    "deterministic_global_item_matching_then_observed_afterstate_maximin"
)
SWAP_OBJECTIVE = "paired_observed_mean_nearest_neighbour_delta"

# Two acceptance rules, so the choice between them can be measured instead of
# argued. `sum` is what shipped: a swap is accepted whenever the single Gower
# ΔNN rises. `pareto_gate` keeps that ordering but REFUSES a swap that pays
# for the sum by degrading a component -- occupancy (where the item landed,
# and in which container) or consumption (which item left the pool).
#
# The name is precise on purpose. It is not a total-free search: the sum
# still orders the admissible moves. It only removes the moves the sum was
# allowed to buy at a component's expense. That keeps the contrast to one
# variable, which is what makes the shadow arm attributable.
ACCEPTANCE_RULES = ("sum", "pareto_gate")
IMPROVEMENT_TOLERANCE = 1e-12
_INFINITY = float("inf")
_SWAP_LOG_LIMIT = 64


def semantic_signature(records: list[dict[str, Any]]) -> tuple[int, int]:
    """Unique items and unique item-orientations, as the guard counts them."""
    items = {int(record.get("item_index", -1)) for record in records}
    poses = {
        (
            int(record.get("item_index", -1)),
            int(record.get("orientation", -1)),
        )
        for record in records
    }
    return len(items), len(poses)


def _identity(record: dict[str, Any]) -> dict[str, int]:
    return {
        "item_index": int(record.get("item_index", -1)),
        "pool_index": int(record.get("pool_index", -1)),
        "container_index": int(record.get("container_index", -1)),
        "orientation": int(record.get("orientation", -1)),
    }


def seed_keys_from_control(
    *,
    pool: list[dict[str, Any]],
    control: list[dict[str, Any]],
    per_stratum: int,
    forced_keys: dict[tuple[Any, ...], str] | set[tuple[Any, ...]],
) -> dict[tuple[Any, ...], str]:
    """Forced-key map that pins the control portfolio into the safe pool.

    The control is a feasible point only while it fits the stratum quota the
    positive arm is built to, so control rows are taken per stratum up to the
    capacity that the genuinely forced rows leave behind.  Truncation is by
    candidate key so the seed does not depend on the control draw order.
    """
    if not isinstance(forced_keys, dict):
        forced_keys = {key: "selected_action" for key in forced_keys}

    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in pool:
        groups[str(record["stratum_key"])].append(record)
    pool_keys = {candidate_key(record) for record in pool}

    control_by_stratum: dict[str, list[tuple[Any, ...]]] = (
        collections.defaultdict(list)
    )
    for record in control:
        key = candidate_key(record)
        if key in pool_keys and key not in forced_keys:
            control_by_stratum[str(record["stratum_key"])].append(key)

    seeded = dict(forced_keys)
    for stratum_key, group in groups.items():
        forced_here = sum(
            1 for record in group if candidate_key(record) in forced_keys
        )
        target = min(len(group), max(int(per_stratum), forced_here))
        capacity = max(0, target - forced_here)
        for key in sorted(set(control_by_stratum.get(stratum_key, [])))[
            :capacity
        ]:
            seeded[key] = "paired_control_seed"
    return seeded


def optimize_observed_state_portfolio(
    portfolio: list[dict[str, Any]],
    *,
    pool: list[dict[str, Any]],
    control: list[dict[str, Any]],
    observed: dict[tuple[Any, ...], dict[str, Any]],
    forced_keys: dict[tuple[Any, ...], str] | set[tuple[Any, ...]],
    max_rounds: int = 64,
    exact_checks_per_round: int = 8,
    exact_scan_limit: int = 32,
    acceptance: str = "sum",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Swap observed states inside each stratum to raise the measured delta.

    ``observed`` maps a candidate key to its replayed settle afterstate. Rows
    without one contribute to neither the objective nor the semantics the
    guard counts, so they stay where they are instead of being traded on
    predicted geometry the guard never looks at.
    """
    if not isinstance(forced_keys, dict):
        forced_keys = {key: "selected_action" for key in forced_keys}

    slots = list(portfolio)
    control_vectors = [
        proxy_feature_vector(observed[key])
        for record in control
        if (key := candidate_key(record)) in observed
    ]

    def trace(
        *,
        terminated: str,
        rounds: int,
        evaluated: int,
        exact: int,
        swaps: list[dict[str, Any]],
        initial: dict[str, float | None],
        final: dict[str, float | None],
        initial_semantics: tuple[int, int],
        final_semantics: tuple[int, int],
        initial_components: dict[str, float | None],
        final_components: dict[str, float | None],
        degrading: int = 0,
        refused_swaps: int = 0,
        refused_components: set[str] | None = None,
    ) -> dict[str, Any]:
        enabled = int(max_rounds) > 0
        return {
            "design": SWAP_DESIGN if enabled else UNSEEDED_DESIGN,
            "seed": (
                "paired_random_control_portfolio" if enabled else "none"
            ),
            "objective": SWAP_OBJECTIVE,
            "distance_basis": "official_replay_observed_x_plus",
            "terminated": terminated,
            "rounds": rounds,
            "swaps_applied": len(swaps),
            "swaps_evaluated": evaluated,
            "exact_evaluations": exact,
            "max_rounds": int(max_rounds),
            "exact_checks_per_round": int(exact_checks_per_round),
            "exact_scan_limit": int(exact_scan_limit),
            "portfolio_size": len(slots),
            "observed_portfolio_size": sum(
                1 for record in slots if candidate_key(record) in observed
            ),
            "control_size": len(control),
            "observed_control_size": len(control_vectors),
            "acceptance": acceptance,
            "initial_objective": initial,
            "final_objective": final,
            "initial_components": initial_components,
            "final_components": final_components,
            # The number that decides whether the acceptance rule matters at
            # all: accepted swaps that raised the sum while a component fell.
            # Zero means the two rules cannot disagree on this board.
            "component_degrading_swaps": degrading,
            "swaps_refused_by_gate": refused_swaps,
            "components_that_refused": sorted(refused_components or ()),
            "initial_semantics": {
                "unique_items": initial_semantics[0],
                "unique_item_orientations": initial_semantics[1],
            },
            "final_semantics": {
                "unique_items": final_semantics[0],
                "unique_item_orientations": final_semantics[1],
            },
            "semantic_constraint": (
                "no accepted swap reduces unique items or unique "
                "item-orientations among observed rows"
            ),
            "swap_log": swaps[:_SWAP_LOG_LIMIT],
            "swap_log_truncated": len(swaps) > _SWAP_LOG_LIMIT,
            "contract": (
                "Monotone local search on the reported paired delta from the "
                "control seed. It does not prove global optimality and does "
                "not guarantee a positive delta."
            ),
        }

    # A portfolio row is tradeable only when the replay observed its settle
    # afterstate and the safe pool still holds it. Anything else is carried
    # through untouched rather than traded on geometry the guard never reads.
    pool_records: dict[tuple[Any, ...], dict[str, Any]] = {}
    for record in pool:
        key = candidate_key(record)
        if key in observed:
            pool_records.setdefault(key, record)
    observed_slots = [
        index
        for index, record in enumerate(slots)
        if candidate_key(record) in pool_records
    ]

    def objective(records: list[dict[str, Any]]) -> dict[str, float | None]:
        return paired_mean_nn_objective(
            [
                proxy_feature_vector(observed[key])
                for record in records
                if (key := candidate_key(record)) in observed
            ],
            control_vectors,
        )

    control_records = [
        observed[key]
        for record in control
        if (key := candidate_key(record)) in observed
    ]

    def components(records: list[dict[str, Any]]) -> dict[str, float | None]:
        return paired_component_objective(
            [
                observed[key]
                for record in records
                if (key := candidate_key(record)) in observed
            ],
            control_records,
        )

    def not_worse(after: float | None, before: float | None) -> bool:
        """A missing component carries no information, so it blocks nothing."""
        if after is None or before is None:
            return True
        return after >= before - IMPROVEMENT_TOLERANCE

    def degrades(
        after: dict[str, float | None], before: dict[str, float | None]
    ) -> list[str]:
        return [
            kind
            for kind in ("occupancy", "consumption")
            if not not_worse(
                after[f"{kind}_delta"], before[f"{kind}_delta"]
            )
        ]

    initial_objective = objective(slots)
    initial_components = components(slots)
    observed_records = [slots[index] for index in observed_slots]
    initial_semantics = semantic_signature(observed_records)
    if (
        len(control_vectors) < 2
        or len(observed_slots) < 2
        or max_rounds <= 0
    ):
        return slots, trace(
            terminated=(
                "disabled"
                if max_rounds <= 0
                else "insufficient_observed_afterstates"
            ),
            rounds=0,
            evaluated=0,
            exact=0,
            swaps=[],
            initial=initial_objective,
            final=initial_objective,
            initial_semantics=initial_semantics,
            final_semantics=initial_semantics,
            initial_components=initial_components,
            final_components=initial_components,
        )

    # Screening geometry: one fixed basis over every replayed safe row, so the
    # candidate ordering comes from a distance matrix built once. Acceptance
    # never trusts it -- the exact paired objective re-derives its own scales.
    keys = sorted(pool_records)
    position = {key: index for index, key in enumerate(keys)}
    vectors = [proxy_feature_vector(observed[key]) for key in keys]
    screen_scales = scale_vector(vectors + control_vectors)
    size = len(keys)
    distance = [[0.0] * size for _ in range(size)]
    for left in range(size):
        for right in range(left + 1, size):
            value = feature_vector_distance(
                vectors[left], vectors[right], scales=screen_scales
            )
            distance[left][right] = value
            distance[right][left] = value

    stratum = {
        key: str(pool_records[key]["stratum_key"]) for key in keys
    }
    by_stratum: dict[str, list[int]] = collections.defaultdict(list)
    for key in keys:
        by_stratum[stratum[key]].append(position[key])

    selected = [position[candidate_key(slots[i])] for i in observed_slots]
    item_counts = collections.Counter(
        int(pool_records[keys[index]].get("item_index", -1))
        for index in selected
    )
    pose_counts = collections.Counter(
        (
            int(pool_records[keys[index]].get("item_index", -1)),
            int(pool_records[keys[index]].get("orientation", -1)),
        )
        for index in selected
    )

    best = initial_objective
    best_components = initial_components
    degrading_swaps = 0
    refused = 0
    refused_by_component: set[str] = set()
    swaps: list[dict[str, Any]] = []
    evaluated = 0
    exact_evaluations = 0
    rounds = 0
    terminated = "no_improving_swap"

    while rounds < int(max_rounds):
        rounds += 1
        selected_set = set(selected)
        nearest, nearest_index, second = _nearest_tables(selected, distance)

        proposals: list[tuple[float, int, int, int]] = []
        for slot, index in enumerate(selected):
            key = keys[index]
            if key in forced_keys:
                continue
            item = int(pool_records[key].get("item_index", -1))
            pose = (item, int(pool_records[key].get("orientation", -1)))
            for other in by_stratum[stratum[key]]:
                if other in selected_set:
                    continue
                other_key = keys[other]
                new_item = int(pool_records[other_key].get("item_index", -1))
                new_pose = (
                    new_item,
                    int(pool_records[other_key].get("orientation", -1)),
                )
                if _reduces_semantics(
                    item_counts,
                    pose_counts,
                    removed=(item, pose),
                    added=(new_item, new_pose),
                ):
                    continue
                evaluated += 1
                proposals.append(
                    (
                        _screened_mean(
                            selected,
                            slot,
                            other,
                            distance=distance,
                            nearest=nearest,
                            nearest_index=nearest_index,
                            second=second,
                        ),
                        slot,
                        other,
                        index,
                    )
                )

        if not proposals:
            terminated = "no_admissible_swap"
            break

        proposals.sort(key=lambda entry: (-entry[0], entry[1], entry[2]))
        winner: tuple[Any, ...] | None = None
        # Screened order is an approximation, so an empty top-K is not proof
        # that the round is exhausted. Keep exact-checking past the budget
        # while nothing has improved, up to the scan limit, and stop early
        # only once a real improvement is in hand.
        scanned = 0
        for _screen, slot, other, index in proposals:
            trial = list(slots)
            trial[observed_slots[slot]] = pool_records[keys[other]]
            candidate_objective = objective(trial)
            exact_evaluations += 1
            scanned += 1
            value = candidate_objective["mean_nearest_neighbor_distance_delta"]
            current = best["mean_nearest_neighbor_distance_delta"]
            if value is not None and current is not None:
                if value > current + IMPROVEMENT_TOLERANCE and (
                    winner is None
                    or value
                    > winner[0]["mean_nearest_neighbor_distance_delta"]
                ):
                    trial_components = components(trial)
                    fell = degrades(trial_components, best_components)
                    if fell and acceptance == "pareto_gate":
                        refused += 1
                        refused_by_component.update(fell)
                        continue
                    winner = (
                        candidate_objective,
                        slot,
                        other,
                        index,
                        trial_components,
                        fell,
                    )
            if winner is not None:
                if scanned >= max(1, int(exact_checks_per_round)):
                    break
            elif scanned >= max(1, int(exact_scan_limit)):
                break

        if winner is None:
            terminated = "no_improving_swap"
            break

        candidate_objective, slot, other, index, new_components, fell = winner
        removed = pool_records[keys[index]]
        added = pool_records[keys[other]]
        slots[observed_slots[slot]] = added
        selected[slot] = other
        _apply_counts(item_counts, pose_counts, removed=removed, added=added)
        swaps.append(
            {
                "round": rounds,
                "stratum_key": stratum[keys[index]],
                "removed": _identity(removed),
                "added": _identity(added),
                "delta_before": best["mean_nearest_neighbor_distance_delta"],
                "delta_after": candidate_objective[
                    "mean_nearest_neighbor_distance_delta"
                ],
                # What the single sum was hiding: which component actually
                # moved, and whether the sum was bought at the other's cost.
                "occupancy_before": best_components["occupancy_delta"],
                "occupancy_after": new_components["occupancy_delta"],
                "consumption_before": best_components["consumption_delta"],
                "consumption_after": new_components["consumption_delta"],
                "degraded_components": fell,
            }
        )
        if fell:
            degrading_swaps += 1
        best = candidate_objective
        best_components = new_components
    else:
        terminated = "round_budget"

    final_semantics = semantic_signature(
        [slots[index] for index in observed_slots]
    )
    return slots, trace(
        terminated=terminated,
        rounds=rounds,
        evaluated=evaluated,
        exact=exact_evaluations,
        swaps=swaps,
        initial=initial_objective,
        final=best,
        initial_semantics=initial_semantics,
        final_semantics=final_semantics,
        initial_components=initial_components,
        final_components=best_components,
        degrading=degrading_swaps,
        refused_swaps=refused,
        refused_components=refused_by_component,
    )


def annotate_swapped_portfolio(
    portfolio: list[dict[str, Any]],
    *,
    pool: list[dict[str, Any]],
    observed: dict[tuple[Any, ...], dict[str, Any]],
    forced_keys: dict[tuple[Any, ...], str] | set[tuple[Any, ...]],
    seed_keys: dict[tuple[Any, ...], str],
) -> list[dict[str, Any]]:
    """Rewrite sampling provenance after the search and rebuild the table.

    The constructor annotates only the rows it happened to pick, and it sees
    the control seed as forced.  After the swaps neither is true, so the rows
    are re-stamped from the final portfolio: ``forced`` means the row could
    not be traded away, and ``seed_role`` keeps the separate fact of where the
    row entered from.
    """
    if not isinstance(forced_keys, dict):
        forced_keys = {key: "selected_action" for key in forced_keys}

    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in pool:
        groups[str(record["stratum_key"])].append(record)
    counts = collections.Counter(
        str(record["stratum_key"]) for record in portfolio
    )
    for record in portfolio:
        key = candidate_key(record)
        stratum_key = str(record["stratum_key"])
        seeded = seed_keys.get(key) == "paired_control_seed"
        record["sampling"] = {
            "design": SWAP_DESIGN,
            "stratum_key": stratum_key,
            "stratum_size": len(groups[stratum_key]),
            "stratum_sampled": counts[stratum_key],
            "inclusion_probability": None,
            "sampling_weight": None,
            "forced": key in forced_keys,
            "forced_reason": forced_keys.get(key),
            "seed_role": (
                "paired_control_seed" if seeded else "swap_optimizer"
            ),
        }
        record["residual_proxy"] = residual_proxy_features(record)
        record["selection_distance_proxy"] = residual_proxy_features(
            observed.get(key, record)
        )

    return [
        {
            "stratum_key": stratum_key,
            "stratum": group[0]["stratum"],
            "population": len(group),
            "forced": sum(
                candidate_key(record) in forced_keys for record in group
            ),
            "sampled": counts.get(stratum_key, 0),
            "inclusion_probability": None,
            "design": SWAP_DESIGN,
        }
        for stratum_key, group in sorted(groups.items())
    ]


def _reduces_semantics(
    item_counts: collections.Counter,
    pose_counts: collections.Counter,
    *,
    removed: tuple[int, tuple[int, int]],
    added: tuple[int, tuple[int, int]],
) -> bool:
    """True when the swap would drop a last-of-its-kind item or pose."""
    item, pose = removed
    new_item, new_pose = added
    if item != new_item and item_counts[item] == 1 and new_item in item_counts:
        return True
    if (
        pose != new_pose
        and pose_counts[pose] == 1
        and new_pose in pose_counts
    ):
        return True
    return False


def _apply_counts(
    item_counts: collections.Counter,
    pose_counts: collections.Counter,
    *,
    removed: dict[str, Any],
    added: dict[str, Any],
) -> None:
    def item(record: dict[str, Any]) -> int:
        return int(record.get("item_index", -1))

    def pose(record: dict[str, Any]) -> tuple[int, int]:
        return (item(record), int(record.get("orientation", -1)))

    for counter, value in (
        (item_counts, item(removed)),
        (pose_counts, pose(removed)),
    ):
        counter[value] -= 1
        if counter[value] <= 0:
            del counter[value]
    item_counts[item(added)] += 1
    pose_counts[pose(added)] += 1


def _nearest_tables(
    selected: list[int], distance: list[list[float]]
) -> tuple[list[float], list[int], list[float]]:
    """Nearest and second-nearest in-portfolio distance for every member.

    Keeping the second-nearest is what makes a swap cost O(n) instead of
    O(n^2): dropping one member only changes the nearest of the members it
    was nearest to, and for those the answer is already stored.
    """
    nearest = [_INFINITY] * len(selected)
    nearest_index = [-1] * len(selected)
    second = [_INFINITY] * len(selected)
    for left, left_index in enumerate(selected):
        row = distance[left_index]
        for right, right_index in enumerate(selected):
            if right == left:
                continue
            value = row[right_index]
            if value < nearest[left]:
                second[left] = nearest[left]
                nearest[left] = value
                nearest_index[left] = right
            elif value < second[left]:
                second[left] = value
    return nearest, nearest_index, second


def _screened_mean(
    selected: list[int],
    slot: int,
    incoming: int,
    *,
    distance: list[list[float]],
    nearest: list[float],
    nearest_index: list[int],
    second: list[float],
) -> float:
    """Portfolio mean nearest-neighbour distance after one screened swap."""
    incoming_row = distance[incoming]
    total = 0.0
    incoming_nearest = _INFINITY
    for other, other_index in enumerate(selected):
        if other == slot:
            continue
        base = (
            second[other] if nearest_index[other] == slot else nearest[other]
        )
        crossing = incoming_row[other_index]
        total += crossing if crossing < base else base
        if crossing < incoming_nearest:
            incoming_nearest = crossing
    total += incoming_nearest
    return total / len(selected)
