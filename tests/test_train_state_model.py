from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from scripts.audit_learnability import FEATURES
from scripts.train_state_model import (
    MAX_PLACED,
    MAX_POOL,
    TOKEN_WIDTH,
    board_tokens,
    candidate_vector,
    load_examples,
)


def snapshot(
    *,
    placed: list[tuple[int, list[float]]],
    pool: int = 2,
    container_index: int = 0,
) -> dict:
    return {
        "case_id": "m-a",
        "step": 3,
        "observation": {
            "container_list": [
                {
                    "index": container_index,
                    "length": 2.0,
                    "width": 1.4,
                    "height": 1.6,
                    "shelf": True,
                    "is_prioritized": False,
                    "packed_items": [
                        {
                            "index": index,
                            "length": 0.5,
                            "width": 0.4,
                            "height": 0.3,
                            "mass": 5,
                            "is_soft": False,
                            "is_prioritized": False,
                            "pos": position,
                            "orn": [0.0, 0.0, 0.0, 1.0],
                        }
                        for index, position in placed
                    ],
                }
            ],
            "pool_list": [
                {
                    "index": 100 + index,
                    "length": 0.3,
                    "width": 0.2,
                    "height": 0.2,
                    "mass": 3,
                    "is_soft": True,
                    "is_prioritized": False,
                }
                for index in range(pool)
            ],
        },
        "physics": {
            "packed_items": [
                {
                    "container_index": container_index,
                    "item_index": index,
                    "position": position,
                }
                for index, position in placed
            ]
        },
    }


class CandidateVectorTests(unittest.TestCase):
    def test_it_carries_geometry_the_eight_scalars_do_not_have(self):
        # The whole premise of this arm: phi_modelling describes predicted
        # contact and never says where in the container the item goes.
        row = {
            "center": [0.3, -0.2, 1.1],
            "size": [0.5, 0.4, 0.3],
            "orientation": 2,
            "container_index": 0,
            "kind": "release_candidate",
        }

        vector = candidate_vector(row, snapshot(placed=[]))

        self.assertEqual(vector[:3], [0.3, -0.2, 1.1])
        self.assertEqual(vector[3:6], [0.5, 0.4, 0.3])
        self.assertNotIn("center_x", FEATURES)
        self.assertNotIn("size_x", FEATURES)

    def test_it_reads_the_container_the_candidate_actually_targets(self):
        row = {
            "center": [0.0, 0.0, 1.0],
            "size": [0.1, 0.1, 0.1],
            "orientation": 0,
            "container_index": 7,
            "kind": "release_candidate",
        }

        vector = candidate_vector(row, snapshot(placed=[], container_index=0))

        # No container 7 in this snapshot, so its geometry must read as
        # absent rather than silently borrowing container 0's.
        self.assertEqual(vector[-6:], [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])


class BoardTokenTests(unittest.TestCase):
    def test_placed_items_are_relative_to_the_candidate(self):
        tokens = board_tokens(
            snapshot(placed=[(0, [1.0, 0.0, 0.5])], pool=0),
            container_index=0,
            origin=[1.0, 0.0, 0.0],
        )

        self.assertEqual(list(tokens[0][:3]), [0.0, 0.0, 0.5])

    def test_the_nearest_placed_items_win_the_budget(self):
        placed = [(index, [float(index), 0.0, 0.0]) for index in range(40)]
        tokens = board_tokens(
            snapshot(placed=placed, pool=0),
            container_index=0,
            origin=[0.0, 0.0, 0.0],
        )

        self.assertEqual(len(tokens), MAX_PLACED)
        # Sorted by distance, so the far items are the ones dropped.
        self.assertEqual(tokens[0][0], 0.0)
        self.assertEqual(tokens[-1][0], float(MAX_PLACED - 1))

    def test_the_pool_is_capped_and_marked_as_not_yet_placed(self):
        tokens = board_tokens(
            snapshot(placed=[], pool=40),
            container_index=0,
            origin=[0.0, 0.0, 0.0],
        )

        self.assertEqual(len(tokens), MAX_POOL)
        # The last column separates placed items from pending ones; a model
        # that cannot tell them apart is being handed a false board.
        self.assertTrue(all(token[-1] == 0.0 for token in tokens))

    def test_an_empty_board_still_yields_one_token(self):
        tokens = board_tokens(
            snapshot(placed=[], pool=0),
            container_index=0,
            origin=[0.0, 0.0, 0.0],
        )

        self.assertEqual(tokens.shape, (1, TOKEN_WIDTH))


class LoadExampleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write(self, run: str, *, board: int, rows: list[dict]) -> None:
        directory = self.root / run / "dataset" / "m-a"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "step-003-state.json").write_text(
            json.dumps(snapshot(placed=[(0, [float(board), 0.0, 0.5])])),
            encoding="utf-8",
        )
        (directory / "step-003-candidates.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )

    def row(self, candidate: int, *, phi: bool = True) -> dict:
        return {
            "case_id": "m-a",
            "step": 3,
            "candidate_id": f"c{candidate}",
            "kind": "release_candidate",
            "container_index": 0,
            "center": [0.1, 0.2, 1.0],
            "size": [0.3, 0.2, 0.2],
            "orientation": 1,
            "score_immediate": 1.0,
            "phi_modelling": (
                {name: 0.5 for name in FEATURES} if phi else {}
            ),
            "physical": {
                "is_placed_safe": True,
                "delta_theta_deg": 1.0,
                "d_norm": 0.1,
            },
        }

    def test_a_row_without_a_feature_vector_is_dropped(self):
        self.write("run-1", board=0, rows=[self.row(0, phi=False)])

        self.assertEqual(load_examples(self.root), [])

    def test_the_same_candidate_on_one_board_is_loaded_once(self):
        directory = self.root / "run-1" / "dataset" / "m-a"
        self.write("run-1", board=0, rows=[self.row(0)])
        (directory / "step-003-random-control.jsonl").write_text(
            json.dumps(self.row(0)) + "\n", encoding="utf-8"
        )

        self.assertEqual(len(load_examples(self.root)), 1)

    def test_two_runs_on_different_boards_are_two_examples(self):
        self.write("run-1", board=0, rows=[self.row(0)])
        self.write("run-2", board=1, rows=[self.row(0)])

        examples = load_examples(self.root)

        self.assertEqual(len(examples), 2)
        self.assertEqual(len({e["state"] for e in examples}), 2)


if __name__ == "__main__":
    unittest.main()
