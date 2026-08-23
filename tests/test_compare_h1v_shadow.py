import unittest

from scripts.compare_h1v_shadow import (
    COMPOSITE_HEADS,
    compare_cell,
    summarize,
)

BRANCH_HEADS = [branch for branch, _s, _d in COMPOSITE_HEADS.values()]
SUFFIX_HEADS = [suffix for _b, suffix, _d in COMPOSITE_HEADS.values()]


def h2_sample(candidate, world, *, fill):
    return {
        "root_candidate_id": candidate,
        "exogenous_world_id": f"world-{world}",
        "raw_outcome_vector": {
            branch: fill if branch == "fill_gain" else 0.0
            for branch in BRANCH_HEADS
        },
        "head_eligibility": {branch: True for branch in BRANCH_HEADS},
    }


def h1v_sample(candidate, world, *, fill, suffix_fill, members=3):
    return {
        "root_candidate_id": candidate,
        "exogenous_world_id": f"world-{world}",
        "raw_outcome_vector": {
            branch: fill if branch == "fill_gain" else 0.0
            for branch in BRANCH_HEADS
        },
        "head_eligibility": {branch: True for branch in BRANCH_HEADS},
        "predicted_leaf_value": {
            "prediction_contract": "V_pi_behavior_leaf_bootstrap_v1",
            "ensemble_size": members,
            "heads": {
                suffix: {
                    "mean": suffix_fill if suffix == "fill_return" else 0.0,
                    "variance": 0.0,
                    "members": [
                        suffix_fill if suffix == "fill_return" else 0.0
                    ] * members,
                }
                for suffix in SUFFIX_HEADS
            },
        },
    }


def root(samples, *, simulations, horizon):
    return {
        "step": 0,
        "candidate_set_id": "set-1",
        "samples": samples,
        "simulations": simulations,
        "horizon": horizon,
    }


class CompareH1VShadowTests(unittest.TestCase):
    def test_agreeing_arms_report_full_recovery_at_half_budget(self):
        h2 = {
            "set-1": root([
                h2_sample("a", w, fill=3.0) for w in range(4)
            ] + [
                h2_sample("b", w, fill=1.0) for w in range(4)
            ], simulations=8, horizon=2),
        }
        h1v = {
            "set-1": root([
                h1v_sample("a", w, fill=1.5, suffix_fill=1.5)
                for w in range(4)
            ] + [
                h1v_sample("b", w, fill=0.5, suffix_fill=0.5)
                for w in range(4)
            ], simulations=8, horizon=1),
        }

        cell = compare_cell(h2, h1v, vote_threshold=3)
        summary = summarize({"cell": cell})

        self.assertEqual(cell["shared_roots"], 1)
        row = cell["roots"][0]
        self.assertEqual(row["relation_matches"], row["relation_pairs"])
        self.assertTrue(row["pareto_agree"])
        self.assertEqual(row["ordering_tau"]["fill"], 1.0)
        self.assertEqual(summary["dominance_relation_agreement"], 1.0)
        self.assertEqual(summary["dominated_recall"], 1.0)
        self.assertEqual(summary["physical_steps"], {"h2": 16, "h1v": 8})

    def test_split_vote_below_threshold_does_not_flag_dominance(self):
        h2 = {
            "set-1": root([
                h2_sample("a", 0, fill=3.0), h2_sample("b", 0, fill=1.0),
            ], simulations=2, horizon=2),
        }
        disagreeing = h1v_sample("a", 0, fill=0.5, suffix_fill=0.5)
        disagreeing["predicted_leaf_value"]["heads"]["fill_return"][
            "members"
        ] = [2.0, -5.0, -5.0]
        h1v = {
            "set-1": root([
                disagreeing, h1v_sample("b", 0, fill=0.4, suffix_fill=0.4),
            ], simulations=2, horizon=1),
        }

        cell = compare_cell(h2, h1v, vote_threshold=3)

        row = cell["roots"][0]
        self.assertEqual(row["h1v_dominated"], [])
        self.assertEqual(row["h2_dominated"], ["b"])
        self.assertFalse(row["pareto_agree"])

    def test_missing_roots_are_counted_not_fabricated(self):
        h2 = {
            "set-1": root(
                [h2_sample("a", 0, fill=1.0), h2_sample("b", 0, fill=0.5)],
                simulations=2, horizon=2,
            ),
            "set-2": root(
                [h2_sample("a", 0, fill=1.0), h2_sample("b", 0, fill=0.5)],
                simulations=2, horizon=2,
            ),
        }
        h1v = {
            "set-1": root(
                [
                    h1v_sample("a", 0, fill=0.5, suffix_fill=0.5),
                    h1v_sample("b", 0, fill=0.2, suffix_fill=0.2),
                ],
                simulations=2, horizon=1,
            ),
        }

        cell = compare_cell(h2, h1v, vote_threshold=3)

        self.assertEqual(cell["shared_roots"], 1)
        self.assertEqual(cell["h2_only_roots"], 1)
        self.assertEqual(cell["h1v_only_roots"], 0)


if __name__ == "__main__":
    unittest.main()
