import unittest

from scripts.vector_search import confidence_pareto_frontier, paired_dominance


def sample(candidate, world, *, fill, soft, eligible=True):
    return {
        "root_candidate_id": candidate,
        "exogenous_world_id": f"world-{world}",
        "raw_outcome_vector": {"fill": fill, "soft": soft},
        "head_eligibility": {"fill": eligible, "soft": eligible},
    }


class VectorSearchTests(unittest.TestCase):
    def test_paired_dominance_uses_joint_same_world_events(self):
        rows = []
        for world in range(20):
            rows.extend([
                sample("a", world, fill=10 + world, soft=0),
                sample("b", world, fill=9 + world, soft=1),
            ])

        result = paired_dominance(
            rows, candidate_id="a", incumbent_id="b",
            objectives={"fill": "maximize", "soft": "minimize"},
        )

        self.assertEqual(result["paired_worlds"], 20)
        self.assertEqual(result["joint_nonworse_count"], 20)
        self.assertEqual(result["joint_strict_count"], 20)
        self.assertEqual(result["dominance_probability"], 1.0)
        self.assertGreater(result["dominance_probability_lcb"], 0.8)

    def test_ineligible_or_unpaired_worlds_are_not_fabricated(self):
        rows = [
            sample("a", 0, fill=2, soft=0),
            sample("b", 0, fill=1, soft=1),
            sample("a", 1, fill=2, soft=0),
            sample("b", 1, fill=1, soft=1, eligible=False),
            sample("a", 2, fill=2, soft=0),
        ]

        result = paired_dominance(
            rows, candidate_id="a", incumbent_id="b",
            objectives={"fill": "maximize", "soft": "minimize"},
        )

        self.assertEqual(result["paired_worlds"], 1)
        self.assertEqual(result["excluded_worlds"], 2)

    def test_confidence_frontier_removes_only_confidently_dominated_action(self):
        rows = []
        for world in range(30):
            rows.extend([
                sample("a", world, fill=10, soft=0),
                sample("b", world, fill=9, soft=1),
                sample("c", world, fill=11, soft=2),
            ])

        result = confidence_pareto_frontier(
            rows,
            objectives={"fill": "maximize", "soft": "minimize"},
            minimum_pairs=20, minimum_probability_lcb=0.8,
        )

        self.assertEqual(result["frontier_candidate_ids"], ["a", "c"])
        self.assertEqual(result["dominated_candidate_ids"], ["b"])
        self.assertEqual(result["dominated_by"]["b"], ["a"])


if __name__ == "__main__":
    unittest.main()
