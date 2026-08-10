import unittest

from scripts.summarize_residual_diversity_pilot import summarize_manifest


def coverage(mean_distance, cells, settled=4, safe=4):
    return {
        "sampled": 4,
        "mean_nearest_neighbor_distance": mean_distance,
        "minimum_nearest_neighbor_distance": mean_distance / 2,
        "unique_items": 3,
        "unique_item_orientations": 4,
        "spatial_cell_count": cells,
        "replayed": 4,
        "settled": settled,
        "valid": settled,
        "placed_safe": safe,
    }


class ResidualDiversityPilotSummaryTests(unittest.TestCase):
    def test_summary_keeps_proxy_and_physical_evidence_separate(self):
        payload = {
            "status": "complete",
            "dataset_id": "pilot",
            "case": {
                "steps": [
                    {
                        "step": 3,
                        "status": "ok",
                        "sampling": {
                            "coverage_comparison": {
                                "stratified_random": coverage(0.1, 2),
                                "residual_diversity": coverage(0.3, 4),
                                "diversity_minus_random": {
                                    "mean_nearest_neighbor_distance": 0.2,
                                    "spatial_cell_count": 2,
                                },
                            },
                            "physical_coverage_comparison": {
                                "stratified_random": coverage(0.08, 2),
                                "residual_diversity": coverage(0.20, 3),
                                "diversity_minus_random": {
                                    "mean_nearest_neighbor_distance": 0.12,
                                    "spatial_cell_count": 1,
                                    "unique_items": 0,
                                    "unique_item_orientations": 0,
                                    "settled": 0,
                                    "placed_safe": 0,
                                },
                            },
                        },
                    }
                ]
            },
        }

        summary = summarize_manifest(payload)

        self.assertEqual(summary["steps_measured"], 1)
        self.assertEqual(summary["steps_with_physical_gain"], 1)
        self.assertAlmostEqual(
            summary["mean_physical_nn_distance_delta"], 0.12
        )
        self.assertAlmostEqual(
            summary["steps"][0]["proxy_nn_distance_delta"], 0.2
        )
        self.assertAlmostEqual(
            summary["steps"][0]["physical_nn_distance_delta"], 0.12
        )
        self.assertEqual(summary["acceptance"]["verdict"], "pass")

    def test_acceptance_fails_when_semantic_or_safety_guard_regresses(self):
        physical = {
            "stratified_random": coverage(0.08, 2),
            "residual_diversity": coverage(0.20, 3),
            "diversity_minus_random": {
                "mean_nearest_neighbor_distance": 0.12,
                "spatial_cell_count": 1,
                "unique_items": -1,
                "unique_item_orientations": 0,
                "settled": 0,
                "placed_safe": -1,
            },
        }
        payload = {
            "status": "complete",
            "dataset_id": "guard-failure",
            "case": {
                "steps": [
                    {
                        "step": 9,
                        "status": "ok",
                        "sampling": {
                            "coverage_comparison": physical,
                            "physical_coverage_comparison": physical,
                        },
                    }
                ]
            },
        }

        summary = summarize_manifest(payload)

        self.assertEqual(summary["acceptance"]["verdict"], "fail")
        self.assertIn("unique_items", summary["acceptance"]["failed_guards"])
        self.assertIn("placed_safe", summary["acceptance"]["failed_guards"])

    def test_missing_physical_comparison_is_not_success(self):
        payload = {
            "status": "complete",
            "case": {
                "steps": [
                    {
                        "step": 3,
                        "status": "ok",
                        "sampling": {"coverage_comparison": {}},
                    }
                ]
            },
        }

        with self.assertRaisesRegex(ValueError, "physical coverage"):
            summarize_manifest(payload)
