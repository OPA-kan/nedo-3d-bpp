from __future__ import annotations

import unittest

import numpy as np

from scripts.build_slide_patches import (
    PATCH_CELLS,
    PATCH_DEPTH,
    canonical_patch,
    height_at,
)


FLOOR = (-1.0, 1.0, -0.7, 0.7, 0.04)


class HeightTests(unittest.TestCase):
    def test_height_prefers_tallest_covering_surface(self):
        surfaces = [FLOOR, (0.0, 0.4, -0.2, 0.2, 0.34)]
        self.assertAlmostEqual(height_at(surfaces, -0.5, 0.0), 0.04)
        self.assertAlmostEqual(height_at(surfaces, 0.2, 0.0), 0.34)


class PatchTests(unittest.TestCase):
    def test_flat_floor_patch_is_constant(self):
        patch = canonical_patch([FLOOR], 0.0, 0.0, (1.0, 0.0), 0.04)
        self.assertEqual(patch.shape, (PATCH_CELLS, PATCH_CELLS))
        np.testing.assert_allclose(patch, 0.0, atol=1e-9)

    def test_box_downhill_lands_in_late_rows_for_any_frame(self):
        # A box 0.2 m along +u from the item; the canonical patch must
        # place it in the late rows whichever world direction u is.
        for u, box in (
            ((1.0, 0.0), (0.15, 0.45, -0.1, 0.1, 0.34)),
            ((0.0, 1.0), (-0.1, 0.1, 0.15, 0.45, 0.34)),
        ):
            patch = canonical_patch([FLOOR, box], 0.0, 0.0, u, 0.04)
            first_half = patch[: PATCH_CELLS // 2].max()
            second_half = patch[PATCH_CELLS // 2:].max()
            self.assertAlmostEqual(second_half, 0.30, places=6)
            self.assertLess(first_half, 0.30)

    def test_mirror_scene_flips_transverse_axis(self):
        box = (-0.1, 0.1, 0.15, 0.45, 0.34)  # box toward +v for u=(1,0)
        mirrored = (-0.1, 0.1, -0.45, -0.15, 0.34)
        patch = canonical_patch([FLOOR, box], 0.0, 0.0, (1.0, 0.0), 0.04)
        patch_m = canonical_patch(
            [FLOOR, mirrored], 0.0, 0.0, (1.0, 0.0), 0.04
        )
        np.testing.assert_allclose(patch, patch_m[:, ::-1], atol=1e-9)

    def test_heights_clipped_to_patch_depth(self):
        tall = (-1.0, 1.0, -0.7, 0.7, 5.0)
        patch = canonical_patch([FLOOR, tall], 0.0, 0.0, (1.0, 0.0), 0.04)
        self.assertAlmostEqual(float(patch.max()), PATCH_DEPTH)


if __name__ == "__main__":
    unittest.main()
