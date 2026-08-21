import random
import unittest

from scripts.run_self_play_packing import play_game
from scripts.self_play_packing_game import GameRules


class FakeEnv:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.violations = 0

    def step(self, _action):
        outcome = self.outcomes.pop(0)
        self.violations += int(outcome.get("new_violations", 0))
        return (
            {"pool": len(self.outcomes)}, 0.0,
            bool(outcome.get("terminated")), False,
            {"status": {
                "is_included": bool(outcome.get("safe", True)),
                "is_valid": bool(outcome.get("safe", True)),
                "is_placed_safe": bool(outcome.get("safe", True)),
            }},
        )


def provider(env, _observation, _limit):
    if not env.outcomes or env.outcomes[0].get("no_candidates"):
        return []
    return [{
        "selection": {"rank": 0, "score": 1.0},
        "command_action": {
            "item_idx": 0, "container_idx": 0,
            "place_pos": [0.0, 0.0, 0.5], "orientation": 0,
        },
    }]


def metrics(env):
    return {"soft_covered_by_other": env.violations}


class SelfPlayPackingDriverTests(unittest.TestCase):
    def test_captures_each_pre_action_decision_state(self):
        seen = []

        def capture(**context):
            seen.append((
                context["step"], context["state"].placements,
                len(context["actions"]),
            ))
            return {"snapshot_path": f"step-{context['step']:03d}.json"}

        result = play_game(
            FakeEnv([{}, {"terminated": True}]), {}, provider,
            rules=GameRules(), handoff_rng=random.Random(1),
            policy_rng=random.Random(2), metrics_fn=metrics,
            max_steps=10, capture_fn=capture,
        )

        self.assertEqual(seen, [(0, 0, 0), (1, 1, 1)])
        self.assertEqual(len(result["captures"]), 2)
        self.assertEqual(
            result["records"][1]["state_snapshot_path"], "step-001.json"
        )
        self.assertEqual(len(result["records"][0]["candidate_set"]), 1)
        self.assertEqual(
            result["records"][0]["candidate_set"][0]["selection"]["rank"], 0
        )

    def test_no_candidate_makes_current_player_lose(self):
        result = play_game(
            FakeEnv([{"no_candidates": True}]), {}, provider,
            rules=GameRules(), handoff_rng=random.Random(1),
            policy_rng=random.Random(2), metrics_fn=metrics,
            max_steps=10,
        )

        self.assertEqual(result["terminal_reason"], "no_retained_candidate")
        self.assertEqual(result["loser"], 0)
        self.assertEqual(result["winner"], 1)
        self.assertEqual(result["rewards"], [-50.0, 50.0])
        self.assertTrue(result["outcome_target_eligible"])

    def test_valid_steps_handoff_and_charge_only_new_violation(self):
        result = play_game(
            FakeEnv([
                {}, {}, {"new_violations": 1}, {},
                {"terminated": True},
            ]), {}, provider,
            rules=GameRules(minimum_block=3, handoff_probability=1.0),
            handoff_rng=random.Random(1), policy_rng=random.Random(2),
            metrics_fn=metrics, max_steps=10,
        )

        self.assertEqual(result["terminal_reason"], "stream_exhausted")
        self.assertIsNone(result["winner"])
        self.assertEqual(result["handoff_count"], 1)
        self.assertEqual(result["completed_block_lengths"], [3])
        self.assertEqual(result["rewards"], [-5.0, 5.0])

    def test_selected_physical_failure_is_not_called_no_candidate(self):
        result = play_game(
            FakeEnv([{"safe": False, "terminated": True}]), {}, provider,
            rules=GameRules(), handoff_rng=random.Random(1),
            policy_rng=random.Random(2), metrics_fn=metrics,
            max_steps=10,
        )

        self.assertEqual(result["terminal_reason"], "selected_action_failure")
        self.assertIsNone(result["loser"])
        self.assertIsNone(result["winner"])
        self.assertEqual(result["rewards"], [0.0, 0.0])
        self.assertFalse(result["training_eligible"])
        self.assertFalse(result["outcome_target_eligible"])


if __name__ == "__main__":
    unittest.main()
