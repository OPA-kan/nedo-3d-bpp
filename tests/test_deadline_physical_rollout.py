import unittest

from scripts.deadline_physical_rollout import (
    can_start_round,
    deadline_checkpoint_search,
)


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class FakeSession:
    def __init__(self, _task_config, *, forced_action, clock, **_kwargs):
        self.clock = clock
        self.forced_action = forced_action
        self.continuation_steps = 0
        self.active = True
        self.clock.value += 0.5

    def advance_one(self):
        self.clock.value += 1.0
        self.continuation_steps += 1

    def result(self):
        return {
            "continuation_steps": self.continuation_steps,
            "checkpoint_vector": {"fill_gain": self.continuation_steps},
        }

    def close(self):
        pass


def _vector(fill):
    return {
        "fill_gain": fill,
        "soft_violation_gain": 0.0,
        "priority_covered_gain": 0.0,
        "priority_misrouted_gain": 0.0,
        "surface_total_variation_delta": 0.0,
    }


class ContestedFakeSession:
    """a and b tie at the common depth; b pulls ahead when deepened."""

    RATES = {0: 0.5, 1: 1.0, 2: 0.2}

    def __init__(self, _task_config, *, forced_action, clock, **_kwargs):
        self.clock = clock
        self.item = forced_action["item_idx"]
        self.continuation_steps = 0
        self.active = True
        self.clock.value += 0.1

    def _fill(self):
        if self.item == 2:
            return 0.2 * self.continuation_steps
        if self.continuation_steps == 0:
            return 0.0
        return 1.0 + self.RATES[self.item] * (self.continuation_steps - 1)

    def advance_one(self):
        self.clock.value += 0.2
        self.continuation_steps += 1

    def result(self):
        return {
            "safe": True,
            "continuation_steps": self.continuation_steps,
            "checkpoint_vector": _vector(self._fill()),
        }

    def close(self):
        pass


class DeadlinePhysicalRolloutTests(unittest.TestCase):
    def test_round_guard_reserves_conservative_last_round_cost(self):
        self.assertTrue(can_start_round(
            now=3.0, deadline_at=10.0, last_round_seconds=4.0,
            initial_round_seconds=2.0, safety_factor=1.5,
            minimum_reserve_seconds=0.25,
        ))
        self.assertFalse(can_start_round(
            now=4.1, deadline_at=10.0, last_round_seconds=4.0,
            initial_round_seconds=2.0, safety_factor=1.5,
            minimum_reserve_seconds=0.25,
        ))

    def test_candidates_advance_in_lockstep_and_stop_before_next_round(self):
        clock = FakeClock()
        candidates = [
            {"candidate_id": "a", "command_action": {
                "item_idx": 0, "container_idx": 0,
                "place_pos": [0, 0, 0], "orientation": 0,
            }},
            {"candidate_id": "b", "command_action": {
                "item_idx": 1, "container_idx": 0,
                "place_pos": [0, 0, 0], "orientation": 0,
            }},
        ]
        result = deadline_checkpoint_search(
            {}, environment_seed=1, prefix_actions=[], candidates=candidates,
            provider=None, legal_filter=None, top_k=3, root_step=0,
            deadline_at=4.5, max_continuation_steps=3,
            safety_factor=1.5, clock=clock, session_factory=FakeSession,
        )
        self.assertEqual(result["rounds_completed"], 1)
        self.assertEqual(result["common_total_depth"], 2)
        self.assertEqual(result["stop_reason"], "predicted_deadline")
        self.assertEqual(
            [row["continuation_steps"] for row in result["candidates"]],
            [1, 1],
        )


    def test_contested_phase_deepens_only_the_undecided_pair(self):
        clock = FakeClock()
        action = {
            "container_idx": 0, "place_pos": [0, 0, 0], "orientation": 0,
        }
        candidates = [
            {"candidate_id": "a", "command_action": {**action, "item_idx": 0}},
            {"candidate_id": "b", "command_action": {**action, "item_idx": 1}},
            {"candidate_id": "c", "command_action": {**action, "item_idx": 2}},
        ]
        result = deadline_checkpoint_search(
            {}, environment_seed=1, prefix_actions=[], candidates=candidates,
            provider=None, legal_filter=None, top_k=3, root_step=0,
            deadline_at=100.0, max_continuation_steps=1,
            contested_extra_steps=4, safety_factor=1.5, clock=clock,
            session_factory=ContestedFakeSession,
        )
        self.assertEqual(result["stop_reason"], "depth_cap")
        self.assertEqual(result["common_total_depth"], 2)
        # a and b tied on the H2 frontier; one contested round separates them
        self.assertEqual(result["contested_rounds_completed"], 1)
        self.assertEqual(result["contested_stop_reason"], "contested_resolved")
        steps = {
            row["root_candidate_id"]: row["continuation_steps"]
            for row in result["candidates"]
        }
        # the dominated candidate c is frozen at the common depth
        self.assertEqual(steps, {"a": 2, "b": 2, "c": 1})
        self.assertEqual(result["checkpoint_pareto_candidates"], ["b"])
        self.assertEqual(result["max_achieved_total_depth"], 3)

    def test_contested_phase_off_by_default_keeps_v1_behavior(self):
        clock = FakeClock()
        action = {
            "container_idx": 0, "place_pos": [0, 0, 0], "orientation": 0,
        }
        candidates = [
            {"candidate_id": "a", "command_action": {**action, "item_idx": 0}},
            {"candidate_id": "b", "command_action": {**action, "item_idx": 1}},
        ]
        result = deadline_checkpoint_search(
            {}, environment_seed=1, prefix_actions=[], candidates=candidates,
            provider=None, legal_filter=None, top_k=3, root_step=0,
            deadline_at=100.0, max_continuation_steps=1,
            safety_factor=1.5, clock=clock,
            session_factory=ContestedFakeSession,
        )
        self.assertEqual(result["contested_rounds_completed"], 0)
        self.assertIsNone(result["contested_stop_reason"])
        self.assertEqual(
            [row["continuation_steps"] for row in result["candidates"]],
            [1, 1],
        )


if __name__ == "__main__":
    unittest.main()
