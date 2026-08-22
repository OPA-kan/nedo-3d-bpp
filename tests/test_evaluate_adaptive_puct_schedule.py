import unittest

from scripts.evaluate_adaptive_puct_schedule import evaluate_adaptive_schedule


def _policy(q_top, visit_top):
    rows = []
    for index, name in enumerate(("a", "b", "c")):
        rows.append({
            "candidate_id": name,
            "rank": index,
            "q": 1.0 if name == q_top else 0.0,
            "visits": 10 if name == visit_top else 1,
            "probability": 10 / 12 if name == visit_top else 1 / 12,
        })
    return rows


def _condition(q_top, visit_top, *, rescue_limit=None, rescued=0):
    result = {
        "policy_target": _policy(q_top, visit_top),
        "candidate_exhaustion_shadow_summary": {
            "audited_nodes": 2,
            "wider_safe_recovered_nodes": 1,
        },
        "candidate_rescue_summary": {"applied_nodes": rescued},
    }
    if rescue_limit is not None:
        result["candidate_rescue_limit"] = rescue_limit
    return result


class AdaptivePuctScheduleTests(unittest.TestCase):
    def test_stops_after_budget_confirmation_when_root_top_is_stable(self):
        conditions = {
            label: _condition("a", "a")
            for label in (
                "h2-s24", "h2-s48", "h3-s48", "h5-s48"
            )
        }
        payload = {"complete": True, "roots": [{
            "root_id": "stable",
            "promoted": False,
            "conditions": conditions,
        }]}

        result = evaluate_adaptive_schedule([payload], expected_roots=1)

        row = result["roots"][0]
        self.assertEqual(row["selected_condition"], "h2-s48")
        self.assertEqual(row["stop_reason"], "budget_top_confirmed")
        self.assertTrue(row["q_top_matches_reference"])
        self.assertTrue(row["visit_top_matches_reference"])
        self.assertEqual(row["rollout_step_budget_upper_bound"], 144)

    def test_escalates_through_horizon_and_budget_when_top_keeps_reversing(self):
        conditions = {
            "h2-s24": _condition("a", "a"),
            "h2-s48": _condition("b", "b"),
            "h3-s48": _condition("c", "c"),
            "h5-s48": _condition("a", "a"),
            "h2-s96": _condition("b", "b"),
            "h3-s96": _condition("b", "b"),
            "h5-s96": _condition("b", "b"),
        }
        payload = {"complete": True, "roots": [{
            "root_id": "reversal",
            "promoted": True,
            "conditions": conditions,
        }]}

        result = evaluate_adaptive_schedule([payload], expected_roots=1)

        row = result["roots"][0]
        self.assertEqual(row["selected_condition"], "h5-s96")
        self.assertEqual(row["stop_reason"], "high_budget_reference")
        self.assertTrue(row["q_top_matches_reference"])
        self.assertEqual(result["selected_condition_counts"]["h5-s96"], 1)
        self.assertEqual(row["rollout_step_budget_upper_bound"], 1488)

    def test_rejects_incomplete_input(self):
        with self.assertRaisesRegex(ValueError, "incomplete"):
            evaluate_adaptive_schedule([{"complete": False, "roots": []}])

    def test_reports_aggressive_and_guarded_rules_separately(self):
        conditions = {
            "h2-s24": _condition("a", "a"),
            "h2-s48": _condition("a", "a"),
            "h3-s48": _condition("b", "b"),
            "h5-s48": _condition("b", "b"),
            "h2-s96": _condition("b", "b"),
            "h3-s96": _condition("b", "b"),
            "h5-s96": _condition("b", "b"),
        }
        payload = {"complete": True, "roots": [{
            "root_id": "horizon-reversal",
            "promoted": True,
            "conditions": conditions,
        }]}

        result = evaluate_adaptive_schedule([payload], expected_roots=1)

        comparison = result["rule_comparison"]
        self.assertEqual(
            comparison["aggressive_budget_top"]["both_top_matches_roots"], 0
        )
        self.assertEqual(
            comparison["horizon_top_confirmed"]["both_top_matches_roots"], 1
        )
        self.assertEqual(
            comparison["full_order_guarded"]["both_top_matches_roots"], 1
        )

    def test_caveat_distinguishes_searchable_rescue_from_shadow_audit(self):
        conditions = {
            label: _condition("a", "a", rescue_limit=64, rescued=2)
            for label in (
                "h2-s24", "h2-s48", "h3-s48", "h5-s48"
            )
        }
        payload = {"complete": True, "roots": [{
            "root_id": "rescued",
            "promoted": False,
            "conditions": conditions,
        }]}

        result = evaluate_adaptive_schedule([payload], expected_roots=1)

        self.assertEqual(result["reference_candidate_rescue_limits"], [64])
        self.assertEqual(result["reference_searchable_rescue_nodes"], 2)
        self.assertTrue(any(
            "conditional on that enlarged support" in caveat
            for caveat in result["caveats"]
        ))
        self.assertFalse(any(
            "shadow-only" in caveat for caveat in result["caveats"]
        ))


if __name__ == "__main__":
    unittest.main()
