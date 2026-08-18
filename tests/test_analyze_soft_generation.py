"""The offline predicate must be the agent's predicate.

`scripts/analyze_soft_generation.py` recomputes stack-aware soft
violations outside the agent, because computing them inside the
candidate loop would perturb the deadline-bound trajectory it measures.
That buys correctness of the experiment at the cost of a second
implementation of the rule, and a second implementation that drifts
makes the whole measurement meaningless while still producing
confident-looking numbers.

So these tests cross-check the offline function against
`agent.candidate_attribute_violations(..., stack_aware=True)` on
constructed geometries, rather than testing it against itself.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent.agent as agent  # noqa: E402
from scripts.analyze_soft_generation import (  # noqa: E402
    aabb_from_center_size,
    footprint_overlap,
    stack_soft_violations,
)
from tests.test_agent import sample_container, sample_item  # noqa: E402


def packed_from(container):
    """The offline packed-item form, from a container's packed items."""
    packed = []
    for item in container["packed_items"]:
        size = agent.get_rotated_dimensions(
            item["length"],
            item["width"],
            item["height"],
            item.get("orientation", 0),
        )
        center = item["pos"]
        half = [value / 2 for value in size]
        packed.append(
            {
                "bb": (
                    [center[i] - half[i] for i in range(3)],
                    [center[i] + half[i] for i in range(3)],
                ),
                "soft": bool(item.get("is_soft", False)),
            }
        )
    return packed


class OfflinePredicateMatchesTheAgentTests(unittest.TestCase):
    def _compare(self, mover, center, size, packed_items):
        container = sample_container(
            require_shelf=False, center_x=0.0, cut_x=0.0
        )
        container["packed_items"] = packed_items
        candidate = agent.AABB(tuple(center), tuple(size), "candidate")

        _, agent_soft = agent.candidate_attribute_violations(
            mover, candidate, container, stack_aware=True
        )
        offline_soft = stack_soft_violations(
            aabb_from_center_size(list(center), list(size)),
            packed_from(container),
            bool(mover.get("is_soft", False)),
        )
        self.assertEqual(
            offline_soft,
            agent_soft,
            f"offline {offline_soft} vs agent {agent_soft}",
        )
        return agent_soft

    def test_agrees_on_a_box_resting_directly_on_a_soft_item(self):
        packed = [
            dict(
                sample_item(1, is_soft=True),
                pos=[0.0, 0.0, 0.1],
                orientation=0,
            )
        ]
        self.assertEqual(
            self._compare(sample_item(2), (0.0, 0.0, 0.3), (0.3, 0.25, 0.2), packed),
            1,
        )

    def test_agrees_on_a_box_floating_well_above_a_soft_item(self):
        packed = [
            dict(
                sample_item(1, is_soft=True),
                pos=[0.0, 0.0, 0.1],
                orientation=0,
            )
        ]
        self.assertEqual(
            self._compare(sample_item(2), (0.0, 0.0, 0.9), (0.3, 0.25, 0.2), packed),
            1,
        )

    def test_agrees_when_the_mover_is_below(self):
        packed = [
            dict(
                sample_item(1, is_soft=True),
                pos=[0.0, 0.0, 0.9],
                orientation=0,
            )
        ]
        self.assertEqual(
            self._compare(sample_item(2), (0.0, 0.0, 0.2), (0.3, 0.25, 0.2), packed),
            0,
        )

    def test_agrees_when_footprints_do_not_overlap(self):
        packed = [
            dict(
                sample_item(1, is_soft=True),
                pos=[0.0, 0.0, 0.1],
                orientation=0,
            )
        ]
        self.assertEqual(
            self._compare(sample_item(2), (2.0, 2.0, 0.5), (0.3, 0.25, 0.2), packed),
            0,
        )

    def test_agrees_that_soft_on_soft_is_allowed(self):
        packed = [
            dict(
                sample_item(1, is_soft=True),
                pos=[0.0, 0.0, 0.1],
                orientation=0,
            )
        ]
        self.assertEqual(
            self._compare(
                sample_item(2, is_soft=True),
                (0.0, 0.0, 0.5),
                (0.3, 0.25, 0.2),
                packed,
            ),
            0,
        )

    def test_agrees_when_several_soft_items_are_covered(self):
        packed = [
            dict(
                sample_item(1, is_soft=True),
                pos=[-0.1, 0.0, 0.1],
                orientation=0,
            ),
            dict(
                sample_item(2, is_soft=True),
                pos=[0.1, 0.0, 0.1],
                orientation=0,
            ),
        ]
        self.assertEqual(
            self._compare(sample_item(3), (0.0, 0.0, 0.6), (0.5, 0.25, 0.2), packed),
            2,
        )


class GeometryHelperTests(unittest.TestCase):
    def test_footprint_overlap_is_zero_for_disjoint_boxes(self):
        a = ([0.0, 0.0, 0.0], [1.0, 1.0, 1.0])
        b = ([2.0, 2.0, 0.0], [3.0, 3.0, 1.0])

        self.assertEqual(footprint_overlap(a, b), 0.0)

    def test_footprint_overlap_is_the_shared_area(self):
        a = ([0.0, 0.0, 0.0], [2.0, 2.0, 1.0])
        b = ([1.0, 1.0, 0.0], [3.0, 4.0, 1.0])

        self.assertAlmostEqual(footprint_overlap(a, b), 1.0)


if __name__ == "__main__":
    unittest.main()
