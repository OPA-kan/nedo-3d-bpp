import unittest

from scripts import analyze_visible_pool_rollout as rollout


class VisiblePoolRolloutReportTests(unittest.TestCase):
    def test_top_k_forces_both_observed_divergence_actions(self):
        rows = [
            {
                "candidate_id": f"c{rank}",
                "q_active": float(10 - rank),
                "left_selected": rank == 4,
                "right_selected": rank == 5,
            }
            for rank in range(6)
        ]

        selected = rollout.selected_rollout_rows(rows, top_k=2)

        self.assertEqual(
            {row["candidate_id"] for row in selected},
            {"c0", "c1", "c4", "c5"},
        )


if __name__ == "__main__":
    unittest.main()
