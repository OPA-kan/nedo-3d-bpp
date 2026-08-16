import importlib.util
import pathlib
import sys
import unittest
from unittest import mock

AGENT_PATH = pathlib.Path(__file__).parents[1] / "agent" / "agent.py"
SPEC = importlib.util.spec_from_file_location(
    "safety_rerank_agent", AGENT_PATH
)
agent = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = agent
SPEC.loader.exec_module(agent)


class _FakeDecision:
    def __init__(self, item, pos, score, orientation=0):
        self.action = {
            "item_idx": item,
            "container_idx": 0,
            "place_pos": list(pos),
            "orientation": orientation,
        }
        self.score = score
        self.candidate = object()


def _rerank(logits, decisions, incumbent):
    """Run safety_rerank_record with the scorer mocked out.

    logits[0] is the incumbent's own score; logits[1:] are the retained
    candidates in rank order.
    """
    with mock.patch.object(
        agent, "safety_shadow_logit", side_effect=list(logits)
    ):
        return agent.safety_rerank_record({}, decisions, incumbent)


class SafetyRerankRecordTests(unittest.TestCase):
    def test_above_trigger_never_proposes(self) -> None:
        incumbent = _FakeDecision(0, (0, 0, 0), 5.0)
        other = _FakeDecision(1, (1, 0, 0), 4.9)
        record = _rerank([3.5, 3.5, 30.0], [incumbent, other], incumbent)
        self.assertFalse(record["triggered"])
        self.assertFalse(record["would_swap"])
        self.assertIsNone(record["proposed_rank"])

    def test_triggered_swap_picks_highest_eligible_logit(self) -> None:
        incumbent = _FakeDecision(0, (0, 0, 0), 5.0)
        near = _FakeDecision(1, (1, 0, 0), 4.9)
        far = _FakeDecision(2, (2, 0, 0), 4.8)
        record = _rerank(
            [-0.5, -0.5, 4.0, 9.0], [incumbent, near, far], incumbent
        )
        self.assertTrue(record["triggered"])
        self.assertTrue(record["would_swap"])
        self.assertEqual(record["proposed_rank"], 2)
        self.assertEqual(record["proposed_logit"], 9.0)
        self.assertTrue(record["candidates"][0]["is_incumbent"])

    def test_score_conservation_excludes_expensive_swaps(self) -> None:
        incumbent = _FakeDecision(0, (0, 0, 0), 10.0)
        cheap = _FakeDecision(1, (1, 0, 0), 8.9)  # loses 1.1 > 1.0 abs
        record = _rerank([-0.5, -0.5, 9.0], [incumbent, cheap], incumbent)
        self.assertTrue(record["triggered"])
        self.assertFalse(record["would_swap"])

    def test_absolute_bound_rescues_near_zero_score_states(self) -> None:
        # The Gate 2 inertness case: incumbent score near zero, safe
        # alternative one score unit below. The relative rule blocked
        # every such rescue; the absolute rule licenses it.
        incumbent = _FakeDecision(0, (0, 0, 0), -0.023)
        rescue = _FakeDecision(1, (1, 0, 0), -0.658)
        record = _rerank(
            [-2.0, -2.0, 6.2], [incumbent, rescue], incumbent
        )
        self.assertTrue(record["would_swap"])
        self.assertEqual(record["proposed_rank"], 1)

    def test_margin_requires_real_escape(self) -> None:
        incumbent = _FakeDecision(0, (0, 0, 0), 5.0)
        # Logit 2.5 clears the trigger but not incumbent+margin (1.0+2.0).
        marginal = _FakeDecision(1, (1, 0, 0), 5.0)
        record = _rerank(
            [1.0, 1.0, 2.5], [incumbent, marginal], incumbent
        )
        self.assertTrue(record["triggered"])
        self.assertFalse(record["would_swap"])

    def test_never_refuses_when_no_alternative_exists(self) -> None:
        incumbent = _FakeDecision(0, (0, 0, 0), 5.0)
        record = _rerank([-3.0, -3.0], [incumbent], incumbent)
        self.assertTrue(record["triggered"])
        self.assertFalse(record["would_swap"])

    def test_missing_model_returns_none(self) -> None:
        incumbent = _FakeDecision(0, (0, 0, 0), 5.0)
        with mock.patch.object(
            agent, "safety_shadow_logit", return_value=None
        ):
            record = agent.safety_rerank_record({}, [incumbent], incumbent)
        self.assertIsNone(record)

    def test_default_mode_is_off_and_constants_are_preregistered(self):
        self.assertEqual(agent.SAFETY_RERANK_MODE, "off")
        self.assertEqual(agent.SAFETY_RERANK_TRIGGER_LOGIT, 2.0)
        self.assertEqual(agent.SAFETY_RERANK_MARGIN_LOGIT, 2.0)
        self.assertEqual(agent.SAFETY_RERANK_MAX_SCORE_LOSS_ABS, 1.0)


if __name__ == "__main__":
    unittest.main()
