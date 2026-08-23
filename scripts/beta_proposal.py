"""Phase 3A proposal: coverage base, feasibility-weighted soft resampling.

Only the feasibility head weights proposals (beta contract): coverage
emits ``sample_budget`` points, F scores them, and ``keep`` proposals
are drawn without replacement by those weights — while ``floor`` raw
coverage points are always passed through untouched, so the base
sampler never leaves the mixture and F is never a hard prune.

Provenance claims only what is true: the generated finite set, the
acceptance model id, and each draw's conditional resampling probability
within that set. No continuous density is asserted.
"""

from __future__ import annotations

import random
from typing import Any

try:
    from scripts.coverage_action_sampler import coverage_candidates
    from scripts.run_self_play_packing import _candidate_set_id
except ModuleNotFoundError:
    from coverage_action_sampler import coverage_candidates
    from run_self_play_packing import _candidate_set_id

BETA_STAGE = "3A_feasibility_only"


def _acting_item_features(
    state: dict[str, Any], stable_item_index: Any,
) -> list[float] | None:
    indices = list(state["visible_item_indices"])
    if stable_item_index not in indices:
        return None
    return [
        float(v)
        for v in state["visible_item_values"][indices.index(stable_item_index)]
    ]


def beta_feasibility_proposals(
    observation: dict[str, Any], state_tensor: dict[str, Any], *,
    ensemble, coverage_seed: int, sample_budget: int,
    keep: int, floor: int, draw_seed: int,
) -> list[dict[str, Any]]:
    """Return ``keep`` resampled + ``floor`` raw coverage proposals."""
    if keep < 0 or floor < 0 or keep + floor < 1:
        raise ValueError("keep and floor must select at least one proposal")
    if sample_budget < keep + floor:
        raise ValueError("sample_budget must cover keep + floor")
    raw = coverage_candidates(
        observation, coverage_seed=coverage_seed, budget=sample_budget,
        z_mode="volume",
    )
    base_set_id = _candidate_set_id(raw)
    scorable = []
    for candidate in raw:
        item = _acting_item_features(
            state_tensor, candidate["selection"].get("stable_item_index")
        )
        if item is not None:
            scorable.append((candidate, item))
    scores = ensemble.predict(
        state_tensor,
        [candidate["command_action"] for candidate, _item in scorable],
        [item for _candidate, item in scorable],
    )
    weighted = [
        (candidate, max(float(score), 1e-6))
        for (candidate, _item), score in zip(scorable, scores)
    ]
    rng = random.Random(draw_seed)
    proposals: list[dict[str, Any]] = []
    # coverage floor: the first `floor` raw points, untouched
    for candidate in raw[:floor]:
        row = dict(candidate)
        provenance = dict(row["proposal_provenance"])
        provenance["beta_stage"] = BETA_STAGE
        provenance["mixture_weight"] = "coverage_floor"
        row["proposal_provenance"] = provenance
        proposals.append(row)
    floor_ids = {row["candidate_id"] for row in proposals}
    pool = [
        (candidate, weight) for candidate, weight in weighted
        if candidate["candidate_id"] not in floor_ids
    ]
    for _draw in range(min(keep, len(pool))):
        total = sum(weight for _c, weight in pool)
        probabilities = [weight / total for _c, weight in pool]
        index = rng.choices(range(len(pool)), weights=probabilities, k=1)[0]
        candidate, _weight = pool.pop(index)
        row = dict(candidate)
        provenance = dict(row["proposal_provenance"])
        provenance.update({
            "beta_stage": BETA_STAGE,
            "acceptance_model_id": getattr(ensemble, "model_id", None),
            "conditional_resampling_probability": probabilities[index],
            "mixture_weight": "feasibility_resampled",
        })
        row["proposal_provenance"] = provenance
        proposals.append(row)
    return proposals, base_set_id


def stratum_entropy(proposals: list[dict[str, Any]]) -> float:
    import collections
    import math

    counts = collections.Counter(
        (
            row["selection"].get("stable_item_index"),
            row["command_action"]["container_idx"],
            row["command_action"]["orientation"],
        )
        for row in proposals
    )
    total = sum(counts.values())
    return -sum(
        (count / total) * math.log(count / total)
        for count in counts.values()
    ) if total else 0.0
