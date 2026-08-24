import unittest

from scripts.counterfactual_graph import item_symmetry_action_orbit_key


def item(index, *, soft=False):
    return {
        "index": index,
        "length": 1.0,
        "width": 2.0,
        "height": 3.0,
        "mass": 4.0,
        "is_prioritized": False,
        "is_soft": soft,
    }


def action(pool_index):
    return {
        "item_idx": pool_index,
        "container_idx": 0,
        "place_pos": [0.1, 0.2, 0.3],
        "orientation": 2,
    }


class ItemSymmetryActionOrbitTests(unittest.TestCase):
    def test_identical_adjacent_items_share_an_action_orbit(self):
        observation = {"pool_list": [item(10), item(11)]}

        self.assertEqual(
            item_symmetry_action_orbit_key(observation, action(0)),
            item_symmetry_action_orbit_key(observation, action(1)),
        )

    def test_pool_order_that_changes_after_removal_is_not_merged(self):
        observation = {
            "pool_list": [item(10), item(20, soft=True), item(11)]
        }

        self.assertNotEqual(
            item_symmetry_action_orbit_key(observation, action(0)),
            item_symmetry_action_orbit_key(observation, action(2)),
        )

    def test_attribute_difference_is_not_merged(self):
        observation = {"pool_list": [item(10), item(11, soft=True)]}

        self.assertNotEqual(
            item_symmetry_action_orbit_key(observation, action(0)),
            item_symmetry_action_orbit_key(observation, action(1)),
        )

    def test_missing_pool_metadata_fails_closed(self):
        self.assertIsNone(item_symmetry_action_orbit_key({}, action(0)))


if __name__ == "__main__":
    unittest.main()
