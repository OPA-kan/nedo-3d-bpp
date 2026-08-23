import random
import unittest
from types import SimpleNamespace
from unittest import mock

from scripts.run_self_play_packing import build_physical_puct_search
from scripts.self_play_packing_game import GameRules

ROOT = {
    "candidate_id": "root",
    "selection": {"rank": 0},
    "command_action": {
        "item_idx": 0, "container_idx": 0,
        "place_pos": [0.0, 0.0, 0.5], "orientation": 0,
    },
}


def fake_leaf_vector(**_kwargs):
    return {
        "prediction_contract": "V_pi_behavior_leaf_bootstrap_v1",
        "semantics": "V_pi_behavior_not_V_star",
        "ensemble_size": 3,
        "heads": {
            "fill_return": {"mean": 2.0, "variance": 0.0, "members": [2.0] * 3},
        },
    }


def branch_metrics(_env):
    return {
        "placed_count": 1,
        "fill_score_proxy": 10.0,
        "soft_covered_by_other": 0,
        "priority_covered_by_other": 0,
        "priority_misrouted": 0,
        "surface_total_variation": 0.25,
    }


def run_search(simulation_env_factory):
    search = build_physical_puct_search(
        {}, case_id="case", environment_seed=42,
        candidate_provider=lambda *_args: [],
        legal_filter_fn=lambda **context: (context["candidates"], {}),
        rules=GameRules(minimum_block=10), top_k=1,
        simulations=1, horizon=1, action_temperature=0.0,
        metrics_fn=branch_metrics, env_factory=simulation_env_factory,
        leaf_vector_fn=fake_leaf_vector,
    )
    _chosen, result = search(
        env=object(), observation={}, candidates=[dict(ROOT)], actions=[],
        state=SimpleNamespace(
            current_player=0, block_length=0,
            placements=0, handoff_count=0,
        ), step=0, policy_rng=random.Random(3),
    )
    return result["multi_head_branch_samples"][0]


@mock.patch("scripts.run_self_play_packing.board_fingerprint", return_value="fp")
@mock.patch("scripts.run_self_play_packing.state_snapshot", return_value={})
@mock.patch(
    "scripts.run_self_play_packing.policy_observation",
    side_effect=lambda _e, o: o,
)
@mock.patch(
    "scripts.run_self_play_packing.capture_replay_contract",
    return_value={"future_stream_id": "stream-1"},
)
@mock.patch("scripts.run_self_play_packing.replay_action_prefix")
class LeafVectorShadowTests(unittest.TestCase):
    def _arm_replay(self, replay):
        replay.return_value = SimpleNamespace(
            matched=True, observation={}, actions_replayed=0,
            observed_fingerprint="fp", error=None,
        )

    def test_horizon_leaf_records_prediction_without_touching_measurement(
        self, replay, *_mocks,
    ):
        self._arm_replay(replay)

        class HorizonEnv:
            def step(self, _action):
                return {}, 0.0, False, False, {"status": {
                    "is_included": True, "is_valid": True,
                    "is_placed_safe": True,
                }}

            def close(self):
                pass

        sample = run_search(HorizonEnv)

        self.assertEqual(sample["termination"], "horizon")
        predicted = sample["predicted_leaf_value"]
        self.assertEqual(
            predicted["prediction_contract"],
            "V_pi_behavior_leaf_bootstrap_v1",
        )
        self.assertEqual(
            predicted["heads"]["fill_return"]["members"], [2.0, 2.0, 2.0]
        )
        # measured joint outcome is untouched by the shadow prediction
        self.assertEqual(sample["raw_outcome_vector"]["fill_gain"], 0.0)
        self.assertEqual(sample["schema_version"], 2)

    def test_censored_termination_skips_prediction_with_reason(
        self, replay, *_mocks,
    ):
        self._arm_replay(replay)

        class TruncatingEnv:
            def step(self, _action):
                return {}, 0.0, False, True, {"status": {
                    "is_included": True, "is_valid": True,
                    "is_placed_safe": True,
                }}

            def close(self):
                pass

        sample = run_search(TruncatingEnv)

        self.assertEqual(sample["termination"], "simulator_truncated")
        self.assertEqual(
            sample["predicted_leaf_value"],
            {"skipped_reason": "simulator_truncated"},
        )


if __name__ == "__main__":
    unittest.main()
