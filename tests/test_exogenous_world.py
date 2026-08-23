import unittest

from scripts.exogenous_world import ExogenousWorld


class ExogenousWorldTests(unittest.TestCase):
    def test_event_draws_are_access_order_independent(self):
        left = ExogenousWorld(
            base_seed=17, root_id="root", sample_index=3,
            future_stream_id="stream-a",
        )
        later = left.uniform("handoff_after_placement", 4)
        earlier = left.uniform("handoff_after_placement", 1)

        right = ExogenousWorld(
            base_seed=17, root_id="root", sample_index=3,
            future_stream_id="stream-a",
        )
        self.assertEqual(
            earlier, right.uniform("handoff_after_placement", 1)
        )
        self.assertEqual(
            later, right.uniform("handoff_after_placement", 4)
        )

    def test_world_identity_changes_with_replica_not_candidate(self):
        first = ExogenousWorld(
            base_seed=17, root_id="root", sample_index=0,
            future_stream_id="stream-a",
        )
        same = ExogenousWorld(
            base_seed=17, root_id="root", sample_index=0,
            future_stream_id="stream-a",
        )
        second = ExogenousWorld(
            base_seed=17, root_id="root", sample_index=1,
            future_stream_id="stream-a",
        )

        self.assertEqual(first.world_id, same.world_id)
        self.assertEqual(
            first.uniform("handoff_after_placement", 0),
            same.uniform("handoff_after_placement", 0),
        )
        self.assertNotEqual(first.world_id, second.world_id)

    def test_event_rng_uses_the_semantic_event_key(self):
        world = ExogenousWorld(
            base_seed=5, root_id="root", sample_index=0,
            future_stream_id=None,
        )
        first = world.event_rng("handoff_after_placement", 2)
        second = world.event_rng("handoff_after_placement", 2)

        self.assertEqual(first.random(), second.random())
        self.assertEqual(first.random(), second.random())


if __name__ == "__main__":
    unittest.main()
