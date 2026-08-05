"""The transport reference planes are unconditional, by official ruling.

SIGNATE confirmed on 2026-08-04 that `resting_surfaces` and
`ceiling_surfaces` in `PlacementValidator.check_transport_path()` keep the
shelf-height planes even when `require_shelf` is False, because the left-ear
small shelf always exists and divides the space. The agent must mirror that
or its transport prediction diverges from the simulator.

These tests exist to stop a future reader from "fixing" the apparent
inconsistency by making the planes conditional. See
docs/COMPETITION_QA.md, section 搬入開始高さの基準面.
"""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("agent_module", ROOT / "agent" / "agent.py")
agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent)


def container(require_shelf: bool, cut_x: float = 0.0) -> dict:
    return {
        "index": 0,
        "length": 2.0,
        "width": 1.45,
        "height": 1.61,
        "thickness": 0.04,
        "buffer": 0.0,
        "cut_x": cut_x,
        "cut_y": 0.0,
        "require_shelf": require_shelf,
        "shelf": require_shelf,
        "packed_items": [],
    }


def start_height(candidate, box) -> float:
    """Lift actually used, recovered from the sweep the agent builds."""
    sweep = agent.transport_sweeps(candidate, box)[0]
    action_center = agent.simulator_action_center(candidate, box)
    return float(sweep.center[2]) - float(action_center[2])


class TransportPlaneContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.no_shelf = container(require_shelf=False)
        self.with_shelf = container(require_shelf=True)
        # 1.61 / 2 + 0.04 = 0.845, the shelf-top resting plane.
        self.plane = 1.61 / 2.0 + 0.04

    def item_resting_at(self, bottom_z: float) -> agent.AABB:
        size = (0.3, 0.3, 0.2)
        return agent.AABB(
            center=(0.0, 0.0, bottom_z + size[2] / 2.0),
            size=size,
            name="candidate",
        )

    def test_shelf_plane_suppresses_the_lift_without_a_shelf(self) -> None:
        """A bottom just above the shelf plane is a direct approach even
        when require_shelf is False. Officially confirmed, not a bug."""
        candidate = self.item_resting_at(self.plane + 0.01)
        self.assertAlmostEqual(start_height(candidate, self.no_shelf), 0.0)

    def test_the_same_pose_behaves_identically_with_a_shelf(self) -> None:
        candidate = self.item_resting_at(self.plane + 0.01)
        self.assertAlmostEqual(
            start_height(candidate, self.no_shelf),
            start_height(candidate, self.with_shelf),
        )

    def test_outside_the_band_the_official_drop_height_returns(self) -> None:
        """Beyond 50 mm above the plane the 80 mm lift applies again, which
        is what the official 'nudge the target Z by a few mm' advice buys."""
        candidate = self.item_resting_at(self.plane + 0.20)
        self.assertGreater(start_height(candidate, self.no_shelf), 0.0)

    def test_the_floor_plane_is_also_unconditional(self) -> None:
        candidate = self.item_resting_at(0.04 + 0.01)
        self.assertAlmostEqual(start_height(candidate, self.no_shelf), 0.0)

    def test_resting_planes_match_the_small_shelf_faces(self) -> None:
        """The official reason for the planes: the small shelf always
        exists. Its faces must therefore BE those planes."""
        box = container(require_shelf=False, cut_x=0.3)
        shelves = agent.shelf_aabbs(box)
        names = {shelf.name for shelf in shelves}
        self.assertIn("small_shelf", names)
        self.assertNotIn("main_shelf", names)
        small = next(s for s in shelves if s.name == "small_shelf")
        self.assertAlmostEqual(float(small.maximum[2]), self.plane)
        self.assertAlmostEqual(float(small.minimum[2]), 1.61 / 2.0)

    def test_main_shelf_still_depends_on_the_flag(self) -> None:
        """Only the CENTRE shelf is flag-controlled; conflating the two is
        the mistake this file guards against."""
        self.assertNotIn(
            "main_shelf",
            {s.name for s in agent.shelf_aabbs(self.no_shelf)},
        )
        self.assertIn(
            "main_shelf",
            {s.name for s in agent.shelf_aabbs(self.with_shelf)},
        )

    def test_transport_samples_use_the_same_plane_logic(self) -> None:
        """Both transport builders must agree; the sampled path is the one
        the corridor check actually walks."""
        candidate = self.item_resting_at(self.plane + 0.01)
        samples = agent.transport_samples(candidate, self.no_shelf)
        action_center = agent.simulator_action_center(candidate, self.no_shelf)
        self.assertTrue(samples)
        for sample in samples:
            self.assertAlmostEqual(
                float(sample.center[2]), float(action_center[2])
            )


if __name__ == "__main__":
    unittest.main()
