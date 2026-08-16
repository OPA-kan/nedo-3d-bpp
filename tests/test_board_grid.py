import unittest

from scripts.fast_afterstate_env import (
    AfterstateBoard,
    board_grid,
    largest_free_span,
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


class BoardGridTests(unittest.TestCase):
    def test_empty_board_is_all_zero(self):
        grid = board_grid(board())
        self.assertEqual(len(grid), 16)
        self.assertEqual(len(grid[0]), 12)
        self.assertEqual(max(max(row) for row in grid), 0.0)

    def test_a_packed_column_raises_exactly_its_cells(self):
        packed = [((0.0, 0.0, 0.4), (0.4, 0.4, 0.8))]
        grid = board_grid(board(packed))
        top = max(max(row) for row in grid)
        self.assertGreater(top, 0.4)  # 0.8 of a ~1.56 interior
        self.assertLess(top, 0.6)
        # The column occupies a small fraction of cells; corners stay 0.
        self.assertEqual(grid[0][0], 0.0)
        self.assertEqual(grid[15][11], 0.0)

    def test_max_pooling_keeps_the_tall_column(self):
        # A thin tall column must not be averaged away.
        packed = [((0.0, 0.0, 0.75), (0.1, 0.1, 1.5))]
        grid = board_grid(board(packed))
        self.assertGreater(max(max(row) for row in grid), 0.9)

    def test_grid_shape_is_configurable(self):
        grid = board_grid(board(), gx=4, gy=4)
        self.assertEqual((len(grid), len(grid[0])), (4, 4))


class LargestFreeSpanTests(unittest.TestCase):
    def test_empty_board_spans_almost_everything(self):
        self.assertGreater(largest_free_span(board()), 0.9)

    def test_a_wall_across_the_middle_halves_the_span(self):
        packed = [((0.0, 0.0, 0.2), (0.2, 1.4, 0.4))]
        span = largest_free_span(board(packed))
        self.assertLess(span, 0.55)
        self.assertGreater(span, 0.3)


if __name__ == "__main__":
    unittest.main()
