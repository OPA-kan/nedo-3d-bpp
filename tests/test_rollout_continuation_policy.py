"""The distilled ranker can become the teacher's own rollout policy.

Cups 001-009 improved the policy at the root and threw the improvement
away: the rollout continuation always took provider rank-0.  These
tests pin the arrow that closes the loop, and pin that it is off by
default so every earlier cup stays reproducible.
"""

from __future__ import annotations

import inspect
import pathlib
import sys
import unittest
import unittest.mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_terminal_rollout_policy as policy  # noqa: E402
from scripts import run_vector_mcts  # noqa: E402
from scripts.rollout_continuation_policy import (  # noqa: E402
    ContinuationRanker,
)


class _StubPolicy:
    """Minimal stand-in for a frozen geometry-feature champion."""

    feature_mode = "geometry"

    def __init__(self, scores: dict[str, float] | None):
        self._scores = scores
        self.calls = []

    def score_candidates(self, snapshot, rows, *, incumbent_id):
        self.calls.append((snapshot, rows, incumbent_id))
        return dict(self._scores) if self._scores is not None else {}


def _candidates(count: int) -> list[dict]:
    return [
        {
            "command_action": {
                "container_idx": 0, "place_pos": [float(index), 0.0, 0.0],
                "orientation": 0, "item_idx": index,
            },
            "selection": {"stable_item_index": index},
        }
        for index in range(count)
    ]


class DefaultsTests(unittest.TestCase):
    def test_the_teacher_is_unchanged_unless_asked(self):
        rollout = inspect.signature(run_vector_mcts._terminal_rollout)
        self.assertIsNone(rollout.parameters["continuation_policy"].default)
        self.assertEqual(rollout.parameters["continuation_top_k"].default, 1)
        search = inspect.signature(run_vector_mcts.vector_search_root)
        self.assertIsNone(search.parameters["continuation_policy"].default)
        self.assertEqual(search.parameters["continuation_top_k"].default, 1)
        episode = inspect.signature(policy.run_episode)
        self.assertIsNone(
            episode.parameters["continuation_model_dir"].default
        )
        self.assertEqual(
            episode.parameters["continuation_top_k"].default, 1
        )

    def test_every_search_call_site_carries_the_continuation_policy(self):
        """Three call sites: root search, online fork, mining fork.

        One left behind would silently keep the frozen rank-0 teacher
        for that path while the run still looked configured.
        """
        source = pathlib.Path(policy.__file__).read_text(encoding="utf-8")
        self.assertEqual(source.count("vector_search_root("), 3)
        self.assertEqual(
            source.count("continuation_policy=continuation_ranker"), 3
        )
        self.assertEqual(
            source.count("continuation_top_k=continuation_top_k"), 3
        )

    def test_a_single_retained_candidate_cannot_be_ranked(self):
        with self.assertRaises(ValueError):
            policy.run_episode(
                None, {}, case_id="c", environment_seed=0,
                attempt_budget=1, top_k=1, rollout_top_k=1,
                rollout_max_steps=1, max_steps=1, policy="legacy",
                output_dir=pathlib.Path("/nonexistent"),
                continuation_model_dir=pathlib.Path("/nonexistent"),
                continuation_top_k=1,
            )


class RankerTests(unittest.TestCase):
    def setUp(self):
        """Stub the snapshot capture; building a real board needs a simulator.

        What these tests pin is which index the ranker returns for a
        given set of scores, which the board does not enter into.  The
        patches are undone on teardown so nothing leaks into the rest of
        the suite.
        """
        import scripts.rollout_continuation_policy as module

        for name, replacement in (
            ("policy_observation", lambda env, observation: {}),
            (
                "state_snapshot",
                lambda env, observed, *, case_id, step: {"case_id": case_id},
            ),
        ):
            patcher = unittest.mock.patch.object(module, name, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_an_h1_champion_is_refused_rather_than_scored_on_zeros(self):
        stub = _StubPolicy({})
        stub.feature_mode = "h1"
        with self.assertRaises(ValueError):
            ContinuationRanker(stub, case_id="c")

    def test_one_candidate_is_never_sent_to_the_model(self):
        stub = _StubPolicy({"0": 0.9})
        ranker = ContinuationRanker(stub, case_id="c")
        self.assertEqual(
            ranker.choose(None, None, _candidates(1), step=0), 0
        )
        self.assertEqual(stub.calls, [])
        self.assertEqual(ranker.stats()["continuation_scored_states"], 0)

    def test_the_incumbent_is_rank_zero_and_ties_keep_it(self):
        stub = _StubPolicy({"0": 0.5, "1": 0.5, "2": 0.5})
        ranker = ContinuationRanker(stub, case_id="c")
        self.assertEqual(
            ranker.choose(None, None, _candidates(3), step=0), 0
        )
        self.assertEqual(stub.calls[0][2], "0")
        self.assertEqual(ranker.stats()["continuation_switches"], 0)

    def test_a_clearly_better_alternate_is_taken(self):
        stub = _StubPolicy({"0": 0.5, "1": 0.81, "2": 0.6})
        ranker = ContinuationRanker(stub, case_id="c")
        self.assertEqual(
            ranker.choose(None, None, _candidates(3), step=0), 1
        )
        stats = ranker.stats()
        self.assertEqual(stats["continuation_switches"], 1)
        self.assertEqual(stats["continuation_scored_states"], 1)

    def test_a_model_that_declines_leaves_the_teacher_alone(self):
        stub = _StubPolicy(None)
        ranker = ContinuationRanker(stub, case_id="c")
        self.assertEqual(
            ranker.choose(None, None, _candidates(2), step=0), 0
        )
        self.assertEqual(ranker.stats()["continuation_declined"], 1)


if __name__ == "__main__":
    unittest.main()
