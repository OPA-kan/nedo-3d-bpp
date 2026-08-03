import unittest

from scripts.measure_dead_end_branch import replay_digest


def observation(items):
    return {"container_list": [{"packed_items": items}]}


class ReplayDigestTest(unittest.TestCase):
    def test_order_invariant(self):
        a = observation(
            [
                {"index": 0, "pos": [0.1, 0.2, 0.3]},
                {"index": 1, "pos": [0.4, 0.5, 0.6]},
            ]
        )
        b = observation(
            [
                {"index": 1, "pos": [0.4, 0.5, 0.6]},
                {"index": 0, "pos": [0.1, 0.2, 0.3]},
            ]
        )
        self.assertEqual(replay_digest(a), replay_digest(b))

    def test_millimetre_move_changes_digest_submillimetre_does_not(self):
        base = observation([{"index": 0, "pos": [0.100, 0.2, 0.3]}])
        moved = observation([{"index": 0, "pos": [0.102, 0.2, 0.3]}])
        jitter = observation([{"index": 0, "pos": [0.1004, 0.2, 0.3]}])
        self.assertNotEqual(replay_digest(base), replay_digest(moved))
        self.assertEqual(replay_digest(base), replay_digest(jitter))


if __name__ == "__main__":
    unittest.main()
