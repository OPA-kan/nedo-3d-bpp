import unittest

from scripts.fast_afterstate_env import (
    AfterstateBoard,
    sealed_void_fraction,
)
from scripts.measure_anchor_recall import load_agent_module

AGENT = load_agent_module()


def container(packed=(), *, cut_x=0.0, shelf=False):
    return {
        "length": 2.0,
        "width": 1.4,
        "height": 1.6,
        "thickness": 0.04,
        "cut_x": cut_x,
        "cut_y": 0.0,
        "shelf": shelf,
        "packed_items": [
            {"pos": list(pos), "dims": list(dims)} for pos, dims in packed
        ],
    }


def board(*args, **kwargs):
    return AfterstateBoard(AGENT, container(*args, **kwargs))


class SealedVoidTests(unittest.TestCase):
    def test_an_empty_plain_container_seals_nothing(self):
        total, by_items = sealed_void_fraction(AGENT, board())
        self.assertAlmostEqual(total, 0.0)
        self.assertAlmostEqual(by_items, 0.0)

    def test_a_shelf_seals_volume_before_anything_is_packed(self):
        """
        The container's own geometry hides space. Reporting that as part of
        what the packing did would blame the policy for the shelf, which is
        why the two fractions are returned separately.
        """
        total, by_items = sealed_void_fraction(AGENT, board(cut_x=0.44))
        self.assertGreater(total, 0.02)
        self.assertAlmostEqual(by_items, 0.0)

    def test_a_column_resting_on_the_floor_seals_nothing(self):
        packed = [((0.0, 0.0, 0.2), (0.5, 0.4, 0.3))]
        _total, by_items = sealed_void_fraction(AGENT, board(packed))
        self.assertAlmostEqual(by_items, 0.0, places=3)

    def test_an_overhang_seals_the_space_beneath_it(self):
        # a slab floating high, with nothing under it
        packed = [((0.0, 0.0, 1.2), (0.6, 0.5, 0.2))]
        _total, by_items = sealed_void_fraction(AGENT, board(packed))
        self.assertGreater(by_items, 0.01)

    def test_it_is_not_the_heightmap_quantity(self):
        """
        The regression this exists for: computed from the heightmap,
        covered_void came out equal to headroom_deficit to machine
        precision, because a heightmap holds one number per column and
        cannot express an overhang at all. A board with a tall stack and a
        short one has a large headroom deficit and no sealed void.
        """
        packed = [
            ((-0.5, 0.0, 0.2), (0.5, 0.4, 0.3)),
            ((-0.5, 0.0, 0.6), (0.5, 0.4, 0.5)),
            ((0.6, 0.0, 0.15), (0.5, 0.4, 0.2)),
        ]
        state = board(packed)
        deficit = state.features()["headroom_deficit"]
        _total, by_items = sealed_void_fraction(AGENT, state)
        self.assertGreater(deficit, 0.1)
        self.assertLess(by_items, deficit / 2.0)

    def test_by_items_never_exceeds_the_total(self):
        packed = [((0.0, 0.0, 1.2), (0.6, 0.5, 0.2))]
        total, by_items = sealed_void_fraction(AGENT, board(packed, cut_x=0.44))
        self.assertLessEqual(by_items, total + 1e-9)


if __name__ == "__main__":
    unittest.main()
