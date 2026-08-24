import random
import unittest
from types import SimpleNamespace
from unittest import mock

from scripts.run_self_play_packing import (
    _candidate_set_id,
    build_exact_physical_legal_filter,
    build_physical_puct_search,
    play_game,
)
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
    def test_candidate_set_id_tracks_support_not_order_or_provenance(self):
        action_a = {
            "item_idx": 0, "container_idx": 0,
            "place_pos": [0.0, 0.0, 0.5], "orientation": 0,
        }
        action_b = {
            "item_idx": 1, "container_idx": 0,
            "place_pos": [0.1, 0.0, 0.5], "orientation": 1,
        }

        def row(name, action, source):
            return {
                "candidate_id": name,
                "command_action": action,
                "selection": {"rank": 0},
                "proposal_provenance": {
                    "source": source, "proposal_probability": 0.25,
                },
            }

        left = [row("a", action_a, "learned"), row("b", action_b, "coverage")]
        right = [
            row("other-b", action_b, "learned"),
            row("other-a", action_a, "rescue"),
            row("duplicate-a", action_a, "coverage"),
        ]

        self.assertEqual(_candidate_set_id(left), _candidate_set_id(right))

    @mock.patch("scripts.run_self_play_packing.board_fingerprint", return_value="fp")
    @mock.patch("scripts.run_self_play_packing.state_snapshot", return_value={})
    @mock.patch("scripts.run_self_play_packing.policy_observation", side_effect=lambda _e, o: o)
    @mock.patch("scripts.run_self_play_packing.capture_replay_contract", return_value={})
    @mock.patch("scripts.run_self_play_packing.replay_action_prefix")
    def test_physical_puct_censors_bounded_exhaustion_without_terminal_loss(
        self, replay, _contract, _observation, _snapshot, _fingerprint,
    ):
        replay.return_value = SimpleNamespace(
            matched=True, observation={}, actions_replayed=0,
            observed_fingerprint="fp", error=None,
        )

        def row(name, item_idx, rank):
            return {
                "candidate_id": name,
                "selection": {"rank": rank},
                "command_action": {
                    "item_idx": item_idx, "container_idx": 0,
                    "place_pos": [item_idx * 0.1, 0.0, 0.5],
                    "orientation": 0,
                },
            }

        root_candidates = [row("dead", 0, 0), row("alive", 1, 1)]
        continuation = row("finish", 2, 0)

        class SimulationEnv:
            def __init__(self):
                self.last_item = None
                self.closed = False

            def step(self, action):
                self.last_item = action["item_idx"]
                return (
                    {}, 0.0, self.last_item == 2, False,
                    {"status": {
                        "is_included": True, "is_valid": True,
                        "is_placed_safe": True,
                    }},
                )

            def close(self):
                self.closed = True

        simulations = []

        def factory():
            env = SimulationEnv()
            simulations.append(env)
            return env

        def provider_for_branch(env, _observation, _limit):
            return [continuation] if env.last_item == 1 else []

        def legal_filter(**context):
            return context["candidates"], {
                "rejected_count": 0,
            }

        search = build_physical_puct_search(
            {}, case_id="case", environment_seed=42,
            candidate_provider=provider_for_branch,
            legal_filter_fn=legal_filter, rules=GameRules(minimum_block=10),
            top_k=2, simulations=4, horizon=2, cpuct=2.0,
            prior_mode="uniform", action_temperature=1.0,
            temperature_drop_step=0,
            metrics_fn=lambda _env: {}, env_factory=factory,
        )

        chosen, result = search(
            env=object(), observation={}, candidates=root_candidates,
            actions=[], state=SimpleNamespace(
                current_player=0, block_length=0,
                placements=0, handoff_count=0,
            ), step=0, policy_rng=random.Random(9),
        )

        self.assertIn(chosen["candidate_id"], {"dead", "alive"})
        self.assertEqual(result["action_temperature"], 0.0)
        self.assertEqual(result["configured_action_temperature"], 1.0)
        self.assertEqual(result["temperature_drop_step"], 0)
        self.assertEqual(sum(row["visits"] for row in result["policy_target"]), 4)
        self.assertGreaterEqual(
            result["simulation_terminal_reasons"][
                "bounded_candidate_exhaustion_censored"
            ],
            1,
        )
        self.assertEqual(result["candidate_exhaustion_unique_nodes"], 1)
        dead = next(
            row for row in result["policy_target"]
            if row["candidate_id"] == "dead"
        )
        self.assertEqual(dead["q"], 0.0)
        self.assertGreater(
            dead["multi_head_target"]["censored_samples"], 0
        )
        self.assertEqual(
            dead["multi_head_target"]["heads"]["fill_gain"][
                "eligible_count"
            ],
            0,
        )
        censored = next(
            row for row in result["multi_head_branch_samples"]
            if row["root_candidate_id"] == "dead"
        )
        self.assertEqual(
            censored["heads"]["game_reward"]["censor_reason"],
            "bounded_candidate_exhaustion",
        )
        self.assertFalse(
            censored["heads"]["game_reward"]["target_eligible"]
        )
        self.assertTrue(all(env.closed for env in simulations))

    @mock.patch("scripts.run_self_play_packing.board_fingerprint", return_value="fp")
    @mock.patch("scripts.run_self_play_packing.state_snapshot", return_value={})
    @mock.patch("scripts.run_self_play_packing.policy_observation", side_effect=lambda _e, o: o)
    @mock.patch("scripts.run_self_play_packing.capture_replay_contract", return_value={})
    @mock.patch("scripts.run_self_play_packing.replay_action_prefix")
    def test_exhaustion_shadow_widening_finds_safe_candidate_without_selecting_it(
        self, replay, _contract, _observation, _snapshot, _fingerprint,
    ):
        replay.return_value = SimpleNamespace(
            matched=True, observation={}, actions_replayed=0,
            observed_fingerprint="fp", error=None,
        )

        def row(name, item_idx, rank, safe=True):
            return {
                "candidate_id": name,
                "selection": {"rank": rank, "shadow_safe": safe},
                "command_action": {
                    "item_idx": item_idx, "container_idx": 0,
                    "place_pos": [item_idx * 0.1, 0.0, 0.5],
                    "orientation": 0,
                },
            }

        root = row("root", 0, 0)
        rejected = [row("bad-0", 1, 0, False), row("bad-1", 2, 1, False)]
        recovered = row("wide-safe", 3, 2, True)

        class SimulationEnv:
            def __init__(self):
                self.at_depth_one = False

            def step(self, _action):
                self.at_depth_one = True
                return {}, 0.0, False, False, {"status": {
                    "is_included": True, "is_valid": True,
                    "is_placed_safe": True,
                }}

            def close(self):
                pass

        provider_limits = []

        def provider(env, _observation, limit):
            self.assertTrue(env.at_depth_one)
            provider_limits.append(limit)
            return (rejected + [recovered])[:limit]

        def legal_filter(**context):
            retained = [
                candidate for candidate in context["candidates"]
                if candidate["selection"]["shadow_safe"]
            ]
            return retained, {
                "proposal_count": len(context["candidates"]),
                "safe_count": len(retained),
                "rejected_count": len(context["candidates"]) - len(retained),
            }

        search = build_physical_puct_search(
            {}, case_id="case", environment_seed=42,
            candidate_provider=provider, legal_filter_fn=legal_filter,
            rules=GameRules(minimum_block=10), top_k=2,
            candidate_audit_limit=3, simulations=1, horizon=2,
            action_temperature=0.0, metrics_fn=lambda _env: {},
            leaf_value_fn=lambda **_context: self.fail(
                "censored exhaustion must not call the value model"
            ),
            env_factory=SimulationEnv,
        )

        chosen, result = search(
            env=object(), observation={}, candidates=[root], actions=[],
            state=SimpleNamespace(
                current_player=0, block_length=0,
                placements=0, handoff_count=0,
            ), step=0, policy_rng=random.Random(3),
        )

        self.assertEqual(chosen["candidate_id"], "root")
        self.assertEqual(provider_limits, [2, 3])
        self.assertEqual(result["candidate_exhaustion_unique_nodes"], 1)
        self.assertEqual(result["leaf_value_calls"], 0)
        self.assertEqual(result["candidate_exhaustion_shadow_summary"], {
            "audited_nodes": 1,
            "top_k_proposal_empty_nodes": 0,
            "top_k_all_rejected_nodes": 1,
            "wider_safe_recovered_nodes": 1,
            "wider_proposal_empty_nodes": 0,
            "wider_all_rejected_nodes": 0,
            "prefix_mismatch_nodes": 0,
        })
        audit = result["candidate_exhaustion_audits"][0]
        self.assertEqual(audit["top_k_safe_count"], 0)
        self.assertEqual(audit["wider_safe_count"], 1)
        self.assertEqual(audit["recovered_candidate_ids"], ["wide-safe"])
        self.assertTrue(audit["root_id"].startswith("puct-root-"))
        self.assertEqual(audit["relative_action_prefix"][0]["item_idx"], 0)
        self.assertEqual(audit["board_fingerprint"], "fp")
        self.assertIn("replay_contract", audit)

    @mock.patch("scripts.run_self_play_packing.board_fingerprint", return_value="fp")
    @mock.patch("scripts.run_self_play_packing.state_snapshot", return_value={})
    @mock.patch("scripts.run_self_play_packing.policy_observation", side_effect=lambda _e, o: o)
    @mock.patch("scripts.run_self_play_packing.capture_replay_contract", return_value={
        "seed": 42,
        "item_order": [0],
        "action_prefix": [],
        "future_stream_id": "stream-1",
        "action_prefix_id": "prefix-0",
    })
    @mock.patch("scripts.run_self_play_packing.replay_action_prefix")
    def test_physical_puct_saves_complete_multi_head_branch_teacher(
        self, replay, _contract, _observation, _snapshot, _fingerprint,
    ):
        replay.return_value = SimpleNamespace(
            matched=True, observation={}, actions_replayed=0,
            observed_fingerprint="fp", error=None,
        )
        root = {
            "candidate_id": "root",
            "selection": {"rank": 0},
            "command_action": {
                "item_idx": 0, "container_idx": 0,
                "place_pos": [0.0, 0.0, 0.5], "orientation": 0,
            },
        }

        class SimulationEnv:
            def __init__(self):
                self.placed = 0
                self.violations = 0

            def step(self, _action):
                self.placed += 1
                self.violations += 1
                return {}, 0.0, False, False, {"status": {
                    "is_included": True, "is_valid": True,
                    "is_placed_safe": True,
                }}

            def close(self):
                pass

        def branch_metrics(env):
            return {
                "placed_count": env.placed,
                "fill_score_proxy": 10.0 * env.placed,
                "soft_covered_by_other": env.violations,
                "priority_covered_by_other": 0,
                "priority_misrouted": 0,
                "surface_total_variation": 0.25 * env.placed,
            }

        search = build_physical_puct_search(
            {}, case_id="case", environment_seed=42,
            candidate_provider=lambda *_args: [],
            legal_filter_fn=lambda **context: (context["candidates"], {}),
            rules=GameRules(minimum_block=10), top_k=1,
            simulations=1, horizon=1, action_temperature=0.0,
            metrics_fn=branch_metrics, env_factory=SimulationEnv,
        )

        _chosen, result = search(
            env=object(), observation={}, candidates=[root], actions=[],
            state=SimpleNamespace(
                current_player=0, block_length=0,
                placements=0, handoff_count=0,
            ), step=0, policy_rng=random.Random(3),
        )

        sample = result["multi_head_branch_samples"][0]
        self.assertEqual(sample["schema_version"], 2)
        self.assertEqual(sample["joint_outcome_contract_version"], 2)
        self.assertEqual(
            sample["objective_contract_version"], "vector_no_weighted_sum_v1"
        )
        self.assertEqual(
            sample["search_allocation"]["reason"], "scalar_puct_traversal"
        )
        self.assertTrue(sample["outcome_sample_id"])
        self.assertTrue(sample["exogenous_world_id"])
        self.assertEqual(sample["exogenous_world_sample_index"], 0)
        self.assertEqual(sample["candidate_set_id"], result["candidate_set_id"])
        self.assertEqual(
            sample["raw_outcome_vector"]["fill_gain"], 10.0
        )
        self.assertTrue(sample["head_eligibility"]["fill_gain"])
        self.assertEqual(
            sample["root_candidate_provenance"]["source"],
            "legacy_provider",
        )
        self.assertEqual(sample["root_candidate_id"], "root")
        self.assertEqual(
            sample["target_semantics"],
            "root_action_bounded_outcome_not_leaf_value",
        )
        self.assertEqual(sample["termination"], "horizon")
        self.assertEqual(sample["relative_action_prefix"][0]["item_idx"], 0)
        self.assertEqual(sample["heads"]["fill_gain"]["value"], 10.0)
        self.assertTrue(
            sample["heads"]["fill_gain"]["target_eligible"]
        )
        self.assertIsNone(
            sample["heads"]["fill_gain"]["censor_reason"]
        )
        self.assertEqual(sample["heads"]["placed_gain"]["value"], 1.0)
        self.assertEqual(sample["heads"]["soft_violation_gain"]["value"], 1.0)
        self.assertFalse(
            sample["heads"]["stability_peak_kinetic_energy"][
                "target_eligible"
            ]
        )
        aggregate = result["policy_target"][0]["multi_head_target"]
        self.assertEqual(aggregate["complete_samples"], 1)
        self.assertEqual(
            aggregate["heads"]["fill_gain"]["mean"], 10.0
        )
        self.assertEqual(aggregate["schema_version"], 2)

    @mock.patch("scripts.run_self_play_packing.board_fingerprint", return_value="fp")
    @mock.patch("scripts.run_self_play_packing.state_snapshot", return_value={})
    @mock.patch("scripts.run_self_play_packing.policy_observation", side_effect=lambda _e, o: o)
    @mock.patch(
        "scripts.run_self_play_packing.capture_replay_contract",
        return_value={"future_stream_id": "stream-1"},
    )
    @mock.patch("scripts.run_self_play_packing.replay_action_prefix")
    def test_root_candidate_replicas_share_exogenous_world_indices(
        self, replay, _contract, _observation, _snapshot, _fingerprint,
    ):
        replay.return_value = SimpleNamespace(
            matched=True, observation={}, actions_replayed=0,
            observed_fingerprint="fp", error=None,
        )

        def row(name, item_idx, rank):
            return {
                "candidate_id": name,
                "selection": {"rank": rank},
                "command_action": {
                    "item_idx": item_idx, "container_idx": 0,
                    "place_pos": [item_idx * 0.1, 0.0, 0.5],
                    "orientation": 0,
                },
            }

        class SimulationEnv:
            def step(self, _action):
                return {}, 0.0, False, False, {"status": {
                    "is_included": True, "is_valid": True,
                    "is_placed_safe": True,
                }}

            def close(self):
                pass

        search = build_physical_puct_search(
            {}, case_id="case", environment_seed=42,
            candidate_provider=lambda *_args: [],
            legal_filter_fn=lambda **context: (context["candidates"], {}),
            rules=GameRules(minimum_block=1, handoff_probability=0.5),
            top_k=2, simulations=2, horizon=1, cpuct=100.0,
            action_temperature=0.0, metrics_fn=lambda _env: {},
            env_factory=SimulationEnv, search_seed=91,
        )

        _chosen, result = search(
            env=object(), observation={},
            candidates=[row("a", 0, 0), row("b", 1, 1)], actions=[],
            state=SimpleNamespace(
                current_player=0, block_length=0,
                placements=0, handoff_count=0,
            ), step=0, policy_rng=random.Random(3),
        )

        samples = result["multi_head_branch_samples"]
        self.assertEqual({row["root_candidate_id"] for row in samples}, {"a", "b"})
        self.assertEqual(
            {row["exogenous_world_sample_index"] for row in samples}, {0}
        )
        self.assertEqual(
            len({row["exogenous_world_id"] for row in samples}), 1
        )
        self.assertEqual(
            len({
                (
                    row["leaf_game_state"]["player_to_move"],
                    row["leaf_game_state"]["handoff_count"],
                )
                for row in samples
            }),
            1,
        )

    @mock.patch("scripts.run_self_play_packing.board_fingerprint", return_value="fp")
    @mock.patch("scripts.run_self_play_packing.state_snapshot", return_value={})
    @mock.patch("scripts.run_self_play_packing.policy_observation", side_effect=lambda _e, o: o)
    @mock.patch(
        "scripts.run_self_play_packing.capture_replay_contract",
        return_value={"future_stream_id": "stream-1"},
    )
    @mock.patch("scripts.run_self_play_packing.replay_action_prefix")
    def test_paired_round_robin_forces_complete_root_world_blocks(
        self, replay, _contract, _observation, _snapshot, _fingerprint,
    ):
        replay.return_value = SimpleNamespace(
            matched=True, observation={}, actions_replayed=0,
            observed_fingerprint="fp", error=None,
        )

        def row(name, item_idx, rank):
            return {
                "candidate_id": name, "selection": {"rank": rank},
                "command_action": {
                    "item_idx": item_idx, "container_idx": 0,
                    "place_pos": [item_idx * 0.1, 0.0, 0.5],
                    "orientation": 0,
                },
            }

        class SimulationEnv:
            def step(self, _action):
                return {}, 0.0, False, False, {"status": {
                    "is_included": True, "is_valid": True,
                    "is_placed_safe": True,
                }}

            def close(self):
                pass

        search = build_physical_puct_search(
            {}, case_id="case", environment_seed=42,
            candidate_provider=lambda *_args: [],
            legal_filter_fn=lambda **context: (context["candidates"], {}),
            rules=GameRules(minimum_block=10), top_k=2,
            simulations=4, horizon=1, action_temperature=0.0,
            metrics_fn=lambda _env: {}, env_factory=SimulationEnv,
            search_seed=91, root_allocation_mode="paired_round_robin",
        )
        candidates = [row("rank0", 0, 0), row("rank1", 1, 1)]

        chosen, result = search(
            env=object(), observation={}, candidates=candidates, actions=[],
            state=SimpleNamespace(
                current_player=0, block_length=0,
                placements=0, handoff_count=0,
            ), step=0, policy_rng=random.Random(3),
        )

        samples = result["multi_head_branch_samples"]
        self.assertEqual(
            [row["root_candidate_id"] for row in samples],
            ["rank0", "rank1", "rank0", "rank1"],
        )
        self.assertEqual(
            [row["exogenous_world_sample_index"] for row in samples],
            [0, 0, 1, 1],
        )
        self.assertEqual(result["policy_target"], [])
        self.assertFalse(result["policy_target_eligible"])
        self.assertEqual(result["root_allocation_mode"], "paired_round_robin")
        self.assertEqual(
            result["execution_policy"], "baseline_rank0_not_search_improvement"
        )
        self.assertEqual(
            samples[0]["search_allocation"]["reason"],
            "paired_round_robin_root_scalar_puct_continuation",
        )
        self.assertEqual(chosen["candidate_id"], "rank0")

        incomplete_search = build_physical_puct_search(
            {}, case_id="case", environment_seed=42,
            candidate_provider=lambda *_args: [],
            legal_filter_fn=lambda **context: (context["candidates"], {}),
            rules=GameRules(minimum_block=10), top_k=2,
            simulations=3, horizon=1, action_temperature=0.0,
            metrics_fn=lambda _env: {}, env_factory=SimulationEnv,
            search_seed=91, root_allocation_mode="paired_round_robin",
        )
        with self.assertRaisesRegex(ValueError, "multiple of the root candidate"):
            incomplete_search(
                env=object(), observation={}, candidates=candidates, actions=[],
                state=SimpleNamespace(
                    current_player=0, block_length=0,
                    placements=0, handoff_count=0,
                ), step=0, policy_rng=random.Random(3),
            )

    def test_paired_round_robin_rejects_root_dirichlet_noise(self):
        with self.assertRaisesRegex(ValueError, "does not use root Dirichlet"):
            build_physical_puct_search(
                {}, case_id="case", environment_seed=42,
                candidate_provider=lambda *_args: [],
                legal_filter_fn=lambda **context: (context["candidates"], {}),
                rules=GameRules(minimum_block=10), top_k=2,
                simulations=4, horizon=1, action_temperature=0.0,
                metrics_fn=lambda _env: {}, env_factory=lambda: object(),
                search_seed=91, root_allocation_mode="paired_round_robin",
                root_dirichlet_alpha=0.3, root_dirichlet_epsilon=0.25,
            )

    @mock.patch("scripts.run_self_play_packing.board_fingerprint", return_value="fp")
    @mock.patch("scripts.run_self_play_packing.state_snapshot", return_value={})
    @mock.patch("scripts.run_self_play_packing.policy_observation", side_effect=lambda _e, o: o)
    @mock.patch("scripts.run_self_play_packing.capture_replay_contract", return_value={})
    @mock.patch("scripts.run_self_play_packing.replay_action_prefix")
    def test_opt_in_candidate_rescue_makes_wider_safe_branch_searchable(
        self, replay, _contract, _observation, _snapshot, _fingerprint,
    ):
        replay.return_value = SimpleNamespace(
            matched=True, observation={}, actions_replayed=0,
            observed_fingerprint="fp", error=None,
        )

        def row(name, item_idx, rank, safe=True):
            return {
                "candidate_id": name,
                "selection": {"rank": rank, "shadow_safe": safe},
                "command_action": {
                    "item_idx": item_idx, "container_idx": 0,
                    "place_pos": [item_idx * 0.1, 0.0, 0.5],
                    "orientation": 0,
                },
            }

        root = row("root", 0, 0)
        rejected = [row("bad-0", 1, 0, False), row("bad-1", 2, 1, False)]
        recovered = row("wide-safe", 3, 2, True)

        class SimulationEnv:
            def __init__(self):
                self.actions = []

            def step(self, action):
                self.actions.append(action["item_idx"])
                return {}, 0.0, False, False, {"status": {
                    "is_included": True, "is_valid": True,
                    "is_placed_safe": True,
                }}

            def close(self):
                pass

        def provider(env, _observation, limit):
            self.assertEqual(env.actions, [0])
            return (rejected + [recovered])[:limit]

        def legal_filter(**context):
            retained = [
                candidate for candidate in context["candidates"]
                if candidate["selection"]["shadow_safe"]
            ]
            return retained, {
                "rejected_count": len(context["candidates"]) - len(retained),
            }

        search = build_physical_puct_search(
            {}, case_id="case", environment_seed=42,
            candidate_provider=provider, legal_filter_fn=legal_filter,
            rules=GameRules(minimum_block=10), top_k=2,
            candidate_audit_limit=3, candidate_rescue_limit=3,
            simulations=1, horizon=2, action_temperature=0.0,
            metrics_fn=lambda _env: {}, env_factory=SimulationEnv,
        )

        _chosen, result = search(
            env=object(), observation={}, candidates=[root], actions=[],
            state=SimpleNamespace(
                current_player=0, block_length=0,
                placements=0, handoff_count=0,
            ), step=0, policy_rng=random.Random(3),
        )

        self.assertEqual(result["candidate_rescue_summary"], {
            "applied_nodes": 1,
            "recovered_candidates": 1,
        })
        self.assertEqual(result["candidate_exhaustion_unique_nodes"], 0)
        self.assertEqual(
            result["multi_head_branch_samples"][0]["termination"], "horizon"
        )
        self.assertEqual(
            result["multi_head_branch_samples"][0]["path_candidate_ids"],
            ["root", "wide-safe"],
        )
        self.assertEqual(
            result["multi_head_branch_samples"][0][
                "path_candidate_provenance"
            ][1]["source"],
            "widening_rescue",
        )
        self.assertEqual(
            result["multi_head_branch_samples"][0]["leaf_game_state"][
                "placements"
            ],
            2,
        )

    @mock.patch("scripts.run_self_play_packing.board_fingerprint", return_value="fp")
    @mock.patch("scripts.run_self_play_packing.state_snapshot", return_value={})
    @mock.patch("scripts.run_self_play_packing.policy_observation", side_effect=lambda _e, o: o)
    @mock.patch("scripts.run_self_play_packing.capture_replay_contract", return_value={})
    @mock.patch("scripts.run_self_play_packing.replay_action_prefix")
    def test_provider_zero_uses_stride_rescue_with_lazy_physics(
        self, replay, _contract, _observation, _snapshot, _fingerprint,
    ):
        replay.return_value = SimpleNamespace(
            matched=True, observation={}, actions_replayed=0,
            observed_fingerprint="fp", error=None,
        )
        root = {
            "candidate_id": "root", "selection": {"rank": 0},
            "command_action": {
                "item_idx": 0, "container_idx": 0,
                "place_pos": [0.0, 0.0, 0.5], "orientation": 0,
            },
        }
        rescue = [{
            "candidate_id": "stride-safe", "selection": {"rank": 0},
            "command_action": {
                "item_idx": 1, "container_idx": 0,
                "place_pos": [0.1, 0.0, 0.5], "orientation": 0,
            },
        }]

        class SimulationEnv:
            def __init__(self):
                self.actions = []

            def step(self, action):
                self.actions.append(action["item_idx"])
                return {}, 0.0, False, False, {"status": {
                    "is_included": True, "is_valid": True,
                    "is_placed_safe": True,
                }}

            def close(self):
                pass

        lazy_limits = []

        def legal_filter(**context):
            lazy_limits.append(context.get("max_safe_candidates"))
            return list(context["candidates"][:1]), {
                "rejected_count": 0, "checked_count": 1,
                "unchecked_count": max(0, len(context["candidates"]) - 1),
            }

        search = build_physical_puct_search(
            {}, case_id="case", environment_seed=42,
            candidate_provider=lambda *_args: [],
            provider_zero_rescue_fn=lambda *_args: rescue,
            provider_zero_rescue_limit=64,
            provider_zero_rescue_safe_limit=1,
            legal_filter_fn=legal_filter,
            rules=GameRules(minimum_block=10), top_k=1,
            simulations=1, horizon=2, action_temperature=0.0,
            metrics_fn=lambda _env: {}, env_factory=SimulationEnv,
        )

        _chosen, result = search(
            env=object(), observation={}, candidates=[root], actions=[],
            state=SimpleNamespace(
                current_player=0, block_length=0,
                placements=0, handoff_count=0,
            ), step=0, policy_rng=random.Random(3),
        )

        self.assertIn(1, lazy_limits)
        self.assertEqual(
            1, result["provider_zero_rescue_summary"]["applied_nodes"]
        )
        self.assertEqual(
            1, result["provider_zero_rescue_summary"]["physical_checks"]
        )
        self.assertEqual(0, result["candidate_exhaustion_unique_nodes"])
        self.assertEqual(
            result["multi_head_branch_samples"][0][
                "path_candidate_provenance"
            ][1]["source"],
            "provider_zero_rescue",
        )

    def test_search_policy_selects_action_and_emits_pi_and_return_target(self):
        def two_candidates(_env, _observation, _limit):
            return [
                {
                    "candidate_id": name,
                    "selection": {"rank": rank},
                    "command_action": {
                        "item_idx": rank, "container_idx": 0,
                        "place_pos": [rank * 0.2, 0.0, 0.5],
                        "orientation": 0,
                    },
                }
                for rank, name in enumerate(("a", "b"))
            ]

        def search(**context):
            self.assertEqual(
                [row["candidate_id"] for row in context["candidates"]],
                ["a", "b"],
            )
            return context["candidates"][1], {
                "algorithm": "puct",
                "policy_target": [
                    {"candidate_id": "a", "probability": 0.25, "visits": 1},
                    {"candidate_id": "b", "probability": 0.75, "visits": 3},
                ],
            }

        result = play_game(
            FakeEnv([{"terminated": True}]), {}, two_candidates,
            rules=GameRules(), handoff_rng=random.Random(1),
            policy_rng=random.Random(2), metrics_fn=metrics,
            max_steps=10, search_fn=search,
            capture_fn=lambda **context: {
                "step": context["step"],
                "snapshot_path": f"s{context['step']}.json",
            },
            evaluate_fn=lambda _env: {"shake_response": {
                "shake_max_shift": 0.02,
                "shake_peak_kinetic_energy": 3.0,
                "shake_items_toppled": 1,
            }},
        )

        self.assertEqual(result["records"][0]["selected_candidate_id"], "b")
        self.assertEqual(result["records"][0]["search"]["algorithm"], "puct")
        self.assertEqual(
            result["learning_targets"][0]["policy_target"][1]["visits"], 3
        )
        self.assertEqual(result["learning_targets"][0]["return_to_go"], 0.0)
        self.assertTrue(result["learning_targets"][0]["value_target_eligible"])
        self.assertIn("value_heads", result["learning_targets"][0])
        self.assertEqual(
            result["learning_targets"][0]["value_heads"][
                "terminal_stability_peak_kinetic_energy"
            ]["value"],
            3.0,
        )

    def test_search_cannot_select_outside_bounded_legal_set(self):
        def provider(_env, _observation, _limit):
            return [{
                "candidate_id": "legal",
                "selection": {"rank": 0},
                "command_action": {
                    "item_idx": 0, "container_idx": 0,
                    "place_pos": [0.0, 0.0, 0.5], "orientation": 0,
                },
            }]

        def search(**_context):
            return {
                "candidate_id": "invented",
                "selection": {"rank": 1},
                "command_action": {
                    "item_idx": 1, "container_idx": 0,
                    "place_pos": [0.2, 0.0, 0.5], "orientation": 0,
                },
            }, {"policy_target": []}

        with self.assertRaisesRegex(RuntimeError, "bounded legal set"):
            play_game(
                FakeEnv([{"terminated": True}]), {}, provider,
                rules=GameRules(), handoff_rng=random.Random(1),
                policy_rng=random.Random(2), metrics_fn=metrics,
                max_steps=10, search_fn=search,
            )

    @mock.patch("scripts.run_self_play_packing.board_fingerprint", return_value="fp")
    @mock.patch("scripts.run_self_play_packing.state_snapshot", return_value={})
    @mock.patch("scripts.run_self_play_packing.policy_observation", side_effect=lambda _e, o: o)
    @mock.patch("scripts.run_self_play_packing.capture_replay_contract", return_value={})
    @mock.patch("scripts.run_self_play_packing.replay_action_prefix")
    def test_exact_filter_uses_fresh_preview_and_authoritative_status(
        self, replay, _contract, _observation, _snapshot, _fingerprint,
    ):
        replay.return_value = SimpleNamespace(
            matched=True, actions_replayed=2,
            observed_fingerprint="fp", error=None,
        )
        statuses = [
            {"is_included": True, "is_valid": True, "is_placed_safe": False},
            {"is_included": True, "is_valid": True, "is_placed_safe": True},
        ]
        previews = []

        class Preview:
            def __init__(self, status):
                self.status = status
                self.closed = False

            def step(self, _action):
                return {}, 0.0, False, False, {"status": self.status}

            def close(self):
                self.closed = True

        def factory():
            preview = Preview(statuses[len(previews)])
            previews.append(preview)
            return preview

        candidates = [
            {
                "candidate_id": name,
                "selection": {"rank": rank},
                "command_action": {
                    "item_idx": rank, "container_idx": 0,
                    "place_pos": [0.0, 0.0, 0.5], "orientation": 0,
                },
            }
            for rank, name in enumerate(("unsafe", "safe"))
        ]
        legal_filter = build_exact_physical_legal_filter(
            {}, case_id="case", environment_seed=42, env_factory=factory
        )

        retained, audit = legal_filter(
            env=object(), observation={}, candidates=candidates,
            actions=[candidates[0]["command_action"]], step=2,
        )

        self.assertEqual([row["candidate_id"] for row in retained], ["safe"])
        self.assertEqual(audit["rejected_count"], 1)
        self.assertEqual(audit["candidates"][0]["status"], statuses[0])
        self.assertTrue(all(preview.closed for preview in previews))
        self.assertEqual(replay.call_count, 2)

    @mock.patch("scripts.run_self_play_packing.board_fingerprint", return_value="fp")
    @mock.patch("scripts.run_self_play_packing.state_snapshot", return_value={})
    @mock.patch("scripts.run_self_play_packing.policy_observation", side_effect=lambda _e, o: o)
    @mock.patch("scripts.run_self_play_packing.capture_replay_contract", return_value={})
    @mock.patch("scripts.run_self_play_packing.replay_action_prefix")
    def test_exact_filter_stops_after_requested_safe_count(
        self, replay, _contract, _observation, _snapshot, _fingerprint,
    ):
        replay.return_value = SimpleNamespace(
            matched=True, actions_replayed=0,
            observed_fingerprint="fp", error=None,
        )
        statuses = [
            {"is_included": True, "is_valid": False, "is_placed_safe": False},
            {"is_included": True, "is_valid": True, "is_placed_safe": True},
        ]
        previews = []

        class Preview:
            def __init__(self, status):
                self.status = status

            def step(self, _action):
                return {}, 0.0, False, False, {"status": self.status}

            def close(self):
                pass

        def factory():
            preview = Preview(statuses[len(previews)])
            previews.append(preview)
            return preview

        candidates = [
            {
                "candidate_id": f"c-{rank}",
                "selection": {"rank": rank},
                "command_action": {
                    "item_idx": rank, "container_idx": 0,
                    "place_pos": [0.0, 0.0, 0.5], "orientation": 0,
                },
            }
            for rank in range(3)
        ]
        legal_filter = build_exact_physical_legal_filter(
            {}, case_id="case", environment_seed=42, env_factory=factory
        )

        retained, audit = legal_filter(
            env=object(), observation={}, candidates=candidates,
            actions=[], step=0, max_safe_candidates=1,
        )

        self.assertEqual(["c-1"], [row["candidate_id"] for row in retained])
        self.assertEqual(2, audit["checked_count"])
        self.assertEqual(1, audit["unchecked_count"])
        self.assertEqual(1, audit["rejected_count"])
        self.assertEqual(2, replay.call_count)

    @mock.patch("scripts.run_self_play_packing.board_fingerprint", return_value="fp")
    @mock.patch("scripts.run_self_play_packing.state_snapshot", return_value={})
    @mock.patch(
        "scripts.run_self_play_packing.policy_observation",
        side_effect=lambda _e, o: o,
    )
    @mock.patch("scripts.run_self_play_packing.capture_replay_contract", return_value={})
    @mock.patch("scripts.run_self_play_packing.replay_action_prefix")
    def test_exact_filter_physically_checks_one_representative_per_item_orbit(
        self, replay, _contract, _observation, _snapshot, _fingerprint,
    ):
        replay.return_value = SimpleNamespace(
            matched=True, actions_replayed=0,
            observed_fingerprint="fp", error=None,
        )
        previews = []

        class Preview:
            def step(self, _action):
                return {}, 0.0, False, False, {"status": {
                    "is_included": True,
                    "is_valid": True,
                    "is_placed_safe": True,
                }}

            def close(self):
                pass

        def factory():
            previews.append(Preview())
            return previews[-1]

        physical = {
            "length": 1.0, "width": 1.0, "height": 1.0, "mass": 1.0,
            "is_prioritized": False, "is_soft": False,
        }
        observation = {
            "pool_list": [
                {**physical, "index": 10},
                {**physical, "index": 11},
            ],
            "container_list": [],
        }
        candidates = [
            {
                "candidate_id": f"c-{pool_index}",
                "selection": {
                    "rank": pool_index,
                    "stable_item_index": 10 + pool_index,
                },
                "command_action": {
                    "item_idx": pool_index, "container_idx": 0,
                    "place_pos": [0.0, 0.0, 0.5], "orientation": 0,
                },
            }
            for pool_index in range(2)
        ]
        legal_filter = build_exact_physical_legal_filter(
            {}, case_id="case", environment_seed=42, env_factory=factory
        )

        retained, audit = legal_filter(
            env=object(), observation=observation, candidates=candidates,
            actions=[], step=0,
        )

        self.assertEqual([row["candidate_id"] for row in retained], ["c-0", "c-1"])
        self.assertEqual(audit["checked_count"], 2)
        self.assertEqual(audit["physical_checked_count"], 1)
        self.assertEqual(audit["symmetry_reused_count"], 1)
        self.assertEqual(audit["physical_step_equivalents"], 1)
        self.assertEqual(len(previews), 1)
        self.assertEqual(replay.call_count, 1)
        self.assertTrue(audit["candidates"][1]["symmetry_reused"])

    @mock.patch("scripts.run_self_play_packing.board_fingerprint", return_value="fp")
    @mock.patch("scripts.run_self_play_packing.state_snapshot", return_value={})
    @mock.patch(
        "scripts.run_self_play_packing.policy_observation",
        side_effect=lambda _e, o: o,
    )
    @mock.patch("scripts.run_self_play_packing.capture_replay_contract", return_value={})
    @mock.patch("scripts.run_self_play_packing.replay_action_prefix")
    def test_exact_filter_reuses_an_unsafe_item_orbit_fail_closed(
        self, replay, _contract, _observation, _snapshot, _fingerprint,
    ):
        replay.return_value = SimpleNamespace(
            matched=True, actions_replayed=0,
            observed_fingerprint="fp", error=None,
        )

        class Preview:
            def step(self, _action):
                return {}, 0.0, False, False, {"status": {
                    "is_included": True,
                    "is_valid": True,
                    "is_placed_safe": False,
                }}

            def close(self):
                pass

        physical = {
            "length": 1.0, "width": 1.0, "height": 1.0, "mass": 1.0,
            "is_prioritized": False, "is_soft": False,
        }
        observation = {"pool_list": [
            {**physical, "index": 10}, {**physical, "index": 11},
        ]}
        candidates = [{
            "candidate_id": f"c-{pool_index}",
            "selection": {"rank": pool_index},
            "command_action": {
                "item_idx": pool_index, "container_idx": 0,
                "place_pos": [0.0, 0.0, 0.5], "orientation": 0,
            },
        } for pool_index in range(2)]
        legal_filter = build_exact_physical_legal_filter(
            {}, case_id="case", environment_seed=42,
            env_factory=Preview,
        )

        retained, audit = legal_filter(
            env=object(), observation=observation, candidates=candidates,
            actions=[], step=0,
        )

        self.assertEqual(retained, [])
        self.assertEqual(audit["physical_checked_count"], 1)
        self.assertEqual(audit["physical_rejected_count"], 1)
        self.assertEqual(audit["rejected_count"], 2)
        self.assertEqual(audit["symmetry_reused_count"], 1)
        self.assertEqual(replay.call_count, 1)
        self.assertTrue(audit["candidates"][1]["symmetry_reused"])

    def test_policy_selects_only_from_prefiltered_legal_moves(self):
        def two_candidates(_env, _observation, _limit):
            return [
                {
                    "candidate_id": "unsafe",
                    "selection": {"rank": 0, "score": 2.0},
                    "command_action": {
                        "item_idx": 0, "container_idx": 0,
                        "place_pos": [0.0, 0.0, 0.5], "orientation": 0,
                    },
                },
                {
                    "candidate_id": "safe",
                    "selection": {"rank": 1, "score": 1.0},
                    "command_action": {
                        "item_idx": 1, "container_idx": 0,
                        "place_pos": [0.5, 0.0, 0.5], "orientation": 0,
                    },
                },
            ]

        def filter_second(**context):
            rows = context["candidates"]
            return [rows[1]], {
                "schema_version": 1, "mode": "test", "step": 0,
                "proposal_count": 2, "safe_count": 1,
                "rejected_count": 1,
                "candidates": [
                    {"candidate_id": "unsafe", "safe": False},
                    {"candidate_id": "safe", "safe": True},
                ],
            }

        result = play_game(
            FakeEnv([{"terminated": True}]), {}, two_candidates,
            rules=GameRules(), handoff_rng=random.Random(1),
            policy_rng=random.Random(2), metrics_fn=metrics,
            max_steps=10, legal_filter_fn=filter_second,
        )

        self.assertEqual(result["terminal_reason"], "stream_exhausted")
        self.assertEqual(result["records"][0]["selected_candidate_id"], "safe")
        self.assertEqual(result["records"][0]["proposal_count"], 2)
        self.assertEqual(result["records"][0]["candidate_count"], 1)
        self.assertEqual(result["prefilter_rejections"], 1)
        self.assertEqual(
            result["legal_move_audits"][0]["candidates"][0]["candidate_id"],
            "unsafe",
        )

    def test_all_rejected_proposals_are_bounded_safe_set_exhaustion(self):
        def reject_all(**context):
            return [], {
                "schema_version": 1, "mode": "test", "step": 0,
                "proposal_count": len(context["candidates"]),
                "safe_count": 0, "rejected_count": 1,
                "candidates": [{"candidate_id": None, "safe": False}],
            }

        result = play_game(
            FakeEnv([{}]), {}, provider,
            rules=GameRules(), handoff_rng=random.Random(1),
            policy_rng=random.Random(2), metrics_fn=metrics,
            max_steps=10, legal_filter_fn=reject_all,
        )

        self.assertEqual(result["terminal_reason"], "no_safe_retained_candidate")
        self.assertEqual(result["loser"], 0)
        self.assertEqual(result["rewards"], [-50.0, 50.0])
        self.assertTrue(result["training_eligible"])
        self.assertTrue(result["outcome_target_eligible"])
        self.assertEqual(result["steps"], 0)
        self.assertEqual(result["prefilter_rejections"], 1)

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
