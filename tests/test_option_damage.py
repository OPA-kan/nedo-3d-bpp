import unittest

from scripts import measure_option_damage as damage


def item(index, *, soft=False, priority=False, dims=(0.3, 0.25, 0.2)):
    length, width, height = dims
    return {
        "index": index,
        "length": length,
        "width": width,
        "height": height,
        "mass": 5,
        "is_soft": soft,
        "is_prioritized": priority,
    }


class OptionTypeTests(unittest.TestCase):
    def test_priority_wins_over_soft(self):
        """
        A prioritised soft item is routed by its priority, so filing it
        under `soft` would count its options in a type that cannot serve it.
        """
        self.assertEqual(
            damage.option_type(item(0, soft=True, priority=True)), "priority"
        )

    def test_soft_and_rigid_split_the_rest(self):
        self.assertEqual(damage.option_type(item(0, soft=True)), "soft")
        self.assertEqual(damage.option_type(item(0)), "rigid")


class TypedClassTests(unittest.TestCase):
    def test_packed_items_leave_the_remaining_set(self):
        classes = damage.typed_classes([item(0), item(1)], {0})

        self.assertEqual(len(classes), 1)
        self.assertEqual(classes[0]["count"], 1)

    def test_identical_dims_with_different_attributes_are_distinct(self):
        classes = damage.typed_classes(
            [item(0), item(1, soft=True), item(2, priority=True)], set()
        )

        self.assertEqual(len(classes), 3)
        self.assertEqual(
            {entry["type"] for entry in classes},
            {"rigid", "soft", "priority"},
        )

    def test_same_class_accumulates_multiplicity(self):
        classes = damage.typed_classes([item(0), item(1), item(2)], set())

        self.assertEqual(len(classes), 1)
        self.assertEqual(classes[0]["count"], 3)

    def test_classes_are_ordered_by_volume_descending(self):
        classes = damage.typed_classes(
            [item(0, dims=(0.1, 0.1, 0.1)), item(1, dims=(0.5, 0.5, 0.5))],
            set(),
        )

        self.assertGreater(classes[0]["volume"], classes[1]["volume"])


class CounterWalkTests(unittest.TestCase):
    def test_nested_diagnostics_are_flattened(self):
        diagnostics = {
            "items": {
                "3": {"attempted": 5, "rejected": {"corridor": 2}},
                "4": [{"attempted": 7, "rejected": {"static_geometry": 1}}],
            }
        }

        counters = list(damage._walk_counters(diagnostics))

        self.assertEqual(sum(c["attempted"] for c in counters), 12)
        self.assertEqual(
            sum(c["rejected"].get("corridor", 0) for c in counters), 2
        )

    def test_a_counter_is_not_descended_into_twice(self):
        counter = {"attempted": 1, "rejected": {"corridor": 1}}

        self.assertEqual(list(damage._walk_counters(counter)), [counter])


class RealisedSuccessorTests(unittest.TestCase):
    def _observation(self):
        return {
            "pool_list": [item(7)],
            "container_list": [{"packed_items": []}],
        }

    def test_the_validator_pose_is_what_gets_packed(self):
        row = {
            "pool_index": 0,
            "container_index": 0,
            "physical": {
                "x_plus": {
                    "position": [1.0, 2.0, 3.0],
                    "quaternion": [0.0, 0.0, 0.0, 1.0],
                }
            },
        }

        successor = damage.realised_successor(self._observation(), row)
        packed = successor["container_list"][0]["packed_items"]

        self.assertEqual(len(packed), 1)
        self.assertEqual(packed[0]["pos"], [1.0, 2.0, 3.0])
        self.assertEqual(packed[0]["orn"], [0.0, 0.0, 0.0, 1.0])

    def test_a_row_without_a_settled_pose_is_skipped(self):
        row = {"pool_index": 0, "container_index": 0, "physical": {}}

        self.assertIsNone(damage.realised_successor(self._observation(), row))

    def test_the_source_observation_is_not_mutated(self):
        observation = self._observation()
        row = {
            "pool_index": 0,
            "container_index": 0,
            "physical": {
                "x_plus": {
                    "position": [1.0, 2.0, 3.0],
                    "quaternion": [0.0, 0.0, 0.0, 1.0],
                }
            },
        }

        damage.realised_successor(observation, row)

        self.assertEqual(observation["container_list"][0]["packed_items"], [])


if __name__ == "__main__":
    unittest.main()
