"""Integration: the family really contains what rule-alpha would execute.

The union in ``scripts/rule_alpha_proposals.py`` is worth nothing unless
the *first* member of ``C_rule-alpha(s)`` is the exact command
``RuleAlphaAgent.policy`` returns from the same board -- that is the
property which makes the exact-agent candidate a safety net rather than
a load-bearing part of the pipeline, and it is a property of rule-alpha's
own ordering, which lives in a vendored file this repository does not
own.  So it is checked against the real simulator rather than a stub.

Needs the real simulator (same gate as test_replay_integration.py).
"""

from __future__ import annotations

import copy
import importlib
import json
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SIMULATOR = ROOT / "simulator"
CONFIG = SIMULATOR / "configs" / "sample_config.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _simulator_available() -> tuple[bool, str]:
    if sys.version_info[:2] < (3, 12):
        return False, "simulator needs Python 3.12+ (PEP 701 f-strings)"
    if importlib.util.find_spec("pybullet") is None:
        return False, "pybullet is not installed"
    if str(SIMULATOR) not in sys.path:
        sys.path.insert(0, str(SIMULATOR))
    try:
        importlib.import_module("src.ground_handling.env")
    except Exception as exc:  # pragma: no cover - environment dependent
        return False, f"simulator unavailable: {exc}"
    return True, ""


AVAILABLE, SKIP_REASON = _simulator_available()

REQUIRE_INTEGRATION = os.environ.get(
    "NEDO_REQUIRE_INTEGRATION", ""
).strip().lower() in {"1", "true", "yes"}

if REQUIRE_INTEGRATION and not AVAILABLE:
    raise RuntimeError(
        "NEDO_REQUIRE_INTEGRATION is set but the rule-alpha proposal family "
        f"integration tests cannot run: {SKIP_REASON}. Install "
        "requirements-simulator.txt on Python 3.12+, or unset the variable "
        "to allow skipping."
    )

STEPS = 4


@unittest.skipUnless(AVAILABLE, SKIP_REASON)
class ProposalFamilyContainsTheActorsMoveTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))["000"]

    def wide_pool_config(self, look_ahead: int = 6) -> dict:
        """The shipped fixture shows one item at a time.

        A per-item proposal family is bounded above by the pool width, so
        on ``look_ahead: 1`` it is *necessarily* the actor's own move and
        nothing else -- true, and tested below, but useless for checking
        that the family widens. Cup scenarios use ``look_ahead: 10``
        (``scripts/build_scenario_matrix.py``), which is the regime the
        union was measured in.
        """
        config = copy.deepcopy(self.config)
        config["item_stream"]["look_ahead"] = int(look_ahead)
        return config

    def test_family_head_is_the_action_policy_would_have_executed(self) -> None:
        from rule_alpha.agent import RuleAlphaAgent
        from scripts.build_replay_dataset import policy_observation
        from scripts.counterfactual_graph import canonical_action
        from scripts.rule_alpha_proposals import RuleAlphaProposer
        from scripts.run_single_agent_packing import _fresh_env

        env = _fresh_env(copy.deepcopy(self.config))
        self.addCleanup(env.close)
        env.reset_settings()
        actor = RuleAlphaAgent()
        proposer = RuleAlphaProposer(max_proposals=8)
        actor.get_init_states(env.get_init_states())
        proposer.get_init_states(env.get_init_states())
        env.reset_item_stream()
        observation, _info = env.reset(seed=42)

        compared = 0
        for _step in range(STEPS):
            observed = policy_observation(env, observation)
            action = actor.policy(observed)
            family = proposer.propose(observed)
            if action is None:
                # An honest decline must be an empty family, not a family
                # whose head is some other item's placement -- otherwise
                # the union would resurrect a move rule-alpha refused.
                self.assertEqual(family, [])
                break
            self.assertTrue(
                family, "policy placed an item but the family was empty"
            )
            self.assertEqual(canonical_action(action), family[0])
            compared += 1
            observation, _reward, terminated, truncated, _info = env.step(
                canonical_action(action)
            )
            if terminated or truncated:
                break
        self.assertGreater(compared, 0, "no step reached the comparison")

    def test_family_is_wider_than_one_and_free_of_duplicates(self) -> None:
        from scripts.build_replay_dataset import policy_observation
        from scripts.rule_alpha_proposals import RuleAlphaProposer, _action_key
        from scripts.run_single_agent_packing import _fresh_env

        env = _fresh_env(self.wide_pool_config())
        self.addCleanup(env.close)
        env.reset_settings()
        proposer = RuleAlphaProposer(max_proposals=8)
        proposer.get_init_states(env.get_init_states())
        env.reset_item_stream()
        observation, _info = env.reset(seed=42)

        family = proposer.propose(policy_observation(env, observation))
        self.assertGreater(
            len(family), 1,
            "a family of one is just the exact-agent candidate again",
        )
        keys = [_action_key(action) for action in family]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertLessEqual(len(family), 8)

    def test_a_one_item_pool_bounds_the_family_to_the_actors_move(self) -> None:
        """The union's width comes from the pool, and this records it.

        One proposal per visible item means a ``look_ahead: 1`` board can
        offer nothing the exact-agent candidate did not already offer.
        Whatever widens the choice set *there* has to be a second
        placement for the same item, not a placement for another item --
        a different proposer, which this union does not attempt.
        """
        from rule_alpha.agent import RuleAlphaAgent
        from scripts.build_replay_dataset import policy_observation
        from scripts.counterfactual_graph import canonical_action
        from scripts.rule_alpha_proposals import RuleAlphaProposer
        from scripts.run_single_agent_packing import _fresh_env

        env = _fresh_env(copy.deepcopy(self.config))
        self.addCleanup(env.close)
        env.reset_settings()
        actor = RuleAlphaAgent()
        proposer = RuleAlphaProposer(max_proposals=8)
        actor.get_init_states(env.get_init_states())
        proposer.get_init_states(env.get_init_states())
        env.reset_item_stream()
        observation, _info = env.reset(seed=42)

        observed = policy_observation(env, observation)
        self.assertEqual(len(observed.get("pool_list") or []), 1)
        family = proposer.propose(observed)
        self.assertEqual(len(family), 1)
        self.assertEqual(family[0], canonical_action(actor.policy(observed)))

    def test_the_limit_is_honoured_and_still_keeps_the_actors_move(self) -> None:
        from rule_alpha.agent import RuleAlphaAgent
        from scripts.build_replay_dataset import policy_observation
        from scripts.counterfactual_graph import canonical_action
        from scripts.rule_alpha_proposals import RuleAlphaProposer
        from scripts.run_single_agent_packing import _fresh_env

        env = _fresh_env(copy.deepcopy(self.config))
        self.addCleanup(env.close)
        env.reset_settings()
        actor = RuleAlphaAgent()
        capped = RuleAlphaProposer(max_proposals=1)
        actor.get_init_states(env.get_init_states())
        capped.get_init_states(env.get_init_states())
        env.reset_item_stream()
        observation, _info = env.reset(seed=42)

        observed = policy_observation(env, observation)
        action = actor.policy(observed)
        self.assertIsNotNone(action, "fixture board should place something")
        family = capped.propose(observed)
        self.assertEqual(len(family), 1)
        self.assertEqual(family[0], canonical_action(action))


@unittest.skipUnless(AVAILABLE, SKIP_REASON)
class SameItemTopKTests(unittest.TestCase):
    """The 2nd..kth candidates choose_for_item sorts and throws away.

    They are the only source of *same-item* diversity, so they are what
    widens the choice set on a one-item pool where a per-item family is
    necessarily just the actor's own move.
    """

    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(CONFIG.read_text(encoding="utf-8"))["000"]

    def board(self, config=None):
        from scripts.build_replay_dataset import policy_observation
        from scripts.run_single_agent_packing import _fresh_env

        env = _fresh_env(config or copy.deepcopy(self.config))
        self.addCleanup(env.close)
        env.reset_settings()
        init = env.get_init_states()
        env.reset_item_stream()
        observation, _info = env.reset(seed=42)
        return env, init, policy_observation(env, observation)

    def test_top_k_keeps_the_actors_move_at_the_head(self) -> None:
        from rule_alpha.agent import RuleAlphaAgent
        from scripts.counterfactual_graph import canonical_action
        from scripts.rule_alpha_proposals import RuleAlphaProposer

        _env, init, observed = self.board()
        actor = RuleAlphaAgent()
        actor.get_init_states(init)
        expected = canonical_action(actor.policy(observed))
        for k in (1, 2, 3, 5):
            proposer = RuleAlphaProposer(max_proposals=64, per_item_top_k=k)
            proposer.get_init_states(init)
            family = proposer.propose(observed)
            with self.subTest(per_item_top_k=k):
                self.assertEqual(family[0], expected)

    def test_top_k_widens_a_one_item_pool(self) -> None:
        """The bound recorded above is exactly what top-k lifts."""
        from scripts.rule_alpha_proposals import RuleAlphaProposer

        _env, init, observed = self.board()
        self.assertEqual(len(observed.get("pool_list") or []), 1)
        widths = {}
        for k in (1, 3):
            proposer = RuleAlphaProposer(max_proposals=64, per_item_top_k=k)
            proposer.get_init_states(init)
            widths[k] = len(proposer.propose(observed))
        self.assertEqual(widths[1], 1)
        self.assertGreater(widths[3], widths[1])

    def test_alternates_are_distinct_commands(self) -> None:
        from scripts.rule_alpha_proposals import RuleAlphaProposer, _action_key

        _env, init, observed = self.board()
        proposer = RuleAlphaProposer(max_proposals=64, per_item_top_k=4)
        proposer.get_init_states(init)
        family = proposer.propose(observed)
        keys = [_action_key(action) for action in family]
        self.assertEqual(len(keys), len(set(keys)))

    def test_max_proposals_still_caps_the_family(self) -> None:
        from scripts.rule_alpha_proposals import RuleAlphaProposer

        _env, init, observed = self.board()
        proposer = RuleAlphaProposer(max_proposals=2, per_item_top_k=8)
        proposer.get_init_states(init)
        self.assertLessEqual(len(proposer.propose(observed)), 2)

    def test_a_missing_hook_fails_loudly_instead_of_narrowing(self) -> None:
        """A re-vendor that drops ranked_observer must not degrade to k=1."""
        import unittest.mock

        from rule_alpha import layer1
        from scripts.rule_alpha_proposals import RuleAlphaProposer

        def without_hook(board, profile, config, max_orientations=3):
            raise AssertionError("not called")

        with unittest.mock.patch.object(
            layer1, "choose_for_item", without_hook
        ):
            RuleAlphaProposer(per_item_top_k=1)  # top-1 needs no hook
            with self.assertRaises(RuntimeError) as caught:
                RuleAlphaProposer(per_item_top_k=2)
        self.assertIn("ranked_observer", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
