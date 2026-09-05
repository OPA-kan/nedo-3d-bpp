"""The ladder's decision must not depend on noise below the geometry's tolerance.

The case is the one the bench traced on scene c-c1s-s0006: with one soft item
on the shelf, the second decision took three different values under 1e-8 m
changes of that item's recorded pose.  The shipped config keeps that
behaviour (it is what the negative control was measured on); the stable
config must not.
"""

from __future__ import annotations

import copy
import dataclasses
import unittest

from bench.arms import make_arm
from bench.scenes import make_scene
from rule_alpha import layer1
from rule_alpha.config import DEFAULT_CONFIG

EXACT = (0.819, 0.369, 1.035)
PERTURBATIONS = {
    "x+5.7e-9": (0.819 + 5.7e-9, 0.369, 1.035),
    "y-1.2e-8": (0.819, 0.369 - 1.2e-8, 1.035),
    "sim": (0.8190000057220459, 0.36899998784065247, 1.0233999661584852),
}
PACKED = {
    "index": 0, "length": 0.65, "width": 0.35, "height": 0.23, "mass": 12.0,
    "is_prioritized": False, "is_soft": True, "orientation": 5, "layer": 1,
    "belongs_to": 0, "dims": (0.23, 0.65, 0.35),
}


def _decide(arm, pos):
    scene = make_scene(6, "c1s", "C")
    containers = scene.rule_alpha_containers()
    c = copy.deepcopy(containers)
    c[0]["packed_items"] = [dict(PACKED, pos=pos)]
    agent = arm(scene)
    agent.get_init_states({"optimize": False, "lookahead_k": 1, "container_list": containers})
    agent.policy({"optimize": False, "lookahead_k": 1, "container_list": c,
                  "pool_list": [scene.items[1]]})
    placement = agent.last_decision.placement
    return (placement.orientation.index,
            tuple(round(float(v), 3) for v in placement.box.center))


class StabilityTests(unittest.TestCase):
    def test_shipped_ladder_is_noise_sensitive_here(self):
        arm = make_arm("ladder")
        decisions = {_decide(arm, EXACT)} | {_decide(arm, p) for p in PERTURBATIONS.values()}
        # documents the defect the bench found; if this ever passes with one
        # decision, the shipped ladder has changed and the control must be redone
        self.assertGreater(len(decisions), 1)

    def test_stable_ladder_ignores_sub_tolerance_noise(self):
        arm = make_arm("ladder-stable")
        base = _decide(arm, EXACT)
        for name, pos in PERTURBATIONS.items():
            self.assertEqual(_decide(arm, pos), base, name)

    def test_quantized_key_rounds_floats_only(self):
        key = (True, 3, -0.6941234, 0.0)
        self.assertEqual(layer1.quantized_key(key, 0.005), (True, 3, -0.695, 0.0))
        self.assertEqual(layer1.quantized_key(key, 0.0), key)

    def test_anchor_clamp_snaps_a_hair_outside_onto_the_bound(self):
        values = [0.7090000057, 0.5, 0.9]
        self.assertEqual(layer1._anchor_values(values, 0.0, 0.709 + 1e-9, 10),
                         [0.7090000057, 0.5])
        self.assertEqual(layer1._anchor_values(values, 0.0, 0.709 + 1e-9, 10, clamp=True),
                         [0.709 + 1e-9, 0.5])

    def test_compaction_may_not_slide_a_terrace_off_its_support(self):
        from rule_alpha import stability
        from rule_alpha._reuse import AABB

        scene = make_scene(1, "c1", "C")
        containers = scene.rule_alpha_containers()
        model_cfg = DEFAULT_CONFIG
        # one hard box on the floor, and a smaller box chosen fully on top of it
        # with 0.20 m of the support's depth still free behind it
        support = {"index": 0, "length": 0.75, "width": 0.56, "height": 0.27, "mass": 18.0,
                   "is_soft": False, "is_prioritized": False, "dims": (0.75, 0.56, 0.27),
                   "pos": (0.3, 0.0, 0.05 + 0.135)}
        c = copy.deepcopy(containers)
        c[0]["packed_items"] = [support]
        top = 0.05 + 0.27
        box = AABB((0.3, -0.10, top + 0.12), (0.55, 0.36, 0.24), "terrace")
        before = stability.evaluate(box, c[0], model_cfg)
        self.assertAlmostEqual(before.contact_area, 0.55 * 0.36, places=6)

        loose = dataclasses.replace(DEFAULT_CONFIG, compact_raised=True,
                                    compaction_keeps_support=False)
        strict = dataclasses.replace(DEFAULT_CONFIG, compact_raised=True,
                                     compaction_keeps_support=True)
        board_loose = layer1.Board(c, loose)
        board_strict = layer1.Board(c, strict)
        moved_loose = layer1.compact_backwards(box, board_loose, 0, "terrace", loose)
        moved_strict = layer1.compact_backwards(box, board_strict, 0, "terrace", strict)
        after_loose = stability.evaluate(moved_loose, c[0], loose)
        after_strict = stability.evaluate(moved_strict, c[0], strict)
        # the shipped slide hangs the box over the back edge down to the 3 cm margin
        self.assertLess(after_loose.contact_area, before.contact_area - 0.01)
        self.assertLess(after_loose.margin, 0.05)
        # the guarded slide keeps every square centimetre of support
        self.assertGreaterEqual(after_strict.contact_area, before.contact_area - 1e-9)
        self.assertGreaterEqual(after_strict.margin, before.margin - 1e-9)

    def test_defaults_are_off(self):
        self.assertEqual(DEFAULT_CONFIG.anchor_slack, 0.0)
        self.assertFalse(DEFAULT_CONFIG.anchor_clamp)
        self.assertFalse(DEFAULT_CONFIG.compaction_keeps_support)
        self.assertEqual(DEFAULT_CONFIG.key_quantum, 0.0)
        stable = make_arm("ladder-stable").config
        self.assertNotEqual(dataclasses.asdict(stable), dataclasses.asdict(DEFAULT_CONFIG))


if __name__ == "__main__":
    unittest.main()
