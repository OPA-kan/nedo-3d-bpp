"""Make the distilled ranker the teacher's own rollout policy.

Cups 001-009 all ran the same loop.  The ranker chose the ROOT action
(policy improvement); the teacher's rollout continuation always took
provider rank-0 (policy evaluation); and the improved policy never
became the next rollout policy.  That missing arrow is *policy
iteration*, and without it nothing compounds -- five consecutive
distillations moved held-out AUC 0.6125 -> 0.6130 on the largest
corpus the season has ever had.

This module is the arrow.  The continuation asks a frozen champion
ensemble to rank the safe candidates the legal filter retained and
executes its argmax instead of rank-0.  Two properties of the current
champion make that cheap and safe:

* its candidate features are ``geometry`` -- container-local position,
  orientation, container and item descriptors -- so a continuation
  candidate is scorable from ``command_action`` and the snapshot
  alone.  No one-step measurement is needed, and the only new physical
  cost is asking the legal filter to retain k safe candidates instead
  of stopping at the first.
* its objective is ``preference``, whose scores are
  ``sigmoid(score_j - score_incumbent)`` with the incumbent floored at
  ``switch_threshold``.  Naming rank-0 the incumbent makes the argmax
  read exactly "keep the frozen rollout policy unless an alternate
  clearly beats it", so ``k == 1``, an unconfident model, and a model
  that declines to score all reduce to today's behaviour.

An ``h1`` champion would need per-candidate one-step vectors, which the
continuation does not measure, so this refuses to load one rather than
silently scoring on zeros.
"""

from __future__ import annotations

import pathlib
import time
from typing import Any

from scripts.measure_anchor_recall import policy_observation, state_snapshot
from scripts.run_self_play_packing import (
    _candidate_action,
    _candidate_selection,
)

CONTRACT = "rollout_continuation_learned_policy_v1"


class ContinuationRanker:
    """Rank a continuation's retained candidates with a frozen ensemble.

    One instance serves every rollout of one episode; the counters are
    cumulative over that episode and are what a cup report reads to say
    whether the loop actually closed (``switches == 0`` means the
    champion never disagreed with rank-0, which is a null result, not a
    successful run).
    """

    def __init__(self, policy: Any, *, case_id: str):
        if getattr(policy, "feature_mode", None) != "geometry":
            raise ValueError(
                "the rollout continuation can only be driven by a"
                " geometry-feature champion: an h1 champion scores"
                " one_step_vector, which the continuation never measures"
            )
        self.policy = policy
        self.case_id = str(case_id)
        self.decisions = 0
        self.scored = 0
        self.switches = 0
        self.declined = 0
        self.seconds = 0.0

    def choose(self, env, observation, retained: list[Any], *, step: int) -> int:
        """Return the index of the candidate the champion would execute."""
        self.decisions += 1
        if len(retained) < 2:
            # nothing to rank: identical to the frozen rank-0 policy
            return 0
        started = time.perf_counter()
        try:
            observed = policy_observation(env, observation)
            snapshot = state_snapshot(
                env, observed, case_id=self.case_id, step=int(step),
            )
            rows = [
                {
                    "safe": True,
                    "root_candidate_id": str(index),
                    "stable_item_index": int(
                        _candidate_selection(candidate).get(
                            "stable_item_index", -1
                        )
                    ),
                    "command_action": _candidate_action(candidate),
                }
                for index, candidate in enumerate(retained)
            ]
            scores = self.policy.score_candidates(
                snapshot, rows, incumbent_id="0",
            )
            if not scores:
                # build_example failed safe; keep the incumbent
                self.declined += 1
                return 0
            self.scored += 1
            # ties break toward rank-0, so a champion with nothing to
            # say leaves the teacher exactly as it was
            best = max(
                range(len(rows)),
                key=lambda index: (
                    float(scores.get(str(index), float("-inf"))), -index,
                ),
            )
            if best != 0:
                self.switches += 1
            return best
        finally:
            self.seconds += time.perf_counter() - started

    def stats(self) -> dict[str, Any]:
        return {
            "contract": CONTRACT,
            "continuation_decisions": int(self.decisions),
            "continuation_scored_states": int(self.scored),
            "continuation_switches": int(self.switches),
            "continuation_declined": int(self.declined),
            "continuation_policy_seconds": float(self.seconds),
        }


def load_continuation_ranker(
    model_dir: pathlib.Path | None, *, case_id: str,
) -> ContinuationRanker | None:
    if model_dir is None:
        return None
    from scripts.learned_allocator_policy import LearnedAllocatorPolicy

    return ContinuationRanker(
        LearnedAllocatorPolicy(pathlib.Path(model_dir)), case_id=case_id,
    )
