from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from scripts.build_counterfactual_graph import (
    build_candidate_provider,
    cumulative_metrics,
    scenario_axes,
    transition_outcomes,
)


class PhysicalOutcomeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
