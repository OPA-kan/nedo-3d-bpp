import importlib.util
import pathlib
import sys
import time
import unittest

AGENT_PATH = pathlib.Path(__file__).parents[1] / "agent" / "agent.py"
SPEC = importlib.util.spec_from_file_location(
    "visible_tree_search_agent", AGENT_PATH
)
agent = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = agent
SPEC.loader.exec_module(agent)


def container(packed=()):
    return {
        "length": 2.0,
        "width": 1.4,
        "height": 1.6,
        "thickness": 0.04,
        "cut_x": 0.0,
        "cut_y": 0.0,
        "shelf": False,
        "packed_items": [
            {"pos": list(pos), "dims": list(dims)} for pos, dims in packed
        ],
    }


def heightmap(box):
    grid = agent.board_grid(box)
    top, _filled = agent.board_occupancy(box, grid)
    return grid, top.copy()


def item(length=0.4, width=0.4, height=0.4, mass=1.0):
    return {
        "length": length,
        "width": width,
        "height": height,
        "mass": mass,
    }


def decision_for(pool_index, center, size, score, orientation=0):
    candidate = agent.AABB(
        center=tuple(center), size=tuple(size), name="settled_candidate"
    )
    return agent.PlacementDecision(
        action={
            "item_idx": pool_index,
            "container_idx": 0,
            "place_pos": list(center),
            "orientation": orientation,
        },
        candidate=candidate,
        score=float(score),
    )


class KnobAndConstantsTests(unittest.TestCase):
    def test_default_mode_is_off_and_constants_are_preregistered(self):
        self.assertEqual(agent.VISIBLE_TREE_SEARCH, "off")
        self.assertEqual(
            agent.VISIBLE_TREE_SEARCH_MODES,
            frozenset({"off", "shadow", "enforce"}),
        )
        self.assertEqual(agent.VISIBLE_TREE_SEARCH_BRANCH, 4)
        self.assertEqual(agent.VISIBLE_TREE_SEARCH_DEPTH, 2)
        self.assertEqual(agent.VISIBLE_TREE_SEARCH_SECONDS, 2.0)
        self.assertEqual(agent.VISIBLE_TREE_SEARCH_TIE_BAND, 0.05)
        self.assertGreater(agent.VISIBLE_TREE_SEARCH_TIE_BAND, 0.0)
        self.assertGreater(
            agent.VISIBLE_TREE_SEARCH_RECEPTIVITY_WEIGHT, 0.0
        )
        self.assertEqual(agent.VISIBLE_TREE_SEARCH_SITE_CAP, 24)


class DecisionRuleTests(unittest.TestCase):
    def test_incumbent_best_never_swaps(self):
        self.assertFalse(agent.visible_tree_should_swap(1.0, 1.0, True))
        self.assertFalse(agent.visible_tree_should_swap(1.0, 99.0, True))

    def test_within_tie_band_stands(self):
        band = agent.VISIBLE_TREE_SEARCH_TIE_BAND
        self.assertFalse(agent.visible_tree_should_swap(1.0, 1.0, False))
        self.assertFalse(
            agent.visible_tree_should_swap(1.0, 1.0 + band, False)
        )
        self.assertFalse(agent.visible_tree_should_swap(1.0, 0.5, False))

    def test_beyond_tie_band_swaps(self):
        band = agent.VISIBLE_TREE_SEARCH_TIE_BAND
        self.assertTrue(
            agent.visible_tree_should_swap(1.0, 1.0 + band + 1e-6, False)
        )
        self.assertTrue(
            agent.visible_tree_should_swap(-2.0, -1.0, False)
        )

    def test_missing_scores_stand(self):
        self.assertFalse(agent.visible_tree_should_swap(None, 5.0, False))
        self.assertFalse(agent.visible_tree_should_swap(5.0, None, False))

    def test_explicit_tie_band_overrides_default(self):
        self.assertTrue(
            agent.visible_tree_should_swap(1.0, 1.02, False, tie_band=0.01)
        )
        self.assertFalse(
            agent.visible_tree_should_swap(1.0, 1.02, False, tie_band=0.5)
        )


class HeightmapTests(unittest.TestCase):
    def test_empty_board_drop_height_is_the_floor(self):
        box = container()
        grid, top = heightmap(box)
        floor = float(box["thickness"])
        self.assertAlmostEqual(
            agent.visible_tree_drop_height(grid, top, 0.0, 0.0, 0.4, 0.4),
            floor,
            places=6,
        )

    def test_stamp_raises_drop_height_over_the_footprint_only(self):
        box = container()
        grid, top = heightmap(box)
        floor = float(box["thickness"])
        candidate = agent.AABB(
            center=(0.0, 0.0, floor + 0.2),
            size=(0.4, 0.4, 0.4),
            name="settled_candidate",
        )
        agent.visible_tree_stamp(grid, top, candidate, box)
        self.assertAlmostEqual(
            agent.visible_tree_drop_height(grid, top, 0.0, 0.0, 0.4, 0.4),
            floor + 0.4,
            places=6,
        )
        self.assertAlmostEqual(
            agent.visible_tree_drop_height(grid, top, 0.7, -0.5, 0.3, 0.3),
            floor,
            places=6,
        )

    def test_packed_cargo_is_part_of_the_surface(self):
        box = container(packed=[((0.3, 0.2, 0.3), (0.4, 0.4, 0.6))])
        grid, top = heightmap(box)
        self.assertAlmostEqual(
            agent.visible_tree_drop_height(grid, top, 0.3, 0.2, 0.2, 0.2),
            0.6,
            places=6,
        )

    def test_footprint_outside_the_interior_returns_none(self):
        box = container()
        grid, top = heightmap(box)
        self.assertIsNone(
            agent.visible_tree_drop_height(grid, top, 5.0, 0.0, 0.4, 0.4)
        )


class SearchTests(unittest.TestCase):
    def observation(self, pool_size=3):
        return {
            "pool_list": [item() for _ in range(pool_size)],
            "container_list": [container()],
        }

    def test_expired_deadline_returns_incumbent_with_budget_exhausted(self):
        observation = self.observation()
        incumbent = decision_for(0, (0.0, 0.0, 0.24), (0.4, 0.4, 0.4), 1.0)
        record, proposed = agent.visible_tree_search_record(
            observation,
            [incumbent],
            incumbent,
            deadline=time.perf_counter() - 1.0,
        )
        self.assertTrue(record["budget_exhausted"])
        self.assertEqual(record["roots_expanded"], 0)
        self.assertFalse(record["would_change"])
        self.assertFalse(record["enforced"])
        self.assertIsNone(proposed)

    def test_single_root_expands_and_never_proposes_itself(self):
        observation = self.observation()
        incumbent = decision_for(0, (0.0, 0.0, 0.24), (0.4, 0.4, 0.4), 1.0)
        record, proposed = agent.visible_tree_search_record(
            observation, [incumbent], incumbent
        )
        self.assertFalse(record["budget_exhausted"])
        self.assertEqual(record["roots_considered"], 1)
        self.assertEqual(record["roots_expanded"], 1)
        self.assertEqual(record["leaves_scored"], 1)
        self.assertIsInstance(record["incumbent_path_score"], float)
        self.assertEqual(
            record["incumbent_path_score"], record["best_path_score"]
        )
        self.assertFalse(record["would_change"])
        self.assertIsNone(proposed)

    def test_roots_deduplicate_by_action(self):
        observation = self.observation()
        incumbent = decision_for(0, (0.0, 0.0, 0.24), (0.4, 0.4, 0.4), 1.0)
        clone = decision_for(0, (0.0, 0.0, 0.24), (0.4, 0.4, 0.4), 1.0)
        other = decision_for(1, (0.6, 0.0, 0.24), (0.4, 0.4, 0.4), 0.9)
        record, _proposed = agent.visible_tree_search_record(
            observation, [clone, other], incumbent
        )
        self.assertEqual(record["roots_considered"], 2)
        self.assertEqual(record["roots_expanded"], 2)
        self.assertTrue(record["roots"][0]["is_incumbent"])

    def test_item_receptivity_is_capped(self):
        box = container()
        state = agent.visible_tree_heightmaps([box])
        # An empty 2.0 x 1.4 board accepts a 0.4 cube nearly everywhere,
        # so the raw landing-site count far exceeds the cap.
        sites = agent.visible_tree_item_receptivity(
            item(), state, [box]
        )
        self.assertEqual(sites, agent.VISIBLE_TREE_SEARCH_SITE_CAP)


if __name__ == "__main__":
    unittest.main()
