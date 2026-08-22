import unittest

from scripts.compare_self_play_puct_rescue import compare_rescue


def _aggregate(
    *, q_top, visit_top, exhausted, stable, rescued=0, provider_zero=0,
):
    return {
        "root_count": 1,
        "reference_candidate_rescue_limits": [64] if rescued else [],
        "reference_censored_exhaustion_events": exhausted * 2,
        "reference_exhaustion_unique_nodes": exhausted,
        "bounded_q_top_stable_roots": int(stable),
        "bounded_visit_top_stable_roots": int(stable),
        "bounded_q_order_stable_roots": int(stable),
        "reference_candidate_rescue_summary": {
            "applied_nodes": rescued,
            "recovered_candidates": rescued,
        },
        "reference_provider_zero_rescue_limits": [64] if provider_zero else [],
        "reference_provider_zero_rescue_summary": {
            "applied_nodes": provider_zero,
            "recovered_candidates": provider_zero,
            "physical_checks": provider_zero,
        },
        "roots": [{
            "root_id": "root-a",
            "reference_signature": {
                "q_top": q_top,
                "visit_top": visit_top,
            },
            "bounded_q_top_stable": stable,
            "bounded_visit_top_stable": stable,
            "bounded_q_order_stable": stable,
        }],
    }


class ComparePuctRescueTests(unittest.TestCase):
    def test_reports_exhaustion_reduction_and_root_action_change(self):
        baseline = _aggregate(
            q_top="a", visit_top="a", exhausted=5, stable=False
        )
        rescue = _aggregate(
            q_top="b", visit_top="b", exhausted=2, stable=True, rescued=3
        )

        result = compare_rescue(baseline, rescue)

        self.assertEqual(result["matched_roots"], 1)
        self.assertEqual(result["censored_exhaustion_event_delta"], -6)
        self.assertEqual(result["unique_exhausted_node_delta"], -3)
        self.assertEqual(result["reference_q_top_changed_roots"], 1)
        self.assertEqual(result["reference_visit_top_changed_roots"], 1)
        self.assertEqual(result["bounded_q_top_stable_root_delta"], 1)
        self.assertEqual(result["searchable_rescue_nodes"], 3)

    def test_rejects_root_mismatch(self):
        baseline = _aggregate(
            q_top="a", visit_top="a", exhausted=1, stable=True
        )
        rescue = _aggregate(
            q_top="a", visit_top="a", exhausted=1, stable=True, rescued=1
        )
        rescue["roots"][0]["root_id"] = "other"

        with self.assertRaisesRegex(ValueError, "root sets differ"):
            compare_rescue(baseline, rescue)

    def test_accepts_lazy_provider_zero_rescue_without_adaptive_k_rescue(self):
        baseline = _aggregate(
            q_top="a", visit_top="a", exhausted=5, stable=False
        )
        rescue = _aggregate(
            q_top="a", visit_top="a", exhausted=2, stable=True,
            provider_zero=3,
        )

        result = compare_rescue(baseline, rescue)

        self.assertEqual(result["provider_zero_rescue_nodes"], 3)
        self.assertEqual(result["provider_zero_physical_checks"], 3)

    def test_rejects_a_fixed_top_k_run_mislabeled_as_rescue(self):
        baseline = _aggregate(
            q_top="a", visit_top="a", exhausted=1, stable=True
        )

        with self.assertRaisesRegex(ValueError, "positive candidate rescue"):
            compare_rescue(baseline, baseline)


if __name__ == "__main__":
    unittest.main()
