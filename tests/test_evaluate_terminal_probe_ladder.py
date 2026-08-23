import unittest

from scripts.evaluate_terminal_probe_ladder import (
    LADDER_HEADS,
    V_SUFFIX_HEADS,
    evaluate,
)


def metrics(fill):
    return {
        "fill_score_proxy": fill,
        "placed_count": 0.0,
        "soft_covered_by_other": 0.0,
        "priority_covered_by_other": 0.0,
        "priority_misrouted": 0.0,
        "surface_total_variation": 0.0,
        "center_of_mass_z": 0.0,
    }


def probe_row(candidate, *, fill_step, fill_suffix, genuine=True):
    return {
        "candidate_set_id": "set-1",
        "root_candidate_id": candidate,
        "genuine_terminal": genuine,
        "root_metrics": metrics(0.0),
        "after_action_metrics": metrics(fill_step),
        "terminal_metrics": metrics(fill_step + fill_suffix),
    }


def arm_root(samples):
    return {"set-1": {
        "step": 0, "candidate_set_id": "set-1",
        "samples": samples, "simulations": len(samples), "horizon": 1,
    }}


def arm_sample(candidate, world, *, fill, predicted_fill=None):
    sample = {
        "root_candidate_id": candidate,
        "exogenous_world_id": f"world-{world}",
        "raw_outcome_vector": {"fill_gain": fill},
        "head_eligibility": {"fill_gain": True},
    }
    if predicted_fill is not None:
        sample["predicted_leaf_value"] = {
            "ensemble_size": 2,
            "heads": {
                suffix: {
                    "mean": predicted_fill if suffix == "fill_return" else 0.0,
                    "members": [
                        predicted_fill if suffix == "fill_return" else 0.0
                    ] * 2,
                }
                for suffix in V_SUFFIX_HEADS.values()
            },
        }
    return sample


class EvaluateTerminalProbeLadderTests(unittest.TestCase):
    def test_ladder_detects_terminal_order_reversal(self):
        # Bounded step says a > b, but the realized terminal says b > a.
        probe = [
            probe_row("a", fill_step=3.0, fill_suffix=1.0),
            probe_row("b", fill_step=1.0, fill_suffix=9.0),
        ]
        h1 = arm_root([
            arm_sample("a", 0, fill=3.0), arm_sample("b", 0, fill=1.0),
        ])

        report = evaluate(probe, h1, h1)

        tau = report["depth_ladder_tau"]["h1_vs_terminal"]["fill"]
        self.assertEqual(tau["mean"], -1.0)
        self.assertEqual(report["roots_with_terminal_pairs"], 1)

    def test_v_within_root_scores_prediction_against_realized_suffix(self):
        probe = [
            probe_row("a", fill_step=1.0, fill_suffix=5.0),
            probe_row("b", fill_step=1.0, fill_suffix=2.0),
        ]
        h1 = arm_root([
            arm_sample("a", 0, fill=1.0, predicted_fill=4.5),
            arm_sample("b", 0, fill=1.0, predicted_fill=2.5),
        ])

        report = evaluate(probe, h1, {})

        fill = report["v_within_root"]["fill"]
        self.assertEqual(fill["tau_mean"], 1.0)
        self.assertEqual(fill["pairwise_accuracy"], 1.0)

    def test_censored_probes_never_enter_the_reference(self):
        probe = [
            probe_row("a", fill_step=1.0, fill_suffix=5.0),
            probe_row("b", fill_step=2.0, fill_suffix=1.0, genuine=False),
        ]
        h1 = arm_root([
            arm_sample("a", 0, fill=1.0), arm_sample("b", 0, fill=2.0),
        ])

        report = evaluate(probe, h1, h1)

        self.assertEqual(report["roots_with_terminal_pairs"], 0)
        self.assertEqual(report["roots_censored"], 1)
        self.assertEqual(report["depth_ladder_tau"]["h1_vs_terminal"], {})


if __name__ == "__main__":
    unittest.main()
