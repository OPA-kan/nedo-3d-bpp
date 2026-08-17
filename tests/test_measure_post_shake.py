import importlib.util
import math
import pathlib
import sys
import unittest

from scripts.measure_post_shake import (
    CONTACT_TOLERANCE,
    FOOTPRINT_EPSILON,
    aabb_from_pose,
    attribute_coverage,
    covers_from_above,
    evaluate_gates,
    extract_placed,
    join_for_gates,
    parse_label,
    spearman,
)

PYBULLET_AVAILABLE = importlib.util.find_spec("pybullet") is not None
ROOT = pathlib.Path(__file__).resolve().parents[1]


def box(center, dims, **flags):
    aabb_min, aabb_max = aabb_from_pose(center, (0, 0, 0, 1), dims)
    entry = {"aabb_min": aabb_min, "aabb_max": aabb_max}
    entry.update(flags)
    return entry


class AabbFromPoseTest(unittest.TestCase):
    def test_identity_pose(self):
        aabb_min, aabb_max = aabb_from_pose(
            (1.0, 2.0, 3.0), (0, 0, 0, 1), (0.4, 0.2, 0.6)
        )
        self.assertEqual(aabb_min, [0.8, 1.9, 2.7])
        self.assertEqual(aabb_max, [1.2, 2.1, 3.3])

    def test_quarter_turn_about_z_swaps_footprint(self):
        half_sqrt2 = math.sqrt(0.5)
        aabb_min, aabb_max = aabb_from_pose(
            (0.0, 0.0, 0.0), (0, 0, half_sqrt2, half_sqrt2), (0.4, 0.2, 0.6)
        )
        self.assertAlmostEqual(aabb_max[0] - aabb_min[0], 0.2)
        self.assertAlmostEqual(aabb_max[1] - aabb_min[1], 0.4)
        self.assertAlmostEqual(aabb_max[2] - aabb_min[2], 0.6)


class CoverageTest(unittest.TestCase):
    def test_soft_covered_by_plain_box_is_a_violation(self):
        soft = box((0, 0, 0.1), (0.4, 0.4, 0.2), is_soft=True)
        plain = box((0, 0, 0.3), (0.4, 0.4, 0.2), is_soft=False)
        self.assertTrue(covers_from_above(soft, plain))
        coverage = attribute_coverage([soft, plain], False)
        self.assertEqual(coverage["post_shake_soft_covered"], 1)
        self.assertEqual(coverage["post_shake_soft_clean"], 0.0)

    def test_uncovered_soft_box_is_clean(self):
        soft = box((0, 0, 0.1), (0.4, 0.4, 0.2), is_soft=True)
        far_above = box((0, 0, 0.5), (0.4, 0.4, 0.2), is_soft=False)
        beside = box((1.0, 0, 0.1), (0.4, 0.4, 0.2), is_soft=False)
        self.assertFalse(covers_from_above(soft, far_above))
        self.assertFalse(covers_from_above(soft, beside))
        coverage = attribute_coverage([soft, far_above, beside], False)
        self.assertEqual(coverage["post_shake_soft_covered"], 0)
        self.assertEqual(coverage["post_shake_soft_clean"], 1.0)

    def test_soft_on_soft_is_free(self):
        lower = box((0, 0, 0.1), (0.4, 0.4, 0.2), is_soft=True)
        upper = box((0, 0, 0.3), (0.4, 0.4, 0.2), is_soft=True)
        coverage = attribute_coverage([lower, upper], False)
        self.assertEqual(coverage["post_shake_soft_covered"], 0)
        self.assertEqual(coverage["post_shake_soft_clean"], 1.0)

    def test_priority_and_soft_judged_independently(self):
        both = box(
            (0, 0, 0.1), (0.4, 0.4, 0.2), is_soft=True, is_prioritized=True
        )
        plain = box((0, 0, 0.3), (0.4, 0.4, 0.2))
        coverage = attribute_coverage([both, plain], False)
        self.assertEqual(coverage["post_shake_soft_covered"], 1)
        self.assertEqual(coverage["post_shake_priority_covered"], 1)

    def test_misrouted_only_when_priority_container_exists(self):
        priority = box(
            (0, 0, 0.1),
            (0.4, 0.4, 0.2),
            is_prioritized=True,
            container_is_prioritized=False,
        )
        without = attribute_coverage([priority], False)
        self.assertEqual(without["post_shake_priority_misrouted"], 0)
        self.assertEqual(without["post_shake_priority_clean"], 1.0)
        with_container = attribute_coverage([priority], True)
        self.assertEqual(with_container["post_shake_priority_misrouted"], 1)
        self.assertEqual(with_container["post_shake_priority_clean"], 0.0)

    def test_no_attribute_items_yields_none_not_one(self):
        plain = box((0, 0, 0.1), (0.4, 0.4, 0.2))
        coverage = attribute_coverage([plain], False)
        self.assertIsNone(coverage["post_shake_soft_clean"])
        self.assertIsNone(coverage["post_shake_priority_clean"])

    def test_corner_gap_beyond_tolerance_is_not_a_cover(self):
        soft = box((0, 0, 0.1), (0.4, 0.4, 0.2), is_soft=True)
        hovering = box(
            (0, 0, 0.2 + CONTACT_TOLERANCE + 0.011),
            (0.4, 0.4, 0.2),
        )
        self.assertFalse(covers_from_above(soft, hovering))


class SpearmanTest(unittest.TestCase):
    def test_perfect_monotone(self):
        self.assertAlmostEqual(
            spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0
        )

    def test_reversed(self):
        self.assertAlmostEqual(
            spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0
        )

    def test_ties_use_average_ranks(self):
        rho = spearman([1, 2, 2, 3], [1, 2, 2, 3])
        self.assertAlmostEqual(rho, 1.0)

    def test_zero_variance_is_none(self):
        self.assertIsNone(spearman([1, 1, 1], [1, 2, 3]))
        self.assertIsNone(spearman([1], [1]))


def joined_row(
    arm,
    cloned_shift,
    recorded_shift,
    cloned_shifted,
    recorded_shifted,
    cloned_toppled=0,
    recorded_toppled=0,
    cloned_ke=1.0,
    recorded_ke=1.0,
):
    return {
        "label": f"row-{arm}-{cloned_shift}",
        "case_id": "case",
        "arm": arm,
        "cloned_max_shift": cloned_shift,
        "recorded_max_shift": recorded_shift,
        "cloned_items_shifted": cloned_shifted,
        "recorded_items_shifted": recorded_shifted,
        "cloned_items_toppled": cloned_toppled,
        "recorded_items_toppled": recorded_toppled,
        "cloned_peak_ke": cloned_ke,
        "recorded_peak_ke": recorded_ke,
    }


class GateTest(unittest.TestCase):
    def passing_rows(self):
        rows = []
        for i in range(5):
            rows.append(
                joined_row(
                    "base",
                    0.01 * (i + 1),
                    0.012 * (i + 1),
                    i,
                    i,
                    cloned_ke=1.0 + 0.1 * i,
                    recorded_ke=1.0 + 0.1 * i,
                )
            )
            rows.append(
                joined_row(
                    "quiet_guard",
                    0.02 * (i + 6),
                    0.022 * (i + 6),
                    i + 5,
                    i + 5,
                    cloned_toppled=1,
                    recorded_toppled=2,
                    cloned_ke=2.0 + 0.1 * i,
                    recorded_ke=2.0 + 0.1 * i,
                )
            )
        return rows

    def test_all_gates_pass_on_faithful_clone(self):
        gates = evaluate_gates(self.passing_rows())
        self.assertTrue(gates["gate_spearman_max_shift"])
        self.assertTrue(gates["gate_spearman_items_shifted"])
        self.assertTrue(gates["gate_toppled"])
        self.assertTrue(gates["direction"]["computable"])
        self.assertTrue(gates["gate_direction"])
        self.assertEqual(gates["verdict"], "pass")

    def test_toppled_gate_fails_when_counts_diverge(self):
        rows = self.passing_rows()
        for row in rows:
            row["cloned_items_toppled"] = row["recorded_items_toppled"] + 2
        gates = evaluate_gates(rows)
        self.assertFalse(gates["gate_toppled"])
        self.assertEqual(gates["verdict"], "fail")

    def test_anticorrelated_shift_fails_spearman_gate(self):
        rows = self.passing_rows()
        recorded = [row["recorded_max_shift"] for row in rows]
        for row, value in zip(rows, reversed(recorded)):
            row["recorded_max_shift"] = value
        gates = evaluate_gates(rows)
        self.assertFalse(gates["gate_spearman_max_shift"])
        self.assertEqual(gates["verdict"], "fail")

    def test_direction_sign_mismatch_fails(self):
        rows = self.passing_rows()
        for row in rows:
            if row["arm"] == "quiet_guard":
                row["cloned_peak_ke"] = 0.1  # clone shows a deficit
        gates = evaluate_gates(rows)
        self.assertTrue(gates["direction"]["computable"])
        self.assertFalse(gates["gate_direction"])
        self.assertEqual(gates["verdict"], "fail")

    def test_direction_not_computable_with_one_arm_does_not_bind(self):
        rows = [row for row in self.passing_rows() if row["arm"] == "base"]
        gates = evaluate_gates(rows)
        self.assertFalse(gates["direction"]["computable"])
        self.assertIsNone(gates["gate_direction"])
        self.assertEqual(gates["verdict"], "pass")


class ExtractionTest(unittest.TestCase):
    def case_config(self):
        return {
            "item_stream": {
                "item_list": [
                    {"index": 0, "length": 0.4, "width": 0.4, "height": 0.2},
                    {"index": 7, "length": 0.3, "width": 0.3, "height": 0.3},
                ]
            }
        }

    def test_only_safely_placed_steps_are_rebuilt(self):
        record = {
            "evaluation": {
                "step_metrics": [
                    {
                        "step": 0,
                        "selected_item_index": 0,
                        "container_index": 0,
                        "status": {"is_placed_safe": True},
                        "settle_final_position": [0.0, 0.0, 0.1],
                        "settle_final_quaternion": [0, 0, 0, 1],
                    },
                    {
                        "step": 1,
                        "selected_item_index": 7,
                        "container_index": 0,
                        "status": {"is_placed_safe": False},
                        "settle_final_position": [0.0, 0.0, 0.4],
                        "settle_final_quaternion": [0, 0, 0, 1],
                    },
                ]
            }
        }
        placed, skipped = extract_placed(self.case_config(), record)
        self.assertEqual(len(placed), 1)
        self.assertEqual(placed[0]["item_config"]["index"], 0)
        self.assertEqual(skipped, [])

    def test_missing_pose_is_reported_not_dropped_silently(self):
        record = {
            "evaluation": {
                "step_metrics": [
                    {
                        "step": 0,
                        "selected_item_index": 0,
                        "container_index": 0,
                        "status": {"is_placed_safe": True},
                        "settle_final_position": None,
                        "settle_final_quaternion": None,
                    }
                ]
            }
        }
        placed, skipped = extract_placed(self.case_config(), record)
        self.assertEqual(placed, [])
        self.assertEqual(skipped, [0])

    def test_parse_label(self):
        self.assertEqual(parse_label("b000-k15-quiet_guard-r2"),
                         ("quiet_guard", 2))
        self.assertEqual(parse_label("b000-k15-base-r0"), ("base", 0))
        self.assertEqual(parse_label("nolabel"), (None, None))

    def test_join_skips_rows_without_both_sides(self):
        shake = {
            "shake_max_shift": 0.1,
            "shake_items_shifted": 1,
            "shake_items_toppled": 0,
            "shake_peak_kinetic_energy": 2.0,
        }
        rows = [
            {"label": "a", "case_id": "c", "arm": "base",
             "cloned": dict(shake), "recorded": dict(shake)},
            {"label": "b", "case_id": "c", "arm": "base",
             "cloned": None, "recorded": dict(shake)},
            {"label": "c", "case_id": "c", "arm": "base",
             "cloned": dict(shake), "recorded": None},
        ]
        joined = join_for_gates(rows)
        self.assertEqual([row["label"] for row in joined], ["a"])


def _load_official_diagnostics():
    module_path = (
        ROOT / "simulator" / "src" / "ground_handling" / "diagnostics.py"
    )
    spec = importlib.util.spec_from_file_location(
        "post_shake_official_diagnostics", module_path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class OfficialConstantDriftTest(unittest.TestCase):
    """The copied constants must equal the official module's."""

    @classmethod
    def setUpClass(cls):
        cls.diagnostics = _load_official_diagnostics()

    def test_coverage_constants_match_diagnostics(self):
        self.assertEqual(
            CONTACT_TOLERANCE, self.diagnostics.CONTACT_TOLERANCE
        )
        self.assertEqual(
            FOOTPRINT_EPSILON, self.diagnostics.FOOTPRINT_EPSILON
        )

    def test_coverage_matches_official_calculator(self):
        calculate_attribute_placement = (
            self.diagnostics.calculate_attribute_placement
        )
        items = [
            box((0, 0, 0.1), (0.4, 0.4, 0.2), is_soft=True,
                is_prioritized=False),
            box((0, 0, 0.3), (0.4, 0.4, 0.2), is_soft=False,
                is_prioritized=True),
            box((1.0, 0, 0.1), (0.4, 0.4, 0.2), is_soft=False,
                is_prioritized=True),
        ]
        official = calculate_attribute_placement(
            [{"is_prioritized": False, "packed_items": items}]
        )
        local = attribute_coverage(
            [dict(item, container_is_prioritized=False) for item in items],
            False,
        )
        self.assertEqual(
            local["post_shake_soft_covered"],
            official["soft_covered_by_other"],
        )
        self.assertEqual(
            local["post_shake_priority_covered"],
            official["priority_covered_by_other"],
        )
        self.assertEqual(
            local["post_shake_soft_clean"], official["soft_clean_ratio"]
        )
        self.assertEqual(
            local["post_shake_priority_clean"],
            official["priority_clean_ratio"],
        )


@unittest.skipUnless(PYBULLET_AVAILABLE, "pybullet not installed")
class RebuildAndShakeTest(unittest.TestCase):
    def minimal_config(self):
        return {
            "containers": {
                "spacing": 2.5,
                "container_list": [
                    {
                        "index": 0,
                        "length": 2.0,
                        "width": 1.45,
                        "height": 1.61,
                        "thickness": 0.04,
                        "buffer": 0.0,
                        "cut_x": 0.44,
                        "cut_y": 0.4,
                        "packed_items": [],
                        "require_shelf": False,
                        "is_prioritized": False,
                    }
                ],
            },
            "item_stream": {
                "item_list": [
                    {
                        "index": 0,
                        "length": 0.5,
                        "width": 0.4,
                        "height": 0.2,
                        "mass": 4.0,
                    },
                    {
                        "index": 1,
                        "length": 0.4,
                        "width": 0.3,
                        "height": 0.2,
                        "mass": 1.0,
                        "is_soft": True,
                    },
                ]
            },
            "validator": {"inclusion_margin": -0.005},
        }

    def case_record(self):
        def step(index, z):
            return {
                "step": index,
                "selected_item_index": index,
                "container_index": 0,
                "status": {"is_placed_safe": True},
                "settle_final_position": [0.0, 0.2, z],
                "settle_final_quaternion": [0.0, 0.0, 0.0, 1.0],
            }

        return {
            "evaluation": {
                "step_metrics": [step(0, 0.14), step(1, 0.34)]
            }
        }

    def test_rebuild_shake_and_coverage_fields(self):
        from scripts.measure_post_shake import rebuild_and_shake

        metrics = rebuild_and_shake(
            self.minimal_config(), self.case_record()
        )
        self.assertEqual(metrics["shake_items"], 2)
        self.assertEqual(metrics["items_rebuilt"], 2)
        self.assertGreaterEqual(metrics["shake_peak_kinetic_energy"], 0.0)
        self.assertLessEqual(metrics["shake_items_toppled"], 2)
        # One soft item in the stream: soft_clean is defined, priority
        # (absent from the stream) stays None rather than 1.0.
        self.assertEqual(metrics["post_shake_soft_items"], 1)
        self.assertIn("post_shake_soft_clean", metrics)
        self.assertIn("post_shake_priority_clean", metrics)
        self.assertIsNone(metrics["post_shake_priority_clean"])
        self.assertLess(metrics["resettle_max_shift"], 0.5)
