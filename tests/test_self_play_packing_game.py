import random
import unittest

from scripts.self_play_packing_game import (
    GameRules,
    GameState,
    apply_attribute_reward,
    apply_terminal_loss,
    advance_after_placement,
    choose_candidate,
)


class SelfPlayPackingRulesTests(unittest.TestCase):
    def test_handoff_cannot_happen_before_minimum_block(self):
        rules = GameRules(minimum_block=3, handoff_probability=1.0)
        state = GameState(current_player=0)
        rng = random.Random(1)

        first = advance_after_placement(state, rules, rng)
        second = advance_after_placement(state, rules, rng)
        third = advance_after_placement(state, rules, rng)

        self.assertFalse(first["handoff"])
        self.assertFalse(second["handoff"])
        self.assertTrue(third["handoff"])
        self.assertEqual(third["completed_block_length"], 3)
        self.assertEqual(state.current_player, 1)
        self.assertEqual(state.block_length, 0)

    def test_failed_handoff_draw_extends_the_same_block(self):
        rules = GameRules(minimum_block=3, handoff_probability=0.0)
        state = GameState(current_player=1)
        rng = random.Random(2)

        events = [advance_after_placement(state, rules, rng) for _ in range(5)]

        self.assertFalse(any(event["handoff"] for event in events))
        self.assertEqual(state.current_player, 1)
        self.assertEqual(state.block_length, 5)

    def test_dense_attribute_reward_is_incremental_and_zero_sum(self):
        rules = GameRules(attribute_penalty=5.0)
        rewards = [0.0, 0.0]

        event = apply_attribute_reward(
            rewards, mover=0,
            before={
                "soft_covered_by_other": 1,
                "priority_covered_by_other": 0,
                "priority_misrouted": 0,
            },
            after={
                "soft_covered_by_other": 2,
                "priority_covered_by_other": 1,
                "priority_misrouted": 0,
            },
            rules=rules,
        )

        self.assertEqual(event["new_violations"], 2)
        self.assertEqual(event["reward_delta"], [-10.0, 10.0])
        self.assertEqual(rewards, [-10.0, 10.0])
        self.assertEqual(sum(rewards), 0.0)

    def test_preexisting_or_decreasing_violation_is_not_recharged(self):
        rewards = [0.0, 0.0]
        event = apply_attribute_reward(
            rewards, mover=1,
            before={"soft_covered_by_other": 2},
            after={"soft_covered_by_other": 1},
            rules=GameRules(attribute_penalty=5.0),
        )

        self.assertEqual(event["new_violations"], 0)
        self.assertEqual(rewards, [0.0, 0.0])

    def test_terminal_loss_is_symmetric_and_zero_sum(self):
        rewards = [5.0, -5.0]
        event = apply_terminal_loss(
            rewards, loser=1, rules=GameRules(terminal_reward=50.0)
        )

        self.assertEqual(event["winner"], 0)
        self.assertEqual(event["reward_delta"], [50.0, -50.0])
        self.assertEqual(rewards, [55.0, -55.0])

    def test_both_players_use_the_same_temperature_policy(self):
        candidates = [
            {"selection": {"rank": rank}, "command_action": {"item_idx": rank}}
            for rank in range(3)
        ]
        choices = []
        for _player in (0, 1):
            chosen = choose_candidate(
                candidates, mode="temperature", temperature=1.5,
                rng=random.Random(99),
            )
            choices.append(chosen["selection"]["rank"])

        self.assertEqual(choices[0], choices[1])


if __name__ == "__main__":
    unittest.main()
