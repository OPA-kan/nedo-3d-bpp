import pathlib
import subprocess
import sys
import unittest

from scripts.evaluate_self_play_component_value_shadow import (
    analyze_row,
    dominance,
)


def _estimate(
    fill, placed, soft, covered=0.0, misrouted=0.0, cog=0.5,
    surface=0.0, std=0.0,
):
    values = {
        "fill": fill,
        "placed_gate": placed,
        "soft_violation": soft,
        "priority_covered": covered,
        "priority_misrouted": misrouted,
        "center_of_mass_z": cog,
        "surface_total_variation": surface,
    }
    return {
        "components": {
            name: {"mean": value, "std": std, "samples": 3, "values": [value] * 3}
            for name, value in values.items()
        }
    }


class ComponentValueShadowTests(unittest.TestCase):
    def test_script_can_be_invoked_by_path(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/evaluate_self_play_component_value_shadow.py",
                "--help",
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_confidence_dominance_requires_every_axis_nonworse(self):
        incumbent = _estimate(5.0, 4.0, 1.0)
        clean_gain = _estimate(6.0, 4.0, 0.0)
        soft_tradeoff = _estimate(7.0, 4.0, 2.0)

        self.assertTrue(dominance(clean_gain, incumbent, beta=0.0)["dominates"])
        self.assertFalse(
            dominance(soft_tradeoff, incumbent, beta=0.0)["dominates"]
        )

    def test_uncertainty_can_block_mean_dominance(self):
        incumbent = _estimate(5.0, 4.0, 0.0, std=0.5)
        candidate = _estimate(5.2, 4.2, 0.0, std=0.5)

        self.assertTrue(dominance(candidate, incumbent, beta=0.0)["dominates"])
        self.assertFalse(dominance(candidate, incumbent, beta=1.0)["dominates"])

    def test_placed_is_a_gate_not_an_official_improvement(self):
        incumbent = _estimate(5.0, 4.0, 0.0)
        more_placed_only = _estimate(5.0, 10.0, 0.0)

        result = dominance(more_placed_only, incumbent, beta=0.0)

        self.assertFalse(result["dominates"])
        self.assertEqual(result["axes"]["placed_gate"]["role"], "gate")

    def test_fill_cog_tradeoff_is_incomparable(self):
        incumbent = _estimate(5.0, 4.0, 0.0, cog=0.5)
        more_fill_higher_cog = _estimate(6.0, 4.0, 0.0, cog=0.7)

        self.assertFalse(
            dominance(more_fill_higher_cog, incumbent, beta=0.0)["dominates"]
        )

    def test_row_selects_only_a_component_dominator(self):
        row = {
            "policy_target": [
                {"candidate_id": "a", "visits": 8, "search_q": 0.0, "rank": 0},
                {"candidate_id": "b", "visits": 4, "search_q": 0.0, "rank": 1},
            ],
            "bounded_branch_outcomes": [
                self._branch("a", "a"), self._branch("b", "b")
            ],
        }

        def predict(state, _game):
            gain = 2.0 if state["tag"] == "b" else 0.0
            clean = -1.0 if state["tag"] == "b" else 0.0
            return {
                "fill_return": {"members": [gain] * 3},
                "placed_return": {"members": [0.0] * 3},
                "soft_violation_return": {"members": [clean] * 3},
                "priority_covered_return": {"members": [0.0] * 3},
                "priority_misrouted_return": {"members": [0.0] * 3},
                "center_of_mass_z_return": {"members": [0.0] * 3},
                "surface_total_variation_return": {"members": [0.0] * 3},
            }

        result = analyze_row(row, predict, ensemble_size=3, beta=0.0)

        self.assertTrue(result["changed"])
        self.assertEqual(result["selected_candidate_id"], "b")

    @staticmethod
    def _branch(candidate_id, tag):
        heads = {}
        for name in (
            "fill_gain", "placed_gain", "soft_violation_gain",
            "priority_covered_gain", "priority_misrouted_gain",
            "center_of_mass_z_delta", "surface_total_variation_delta",
        ):
            heads[name] = {"value": 0.0, "target_eligible": True}
        return {
            "root_candidate_id": candidate_id,
            "continuation_censored": False,
            "termination": "horizon",
            "leaf_state": {"tag": tag},
            "leaf_game_state": {},
            "heads": heads,
        }


if __name__ == "__main__":
    unittest.main()
