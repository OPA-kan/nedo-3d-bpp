import copy
import unittest

from scripts.league import (
    match,
    new_registry,
    paired_relation,
    promote,
    promotion_decision,
)


def heads(**overrides):
    base = {
        "placed_count": 15.0,
        "fill_score_proxy": 12.0,
        "soft_covered_by_other": 0.0,
        "priority_covered_by_other": 0.0,
        "priority_misrouted": 0.0,
        "center_of_mass_z": 0.7,
        "post_shake_max_shift": 0.05,
        "post_shake_items_toppled": 0.0,
    }
    base.update(overrides)
    return base


def outcome(cell, **overrides):
    return {
        "case_id": f"case-{cell}",
        "environment_seed": 42,
        "policy": "legacy",
        "steps": 15,
        "termination": "stream_exhausted",
        "genuine_termination": True,
        "heads": heads(**overrides),
    }


def arm(cells, per_cell_overrides=None):
    per_cell_overrides = per_cell_overrides or {}
    return {
        cell: outcome(cell, **per_cell_overrides.get(cell, {}))
        for cell in cells
    }


CELLS = [f"cell-{index}" for index in range(10)]


class LeagueTests(unittest.TestCase):
    def test_paired_relation_orientation(self):
        self.assertEqual(
            paired_relation(heads(fill_score_proxy=12.5), heads()),
            "challenger_wins",
        )
        self.assertEqual(
            paired_relation(heads(), heads(soft_covered_by_other=1.0)),
            "challenger_wins",
        )
        self.assertEqual(
            paired_relation(
                heads(fill_score_proxy=12.5, soft_covered_by_other=1.0),
                heads(),
            ),
            "incomparable",
        )
        self.assertEqual(paired_relation(heads(), heads()), "equal")

    def test_promotion_needs_more_wins_than_losses(self):
        registry = new_registry("pi0", arm(CELLS), source="run-0")
        # challenger wins 1 cell, everything else identical -> promoted
        challenger = arm(CELLS, {"cell-0": {"fill_score_proxy": 13.0}})
        decision = promotion_decision(challenger, registry)
        self.assertTrue(decision["promoted"])
        # pure trade-off everywhere (incomparable) -> not promoted
        challenger = arm(CELLS, {
            "cell-0": {"fill_score_proxy": 13.0, "center_of_mass_z": 0.8},
        })
        decision = promotion_decision(challenger, registry)
        self.assertFalse(decision["promoted"])
        self.assertIn(
            "wins 0 do not exceed losses 0",
            decision["main_gate"]["reasons"][0],
        )

    def test_champion_gate_blocks_aggregate_hard_regression(self):
        registry = new_registry("pi0", arm(CELLS), source="run-0")
        challenger = arm(CELLS, {
            "cell-0": {"fill_score_proxy": 14.0},
            "cell-1": {"fill_score_proxy": 14.0},
            # a new rule violation appears on one episode
            "cell-2": {"soft_covered_by_other": 1.0,
                       "fill_score_proxy": 14.0},
        })
        decision = promotion_decision(challenger, registry)
        self.assertFalse(decision["promoted"])
        self.assertTrue(any(
            "violations regress" in reason
            for reason in decision["main_gate"]["reasons"]
        ))

    def test_league_is_a_collapse_detector_not_a_per_episode_veto(self):
        # The pi5 scenario from design review: a single special-stream
        # trade-off against an old milestone must NOT block promotion
        # while the challenger clearly beats the champion.
        registry = new_registry("pi0", arm(CELLS), source="run-0")
        pi4 = arm(CELLS, {"cell-0": {"fill_score_proxy": 12.5}})
        registry = promote(registry, "pi4", pi4, source="run-4")
        # milestone member that was uniquely good on cell-9
        milestone = arm(CELLS, {"cell-9": {"center_of_mass_z": 0.55}})
        registry["members"].append({
            "name": "pi1", "role": "milestone", "generation": 1,
            "source": "run-1", "outcomes": milestone,
        })
        challenger = arm(CELLS, {
            "cell-0": {"fill_score_proxy": 13.5},
            "cell-1": {"fill_score_proxy": 13.5},
            "cell-2": {"fill_score_proxy": 13.5},
            # trade-off on pi1's special stream: better fill, worse CoG
            "cell-9": {"fill_score_proxy": 13.5, "center_of_mass_z": 0.75},
        })
        decision = promotion_decision(challenger, registry)
        self.assertTrue(decision["main_gate"]["passed"])
        self.assertFalse(decision["league_checks"]["pi1"]["collapsed"])
        self.assertTrue(decision["promoted"])

    def test_league_detects_catastrophic_collapse(self):
        registry = new_registry("pi0", arm(CELLS), source="run-0")
        pi4 = arm(CELLS, {"cell-0": {"fill_score_proxy": 12.5}})
        registry = promote(registry, "pi4", pi4, source="run-4")
        # beats pi4 on one cell but strictly loses to the anchor on five
        overrides = {"cell-0": {"fill_score_proxy": 13.0}}
        for index in range(1, 6):
            overrides[f"cell-{index}"] = {"fill_score_proxy": 11.0}
        challenger = arm(CELLS, overrides)
        decision = promotion_decision(challenger, registry)
        self.assertTrue(decision["league_checks"]["pi0"]["collapsed"])
        self.assertFalse(decision["promoted"])

    def test_promote_keeps_anchor_previous_and_milestones(self):
        registry = new_registry("pi0", arm(CELLS), source="run-0")
        for generation in (1, 2, 3, 4):
            registry = promote(
                registry, f"pi{generation}",
                arm(CELLS, {
                    "cell-0": {"fill_score_proxy": 12.0 + generation},
                }),
                source=f"run-{generation}",
            )
        roles = {m["name"]: m["role"] for m in registry["members"]}
        self.assertEqual(roles["pi0"], "anchor")
        self.assertEqual(roles["pi4"], "champion")
        self.assertEqual(roles["pi3"], "previous")
        # pi3 (generation 3) survives as milestone after pi5 arrives
        registry = promote(
            registry, "pi5",
            arm(CELLS, {"cell-0": {"fill_score_proxy": 18.0}}),
            source="run-5",
        )
        roles = {m["name"]: m["role"] for m in registry["members"]}
        self.assertEqual(roles["pi3"], "milestone")
        self.assertEqual(roles["pi4"], "previous")
        self.assertEqual(roles["pi5"], "champion")
        self.assertNotIn("pi1", roles)
        self.assertNotIn("pi2", roles)

    def test_match_rejects_mismatched_cells(self):
        with self.assertRaises(ValueError):
            match(arm(CELLS[:3]), arm(CELLS[:2]))


if __name__ == "__main__":
    unittest.main()
