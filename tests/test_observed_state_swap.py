from __future__ import annotations

import itertools
import random
import unittest

from scripts.build_replay_dataset import split_observed_outcomes
from scripts.measure_anchor_recall import candidate_key
from scripts.observed_state_swap import (
    SWAP_DESIGN,
    _nearest_tables,
    _screened_mean,
    annotate_swapped_portfolio,
    optimize_observed_state_portfolio,
    seed_keys_from_control,
    semantic_signature,
)
from scripts.residual_diversity import (
    feature_vector_distance,
    paired_mean_nn_objective,
    proxy_feature_vector,
    scale_vector,
    settled_portfolio_comparison,
)


def candidate(
    *,
    pool_index: int,
    item_index: int = 0,
    orientation: int = 0,
    container_index: int = 0,
    center: tuple[float, float, float] = (0.0, 0.0, 0.5),
    score: float = 1.0,
    stratum_key: str = "only",
) -> dict:
    return {
        "pool_index": pool_index,
        "item_index": item_index,
        "container_index": container_index,
        "orientation": orientation,
        "kind": "release_candidate",
        "center": list(center),
        "size": [0.3, 0.2, 0.2],
        "action_center": list(center),
        "score": score,
        "score_rank": pool_index,
        "score_population": 64,
        "release_risk": {"passed": True, "features": {}},
        "stratum_key": stratum_key,
        "stratum": {"kind": "release_candidate", "gate": "pass"},
        "sampling": {"design": "overdraw"},
    }


def settled(record: dict, *, position=None) -> dict:
    return {
        "is_placed_safe": True,
        "is_valid": True,
        "is_included": True,
        "x_plus": {
            "position": list(position or record["center"]),
            "aabb_dimensions": [0.3, 0.2, 0.2],
            "quaternion": [0.0, 0.0, 0.0, 1.0],
        },
    }


def random_population(seed: int, *, count: int = 24, offset: int = 0):
    rng = random.Random(seed)
    records = []
    for index in range(count):
        records.append(
            candidate(
                pool_index=offset + index,
                item_index=index % 6,
                orientation=index % 3,
                center=(rng.random(), rng.random(), rng.random()),
                score=float(count - index),
            )
        )
    return records


class ObjectiveDefinitionTests(unittest.TestCase):
    def test_paired_objective_is_the_reported_delta_bit_for_bit(self):
        primary = random_population(11, count=6)
        control = random_population(12, count=6, offset=100)
        results = {
            candidate_key(record): settled(record)
            for record in primary + control
        }

        comparison = settled_portfolio_comparison(
            diversity_sample=primary,
            random_sample=control,
            results=results,
        )
        objective = paired_mean_nn_objective(
            [
                proxy_feature_vector(
                    {**record, "settle_tilt_deg": 0.0}
                )
                for record in primary
            ],
            [
                proxy_feature_vector(
                    {**record, "settle_tilt_deg": 0.0}
                )
                for record in control
            ],
        )

        self.assertEqual(
            objective["mean_nearest_neighbor_distance_delta"],
            comparison["diversity_minus_random"][
                "mean_nearest_neighbor_distance"
            ],
        )

    def test_screened_mean_matches_a_full_recomputation(self):
        records = random_population(13, count=9)
        vectors = [proxy_feature_vector(record) for record in records]
        scales = scale_vector(vectors)
        size = len(records)
        distance = [
            [
                feature_vector_distance(
                    vectors[left], vectors[right], scales=scales
                )
                for right in range(size)
            ]
            for left in range(size)
        ]
        selected = [0, 2, 4, 6]
        nearest, nearest_index, second = _nearest_tables(selected, distance)

        for slot, incoming in itertools.product(range(4), (1, 3, 5, 7, 8)):
            replaced = list(selected)
            replaced[slot] = incoming
            expected = sum(
                min(
                    distance[left][right]
                    for right in replaced
                    if right != left
                )
                for left in replaced
            ) / len(replaced)

            self.assertAlmostEqual(
                _screened_mean(
                    selected,
                    slot,
                    incoming,
                    distance=distance,
                    nearest=nearest,
                    nearest_index=nearest_index,
                    second=second,
                ),
                expected,
                places=12,
            )


class SwapOptimizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pool = random_population(21, count=20)
        self.control = self.pool[:6]
        self.observed = {
            candidate_key(record): {
                **record,
                "settle_tilt_deg": 0.0,
            }
            for record in self.pool
        }

    def optimize(self, portfolio, **kwargs):
        return optimize_observed_state_portfolio(
            list(portfolio),
            pool=self.pool,
            control=self.control,
            observed=self.observed,
            forced_keys=kwargs.pop("forced_keys", {}),
            **kwargs,
        )

    def test_control_seed_starts_the_search_at_a_zero_delta(self):
        _final, trace = self.optimize(self.control)

        self.assertEqual(
            trace["initial_objective"]["mean_nearest_neighbor_distance_delta"],
            0.0,
        )

    def test_search_only_moves_the_measured_objective_upwards(self):
        final, trace = self.optimize(self.control)

        initial = trace["initial_objective"][
            "mean_nearest_neighbor_distance_delta"
        ]
        last = trace["final_objective"][
            "mean_nearest_neighbor_distance_delta"
        ]
        self.assertGreater(trace["swaps_applied"], 0)
        self.assertGreater(last, initial)
        for entry in trace["swap_log"]:
            self.assertGreater(entry["delta_after"], entry["delta_before"])
        self.assertEqual(
            last,
            settled_portfolio_comparison(
                diversity_sample=final,
                random_sample=self.control,
                results={
                    key: {
                        "is_placed_safe": True,
                        "x_plus": {
                            "position": record["center"],
                            "aabb_dimensions": record["size"],
                            "quaternion": [0.0, 0.0, 0.0, 1.0],
                        },
                    }
                    for key, record in self.observed.items()
                },
            )["diversity_minus_random"]["mean_nearest_neighbor_distance"],
        )

    def test_stratum_counts_and_population_are_invariants(self):
        for index, record in enumerate(self.pool):
            record["stratum_key"] = f"s{index % 3}"
        final, _trace = self.optimize(self.control)

        def counts(records):
            table: dict[str, int] = {}
            for record in records:
                key = str(record["stratum_key"])
                table[key] = table.get(key, 0) + 1
            return table

        self.assertEqual(counts(final), counts(self.control))
        self.assertLessEqual(
            {candidate_key(record) for record in final},
            {candidate_key(record) for record in self.pool},
        )
        self.assertEqual(
            len({candidate_key(record) for record in final}), len(final)
        )

    def test_forced_rows_are_never_traded_away(self):
        forced = candidate_key(self.control[2])
        final, trace = self.optimize(
            self.control, forced_keys={forced: "selected_action"}
        )

        self.assertIn(forced, {candidate_key(record) for record in final})
        for entry in trace["swap_log"]:
            self.assertNotEqual(
                entry["removed"]["pool_index"],
                self.control[2]["pool_index"],
            )

    def test_semantic_coverage_never_falls(self):
        final, trace = self.optimize(self.control)

        self.assertGreaterEqual(
            semantic_signature(final)[0], semantic_signature(self.control)[0]
        )
        self.assertGreaterEqual(
            semantic_signature(final)[1], semantic_signature(self.control)[1]
        )
        self.assertEqual(
            semantic_signature(final),
            (
                trace["final_semantics"]["unique_items"],
                trace["final_semantics"]["unique_item_orientations"],
            ),
        )

    def test_a_swap_that_would_drop_the_last_of_an_item_is_refused(self):
        # Two strata; the unique item lives in a stratum whose replacements
        # all duplicate an item the portfolio already covers.
        pool = [
            candidate(
                pool_index=0,
                item_index=0,
                center=(0.0, 0.0, 0.5),
                stratum_key="a",
            ),
            candidate(
                pool_index=1,
                item_index=1,
                center=(0.02, 0.0, 0.5),
                stratum_key="a",
            ),
            candidate(
                pool_index=2,
                item_index=0,
                center=(9.0, 0.0, 0.5),
                stratum_key="a",
            ),
            candidate(
                pool_index=3,
                item_index=0,
                center=(0.0, 1.0, 0.5),
                stratum_key="b",
            ),
        ]
        observed = {
            candidate_key(record): {**record, "settle_tilt_deg": 0.0}
            for record in pool
        }
        portfolio = [pool[0], pool[1], pool[3]]

        final, trace = optimize_observed_state_portfolio(
            list(portfolio),
            pool=pool,
            control=list(portfolio),
            observed=observed,
            forced_keys={},
        )

        self.assertIn(1, [record["item_index"] for record in final])
        self.assertGreaterEqual(
            trace["final_semantics"]["unique_items"],
            trace["initial_semantics"]["unique_items"],
        )

    def test_zero_rounds_leaves_the_portfolio_untouched(self):
        final, trace = self.optimize(self.control, max_rounds=0)

        self.assertEqual(
            [candidate_key(record) for record in final],
            [candidate_key(record) for record in self.control],
        )
        self.assertEqual(trace["terminated"], "disabled")
        self.assertEqual(trace["swaps_applied"], 0)

    def test_rows_without_an_observed_afterstate_stay_put(self):
        unobserved = self.pool[7]
        del self.observed[candidate_key(unobserved)]
        portfolio = list(self.control) + [unobserved]

        final, _trace = self.optimize(portfolio)

        self.assertIs(final[-1], unobserved)

    def test_a_row_outside_the_safe_pool_is_carried_through(self):
        outsider = candidate(pool_index=900, item_index=9)
        self.observed[candidate_key(outsider)] = {
            **outsider,
            "settle_tilt_deg": 0.0,
        }
        portfolio = list(self.control) + [outsider]

        final, _trace = self.optimize(portfolio)

        self.assertIs(final[-1], outsider)

    def test_a_swap_the_screening_ranks_low_is_still_reachable(self):
        # One exact check per round: without scanning past the budget when
        # nothing improved, a mis-ranked screening would end the search here.
        final, trace = self.optimize(
            self.control, exact_checks_per_round=1, exact_scan_limit=64
        )
        _greedy, greedy_trace = self.optimize(
            self.control, exact_checks_per_round=1, exact_scan_limit=1
        )

        self.assertGreaterEqual(
            trace["final_objective"][
                "mean_nearest_neighbor_distance_delta"
            ],
            greedy_trace["final_objective"][
                "mean_nearest_neighbor_distance_delta"
            ],
        )
        self.assertEqual(len(final), len(self.control))

    def test_round_budget_is_reported_rather_than_silently_hit(self):
        _final, trace = self.optimize(self.control, max_rounds=1)

        self.assertEqual(trace["terminated"], "round_budget")
        self.assertEqual(trace["rounds"], 1)


class SeedCapacityTests(unittest.TestCase):
    def test_control_rows_fill_only_the_capacity_the_forced_rows_leave(self):
        pool = [
            candidate(pool_index=index, item_index=index) for index in range(8)
        ]
        control = pool[:4]
        forced = {candidate_key(pool[6]): "selected_action"}

        seeds = seed_keys_from_control(
            pool=pool, control=control, per_stratum=3, forced_keys=forced
        )

        self.assertEqual(seeds[candidate_key(pool[6])], "selected_action")
        self.assertEqual(
            sum(
                1
                for reason in seeds.values()
                if reason == "paired_control_seed"
            ),
            2,
        )

    def test_control_rows_outside_the_safe_pool_are_not_seeded(self):
        pool = [
            candidate(pool_index=index, item_index=index) for index in range(4)
        ]
        control = pool[:2] + [candidate(pool_index=99, item_index=9)]

        seeds = seed_keys_from_control(
            pool=pool, control=control, per_stratum=4, forced_keys={}
        )

        self.assertEqual(len(seeds), 2)
        self.assertNotIn(candidate_key(control[2]), seeds)


class AnnotationTests(unittest.TestCase):
    def test_provenance_separates_forced_rows_from_seeded_rows(self):
        pool = [
            candidate(pool_index=index, item_index=index) for index in range(5)
        ]
        observed = {
            candidate_key(record): {**record, "settle_tilt_deg": 0.0}
            for record in pool
        }
        forced = {candidate_key(pool[0]): "selected_action"}
        seeds = {**forced, candidate_key(pool[1]): "paired_control_seed"}

        table = annotate_swapped_portfolio(
            pool[:3],
            pool=pool,
            observed=observed,
            forced_keys=forced,
            seed_keys=seeds,
        )

        self.assertTrue(pool[0]["sampling"]["forced"])
        self.assertEqual(
            pool[0]["sampling"]["forced_reason"], "selected_action"
        )
        self.assertFalse(pool[1]["sampling"]["forced"])
        self.assertEqual(
            pool[1]["sampling"]["seed_role"], "paired_control_seed"
        )
        self.assertEqual(pool[2]["sampling"]["seed_role"], "swap_optimizer")
        self.assertEqual(
            [row["sampled"] for row in table],
            [3],
        )
        self.assertTrue(
            all(
                record["sampling"]["design"] == SWAP_DESIGN
                for record in pool[:3]
            )
        )
        self.assertTrue(
            all(
                record["sampling"]["sampling_weight"] is None
                for record in pool[:3]
            )
        )


class SafeSplitIntegrationTests(unittest.TestCase):
    def build(self, *, swap_rounds: int):
        rng = random.Random(5)
        primary = random_population(31, count=18)
        control = random_population(32, count=18, offset=200)
        results = {}
        for index, record in enumerate(primary + control):
            safe = index % 9 != 0
            results[candidate_key(record)] = {
                "is_placed_safe": safe,
                "is_valid": True,
                "is_included": True,
                "x_plus": (
                    {
                        "position": [
                            value + rng.random() * 0.1
                            for value in record["center"]
                        ],
                        "aabb_dimensions": [0.3, 0.2, 0.2],
                        "quaternion": [0.0, 0.0, 0.0, 1.0],
                    }
                    if safe
                    else None
                ),
            }
        positive, negative, control_positive, report = (
            split_observed_outcomes(
                primary,
                control,
                results=results,
                per_stratum=6,
                rng=random.Random(3),
                forced_keys={},
                swap_rounds=swap_rounds,
            )
        )
        comparison = settled_portfolio_comparison(
            diversity_sample=positive,
            random_sample=control_positive,
            results=results,
        )
        return positive, negative, control_positive, report, comparison

    def test_trace_final_objective_equals_the_reported_guard_number(self):
        _positive, _negative, _control, report, comparison = self.build(
            swap_rounds=64
        )

        self.assertEqual(
            report["swap_optimizer"]["final_objective"][
                "mean_nearest_neighbor_distance_delta"
            ],
            comparison["diversity_minus_random"][
                "mean_nearest_neighbor_distance"
            ],
        )

    def test_seeded_search_starts_from_the_control_and_improves_on_greedy(
        self,
    ):
        _p, _n, _c, seeded_report, seeded = self.build(swap_rounds=64)
        _p0, _n0, _c0, greedy_report, greedy = self.build(swap_rounds=0)

        self.assertEqual(
            seeded_report["swap_optimizer"]["initial_objective"][
                "mean_nearest_neighbor_distance_delta"
            ],
            0.0,
        )
        self.assertEqual(
            greedy_report["swap_optimizer"]["terminated"], "disabled"
        )
        self.assertGreater(
            seeded["diversity_minus_random"][
                "mean_nearest_neighbor_distance"
            ],
            0.0,
        )
        self.assertGreaterEqual(
            seeded["diversity_minus_random"]["unique_items"], 0
        )
        self.assertGreaterEqual(
            seeded["diversity_minus_random"]["unique_item_orientations"], 0
        )
        self.assertGreater(seeded_report["control_seeded_positive"], 0)
        self.assertEqual(greedy_report["control_seeded_positive"], 0)

    def test_shared_rows_do_not_rewrite_the_control_arm_provenance(self):
        positive, _negative, control, _report, _comparison = self.build(
            swap_rounds=64
        )
        shared = {candidate_key(record) for record in positive} & {
            candidate_key(record) for record in control
        }

        self.assertTrue(shared, "expected the seed to share rows")
        for record in control:
            self.assertEqual(
                record["sampling"]["design"],
                "observed_safe_stratified_random_control",
            )
        for record in positive:
            self.assertEqual(record["sampling"]["design"], SWAP_DESIGN)

    def test_positive_arm_stays_safe_only_and_disjoint_from_the_negatives(
        self,
    ):
        positive, negative, _control, _report, _comparison = self.build(
            swap_rounds=64
        )

        self.assertTrue(negative)
        self.assertFalse(
            {candidate_key(record) for record in positive}
            & {candidate_key(record) for record in negative}
        )


if __name__ == "__main__":
    unittest.main()
