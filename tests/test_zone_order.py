import os
import unittest

from scripts.measure_anchor_recall import load_agent_module

AGENT = load_agent_module()


def container(*, cut_x=0.0, shelf=False, width=1.52):
    return {
        "length": 2.0,
        "width": width,
        "height": 1.62,
        "thickness": 0.05,
        "cut_x": cut_x,
        "cut_y": 0.0,
        "shelf": shelf,
        "packed_items": [],
    }


def box(x, y, bottom, size=(0.5, 0.4, 0.24)):
    return AGENT.AABB(
        center=(x, y, bottom + size[2] / 2.0),
        size=size,
        name="release_candidate",
    )


class ZoneClassificationTests(unittest.TestCase):
    def test_a_shelfless_container_has_only_deep_and_centre(self):
        plain = container()
        for y, expected in ((0.60, "deep"), (0.00, "centre"), (-0.60, "centre")):
            with self.subTest(y=y):
                self.assertEqual(
                    AGENT.candidate_zone(box(0.0, y, 0.066), plain), expected
                )

    def test_resting_on_the_shelf_is_shelf_top(self):
        shelved = container(shelf=True)
        plate = [
            a for a in AGENT.shelf_aabbs(shelved) if a.name == "main_shelf"
        ][0]
        pose = box(0.0, 0.30, float(plate.maximum[2]))
        self.assertEqual(AGENT.candidate_zone(pose, shelved), "shelf_top")

    def test_a_tall_floor_pose_by_the_door_is_not_shelf_top(self):
        """
        The defect this exists for. Classifying on the pose's TOP made a tall
        item standing on the floor near the entrance read as `shelf_top`, so
        a doctrine arm spent its first picks on exactly the poses it was
        meant to defer.
        """
        shelved = container(shelf=True)
        tall = box(0.0, -0.50, 0.066, size=(0.4, 0.3, 1.0))
        self.assertGreater(float(tall.maximum[2]), 0.86)
        self.assertEqual(AGENT.candidate_zone(tall, shelved), "centre")

    def test_under_the_shelf_is_its_own_zone(self):
        shelved = container(shelf=True)
        self.assertEqual(
            AGENT.candidate_zone(box(0.0, 0.30, 0.066), shelved), "under_shelf"
        )

    def test_a_shelf_container_has_no_deep_floor_zone(self):
        # Geometric fact, not a classifier choice: the plate spans
        # y 0.05..0.71 against a half width of 0.76, so every deep floor
        # pose is under it. Recorded as a test so a later change that
        # "fixes" deep=0 has to argue with the geometry.
        shelved = container(shelf=True)
        zones = {
            AGENT.candidate_zone(box(0.0, y / 100.0, 0.066), shelved)
            for y in range(10, 71, 5)
        }
        self.assertNotIn("deep", zones)


class ZoneScoreTests(unittest.TestCase):
    def reload(self, **env):
        """
        A FRESH import under the given environment.

        importlib.reload cannot be used here: the agent is loaded from a
        path with spec_from_file_location, so it has no findable parent
        package and reload raises. Loading a new copy also means each arm
        of these tests reads the knob exactly the way a subprocess ablation
        arm does.
        """
        previous = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        try:
            return load_agent_module()
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_off_by_default_leaves_the_score_untouched(self):
        module = load_agent_module()
        self.assertEqual(module.ZONE_ORDER_MODE, "off")
        plain = container()
        item = {"mass": 1.0}
        deep = module.Ranker.score(box(0.0, 0.60, 0.066), item, plain, False)
        near = module.Ranker.score(box(0.0, -0.60, 0.066), item, plain, False)
        # only the shipped +0.35*y depth term separates them
        self.assertAlmostEqual(deep - near, 0.35 * 1.2, places=6)

    def test_doctrine_ranks_the_shelf_top_above_under_the_shelf(self):
        module = self.reload(ZONE_ORDER="doctrine", ZONE_ORDER_BONUS="1.0")
        shelved = container(shelf=True)
        plate = [
            a for a in module.shelf_aabbs(shelved) if a.name == "main_shelf"
        ][0]
        item = {"mass": 1.0}
        on_top = module.Ranker.score(
            box(0.0, 0.30, float(plate.maximum[2])), item, shelved, False
        )
        beneath = module.Ranker.score(
            box(0.0, 0.30, 0.066), item, shelved, False
        )
        self.assertGreater(on_top, beneath)

    def test_the_span_must_clear_the_support_term(self):
        """
        Why the default bonus is 1.0 and not 0.5.

        A pose resting on the shelf plate scores support 1 and a release
        pose under it scores support 0 -- support_ratio wants 6 mm of
        contact and a release candidate is sent 16 mm clear of its surface.
        So `2.0 * support` swings 2.0 between exactly the pair the doctrine
        is about, and a zone span of 1.5 could not reorder it. The knob
        would have run as an arm and expressed nothing.
        """
        module = self.reload(ZONE_ORDER="doctrine", ZONE_ORDER_BONUS="1.0")
        span = module.ZONE_ORDER_BONUS * (
            max(module.ZONE_RANKS["doctrine"].values())
            - min(module.ZONE_RANKS["doctrine"].values())
        )
        self.assertGreater(span, 2.0)

    def test_reversed_inverts_it(self):
        module = self.reload(ZONE_ORDER="reversed", ZONE_ORDER_BONUS="1.0")
        shelved = container(shelf=True)
        plate = [
            a for a in module.shelf_aabbs(shelved) if a.name == "main_shelf"
        ][0]
        item = {"mass": 1.0}
        on_top = module.Ranker.score(
            box(0.0, 0.30, float(plate.maximum[2])), item, shelved, False
        )
        beneath = module.Ranker.score(
            box(0.0, 0.30, 0.066), item, shelved, False
        )
        self.assertLess(on_top, beneath)

    def test_an_unknown_mode_is_refused_at_import(self):
        with self.assertRaises(ValueError):
            self.reload(ZONE_ORDER="deepest_first")

    def test_the_bonus_span_is_three_units(self):
        module = self.reload(ZONE_ORDER="doctrine", ZONE_ORDER_BONUS="1.0")
        ranks = module.ZONE_RANKS["doctrine"]
        self.assertEqual(max(ranks.values()) - min(ranks.values()), 3)


if __name__ == "__main__":
    unittest.main()
