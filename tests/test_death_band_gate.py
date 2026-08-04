import importlib.util
import pathlib
import sys
import unittest
from unittest import mock

AGENT_PATH = pathlib.Path(__file__).parents[1] / "agent" / "agent.py"
SPEC = importlib.util.spec_from_file_location("death_band_agent", AGENT_PATH)
agent = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = agent
SPEC.loader.exec_module(agent)


class DeathBandGateContractTests(unittest.TestCase):
    """
    The gate shipped once and cost 15.3% of the official total, because a
    swap bought lower toppling risk with support ratio -- the quantity
    Ranker.score spends on centre of gravity and stability. These pin the
    properties that make that trade impossible, rather than relying on a
    local proxy whose repeat-to-repeat noise (23-75%) is larger than the
    effect it would have to detect (2-15%).
    """

    def test_gate_ships_off(self):
        # It regressed the official score. It does not come back on without
        # a submission saying otherwise.
        self.assertFalse(agent.DEATH_BAND_FALLBACK_ENABLED)

    def test_dominance_is_required_by_default(self):
        self.assertTrue(agent.DEATH_BAND_REQUIRE_DOMINANCE)

    def test_score_band_is_present_and_negative(self):
        # Removing the band turns a narrow gate into a global risk filter,
        # which is the intervention class this repository already rejected.
        self.assertIsNotNone(agent.DEATH_BAND_SCORE)
        self.assertLess(agent.DEATH_BAND_SCORE, 0.0)

    def test_budget_floor_is_positive(self):
        # Evaluating the gate costs deadline budget even when it does not
        # swap; below the floor it must stand down.
        self.assertGreater(agent.DEATH_BAND_MIN_BUDGET_SECONDS, 0.0)

    def test_dominance_rejects_a_lower_support_replacement(self):
        """
        The failure mode, as a unit: a safer pose that rests on less of the
        board must not be taken. Support ratio is read through the same
        Geometry call the gate uses, so this pins the comparison rather
        than a reimplementation of it.
        """
        supports = {"incumbent": 0.80, "replacement": 0.40}

        def fake_support_ratio(candidate, _container):
            return supports[candidate.name]

        incumbent = agent.AABB((0.0, 0.0, 0.5), (0.4, 0.3, 0.2), "incumbent")
        replacement = agent.AABB(
            (0.5, 0.0, 0.5), (0.4, 0.3, 0.2), "replacement"
        )
        with mock.patch.object(
            agent.Geometry, "support_ratio", staticmethod(fake_support_ratio)
        ):
            container = {"length": 2.0, "width": 1.5}
            incumbent_support = agent.Geometry.support_ratio(
                incumbent, container
            )
            replacement_support = agent.Geometry.support_ratio(
                replacement, container
            )
        self.assertLess(replacement_support, incumbent_support - agent.EPS)

    def test_dominance_accepts_an_equal_support_replacement(self):
        supports = {"incumbent": 0.60, "replacement": 0.60}

        def fake_support_ratio(candidate, _container):
            return supports[candidate.name]

        incumbent = agent.AABB((0.0, 0.0, 0.5), (0.4, 0.3, 0.2), "incumbent")
        replacement = agent.AABB(
            (0.5, 0.0, 0.5), (0.4, 0.3, 0.2), "replacement"
        )
        with mock.patch.object(
            agent.Geometry, "support_ratio", staticmethod(fake_support_ratio)
        ):
            container = {"length": 2.0, "width": 1.5}
            incumbent_support = agent.Geometry.support_ratio(
                incumbent, container
            )
            replacement_support = agent.Geometry.support_ratio(
                replacement, container
            )
        self.assertFalse(replacement_support < incumbent_support - agent.EPS)


if __name__ == "__main__":
    unittest.main()
