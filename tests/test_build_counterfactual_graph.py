from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from scripts.build_counterfactual_graph import (
    build_candidate_provider,
    cumulative_metrics,
    post_shake_metrics,
    scenario_axes,
    transition_outcomes,
)


class PhysicalOutcomeTests(unittest.TestCase):
    def test_post_shake_labels_share_one_exact_shake(self):
        class Evaluator:
            def __init__(self):
                self.phase = "pre"

            def _live_poses(self, _containers):
                return [{"phase": self.phase}]

            def settled_snapshot(self, _containers):
                return {
                    "soft_items": 1,
                    "soft_covered_by_other": int(self.phase == "post"),
                    "soft_clean_ratio": 0.0 if self.phase == "post" else 1.0,
                    "priority_items": 0,
                    "priority_covered_by_other": 0,
                    "priority_misrouted": 0,
                    "priority_clean_ratio": None,
                    "has_priority_container": False,
                }

            def shake_test(self, containers):
                self._live_poses(containers)
                self.phase = "post"
                self._live_poses(containers)
                self.phase = "pre"
                return {
                    "shake_items": 1,
                    "shake_items_lost": 0,
                    "shake_max_shift": 0.25,
                    "shake_mean_shift": 0.25,
                    "shake_max_rotation_deg": 3.0,
                    "shake_items_shifted": 1,
                    "shake_items_toppled": 0,
                    "shake_peak_kinetic_energy": 2.5,
                }

        env = SimpleNamespace(
            evaluator=Evaluator(),
            container_manager=SimpleNamespace(containers=[object()]),
        )

        metrics = post_shake_metrics(env)

        self.assertTrue(metrics["post_shake_measured"])
        self.assertEqual(metrics["post_shake_live_poses_calls"], 2)
        self.assertEqual(metrics["post_shake_soft_covered_by_other"], 1)
        self.assertEqual(
            metrics["post_shake_soft_covered_by_other_before"], 0
        )
        self.assertEqual(
            metrics["post_shake_soft_clean_to_covered_events"], 1
        )
        self.assertEqual(metrics["post_shake_soft_clean_ratio"], 0.0)
        self.assertEqual(metrics["post_shake_max_shift"], 0.25)
        self.assertEqual(metrics["post_shake_peak_kinetic_energy"], 2.5)

    def test_empty_board_uses_its_unchanged_pre_state_as_post_state(self):
        class Evaluator:
            def _live_poses(self, _containers):
                return []

            def settled_snapshot(self, _containers):
                return {
                    "soft_items": 0,
                    "soft_covered_by_other": 0,
                    "soft_clean_ratio": None,
                }

            def shake_test(self, containers):
                self._live_poses(containers)
                return {"shake_items": 0, "shake_items_lost": 0}

        env = SimpleNamespace(
            evaluator=Evaluator(),
            container_manager=SimpleNamespace(containers=[]),
        )

        metrics = post_shake_metrics(env)

        self.assertEqual(metrics["post_shake_live_poses_calls"], 1)
        self.assertEqual(metrics["post_shake_soft_covered_by_other"], 0)
        self.assertEqual(
            metrics["post_shake_soft_clean_to_covered_events"], 0
        )
        self.assertIsNone(metrics["post_shake_soft_clean_ratio"])

    def test_existing_soft_violation_is_not_attributed_to_shake(self):
        class Evaluator:
            def _live_poses(self, _containers):
                return [{}]

            def settled_snapshot(self, _containers):
                return {
                    "soft_items": 1,
                    "soft_covered_by_other": 1,
                    "soft_clean_ratio": 0.0,
                }

            def shake_test(self, containers):
                self._live_poses(containers)
                self._live_poses(containers)
                return {"shake_items": 1, "shake_items_lost": 0}

        env = SimpleNamespace(
            evaluator=Evaluator(),
            container_manager=SimpleNamespace(containers=[object()]),
        )

        metrics = post_shake_metrics(env)

        self.assertEqual(metrics["post_shake_soft_covered_by_other"], 1)
        self.assertEqual(
            metrics["post_shake_soft_clean_to_covered_events"], 0
        )

    def test_scenario_axes_are_saved_with_the_graph(self):
        config = {
            "containers": {
                "container_list": [
                    {
                        "require_shelf": True,
                        "is_prioritized": False,
                        "packed_items": [{"index": 1}],
                    },
                    {
                        "require_shelf": False,
                        "is_prioritized": True,
                        "packed_items": [{"index": 2}, {"index": 3}],
                    },
                ]
            },
            "item_stream": {
                "look_ahead": 40,
                "item_list": [{}, {}, {}],
            },
        }
        self.assertEqual(
            scenario_axes(config),
            {
                "container_count": 2,
                "shelf_count": 1,
                "dedicated_container_count": 1,
                "preloaded_item_count": 3,
                "pool_width": 40,
                "stream_item_count": 3,
                "stream_variant": "original",
            },
        )

    def test_candidate_frontier_spends_width_on_distinct_items(self):
        def decision(pool_index, score, name=None):
            return SimpleNamespace(
                action={
                    "item_idx": pool_index,
                    "container_idx": 0,
                    "place_pos": [score / 10, 0, 0.5],
                    "orientation": 0,
                },
                candidate=SimpleNamespace(name=name),
                score=score,
            )

        emitted = [
            (0, {"index": 10}, decision(0, 5.0)),
            (0, {"index": 10}, decision(0, 6.0)),
            (1, {"index": 11}, decision(1, 4.0)),
            (2, {"index": 12}, decision(2, 9.0, "release_candidate")),
        ]

        class PlacementCore:
            @staticmethod
            def top_candidates(
                _observation,
                _indexed_items,
                _k,
                **kwargs,
            ):
                observer = kwargs["candidate_observer"]
                for pool_index, item, selected in emitted:
                    observer(pool_index, item, 0, 0, selected)
                return []

        module = SimpleNamespace(
            RELEASE_RISK_LIVE_RERANK=False,
            RELEASE_RISK_RERANK_LAMBDA=1.0,
            PlacementCore=PlacementCore,
        )
        provider = build_candidate_provider(module, attempt_budget=64)
        with (
            mock.patch(
                "scripts.build_counterfactual_graph.policy_observation",
                return_value={"pool_list": []},
            ),
            mock.patch(
                "scripts.build_counterfactual_graph.policy_indexed_items",
                return_value=[(0, {"index": 10})],
            ),
        ):
            candidates = provider(object(), {}, 2)

        self.assertEqual(
            [candidate.selection["stable_item_index"] for candidate in candidates],
            [10, 11],
        )
        self.assertEqual(candidates[0].selection["score"], 6.0)
        self.assertTrue(
            all(
                candidate.selection["candidate_kind"] == "settled_candidate"
                for candidate in candidates
            )
        )

    def test_release_from_another_item_fills_unused_graph_width(self):
        def selected(pool_index, item_index, score, name):
            return (
                pool_index,
                {"index": item_index},
                SimpleNamespace(
                    action={
                        "item_idx": pool_index,
                        "container_idx": 0,
                        "place_pos": [0, 0, 0.5],
                        "orientation": 0,
                    },
                    candidate=SimpleNamespace(name=name),
                    score=score,
                ),
            )

        emitted = [
            selected(0, 10, 5.0, None),
            selected(1, 11, 8.0, "release_candidate"),
        ]

        class PlacementCore:
            @staticmethod
            def top_candidates(_obs, _items, _k, **kwargs):
                for pool_index, item, decision in emitted:
                    kwargs["candidate_observer"](
                        pool_index, item, 0, 0, decision
                    )
                return []

        module = SimpleNamespace(
            RELEASE_RISK_LIVE_RERANK=False,
            RELEASE_RISK_RERANK_LAMBDA=1.0,
            PlacementCore=PlacementCore,
        )
        with (
            mock.patch(
                "scripts.build_counterfactual_graph.policy_observation",
                return_value={},
            ),
            mock.patch(
                "scripts.build_counterfactual_graph.policy_indexed_items",
                return_value=[(0, {"index": 10})],
            ),
        ):
            candidates = build_candidate_provider(
                module, attempt_budget=64
            )(object(), {}, 2)
        self.assertEqual(
            [candidate.selection["stable_item_index"] for candidate in candidates],
            [10, 11],
        )
        self.assertEqual(
            [candidate.selection["candidate_kind"] for candidate in candidates],
            ["settled_candidate", "release_candidate"],
        )

    def test_measurement_provider_keeps_same_item_release_fallback(self):
        def selected(name, score):
            return SimpleNamespace(
                action={"item_idx": 0, "container_idx": 0,
                        "place_pos": [0, 0, 0.5], "orientation": 0},
                candidate=SimpleNamespace(name=name), score=score,
            )

        class PlacementCore:
            @staticmethod
            def top_candidates(_obs, _items, _k, **kwargs):
                observer = kwargs["candidate_observer"]
                observer(0, {"index": 10}, 0, 0, selected(None, 5.0))
                observer(
                    0, {"index": 10}, 0, 0,
                    selected("release_candidate", 4.0),
                )
                return []

        module = SimpleNamespace(
            RELEASE_RISK_LIVE_RERANK=False,
            RELEASE_RISK_RERANK_LAMBDA=1.0,
            PlacementCore=PlacementCore,
        )
        with (
            mock.patch(
                "scripts.build_counterfactual_graph.policy_observation",
                return_value={},
            ),
            mock.patch(
                "scripts.build_counterfactual_graph.policy_indexed_items",
                return_value=[(0, {"index": 10})],
            ),
        ):
            candidates = build_candidate_provider(
                module, attempt_budget=64, include_release_fallbacks=True,
            )(object(), {}, 10)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(
            [candidate.selection["candidate_kind"] for candidate in candidates],
            ["settled_candidate", "release_candidate"],
        )

    def test_measurement_provider_can_scan_beyond_live_item_cap(self):
        def selected(pool_index):
            return SimpleNamespace(
                action={"item_idx": pool_index, "container_idx": 0,
                        "place_pos": [0, 0, 0.5], "orientation": 0},
                candidate=SimpleNamespace(name=None), score=1.0,
            )

        class PlacementCore:
            @staticmethod
            def top_candidates(_obs, items, _k, **kwargs):
                pool_index, item = items[0]
                kwargs["candidate_observer"](
                    pool_index, item, 0, 0, selected(pool_index),
                )
                return []

        module = SimpleNamespace(
            RELEASE_RISK_LIVE_RERANK=False,
            RELEASE_RISK_RERANK_LAMBDA=1.0,
            PlacementCore=PlacementCore,
            online_item_order=lambda pool: list(enumerate(pool)),
        )
        pool = [{"index": index} for index in range(12)]
        with mock.patch(
            "scripts.build_counterfactual_graph.policy_observation",
            return_value={"pool_list": pool},
        ):
            candidates = build_candidate_provider(
                module, attempt_budget=64, scan_all_visible_items=True,
            )(object(), {}, 100)
        self.assertEqual(len(candidates), 12)
        self.assertTrue(all(
            candidate.selection["all_visible_items_scanned"]
            for candidate in candidates
        ))

    def test_measurement_provider_forwards_opt_in_candidate_stride(self):
        calls = []

        module = SimpleNamespace(
            RELEASE_RISK_LIVE_RERANK=False,
            RELEASE_RISK_RERANK_LAMBDA=1.0,
            PlacementCore=SimpleNamespace(),
            LIVE_SEARCH_INTERLEAVE=1,
            iter_prioritized_candidates=(
                lambda _observation, _items, **kwargs:
                calls.append(kwargs) or iter(())
            ),
        )
        with (
            mock.patch(
                "scripts.build_counterfactual_graph.policy_observation",
                return_value={},
            ),
            mock.patch(
                "scripts.build_counterfactual_graph.policy_indexed_items",
                return_value=[(0, {"index": 10})],
            ),
        ):
            candidates = build_candidate_provider(
                module, attempt_budget=512, candidate_stride=4,
            )(object(), {}, 64)

        self.assertEqual(candidates, [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["stride"], 4)
        self.assertEqual(calls[0]["attempt_budget"], 512)

    def test_strided_provider_scores_the_existing_candidate_stream(self):
        item = {"index": 10}
        candidate = SimpleNamespace(name=None)
        decision = SimpleNamespace(
            action={
                "item_idx": 0,
                "container_idx": 0,
                "place_pos": [0, 0, 0.5],
                "orientation": 0,
            },
            candidate=candidate,
            score=7.0,
        )
        module = SimpleNamespace(
            RELEASE_RISK_LIVE_RERANK=False,
            RELEASE_RISK_RERANK_LAMBDA=1.0,
            PlacementCore=SimpleNamespace(),
            LIVE_SEARCH_INTERLEAVE=1,
            iter_prioritized_candidates=(
                lambda *_args, **_kwargs:
                iter([(0, item, 0, 0, candidate)])
            ),
            make_placement_decision=lambda *_args, **_kwargs: decision,
        )
        observation = {
            "pool_list": [item],
            "container_list": [{"is_prioritized": False}],
        }
        with (
            mock.patch(
                "scripts.build_counterfactual_graph.policy_observation",
                return_value=observation,
            ),
            mock.patch(
                "scripts.build_counterfactual_graph.policy_indexed_items",
                return_value=[(0, item)],
            ),
        ):
            candidates = build_candidate_provider(
                module, attempt_budget=512, candidate_stride=4,
            )(object(), {}, 64)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].selection["score"], 7.0)
        self.assertEqual(candidates[0].selection["candidate_stride"], 4)

    def test_measurement_provider_rejects_nonpositive_stride(self):
        module = SimpleNamespace(
            RELEASE_RISK_LIVE_RERANK=False,
            RELEASE_RISK_RERANK_LAMBDA=1.0,
        )
        with self.assertRaisesRegex(ValueError, "candidate_stride"):
            build_candidate_provider(
                module, attempt_budget=512, candidate_stride=0,
            )

    def test_measurement_provider_saves_direct_and_stack_attribute_heads(self):
        decision = SimpleNamespace(
            action={
                "item_idx": 0,
                "container_idx": 0,
                "place_pos": [0, 0, 0.5],
                "orientation": 0,
            },
            candidate=SimpleNamespace(name=None),
            score=1.0,
        )

        class PlacementCore:
            @staticmethod
            def top_candidates(_obs, _items, _k, **kwargs):
                kwargs["candidate_observer"](
                    0, {"index": 10}, 0, 0, decision,
                )
                return []

        module = SimpleNamespace(
            RELEASE_RISK_LIVE_RERANK=False,
            RELEASE_RISK_RERANK_LAMBDA=1.0,
            PlacementCore=PlacementCore,
            candidate_attribute_violations=(
                lambda _item, _candidate, _container, *, stack_aware:
                (2, 3) if stack_aware else (0, 1)
            ),
        )
        observation = {
            "pool_list": [{"index": 10, "is_prioritized": True}],
            "container_list": [
                {"is_prioritized": False},
                {"is_prioritized": True},
            ],
        }
        with (
            mock.patch(
                "scripts.build_counterfactual_graph.policy_observation",
                return_value=observation,
            ),
            mock.patch(
                "scripts.build_counterfactual_graph.policy_indexed_items",
                return_value=[(0, {"index": 10})],
            ),
        ):
            candidates = build_candidate_provider(
                module, attempt_budget=512,
            )(object(), {}, 64)

        selection = candidates[0].selection
        self.assertEqual(selection["priority_routing_violation"], 1)
        self.assertEqual(selection["priority_violations_direct"], 0)
        self.assertEqual(selection["soft_violations_direct"], 1)
        self.assertEqual(selection["priority_violations_stack"], 2)
        self.assertEqual(selection["soft_violations_stack"], 3)

    def test_records_all_score_proxies_without_collapsing_them(self):
        class Container:
            packed_items = [object(), object()]

        class Evaluator:
            def settled_snapshot(self, _containers):
                return {
                    "placed_count": 2,
                    "placed_volume": 0.8,
                    "fill_percent_proxy": 20.0,
                    "center_of_mass_z": 0.42,
                    "com_z": 0.42,
                    "surface_total_variation": 0.07,
                    "priority_items": 1,
                    "priority_misrouted": 0,
                    "soft_items": 1,
                    "soft_covered_by_other": 1,
                }

        class ContainerManager:
            containers = [Container()]

        class Env:
            evaluator = Evaluator()
            container_manager = ContainerManager()
            step_metrics = [
                {
                    "settle_angle_deg": 12.0,
                    "settle_displacement_norm": 0.03,
                }
            ]

        metrics = cumulative_metrics(Env())
        self.assertEqual(metrics["placed_count"], 2)
        self.assertEqual(metrics["fill_score_proxy"], 20.0)
        self.assertEqual(metrics["com_z"], 0.42)
        self.assertEqual(metrics["priority_misrouted"], 0)
        self.assertEqual(metrics["soft_covered_by_other"], 1)

        immediate, cumulative = transition_outcomes(
            Env(),
            {
                "status": {
                    "is_included": True,
                    "is_valid": True,
                    "is_placed_safe": True,
                }
            },
            {
                "placed_count": 1,
                "placed_volume": 0.5,
                "fill_score_proxy": 12.5,
                "com_z": 0.35,
            },
        )
        self.assertEqual(immediate["placed_count_delta"], 1.0)
        self.assertAlmostEqual(immediate["placed_volume_delta"], 0.3)
        self.assertAlmostEqual(immediate["com_z_delta"], 0.07)
        self.assertEqual(immediate["settle_angle_deg"], 12.0)
        self.assertTrue(immediate["is_placed_safe"])
        self.assertEqual(cumulative["soft_covered_by_other"], 1)

    def test_transition_can_attach_post_shake_state_and_delta(self):
        class Container:
            packed_items = [object()]

        class Evaluator:
            def __init__(self):
                self.phase = "pre"

            def settled_snapshot(self, _containers):
                return {
                    "placed_count": 1,
                    "placed_volume": 0.4,
                    "fill_percent_proxy": 10.0,
                    "soft_items": 1,
                    "soft_covered_by_other": int(self.phase == "post"),
                    "soft_clean_ratio": 0.0 if self.phase == "post" else 1.0,
                }

            def _live_poses(self, _containers):
                return [{"phase": self.phase}]

            def shake_test(self, containers):
                self._live_poses(containers)
                self.phase = "post"
                self._live_poses(containers)
                self.phase = "pre"
                return {"shake_items": 1, "shake_max_shift": 0.1}

        env = SimpleNamespace(
            evaluator=Evaluator(),
            container_manager=SimpleNamespace(containers=[Container()]),
            step_metrics=[],
        )

        immediate, cumulative = transition_outcomes(
            env,
            {"status": {"is_placed_safe": True}},
            {
                "post_shake_soft_covered_by_other": 0,
                "post_shake_soft_clean_to_covered_events": 2,
            },
            include_post_shake=True,
        )

        self.assertEqual(cumulative["post_shake_soft_covered_by_other"], 1)
        self.assertEqual(
            cumulative["post_shake_soft_clean_to_covered_events"], 3
        )
        self.assertEqual(
            immediate["post_shake_soft_covered_by_other_after"], 1
        )
        self.assertEqual(
            immediate["post_shake_soft_covered_by_other_delta"], 1.0
        )
        self.assertEqual(
            immediate["post_shake_soft_clean_to_covered_events_delta"], 1.0
        )


if __name__ == "__main__":
    unittest.main()
