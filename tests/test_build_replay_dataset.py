from __future__ import annotations

import pathlib
import random
import inspect
import tempfile
import threading
import unittest

from scripts.build_replay_dataset import (
    OutputDirectoryClaimed,
    assign_strata,
    build_dataset_id,
    build_row,
    claim_output_directory,
    gate_verdict,
    match_selected,
    modelling_features,
    outcome_labels,
    run_case,
    sample_candidate_population,
    sampling_coverage_comparison,
    score_band,
    selected_action_error,
    stratified_sample,
)
from scripts.residual_diversity import (
    maximin_residual_sample,
    residual_proxy_coverage,
    settled_portfolio_comparison,
)
from scripts.measure_anchor_recall import (
    candidate_key,
    legacy_prefix_indexed_items,
    load_agent_module,
    policy_indexed_items,
)

agent = load_agent_module()


def candidate(
    *,
    pool_index: int = 0,
    item_index: int = 0,
    container_index: int = 0,
    orientation: int = 0,
    kind: str = "release_candidate",
    center: tuple[float, float, float] = (0.0, 0.0, 0.5),
    score: float = 1.0,
    passed: bool | None = True,
) -> dict:
    record = {
        "pool_index": pool_index,
        "item_index": item_index,
        "container_index": container_index,
        "orientation": orientation,
        "kind": kind,
        "center": list(center),
        "size": [0.3, 0.2, 0.2],
        "action_center": list(center),
        "score": score,
    }
    if passed is not None:
        record["release_risk"] = {
            "features": {"support_ratio": 0.9},
            "passed": passed,
            "reasons": [] if passed else ["support"],
        }
    return record


class StratumTests(unittest.TestCase):
    def test_score_band_splits_the_ranking(self) -> None:
        self.assertEqual(score_band(0, 1000), "top1")
        self.assertEqual(score_band(5, 1000), "top10")
        self.assertEqual(score_band(50, 1000), "top10pct")
        self.assertEqual(score_band(500, 1000), "tail")

    def test_score_bands_partition_the_ranking(self) -> None:
        # The band names read as nested sets (top1 within top10 within
        # top10pct). They must not be: overlapping bands would put one
        # candidate in several strata and break both the inclusion
        # probabilities and the Horvitz-Thompson weights derived from them.
        for population in (1, 5, 12, 40, 100, 283, 1000):
            ranks_by_band: dict[str, set[int]] = {}
            for rank in range(population):
                ranks_by_band.setdefault(
                    score_band(rank, population), set()
                ).add(rank)

            covered: set[int] = set()
            for band, ranks in ranks_by_band.items():
                self.assertFalse(
                    covered & ranks,
                    f"band {band} overlaps another at N={population}",
                )
                covered |= ranks
            self.assertEqual(covered, set(range(population)))

        # Boundaries are adjacent, with no rank left over between bands.
        self.assertEqual(
            {score_band(rank, 1000) for rank in range(1000)},
            {"top1", "top10", "top10pct", "tail"},
        )
        self.assertEqual(score_band(9, 1000), "top10")
        self.assertEqual(score_band(10, 1000), "top10pct")
        self.assertEqual(score_band(99, 1000), "top10pct")
        self.assertEqual(score_band(100, 1000), "tail")

    def test_settled_candidates_have_no_gate_verdict(self) -> None:
        self.assertEqual(
            gate_verdict(candidate(kind="candidate", passed=None)),
            "not_applicable",
        )
        self.assertEqual(gate_verdict(candidate(passed=True)), "pass")
        self.assertEqual(gate_verdict(candidate(passed=False)), "reject")

    def test_strata_rank_within_kind_and_carry_the_gate_verdict(self) -> None:
        records = [
            candidate(center=(0.0, 0.0, 0.1), score=1.0, passed=True),
            candidate(center=(0.0, 0.0, 0.2), score=5.0, passed=False),
            candidate(
                center=(0.0, 0.0, 0.3),
                score=9.0,
                kind="candidate",
                passed=None,
            ),
        ]

        assign_strata(records)

        by_center = {record["center"][2]: record for record in records}
        # Ranking is per kind, so the release candidate scoring 5.0 is rank 0
        # of its own population rather than rank 1 overall.
        self.assertEqual(by_center[0.2]["score_rank"], 0)
        self.assertEqual(by_center[0.2]["score_population"], 2)
        self.assertEqual(by_center[0.2]["stratum"]["gate"], "reject")
        self.assertEqual(by_center[0.1]["score_rank"], 1)
        self.assertEqual(by_center[0.3]["score_rank"], 0)
        self.assertEqual(
            by_center[0.3]["stratum"]["gate"], "not_applicable"
        )
        self.assertEqual(
            by_center[0.2]["stratum_key"],
            "kind=release_candidate|gate=reject|score_band=top1",
        )


class SamplingTests(unittest.TestCase):
    def test_settled_portfolio_comparison_uses_physical_afterstates(self):
        records = [
            candidate(center=(float(index), 0.0, 0.5), score=10 - index)
            for index in range(4)
        ]
        results = {}
        settled_x = (0.00, 0.02, 0.98, 1.00)
        for record, x_position in zip(records, settled_x):
            results[candidate_key(record)] = {
                "is_valid": True,
                "is_placed_safe": True,
                "x_plus": {
                    "position": [x_position, 0.0, 0.5],
                    "quaternion": [0.0, 0.0, 0.0, 1.0],
                    "aabb_dimensions": [0.2, 0.2, 0.2],
                },
            }

        report = settled_portfolio_comparison(
            diversity_sample=[records[0], records[3]],
            random_sample=[records[0], records[1]],
            results=results,
        )

        self.assertEqual(report["residual_diversity"]["settled"], 2)
        self.assertEqual(report["stratified_random"]["placed_safe"], 2)
        self.assertGreater(
            report["residual_diversity"]
            ["mean_nearest_neighbor_distance"],
            report["stratified_random"]
            ["mean_nearest_neighbor_distance"],
        )

    def test_settled_coverage_distinguishes_tilt_at_the_same_position(self):
        records = [
            candidate(
                item_index=index,
                center=(0.0, 0.0, 0.5),
                score=10 - index,
            )
            for index in range(4)
        ]
        quaternions = (
            [0.0, 0.0, 0.0, 1.0],
            [0.0, 0.0, 0.0, 1.0],
            [0.0, 0.0, 0.0, 1.0],
            [0.70710678, 0.0, 0.0, 0.70710678],
        )
        results = {
            candidate_key(record): {
                "is_valid": True,
                "is_placed_safe": True,
                "x_plus": {
                    "position": [0.0, 0.0, 0.5],
                    "quaternion": quaternion,
                    "aabb_dimensions": [0.2, 0.2, 0.2],
                },
            }
            for record, quaternion in zip(records, quaternions)
        }

        report = settled_portfolio_comparison(
            random_sample=records[:2],
            diversity_sample=records[2:],
            results=results,
        )

        self.assertGreater(
            report["residual_diversity"]
            ["mean_nearest_neighbor_distance"],
            report["stratified_random"]
            ["mean_nearest_neighbor_distance"],
        )

    def test_run_case_defaults_to_legacy_probability_sampling(self):
        parameter = inspect.signature(run_case).parameters["sampling_mode"]
        self.assertEqual(parameter.default, "stratified_random")

    def test_coverage_comparison_uses_same_population_without_weights(self):
        records = [
            candidate(center=(x, 0.0, 0.5), score=10.0 - index)
            for index, x in enumerate(
                (0.00, 0.01, 0.02, 0.03, 0.97, 0.98, 0.99, 1.00)
            )
        ]
        assign_strata(records)
        diversity, _ = sample_candidate_population(
            records,
            sampling_mode="residual_diversity",
            per_stratum=2,
            rng=random.Random(4),
            forced_keys={},
        )
        random_sample, _ = sample_candidate_population(
            [dict(record) for record in records],
            sampling_mode="stratified_random",
            per_stratum=2,
            rng=random.Random(4),
            forced_keys={},
        )

        comparison = sampling_coverage_comparison(
            records,
            diversity_sample=diversity,
            random_sample=random_sample,
        )

        self.assertEqual(comparison["population"], len(records))
        self.assertEqual(
            comparison["stratified_random"]["sampled"],
            comparison["residual_diversity"]["sampled"],
        )
        self.assertAlmostEqual(
            comparison["diversity_minus_random"]
            ["mean_nearest_neighbor_distance"],
            comparison["residual_diversity"]
            ["mean_nearest_neighbor_distance"]
            - comparison["stratified_random"]
            ["mean_nearest_neighbor_distance"],
        )
        self.assertTrue(
            all(
                row["sampling"]["sampling_weight"] is None
                for row in diversity
            )
        )

    def test_residual_coverage_distinguishes_clustered_and_spread_samples(
        self,
    ) -> None:
        population = [
            candidate(center=(x, 0.0, 0.5), score=1.0)
            for x in (0.00, 0.01, 0.02, 0.98, 0.99, 1.00)
        ]
        clustered = population[:3]
        spread = [population[0], population[2], population[-1]]

        clustered_metrics = residual_proxy_coverage(
            clustered, reference_records=population
        )
        spread_metrics = residual_proxy_coverage(
            spread, reference_records=population
        )

        self.assertGreater(
            spread_metrics["mean_nearest_neighbor_distance"],
            clustered_metrics["mean_nearest_neighbor_distance"],
        )
        self.assertGreater(
            spread_metrics["spatial_cell_count"],
            clustered_metrics["spatial_cell_count"],
        )

    def test_population_sampler_keeps_inference_and_coverage_modes_separate(
        self,
    ) -> None:
        records = [
            candidate(center=(0.1 * index, 0.0, 0.5), score=-float(index))
            for index in range(20)
        ]
        assign_strata(records)

        random_sample, _ = sample_candidate_population(
            records,
            sampling_mode="stratified_random",
            per_stratum=3,
            rng=random.Random(4),
            forced_keys={},
        )
        diversity_sample, _ = sample_candidate_population(
            records,
            sampling_mode="residual_diversity",
            per_stratum=3,
            rng=random.Random(4),
            forced_keys={},
        )

        self.assertTrue(
            any(row["sampling"]["sampling_weight"] for row in random_sample)
        )
        self.assertTrue(
            all(
                row["sampling"]["sampling_weight"] is None
                for row in diversity_sample
            )
        )
        self.assertTrue(
            all("residual_proxy" in row for row in diversity_sample)
        )

    def test_maximin_sampling_reaches_a_distinct_spatial_cluster(self) -> None:
        records = [
            candidate(
                center=(x, 0.0, 0.5),
                score=10.0 - index,
            )
            for index, x in enumerate((0.00, 0.01, 0.02, 1.00, 1.01, 1.02))
        ]

        sample = maximin_residual_sample(
            records,
            quota=2,
            forced_keys={},
        )

        self.assertEqual(len(sample), 2)
        self.assertEqual(sample[0]["center"][0], 0.0)
        self.assertGreater(sample[1]["center"][0], 0.9)

    def test_maximin_sampling_preserves_forced_candidates(self) -> None:
        records = [
            candidate(center=(float(index), 0.0, 0.5), score=-float(index))
            for index in range(5)
        ]
        forced = records[2]

        sample = maximin_residual_sample(
            records,
            quota=2,
            forced_keys={candidate_key(forced): "selected_action"},
        )

        self.assertIn(candidate_key(forced), {candidate_key(row) for row in sample})
        self.assertTrue(forced["sampling"]["forced"])
        self.assertEqual(
            forced["sampling"]["forced_reason"], "selected_action"
        )
        self.assertIsNone(forced["sampling"]["inclusion_probability"])
        self.assertIsNone(forced["sampling"]["sampling_weight"])

    def test_maximin_sampling_is_deterministic_and_marks_coverage_design(
        self,
    ) -> None:
        def population() -> list[dict]:
            return [
                candidate(
                    pool_index=index % 2,
                    orientation=index % 3,
                    center=(0.1 * index, 0.03 * (index % 4), 0.5),
                    score=10.0 - index,
                )
                for index in range(10)
            ]

        first = maximin_residual_sample(
            population(), quota=4, forced_keys={}
        )
        second = maximin_residual_sample(
            population(), quota=4, forced_keys={}
        )

        self.assertEqual(
            [candidate_key(row) for row in first],
            [candidate_key(row) for row in second],
        )
        for row in first:
            self.assertEqual(
                row["sampling"]["design"],
                "deterministic_residual_proxy_maximin",
            )
            self.assertIsNone(row["sampling"]["inclusion_probability"])
            self.assertIsNone(row["sampling"]["sampling_weight"])

    def test_rejected_candidates_survive_sampling(self) -> None:
        # A ranking-shaped population: rejects exist but are rare, exactly
        # the case an unstratified top-N sample would drop entirely.
        records = [
            candidate(center=(0.0, 0.0, float(index)), score=100.0 - index)
            for index in range(40)
        ]
        records += [
            candidate(
                center=(1.0, 0.0, float(index)),
                score=1.0 - index,
                passed=False,
            )
            for index in range(3)
        ]
        assign_strata(records)

        sample, table = stratified_sample(
            records,
            per_stratum=4,
            rng=random.Random(0),
            forced_keys=set(),
        )

        rejected = [
            row for row in sample if row["stratum"]["gate"] == "reject"
        ]
        self.assertEqual(len(rejected), 3)
        self.assertTrue(all(row["stratum_key"] for row in table))
        self.assertEqual(
            sum(entry["population"] for entry in table), len(records)
        )

    def test_inclusion_probability_and_weight_are_recorded(self) -> None:
        records = [
            candidate(center=(0.0, 0.0, float(index)), score=-float(index))
            for index in range(20)
        ]
        assign_strata(records)

        sample, table = stratified_sample(
            records,
            per_stratum=5,
            rng=random.Random(1),
            forced_keys=set(),
        )

        tail = [
            row for row in sample if row["stratum"]["score_band"] == "tail"
        ]
        self.assertTrue(tail)
        for row in tail:
            sampling = row["sampling"]
            self.assertGreater(sampling["inclusion_probability"], 0.0)
            self.assertLessEqual(sampling["inclusion_probability"], 1.0)
            self.assertAlmostEqual(
                sampling["sampling_weight"],
                1.0 / sampling["inclusion_probability"],
            )
            self.assertFalse(sampling["forced"])
        # Horvitz-Thompson: the weights of one stratum recover its size.
        entry = next(
            item
            for item in table
            if item["stratum"]["score_band"] == "tail"
        )
        self.assertAlmostEqual(
            sum(row["sampling"]["sampling_weight"] for row in tail),
            entry["population"],
        )

    def test_selected_candidate_is_always_included_with_probability_one(
        self,
    ) -> None:
        records = [
            candidate(center=(0.0, 0.0, float(index)), score=-float(index))
            for index in range(30)
        ]
        assign_strata(records)
        # Pick something deep in the tail that a small draw would miss.
        forced = records[-1]
        forced_key = candidate_key(forced)

        sample, _table = stratified_sample(
            records,
            per_stratum=2,
            rng=random.Random(7),
            forced_keys={forced_key},
        )

        chosen = {candidate_key(row) for row in sample}
        self.assertIn(forced_key, chosen)
        self.assertEqual(forced["sampling"]["inclusion_probability"], 1.0)
        self.assertTrue(forced["sampling"]["forced"])
        self.assertEqual(
            forced["sampling"]["forced_reason"], "selected_action"
        )
        # The forced row consumes one slot instead of being an extra draw.
        same_stratum = [
            row
            for row in sample
            if row["stratum_key"] == forced["stratum_key"]
        ]
        self.assertEqual(len(same_stratum), 2)

    def test_stratum_of_only_forced_rows_reports_no_draw_probability(
        self,
    ) -> None:
        records = [candidate(center=(0.0, 0.0, 1.0), score=1.0)]
        assign_strata(records)
        forced_key = candidate_key(records[0])

        _sample, table = stratified_sample(
            records,
            per_stratum=4,
            rng=random.Random(0),
            forced_keys={forced_key},
        )

        entry = table[0]
        self.assertEqual(entry["population"], 1)
        self.assertEqual(entry["forced"], 1)
        # Nothing was drawn, so there is no draw probability to report.
        # 0.0 would read as "sampled with probability zero".
        self.assertIsNone(entry["inclusion_probability"])

    def test_forced_reason_mapping_marks_shadow_rerank_selection(
        self,
    ) -> None:
        records = [
            candidate(center=(0.0, 0.0, float(index)), score=-float(index))
            for index in range(6)
        ]
        assign_strata(records)
        selected = records[0]
        shadow = records[-1]

        sample, _table = stratified_sample(
            records,
            per_stratum=1,
            rng=random.Random(3),
            forced_keys={
                candidate_key(shadow): "shadow_rerank_selection",
                candidate_key(selected): "selected_action",
            },
        )

        chosen = {candidate_key(row) for row in sample}
        self.assertIn(candidate_key(selected), chosen)
        self.assertIn(candidate_key(shadow), chosen)
        self.assertEqual(
            selected["sampling"]["forced_reason"], "selected_action"
        )
        self.assertEqual(
            shadow["sampling"]["forced_reason"], "shadow_rerank_selection"
        )
        self.assertEqual(shadow["sampling"]["inclusion_probability"], 1.0)


class LabelTests(unittest.TestCase):
    def test_outcome_splits_regression_targets_and_labels(self) -> None:
        result = {
            "is_included": True,
            "is_valid": True,
            "is_placed_safe": False,
            "settle_metrics": {
                "settle_angle_deg": 90.3,
                "settle_displacement_norm": 0.871,
                "settle_displacement_xyz": [0.8, 0.3, -0.12],
                "settle_final_position": [0.1, 0.2, 0.3],
                "settle_final_quaternion": [0.0, 0.0, 0.0, 1.0],
                "settle_aabb_dimensions": [0.2, 0.3, 0.4],
            },
        }

        outcome = outcome_labels(result)

        self.assertAlmostEqual(outcome["delta_theta_deg"], 90.3)
        self.assertAlmostEqual(outcome["d_xy"], (0.8**2 + 0.3**2) ** 0.5)
        self.assertAlmostEqual(outcome["d_z"], 0.12)
        self.assertEqual(outcome["x_plus"]["position"], [0.1, 0.2, 0.3])
        self.assertTrue(outcome["settled"])
        self.assertTrue(outcome["Y"]["rotated_over_30"])
        self.assertTrue(outcome["Y"]["not_placed_safe"])
        self.assertFalse(outcome["Y"]["not_valid"])
        self.assertFalse(outcome["Y"]["not_included"])
        self.assertTrue(outcome["Y"]["physically_dangerous"])

    def test_unreached_candidate_still_yields_labels(self) -> None:
        outcome = outcome_labels(
            {
                "is_included": False,
                "is_valid": False,
                "is_placed_safe": False,
                "settle_metrics": None,
            }
        )

        self.assertFalse(outcome["settled"])
        self.assertIsNone(outcome["delta_theta_deg"])
        self.assertIsNone(outcome["d_xy"])
        self.assertTrue(outcome["Y"]["not_included"])
        self.assertTrue(outcome["Y"]["not_valid"])


class RowTests(unittest.TestCase):
    def test_diversity_row_keeps_the_residual_proxy_descriptor(self) -> None:
        records = [candidate(center=(0.2, 0.3, 0.5), passed=True)]
        assign_strata(records)
        sample = maximin_residual_sample(
            records, quota=1, forced_keys={}
        )

        row = build_row(
            sample[0],
            dataset_id="ds",
            snapshot_id="ds:000:step-000",
            case_id="000",
            step=0,
            snapshot_name="s.json",
            selected_key=None,
            anytime_keys=set(),
            physical=None,
            feature_availability=(
                agent.ReleaseRiskFeatures.feature_availability()
            ),
        )

        self.assertEqual(
            row["residual_proxy"], sample[0]["residual_proxy"]
        )

    def test_selected_action_is_matched_to_its_candidate(self) -> None:
        records = [
            candidate(center=(0.0, 0.0, 0.5)),
            candidate(center=(0.0, 0.0, 0.9)),
        ]
        action = {
            "item_idx": 0,
            "container_idx": 0,
            "orientation": 0,
            "place_pos": [0.0, 0.0, 0.9],
        }

        self.assertEqual(
            match_selected(action, records), candidate_key(records[1])
        )

    def test_action_outside_the_population_matches_nothing(self) -> None:
        records = [candidate(center=(0.0, 0.0, 0.5))]
        action = {
            "item_idx": 0,
            "container_idx": 0,
            "orientation": 0,
            "place_pos": [0.0, 0.0, 0.25],
        }

        self.assertIsNone(match_selected(action, records))

    def test_row_joins_state_action_features_and_labels(self) -> None:
        records = [candidate(center=(0.0, 0.0, 0.5), passed=False)]
        assign_strata(records)
        sample, _table = stratified_sample(
            records,
            per_stratum=1,
            rng=random.Random(0),
            forced_keys=set(),
        )
        record = sample[0]
        key = candidate_key(record)

        row = build_row(
            record,
            dataset_id="ds-1",
            snapshot_id="ds-1:000:step-013",
            case_id="000",
            step=13,
            snapshot_name="step-013-state.json",
            selected_key=key,
            anytime_keys=set(),
            physical={"is_included": True},
            feature_availability={"support_ratio": "available"},
        )

        self.assertEqual(row["dataset_id"], "ds-1")
        self.assertEqual(row["snapshot_id"], "ds-1:000:step-013")
        self.assertEqual(row["case_id"], "000")
        self.assertEqual(row["step"], 13)
        self.assertEqual(row["snapshot_path"], "step-013-state.json")
        self.assertEqual(row["phi"], {"support_ratio": 0.9})
        self.assertFalse(row["gate_passed"])
        self.assertEqual(row["gate_reasons"], ["support"])
        self.assertEqual(row["score_immediate"], 1.0)
        self.assertTrue(row["selected"])
        self.assertFalse(row["found_by_anytime"])
        self.assertEqual(row["stratum"]["gate"], "reject")
        self.assertIn("inclusion_probability", row["sampling"])
        self.assertEqual(row["physical"], {"is_included": True})


class PopulationAlignmentTests(unittest.TestCase):
    """
    The replay population must be the item set the policy searched.

    Under the default class_aware coverage the legacy ordered prefix is a
    different set: it drops the reserved soft/priority representatives and
    admits normal items the policy never considered. Sampling from the
    prefix silently changes the estimand and can leave the selected action
    outside the population entirely.
    """

    @staticmethod
    def pool() -> list[dict]:
        def entry(index: int, soft: bool = False, prio: bool = False) -> dict:
            return {
                "index": index,
                "length": 0.3,
                "width": 0.3,
                "height": 0.3,
                "mass": 10.0 - index * 0.1,
                "is_soft": soft,
                "is_prioritized": prio,
            }

        return (
            [entry(index) for index in range(12)]
            + [entry(12, soft=True), entry(13, prio=True)]
        )

    def test_class_aware_coverage_differs_from_the_legacy_prefix(
        self,
    ) -> None:
        observation = {"pool_list": self.pool()}
        previous = agent.ITEM_COVERAGE_MODE
        agent.ITEM_COVERAGE_MODE = "class_aware"
        try:
            policy_set = [
                index
                for index, _item in policy_indexed_items(agent, observation)
            ]
        finally:
            agent.ITEM_COVERAGE_MODE = previous
        legacy_set = [
            index
            for index, _item in legacy_prefix_indexed_items(agent, observation)
        ]

        self.assertNotEqual(policy_set, legacy_set)
        # The soft and priority representatives exist only in the policy set.
        self.assertIn(12, policy_set)
        self.assertIn(13, policy_set)
        self.assertNotIn(12, legacy_set)
        self.assertNotIn(13, legacy_set)
        # And the prefix admits normal items the policy never searched.
        self.assertTrue(set(legacy_set) - set(policy_set))

    def test_legacy_mode_leaves_the_two_sets_equal(self) -> None:
        observation = {"pool_list": self.pool()}
        previous = agent.ITEM_COVERAGE_MODE
        agent.ITEM_COVERAGE_MODE = "legacy"
        try:
            policy_set = [
                index
                for index, _item in policy_indexed_items(agent, observation)
            ]
        finally:
            agent.ITEM_COVERAGE_MODE = previous

        self.assertEqual(
            policy_set,
            [
                index
                for index, _item in legacy_prefix_indexed_items(
                    agent, observation
                )
            ],
        )


class SelectedActionErrorTests(unittest.TestCase):
    def test_missing_placement_candidate_is_an_error(self) -> None:
        message = selected_action_error(
            {"action_source": "placement_core"}, None
        )
        self.assertIsNotNone(message)
        self.assertIn("not found in the enumerated population", message)

    def test_protocol_fallback_is_not_an_error(self) -> None:
        for source in ("fixed_fallback", "unsafe_protocol_fallback"):
            self.assertIsNone(
                selected_action_error({"action_source": source}, None)
            )

    def test_matched_selection_is_not_an_error(self) -> None:
        self.assertIsNone(
            selected_action_error({"action_source": "placement_core"}, ("k",))
        )


class UnavailableFeatureTests(unittest.TestCase):
    def test_unavailable_features_are_kept_out_of_the_modelling_vector(
        self,
    ) -> None:
        availability = agent.ReleaseRiskFeatures.feature_availability()
        features = {
            "support_ratio": 0.9,
            "initial_tilt_deg": 0.0,
            "initial_orientation": 3,
        }

        modelling = modelling_features(features, availability)

        self.assertIn("support_ratio", modelling)
        self.assertNotIn("initial_tilt_deg", modelling)

    def test_row_marks_the_placeholder_machine_readably(self) -> None:
        records = [candidate(center=(0.0, 0.0, 0.5), passed=True)]
        records[0]["release_risk"]["features"] = {
            "support_ratio": 0.9,
            "initial_tilt_deg": 0.0,
        }
        assign_strata(records)
        sample, _table = stratified_sample(
            records,
            per_stratum=1,
            rng=random.Random(0),
            forced_keys=set(),
        )

        row = build_row(
            sample[0],
            dataset_id="ds",
            snapshot_id="ds:000:step-000",
            case_id="000",
            step=0,
            snapshot_name="s.json",
            selected_key=None,
            anytime_keys=set(),
            physical=None,
            feature_availability=(
                agent.ReleaseRiskFeatures.feature_availability()
            ),
        )

        self.assertIn("initial_tilt_deg", row["phi"])
        self.assertNotIn("initial_tilt_deg", row["phi_modelling"])
        self.assertEqual(
            row["phi_availability"]["initial_tilt_deg"],
            "unavailable_placeholder",
        )
        self.assertIn("initial_tilt_deg", row["phi_unavailable"])


class IdentifierTests(unittest.TestCase):
    def test_dataset_snapshot_candidate_triple_is_unique(self) -> None:
        records = [
            candidate(center=(0.0, 0.0, float(index)), score=-float(index))
            for index in range(12)
        ]
        assign_strata(records)
        sample, _table = stratified_sample(
            records,
            per_stratum=12,
            rng=random.Random(0),
            forced_keys=set(),
        )
        availability = agent.ReleaseRiskFeatures.feature_availability()

        triples = set()
        for snapshot in ("ds:000:step-000", "ds:000:step-001"):
            for record in sample:
                row = build_row(
                    record,
                    dataset_id="ds",
                    snapshot_id=snapshot,
                    case_id="000",
                    step=0,
                    snapshot_name="s.json",
                    selected_key=None,
                    anytime_keys=set(),
                    physical=None,
                    feature_availability=availability,
                )
                triples.add(
                    (
                        row["dataset_id"],
                        row["snapshot_id"],
                        row["candidate_id"],
                    )
                )

        self.assertEqual(len(triples), 2 * len(sample))

    def test_dataset_ids_differ_for_runs_started_in_the_same_second(
        self,
    ) -> None:
        # Exercises the production builder, not a copy of it: a test that
        # rebuilt the id itself would still pass if the entropy were dropped
        # from the real implementation.
        def make() -> str:
            return build_dataset_id(
                run_id="20260730_120000",
                case_id="000",
                selection_mode="weighted",
                coverage_mode="class_aware",
                risk_gate_mode="shadow",
                config_digest="0d1bb318ef02a2ae",
            )

        ids = {make() for _ in range(256)}
        self.assertEqual(len(ids), 256)
        # The stable part is still there, so the id stays human-sortable.
        self.assertTrue(
            make().startswith(
                "20260730_120000-000-weighted-class_aware-shadow-0d1bb318-"
            )
        )


class OutputDirectoryTests(unittest.TestCase):
    def test_directory_holding_a_manifest_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory)
            (target / "manifest.json").write_text("{}", encoding="utf-8")

            with self.assertRaises(OutputDirectoryClaimed) as caught:
                claim_output_directory(target)

        self.assertIn("refusing to mix two datasets", str(caught.exception))

    def test_overwrite_reuses_the_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory)
            (target / "manifest.json").write_text("{}", encoding="utf-8")

            manifest = claim_output_directory(target, overwrite=True)

        self.assertEqual(manifest.name, "manifest.json")

    def test_only_one_of_many_concurrent_claims_succeeds(self) -> None:
        # The real race: two runs given the same absent or empty
        # --output-dir. A mkdir(exist_ok=True) followed by an exists() check
        # lets both through, after which they interleave two datasets under
        # the same per-step file names.
        workers = 16
        for scenario in ("absent", "empty"):
            with tempfile.TemporaryDirectory() as directory:
                target = pathlib.Path(directory) / "out"
                if scenario == "empty":
                    target.mkdir()

                start = threading.Barrier(workers)
                outcomes: list[str] = []
                lock = threading.Lock()

                def attempt() -> None:
                    start.wait()
                    try:
                        claim_output_directory(target)
                    except OutputDirectoryClaimed:
                        result = "refused"
                    else:
                        result = "claimed"
                    with lock:
                        outcomes.append(result)

                threads = [
                    threading.Thread(target=attempt) for _ in range(workers)
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

                self.assertEqual(
                    outcomes.count("claimed"),
                    1,
                    f"{scenario}: {outcomes.count('claimed')} winners",
                )
                self.assertEqual(outcomes.count("refused"), workers - 1)


if __name__ == "__main__":
    unittest.main()
