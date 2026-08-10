from __future__ import annotations

import unittest

from scripts.summarize_residual_diversity_matrix import summarize_matrix


def scenario_summary(
    *,
    case_id: str,
    containers: int,
    shelves: int,
    verdict: str = "pass",
    positive: int = 12,
    negative: int = 3,
) -> dict:
    return {
        "dataset_id": f"dataset-{case_id}",
        "case_id": case_id,
        "sampling_mode": "residual_diversity_safe_split",
        "status": "complete",
        "scenario_context": {
            "container_count": containers,
            "shelf_count": shelves,
            "shelf_pattern": [False] * (containers - shelves)
            + [True] * shelves,
            "priority_container_count": 0,
            "initial_preloaded_count": 0,
        },
        "steps_measured": 3,
        "mean_physical_nn_distance_delta": 0.02,
        "acceptance": {"verdict": verdict, "failed_guards": []},
        "steps": [
            {
                "step": 3,
                "positive_transition": positive,
                "negative_physical_risk": negative,
            }
        ],
    }


class ResidualDiversityMatrixSummaryTests(unittest.TestCase):
    def test_reports_condition_coverage_and_label_balance_without_pooling(self):
        summaries = [
            scenario_summary(
                case_id="m-single-empty-noshelf", containers=1, shelves=0
            ),
            scenario_summary(
                case_id="m-single-empty-shelf", containers=1, shelves=1
            ),
            scenario_summary(
                case_id="m-dual-empty", containers=2, shelves=0
            ),
            scenario_summary(
                case_id="m-dual-shelf-mixed", containers=2, shelves=1
            ),
        ]

        result = summarize_matrix(summaries)

        self.assertEqual(result["scenario_count"], 4)
        self.assertEqual(result["condition_coverage"]["container_counts"], [1, 2])
        self.assertEqual(result["condition_coverage"]["shelf_counts"], [0, 1])
        self.assertTrue(result["condition_coverage"]["core_2x2_complete"])
        self.assertEqual(result["labels"]["positive_transition"], 48)
        self.assertEqual(result["labels"]["negative_physical_risk"], 12)
        self.assertEqual(result["acceptance"]["verdict"], "pass")

    def test_one_failed_scenario_is_not_hidden_by_the_aggregate(self):
        summaries = [
            scenario_summary(
                case_id="m-single-empty-noshelf", containers=1, shelves=0
            ),
            scenario_summary(
                case_id="m-single-empty-shelf",
                containers=1,
                shelves=1,
                verdict="fail",
            ),
            scenario_summary(case_id="m-dual-empty", containers=2, shelves=0),
            scenario_summary(
                case_id="m-dual-shelf-mixed", containers=2, shelves=1
            ),
        ]

        result = summarize_matrix(summaries)

        self.assertEqual(result["acceptance"]["verdict"], "fail")
        self.assertEqual(
            result["acceptance"]["failed_scenarios"],
            ["m-single-empty-shelf"],
        )


if __name__ == "__main__":
    unittest.main()
