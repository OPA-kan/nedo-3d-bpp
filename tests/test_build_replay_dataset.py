from __future__ import annotations

import random
import unittest

from scripts.build_replay_dataset import (
    assign_strata,
    build_row,
    gate_verdict,
    match_selected,
    outcome_labels,
    score_band,
    stratified_sample,
)
from scripts.measure_anchor_recall import candidate_key


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
            case_id="000",
            step=13,
            snapshot_name="step-013-state.json",
            selected_key=key,
            anytime_keys=set(),
            physical={"is_included": True},
        )

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


if __name__ == "__main__":
    unittest.main()
