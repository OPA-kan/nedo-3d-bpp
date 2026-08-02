from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import measure_search_ceiling as ceiling  # noqa: E402


class ActionShapeTests(unittest.TestCase):
    def test_action_record_carries_the_pool_and_item_index_apart(self):
        # The pool index addresses the visible pool, the item index names the
        # baggage. Conflating them silently validates the wrong item when the
        # pool is not the identity, which is every Task B case.
        observation = {"pool_list": [{"index": 41}, {"index": 7}]}
        action = {
            "item_idx": 1,
            "container_idx": 0,
            "place_pos": np.array([0.1, 0.2, 0.3], dtype=np.float32),
            "orientation": 3,
        }

        record = ceiling.action_record(action, observation)

        self.assertEqual(record["pool_index"], 1)
        self.assertEqual(record["item_index"], 7)
        self.assertEqual(record["orientation"], 3)
        self.assertEqual(
            [round(v, 3) for v in record["action_center"]], [0.1, 0.2, 0.3]
        )

    def test_rescue_action_round_trips_a_record(self):
        record = {
            "pool_index": 0,
            "container_index": 1,
            "action_center": [0.5, -0.25, 0.75],
            "orientation": 5,
        }

        action = ceiling.rescue_action(record)

        self.assertEqual(action["item_idx"], 0)
        self.assertEqual(action["container_idx"], 1)
        self.assertEqual(action["orientation"], 5)
        self.assertEqual(action["place_pos"].dtype, np.float32)
        self.assertEqual(
            [float(v) for v in action["place_pos"]], [0.5, -0.25, 0.75]
        )


class OracleOrderingTests(unittest.TestCase):
    def _patch(self, settled, release, complete=(True, True)):
        return (
            mock.patch.object(
                ceiling,
                "enumerate_dual_settled_oracle",
                return_value=(settled, complete[0], {}),
            ),
            mock.patch.object(
                ceiling,
                "enumerate_oracle_candidates",
                return_value=(release, complete[1], {}),
            ),
            mock.patch.object(
                ceiling,
                "enrich_score",
                side_effect=lambda _m, _o, r: dict(r),
            ),
        )

    def test_candidates_are_ranked_by_the_agents_own_score(self):
        # The rescue must remove the search failure without also upgrading
        # the ranking, or the ceiling measures a better agent instead of a
        # better search.
        settled = [{"id": "a", "score": 1.0}, {"id": "b", "score": 9.0}]
        release = [{"id": "c", "score": 5.0}]
        with self._patch(settled, release)[0], self._patch(
            settled, release
        )[1], self._patch(settled, release)[2]:
            records = ceiling.oracle_candidates(object(), {})

        self.assertEqual([r["id"] for r in records], ["b", "c", "a"])
        self.assertEqual([r["oracle_rank"] for r in records], [0, 1, 2])

    def test_a_truncated_enumeration_refuses_to_run(self):
        # A dead end declared from an incomplete set is the one failure this
        # measurement cannot survive: it would report a ceiling that is only
        # the enumeration cap.
        settled, release = [{"id": "a", "score": 1.0}], []
        patches = self._patch(settled, release, complete=(False, True))
        with patches[0], patches[1], patches[2]:
            with self.assertRaises(RuntimeError):
                ceiling.oracle_candidates(object(), {})


class RescuePolicyTests(unittest.TestCase):
    def test_both_policies_are_offered_and_search_is_the_default(self):
        # 'search' isolates the search failure; 'all' also replaces picks that
        # fail physically and therefore measures a different, larger ceiling.
        self.assertEqual(ceiling.RESCUE_POLICIES, ("search", "all"))


if __name__ == "__main__":
    unittest.main()
