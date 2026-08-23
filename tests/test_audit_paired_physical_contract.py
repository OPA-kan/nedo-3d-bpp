import unittest

from scripts.audit_paired_physical_contract import (
    PARETO_OBJECTIVES,
    audit_manifest,
)


def branch_sample(candidate, replica, *, fill=1.0, candidate_set="set-1"):
    return {
        "schema_version": 2,
        "root_candidate_id": candidate,
        "candidate_set_id": candidate_set,
        "exogenous_world_id": f"world-{replica}",
        "exogenous_world_sample_index": replica,
        "exogenous_world": {"contract_version": 1, "sample_index": replica},
        "raw_outcome_vector": {
            name: fill if name == "fill_gain" else 0.0
            for name in PARETO_OBJECTIVES
        },
        "head_eligibility": {name: True for name in PARETO_OBJECTIVES},
    }


def search_record(samples, candidates, *, simulations):
    return {
        "step": 0,
        "selection": {"rank": 0},
        "search": {
            "root_allocation_mode": "paired_round_robin",
            "policy_target_eligible": False,
            "policy_target": [],
            "execution_policy": "baseline_rank0_not_search_improvement",
            "root_dirichlet_alpha": 0.0,
            "root_dirichlet_epsilon": 0.0,
            "root_dirichlet_noise": None,
            "simulations": simulations,
            "candidate_set_id": "set-1",
            "candidate_outcome_summaries": [
                {"candidate_id": candidate} for candidate in candidates
            ],
            "multi_head_branch_samples": samples,
        },
    }


def manifest(records):
    return {
        "case_id": "unit-case",
        "policy_generation": "pi0-paired0",
        "selection": {"mcts": {"root_allocation_mode": "paired_round_robin"}},
        "games": [{"records": records}],
    }


class AuditPairedPhysicalContractTests(unittest.TestCase):
    def test_complete_paired_block_passes_and_reports_frontier(self):
        samples = [
            branch_sample(candidate, replica, fill=2.0 if candidate == "a" else 1.0)
            for replica in range(2)
            for candidate in ("a", "b")
        ]
        record = search_record(samples, ["a", "b"], simulations=4)

        report = audit_manifest(manifest([record]))

        self.assertTrue(report["passed"])
        self.assertEqual(report["searched_roots"], 1)
        root = report["roots"][0]
        self.assertEqual(root["replicas_per_candidate"], 2)
        self.assertEqual(root["distinct_worlds"], 2)
        self.assertEqual(root["violations"], [])
        self.assertIsNotNone(root["confidence_pareto"])

    def test_sibling_world_mismatch_is_a_violation(self):
        samples = [
            branch_sample("a", 0),
            {**branch_sample("b", 0), "exogenous_world_id": "world-other"},
        ]
        record = search_record(samples, ["a", "b"], simulations=2)

        report = audit_manifest(manifest([record]))

        self.assertFalse(report["passed"])
        self.assertTrue(any(
            "spans" in violation
            for violation in report["roots"][0]["violations"]
        ))

    def test_unequal_allocation_and_duplicates_are_violations(self):
        samples = [
            branch_sample("a", 0),
            branch_sample("a", 0),
            branch_sample("b", 0),
        ]
        record = search_record(samples, ["a", "b"], simulations=3)

        report = audit_manifest(manifest([record]))

        self.assertFalse(report["passed"])
        joined = " ".join(report["roots"][0]["violations"])
        self.assertIn("duplicate (candidate, world) cells", joined)
        self.assertIn("unequal per-candidate allocation", joined)

    def test_policy_target_leak_is_a_violation(self):
        samples = [branch_sample("a", 0), branch_sample("b", 0)]
        record = search_record(samples, ["a", "b"], simulations=2)
        record["search"]["policy_target"] = [{"candidate_id": "a"}]

        report = audit_manifest(manifest([record]))

        self.assertFalse(report["passed"])
        self.assertTrue(any(
            "policy target" in violation
            for violation in report["roots"][0]["violations"]
        ))

    def test_non_paired_manifest_is_rejected(self):
        bad = manifest([])
        bad["selection"]["mcts"]["root_allocation_mode"] = "scalar_puct"

        with self.assertRaises(ValueError):
            audit_manifest(bad)


if __name__ == "__main__":
    unittest.main()
