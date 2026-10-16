"""The cliff veto (``config.cliff_veto``, ``surface.cliff_veto``): in the
middle band of the phase a rung's pick that closes a cliff's worth of
usable surface beyond its own footprint yields to the first survivor of
its rung that closes less than half of it.

The board: the back half of the ULD full of tall soft cargo (no tops to
offer), a column at the right of the front strip, so the free floor is
one 1.05 x 0.6 m strip.  A 0.55 x 0.40 box laid in the middle of the
strip leaves two 0.25 m pieces, narrower than the 0.43 m window: it
closes the whole strip (0.22 of the floor beyond its footprint).  The
same box flush at the chamfer side leaves a 0.49 m piece and closes
only the floor in front of itself (0.07).
"""

from __future__ import annotations

import dataclasses
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_rule_alpha import ULD, make_container_dict  # noqa: E402

from rule_alpha import classify as cls  # noqa: E402
from rule_alpha import layer1, surface  # noqa: E402
from rule_alpha._reuse import AABB  # noqa: E402
from rule_alpha.config import DEFAULT_CONFIG  # noqa: E402

ON = dataclasses.replace(DEFAULT_CONFIG, cliff_veto=True)


def _profile(index, dims, soft=False):
    return cls.classify_item(
        index,
        {"index": index, "length": dims[0], "width": dims[1], "height": dims[2],
         "mass": 10.0, "is_soft": soft, "is_prioritized": False},
        DEFAULT_CONFIG,
    )


def _place(board, x, y, dims, soft=False):
    z = board.model(0).z_floor
    box = AABB((x, y, z + dims[2] / 2.0), dims, "packed")
    profile = _profile(0, dims, soft)
    board.apply(layer1.Placement(
        box=box, profile=profile, orientation=profile.orientations[0],
        container_idx=0, surface="floor", surface_name="floor",
        role=cls.ROLE_NONE, archetype=layer1.A_MAX_FOOTPRINT, reason="test fixture",
        layer=layer1.stack_level(box, board.container(0), cls.ROLE_NONE, DEFAULT_CONFIG),
    ))


def _candidate(board, x, y, dims=(0.55, 0.40, 0.24), index=9):
    z = board.model(0).z_floor
    box = AABB((x, y, z + dims[2] / 2.0), dims, "candidate")
    profile = _profile(index, dims)
    return layer1.Candidate(
        box=box, profile=profile, orientation=profile.orientations[0],
        container_idx=0, surface="floor", surface_name="floor", role=cls.ROLE_NONE,
    )


def _strip_board():
    board = layer1.Board([make_container_dict(index=0, **ULD)], DEFAULT_CONFIG)
    for x in (-0.25, 0.30, 0.80):
        _place(board, x, 0.30, (0.50, 0.75, 1.2), soft=True)
    _place(board, 0.732, -0.40, (0.42, 0.60, 1.2), soft=True)
    return board


class ClosedShareTest(unittest.TestCase):
    def test_the_middle_pose_closes_the_strip_and_the_side_pose_its_front(self):
        board = _strip_board()
        scorer = surface.SurfaceScorer(DEFAULT_CONFIG)
        load = scorer.load(board, 0)
        base = scorer.mask(load)
        mid = _candidate(board, -0.005, -0.40)
        side = _candidate(board, -0.245, -0.40)
        c_mid = surface.closed_share(scorer, load, base, mid.box)
        c_side = surface.closed_share(scorer, load, base, side.box)
        self.assertGreater(c_mid, 0.18, f"the middle pose closes the strip: {c_mid:.3f}")
        self.assertLess(c_side, 0.09, f"the side pose closes its front only: {c_side:.3f}")
        self.assertLess(c_side, 0.5 * c_mid)
        # the band: the strip is a third of the floor
        ratio = surface.usable_surface_ratio(board, 0)
        self.assertTrue(0.25 <= ratio <= 0.6, ratio)


class CliffVetoTest(unittest.TestCase):
    def test_the_cliff_pick_yields_to_the_survivor_that_halves_it(self):
        board = _strip_board()
        mid = _candidate(board, -0.005, -0.40)
        side = _candidate(board, -0.245, -0.40)
        stats = {}
        picked = surface.cliff_veto(mid, layer1.A_MAX_FOOTPRINT, [mid, side], board, 0, ON, stats)
        self.assertIsNotNone(picked)
        self.assertIs(picked[0], side)
        self.assertEqual(picked[1], f"cliff/{layer1.A_MAX_FOOTPRINT}")
        self.assertEqual(stats["checks"], 1)
        self.assertEqual(stats["cliffs"], 1)
        self.assertEqual(stats["fired"], 1)
        self.assertEqual(stats[f"fired_{layer1.A_MAX_FOOTPRINT}"], 1)
        self.assertGreater(stats["seconds"], 0.0)

    def test_the_pick_stands_when_it_is_no_cliff(self):
        board = _strip_board()
        mid = _candidate(board, -0.005, -0.40)
        side = _candidate(board, -0.245, -0.40)
        stats = {}
        self.assertIsNone(surface.cliff_veto(side, layer1.A_MAX_FOOTPRINT, [side, mid], board, 0, ON, stats))
        self.assertEqual(stats["checks"], 1)
        self.assertNotIn("cliffs", stats)
        self.assertNotIn("fired", stats)

    def test_the_first_survivor_in_the_rungs_order_that_halves_it_is_taken(self):
        board = _strip_board()
        mid = _candidate(board, -0.005, -0.40)
        mid2 = _candidate(board, 0.0, -0.40, index=10)
        side = _candidate(board, -0.245, -0.40, index=11)
        side_front = _candidate(board, -0.245, -0.50, index=12)
        picked = surface.cliff_veto(mid, layer1.A_MAX_FOOTPRINT, [mid, mid2, side, side_front], board, 0, ON)
        self.assertIs(picked[0], side, "the second middle pose is a cliff too; the first side pose is taken")

    def test_the_threshold_the_k_and_the_budget_hold_the_pick(self):
        board = _strip_board()
        mid = _candidate(board, -0.005, -0.40)
        side = _candidate(board, -0.245, -0.40)
        high = dataclasses.replace(ON, cliff_veto_close=0.5)
        self.assertIsNone(surface.cliff_veto(mid, layer1.A_MAX_FOOTPRINT, [mid, side], board, 0, high))
        one = dataclasses.replace(ON, cliff_veto_k=1)
        self.assertIsNone(surface.cliff_veto(mid, layer1.A_MAX_FOOTPRINT, [mid, side], board, 0, one))
        stats = {}
        none = dataclasses.replace(ON, cliff_veto_seconds=0.0)
        self.assertIsNone(surface.cliff_veto(mid, layer1.A_MAX_FOOTPRINT, [mid, side], board, 0, none, stats))
        self.assertEqual(stats.get("timeouts"), 1)
        self.assertNotIn("fired", stats)


class LadderWiringTest(unittest.TestCase):
    """``choose_for_item`` asks the veto only with the switch on and the
    container in the band the agent read (``board.cliff_band``)."""

    def _calls(self, config, board):
        profile = _profile(9, (0.55, 0.40, 0.24))
        calls = []
        real = surface.cliff_veto

        def spy(chosen, archetype, ordered, b, ci, cfg, stats=None):
            calls.append((archetype, len(ordered), stats))
            return real(chosen, archetype, ordered, b, ci, cfg, stats)

        surface.cliff_veto = spy
        try:
            decision = layer1.choose_for_item(board, profile, config)
        finally:
            surface.cliff_veto = real
        return decision, calls

    def test_the_veto_runs_in_the_band_and_not_outside_it(self):
        board = _strip_board()
        board.cliff_band = frozenset({0})
        board.cliff_stats = {}
        decision, calls = self._calls(ON, board)
        self.assertIsNotNone(decision)
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][2], board.cliff_stats)
        self.assertEqual(board.cliff_stats.get("checks"), 1)
        # outside the band: never asked
        board = _strip_board()
        board.cliff_band = frozenset()
        _decision, calls = self._calls(ON, board)
        self.assertEqual(calls, [])
        # the switch off: never asked, band or not
        board = _strip_board()
        board.cliff_band = frozenset({0})
        _decision, calls = self._calls(DEFAULT_CONFIG, board)
        self.assertEqual(calls, [])


class AgentBandTest(unittest.TestCase):
    def test_the_agent_reads_the_band_once_a_call(self):
        from rule_alpha.agent import RuleAlphaAgent

        agent = RuleAlphaAgent(config=ON)
        agent.board = _strip_board()
        band = agent._cliff_band()
        self.assertEqual(band, frozenset({0}), "the strip is a third of the floor: in the band")
        self.assertEqual(agent.cliff_stats["reads"], 1)
        self.assertEqual(agent.cliff_stats["band_steps"], 1)
        # the band's bounds
        agent = RuleAlphaAgent(config=dataclasses.replace(ON, cliff_veto_high=0.3))
        agent.board = _strip_board()
        self.assertEqual(agent._cliff_band(), frozenset())
        self.assertNotIn("band_steps", agent.cliff_stats)
        agent = RuleAlphaAgent(config=dataclasses.replace(ON, cliff_veto_low=0.4))
        agent.board = _strip_board()
        self.assertEqual(agent._cliff_band(), frozenset())
        # an open floor is above the band
        agent = RuleAlphaAgent(config=ON)
        agent.board = layer1.Board([make_container_dict(index=0, **ULD)], DEFAULT_CONFIG)
        self.assertEqual(agent._cliff_band(), frozenset())


if __name__ == "__main__":
    unittest.main()
