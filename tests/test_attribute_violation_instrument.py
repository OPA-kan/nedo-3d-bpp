import unittest

from scripts.attribute_violation_instrument import (
    attribute_violation_counters,
    settled_attribute_violation_counters,
)


def item(index, *, z, soft=False, priority=False, x=0.0):
    return {
        "index": index,
        "aabb_min": [x - 0.1, -0.1, z - 0.1],
        "aabb_max": [x + 0.1, 0.1, z + 0.1],
        "is_soft": soft,
        "is_prioritized": priority,
    }


class AttributeViolationInstrumentTests(unittest.TestCase):
    def test_settled_adapter_reads_pybullet_aabbs(self):
        class PackedItem:
            index = 5
            pybullet_id = 50
            is_soft = True
            is_prioritized = False

        class Client:
            @staticmethod
            def getAABB(_identifier):
                return ([-0.1, -0.1, -0.1], [0.1, 0.1, 0.1])

        container = type("Container", (), {
            "index": 0, "packed_items": [PackedItem()],
        })()
        env = type("Env", (), {
            "client": Client(),
            "container_manager": type("Manager", (), {
                "containers": [container],
            })(),
        })()

        counters = settled_attribute_violation_counters(env)

        self.assertEqual(counters["soft_direct_violated_items"], 0)

    def test_settled_adapter_censors_nonphysical_test_doubles(self):
        env = type("Env", (), {
            "client": object(),
            "container_manager": type("Manager", (), {
                "containers": [type("Container", (), {
                    "packed_items": [object()],
                })()],
            })(),
        })()

        self.assertEqual(settled_attribute_violation_counters(env), {})

    def test_direct_item_and_pair_counts_are_both_retained(self):
        counters = attribute_violation_counters([{
            "packed_items": [
                item(0, z=0.0, soft=True),
                item(1, z=0.2, x=-0.05),
                item(2, z=0.2, x=0.05),
            ],
        }])

        self.assertEqual(counters["soft_direct_violated_items"], 1)
        self.assertEqual(counters["soft_direct_violating_pairs"], 2)

    def test_stack_reading_sees_load_through_same_attribute_item(self):
        counters = attribute_violation_counters([{
            "packed_items": [
                item(0, z=0.0, soft=True),
                item(1, z=0.2, soft=True),
                item(2, z=0.4),
            ],
        }])

        self.assertEqual(counters["soft_direct_violated_items"], 1)
        self.assertEqual(counters["soft_stack_violated_items"], 2)
        self.assertEqual(counters["soft_stack_violating_pairs"], 2)

    def test_attributes_are_independent(self):
        counters = attribute_violation_counters([{
            "packed_items": [
                item(0, z=0.0, soft=True, priority=True),
                item(1, z=0.2, soft=True),
            ],
        }])

        self.assertEqual(counters["soft_direct_violated_items"], 0)
        self.assertEqual(counters["priority_direct_violated_items"], 1)


if __name__ == "__main__":
    unittest.main()
