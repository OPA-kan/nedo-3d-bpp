"""The rule-alpha proposal family and its union into the candidate set."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.counterfactual_graph import BranchCandidate  # noqa: E402
from scripts.rule_alpha_proposals import (  # noqa: E402
    CANDIDATE_KIND,
    PROVIDER_NAME,
    _action_key,
    proposal_candidate,
    union_provider,
)
from scripts.run_terminal_rollout_policy import (  # noqa: E402
    find_exact_agent_candidate,
)


def _action(item=0, container=0, pos=(0.1, 0.2, 0.3), orientation=0):
    return {
        "item_idx": item,
        "container_idx": container,
        "place_pos": list(pos),
        "orientation": orientation,
    }


def _candidate(action, candidate_id="generic"):
    return BranchCandidate(
        candidate_id=candidate_id,
        command_action=action,
        selection={"provider": "generic", "rank": 0},
    )


class _StubProposer:
    def __init__(self, actions):
        self.actions = actions
        self.seconds = 0.0
        self.calls = 0

    def propose(self, _observation):
        self.calls += 1
        return list(self.actions)


OBSERVATION = {"pool_list": [{"index": 7}, {"index": 9}], "container_list": []}


class ActionKeyTests(unittest.TestCase):
    def test_key_matches_across_int_and_float_spellings(self):
        self.assertEqual(
            _action_key(_action(pos=(0.1, 0.2, 0.3))),
            _action_key({
                "item_idx": 0.0, "container_idx": 0.0,
                "place_pos": (0.1, 0.2, 0.3), "orientation": 0.0,
            }),
        )

    def test_key_separates_distinct_orientations(self):
        self.assertNotEqual(
            _action_key(_action(orientation=0)),
            _action_key(_action(orientation=1)),
        )


class ProposalCandidateTests(unittest.TestCase):
    def test_carries_the_stable_item_index_not_the_pool_index(self):
        candidate = proposal_candidate(_action(item=1), OBSERVATION, rank=3)
        self.assertEqual(candidate.selection["pool_index"], 1)
        self.assertEqual(candidate.selection["stable_item_index"], 9)
        self.assertEqual(candidate.selection["provider"], PROVIDER_NAME)
        self.assertEqual(candidate.selection["candidate_kind"], CANDIDATE_KIND)
        self.assertEqual(candidate.selection["rank"], 3)

    def test_identical_commands_share_one_candidate_id(self):
        first = proposal_candidate(_action(), OBSERVATION, rank=0)
        second = proposal_candidate(_action(), OBSERVATION, rank=5)
        self.assertEqual(first.candidate_id, second.candidate_id)


class UnionProviderTests(unittest.TestCase):
    def _provide(self, base_actions, family_actions):
        base = [
            _candidate(action, candidate_id=f"generic-{index}")
            for index, action in enumerate(base_actions)
        ]
        stats: dict = {}
        provider = union_provider(
            lambda _env, _obs, _limit: list(base),
            _StubProposer(family_actions),
            observation_fn=lambda _env, _obs: OBSERVATION,
            stats=stats,
        )
        return provider(None, {}, 3), stats

    def test_family_is_appended_beyond_the_base_limit(self):
        base = [_action(item=0), _action(item=1)]
        family = [_action(item=0, pos=(9.0, 9.0, 9.0))]
        candidates, stats = self._provide(base, family)
        self.assertEqual(len(candidates), 3)
        self.assertEqual(stats["base_candidates"], 2)
        self.assertEqual(stats["union_added"], 1)
        self.assertEqual(stats["union_duplicates"], 0)
        self.assertEqual(stats["union_states"], 1)

    def test_a_proposal_the_generic_set_already_has_is_not_duplicated(self):
        shared = _action(item=1, pos=(0.5, 0.5, 0.5))
        candidates, stats = self._provide([shared], [shared])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(stats["union_added"], 0)
        self.assertEqual(stats["union_duplicates"], 1)

    def test_the_family_dedupes_against_itself(self):
        repeated = _action(item=0, pos=(1.0, 1.0, 1.0))
        candidates, stats = self._provide([], [repeated, repeated])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(stats["union_added"], 1)

    def test_base_candidates_keep_their_order_and_identity(self):
        base = [_action(item=0), _action(item=1)]
        candidates, _stats = self._provide(base, [_action(item=2)])
        self.assertEqual(
            [c.candidate_id for c in candidates[:2]],
            ["generic-0", "generic-1"],
        )


class FindExactAgentCandidateTests(unittest.TestCase):
    """The read-only lookup used when --no-exact-agent-candidate is set."""

    def test_reports_a_hit_when_the_provider_already_supplied_the_move(self):
        action = _action(item=1, pos=(0.4, 0.5, 0.6))
        candidate_id, hit = find_exact_agent_candidate(
            [_candidate(action, candidate_id="from-provider")], action,
        )
        self.assertTrue(hit)
        self.assertEqual(candidate_id, "from-provider")

    def test_reports_a_miss_without_adding_anything(self):
        candidates = [_candidate(_action(item=0), candidate_id="other")]
        candidate_id, hit = find_exact_agent_candidate(
            candidates, _action(item=1),
        )
        self.assertFalse(hit)
        self.assertIsNone(candidate_id)
        self.assertEqual(len(candidates), 1)

    def test_a_union_proposal_satisfies_the_lookup(self):
        action = _action(item=1, pos=(0.4, 0.5, 0.6))
        unioned = proposal_candidate(action, OBSERVATION, rank=2)
        candidate_id, hit = find_exact_agent_candidate([unioned], action)
        self.assertTrue(hit)
        self.assertEqual(candidate_id, unioned.candidate_id)


if __name__ == "__main__":
    unittest.main()
