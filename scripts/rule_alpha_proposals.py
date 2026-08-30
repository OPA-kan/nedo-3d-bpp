"""A rule-alpha *proposal family* for the inference-side candidate set.

Cup 008 exposed a train/inference mismatch that sits upstream of every
ranker (`reports/league/diversity-cup-008.md`): rule-alpha's executed
action was absent from the candidate provider's set on 89 of 89 boards.
During mining ``add_exact_agent_candidate`` papers over this by unioning
the exact actor command into the fork's roots, so a preference label is
written for a move that at inference is not in the choice set at all.

The fix is to make the candidate set itself able to contain rule-alpha's
moves.  ``RuleAlphaProposer`` runs rule-alpha's own Layer 1 chooser over
*every* visible pool item rather than stopping at the first item that
yields a placement, which is what ``RuleAlphaAgent.policy`` does.  The
action ``policy`` would have executed is the first non-``None`` decision
in that same order, so it is in the family **by construction** -- and the
rest of the family is the move rule-alpha would have made for each of the
other items on offer.

``rule_alpha/`` is vendored file-by-file from an orphan branch that shares
no history with this one (see the vendor note in
``reports/league/cup-ledger.md``), so nothing here edits it: the proposer
drives a plain ``RuleAlphaAgent`` from outside.  That means reusing the
agent's own board-rebuild preamble through its private helpers, which is
deliberate -- duplicating the preamble would let the family drift away
from what the actor actually does, and drift is the exact bug being
fixed.

This is a *baseline*, not the goal.  Its job is to make teacher actions
executable so the mismatch can be measured away; whether a generic
geometric proposer finds winning actions rule-alpha cannot is the
separate question it unblocks.
"""

from __future__ import annotations

import inspect
import pathlib
import sys
import time
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rule_alpha import classify as cls  # noqa: E402
from rule_alpha import layer1  # noqa: E402
from rule_alpha.agent import RuleAlphaAgent  # noqa: E402
from scripts.counterfactual_graph import (  # noqa: E402
    BranchCandidate,
    canonical_action,
    stable_id,
)
from scripts.run_self_play_packing import _candidate_action  # noqa: E402

PROVIDER_NAME = "rule_alpha_proposal_family"
CANDIDATE_KIND = "rule_alpha_proposal"

# rule-alpha's own class priority, lifted from ``RuleAlphaAgent.policy``.
# Kept here rather than imported because the agent inlines it in a sort
# key; the ordering test in tests/test_rule_alpha_proposals.py fails if
# the vendored agent ever changes it.
_CLASS_RANK = {
    cls.NORMAL_HARD: 0,
    cls.PRIORITY: 2,
    cls.SOFT_PRIORITY: 3,
    cls.SOFT: 4,
}


def _supports_ranked_observer() -> bool:
    return "ranked_observer" in inspect.signature(
        layer1.choose_for_item
    ).parameters


def _placement_action(
    candidate, board, config, *, pool_index: int,
) -> dict[str, Any]:
    """A candidate's command, compacted exactly as ``choose_for_item`` does."""
    box = candidate.box
    if config.compaction_iterations > 0 and candidate.surface in (
        ("floor", "item") if config.compact_raised else ("floor",)
    ):
        box = layer1.compact_backwards(
            box, board, candidate.container_idx, candidate.role, config
        )
    centre = layer1.action_center(
        box, board.model(candidate.container_idx),
        board.container(candidate.container_idx), config,
    )
    return canonical_action({
        "item_idx": int(pool_index),
        "container_idx": int(candidate.container_idx),
        "place_pos": np.asarray(centre, dtype=np.float32),
        "orientation": int(candidate.orientation.index),
    })


class RuleAlphaProposer:
    """``C_rule-alpha(s)``: Layer 1 placements for the visible pool.

    ``per_item_top_k`` above 1 also keeps the 2nd..kth candidates of the
    archetype that won for each item -- the ones ``choose_for_item``
    sorts and then throws away.  They are close to free: the expensive
    work is generating and physically validating ~4,100 candidate boxes
    per item, which has already been paid by the time the ladder picks a
    winner.  They are also the only source of *same-item* diversity, so
    they are what widens the choice set on a one-item pool, where a
    per-item family is necessarily just the actor's own move.
    """

    def __init__(self, config=None, *, max_proposals: int = 8,
                 per_item_top_k: int = 1):
        if int(max_proposals) < 1:
            raise ValueError("max_proposals must be positive")
        if int(per_item_top_k) < 1:
            raise ValueError("per_item_top_k must be positive")
        if int(per_item_top_k) > 1 and not _supports_ranked_observer():
            raise RuntimeError(
                "layer1.choose_for_item has no ranked_observer parameter, so"
                " same-item alternates cannot be recovered. It is a"
                " trunk-only addition (see reports/league/cup-ledger.md) and"
                " was most likely dropped by a re-vendor of rule_alpha/;"
                " re-apply it rather than falling back to top-1, which would"
                " silently narrow the proposal family."
            )
        self.solver = RuleAlphaAgent(config=config)
        self.max_proposals = int(max_proposals)
        self.per_item_top_k = int(per_item_top_k)
        self.seconds = 0.0
        self.calls = 0
        self.same_item_alternates = 0

    # -- episode setup, mirroring the official three -------------------
    def get_init_states(self, init_states: dict) -> bool:
        return self.solver.get_init_states(init_states)

    def optimize(self, item_list: list):
        return self.solver.optimize(item_list)

    # -- the family ----------------------------------------------------
    def propose(self, observation: dict[str, Any]) -> list[dict[str, Any]]:
        """Canonical actions rule-alpha can generate from this board.

        The first entry is what ``RuleAlphaAgent.policy`` would return
        (or the list is empty exactly when ``policy`` would decline).
        """
        started = time.perf_counter()
        solver = self.solver
        config = solver.config
        # Same preamble as ``policy``: rebuild the board from the settled
        # truth the simulator reports, then restore the manifest-derived
        # strip widths that the rebuild throws away.
        solver.board = layer1.Board(
            observation.get("container_list") or [], config
        )
        solver._reapply_zone_scales()
        solver._resize_zones_for_what_is_left()

        actions: list[dict[str, Any]] = []
        seen: set[tuple] = set()
        alternates = 0
        for pool_index, item in _ordered_pool(observation, config):
            if len(actions) >= self.max_proposals:
                break
            ranked: list = []
            observer = None
            if self.per_item_top_k > 1:
                def observer(_archetype, candidates, _sink=ranked):
                    _sink.extend(candidates)
            decision = layer1.choose_for_item(
                solver.board, item, config,
                **({"ranked_observer": observer} if observer else {}),
            )
            if decision is None:
                continue
            placement = decision.placement
            model = solver.board.model(placement.container_idx)
            centre = layer1.action_center(
                placement.box, model,
                solver.board.container(placement.container_idx), config,
            )
            chosen = canonical_action({
                "item_idx": pool_index,
                "container_idx": int(placement.container_idx),
                "place_pos": np.asarray(centre, dtype=np.float32),
                "orientation": int(placement.orientation.index),
            })
            # The winner first, then this item's discarded 2nd..kth. The
            # order matters: propose()[0] must stay the action the actor
            # would execute, whatever else the family carries.
            for rank, action in enumerate(
                [chosen] + [
                    _placement_action(
                        candidate, solver.board, config,
                        pool_index=pool_index,
                    )
                    for candidate in ranked[1:self.per_item_top_k]
                ]
            ):
                if len(actions) >= self.max_proposals:
                    break
                key = _action_key(action)
                if key in seen:
                    continue
                seen.add(key)
                actions.append(action)
                if rank:
                    alternates += 1
        self.seconds += time.perf_counter() - started
        self.calls += 1
        self.same_item_alternates += alternates
        return actions


def _ordered_pool(observation: dict[str, Any], config) -> list[tuple[int, Any]]:
    profiles = [
        (pool_index, cls.classify_item(int(item["index"]), item, config))
        for pool_index, item in enumerate(observation.get("pool_list") or [])
    ]
    return sorted(
        profiles,
        key=lambda pair: (
            _CLASS_RANK[pair[1].cargo_class],
            -round(pair[1].max_footprint, 6),
            pair[0],
        ),
    )


def _action_key(action: dict[str, Any]) -> tuple:
    """Exact-command identity, matching ``add_exact_agent_candidate``."""
    command = canonical_action(action)
    return (
        int(command["item_idx"]),
        int(command["container_idx"]),
        tuple(round(float(value), 9) for value in command["place_pos"]),
        int(command["orientation"]),
    )


def proposal_candidate(
    action: dict[str, Any], observation: dict[str, Any], *, rank: int,
) -> BranchCandidate:
    command = canonical_action(action)
    pool = observation.get("pool_list") or []
    pool_index = int(command["item_idx"])
    stable_item_index = (
        int(pool[pool_index].get("index", pool_index))
        if 0 <= pool_index < len(pool) else None
    )
    return BranchCandidate(
        # Same id recipe as every other candidate, so an identical
        # command produced by the generic provider and by rule-alpha
        # collapses to one node rather than racing itself in a fork.
        candidate_id=stable_id("candidate", {
            "action": command,
            "kind": CANDIDATE_KIND,
            "stable_item_index": stable_item_index,
        }),
        command_action=command,
        selection={
            "provider": PROVIDER_NAME,
            "rank": int(rank),
            "pool_index": pool_index,
            "stable_item_index": stable_item_index,
            "candidate_kind": CANDIDATE_KIND,
        },
    )


def union_provider(
    base_provider, proposer: RuleAlphaProposer, *,
    observation_fn, stats: dict[str, Any] | None = None,
):
    """Wrap a candidate provider with ``C(s) | C_rule-alpha(s)``.

    The family is *appended* rather than merged into the ranked
    truncation: the point is that these actions become selectable at all,
    and dropping them to respect the base ``limit`` would reintroduce the
    very mismatch this fixes.  Duplicates are collapsed on the exact
    command, so a proposal the generic provider already found costs
    nothing and is counted as a support hit for the generic set.
    """

    def provide(env, raw_observation, limit: int) -> list[Any]:
        base = list(base_provider(env, raw_observation, limit))
        observed = observation_fn(env, raw_observation)
        present = {
            _action_key(_candidate_action(candidate)) for candidate in base
        }
        added = []
        duplicates = 0
        for action in proposer.propose(observed):
            key = _action_key(action)
            if key in present:
                duplicates += 1
                continue
            present.add(key)
            added.append(
                proposal_candidate(
                    action, observed, rank=len(base) + len(added),
                )
            )
        if stats is not None:
            stats["base_candidates"] = (
                stats.get("base_candidates", 0) + len(base)
            )
            stats["union_added"] = stats.get("union_added", 0) + len(added)
            stats["union_duplicates"] = (
                stats.get("union_duplicates", 0) + duplicates
            )
            stats["union_states"] = stats.get("union_states", 0) + 1
        return base + added

    return provide
