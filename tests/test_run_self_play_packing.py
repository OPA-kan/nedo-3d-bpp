import random
import unittest
from types import SimpleNamespace
from unittest import mock

from scripts.run_self_play_packing import (
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
        )

        self.assertEqual(result["records"][0]["selected_candidate_id"], "b")
        self.assertEqual(result["records"][0]["search"]["algorithm"], "puct")
        self.assertEqual(
            result["learning_targets"][0]["policy_target"][1]["visits"], 3
        )
        self.assertEqual(result["learning_targets"][0]["return_to_go"], 0.0)
        self.assertTrue(result["learning_targets"][0]["value_target_eligible"])

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
