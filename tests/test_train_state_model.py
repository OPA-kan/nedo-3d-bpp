from __future__ import annotations

import unittest

from scripts.train_state_model import (
    ARMS,
    MAX_PLACED,
    TOKEN_WIDTH,
    board_tokens,
    candidate_vector,
    filter_positive_source,
    markdown,
)


def snapshot(placed: int = 3, pool: int = 2) -> dict:
    return {
        "observation": {
            "container_list": [
                {
                    "index": 0,
                    "length": 2.0,
                    "width": 1.4,
                    "height": 1.6,
                    "shelf": False,
                    "is_prioritized": False,
                    "packed_items": [
                        {
                            "index": index,
                            "length": 0.4,
                            "width": 0.3,
                            "height": 0.2,
                            "mass": 5,
                            "pos": [float(index), 0.0, 0.5],
                            "orn": [0.0, 0.0, 0.0, 1.0],
                        }
                        for index in range(placed)
                    ],
                }
            ],
            "pool_list": [
                {"index": index, "length": 0.5, "width": 0.4, "height": 0.3}
                for index in range(pool)
            ],
        }
    }


class TokenTests(unittest.TestCase):
    def test_placed_items_are_ordered_by_distance_to_the_candidate(self):
        tokens = board_tokens(
            snapshot(placed=3, pool=0), container_index=0, origin=[2.0, 0, 0.5]
        )

        # Nearest first: the item at x=2 is the candidate's own neighbourhood.
        self.assertAlmostEqual(float(tokens[0][0]), 0.0)
        self.assertLessEqual(abs(tokens[0][0]), abs(tokens[-1][0]))

    def test_the_token_budget_is_enforced(self):
        tokens = board_tokens(
            snapshot(placed=MAX_PLACED + 20, pool=0),
            container_index=0,
            origin=[0.0, 0.0, 0.0],
        )

        self.assertEqual(len(tokens), MAX_PLACED)
        self.assertEqual(tokens.shape[1], TOKEN_WIDTH)

    def test_a_board_with_nothing_on_it_still_yields_a_token(self):
        tokens = board_tokens(
            {"observation": {"container_list": [], "pool_list": []}},
            container_index=0,
            origin=[0.0, 0.0, 0.0],
        )

        self.assertEqual(tokens.shape, (1, TOKEN_WIDTH))


class CandidateVectorTests(unittest.TestCase):
    def test_it_carries_what_phi_modelling_does_not(self):
        vector = candidate_vector(
            {
                "center": [0.1, 0.2, 0.3],
                "size": [0.4, 0.5, 0.6],
                "orientation": 2,
                "container_index": 0,
                "kind": "release_candidate",
            },
            snapshot(),
        )

        # Where in the container the item is going, which the eight contact
        # scalars never say. This is the arm that produced the largest gain.
        self.assertEqual(vector[:3], [0.1, 0.2, 0.3])
        self.assertAlmostEqual(vector[6], 0.4 * 0.5 * 0.6)
        self.assertEqual(vector[7 + 2], 1.0)


class MarkdownTests(unittest.TestCase):
    def test_every_line_is_a_string(self):
        # A trailing comma inside parentheses silently makes a tuple, and
        # "\n".join then raises after the whole training run has finished --
        # the most expensive possible moment to find a formatting typo.
        report = {
            "verdict": "state_model_beats_incumbent",
            "corpus": {"rows": 10, "states": 3, "cases": ["a", "b"]},
            "design": {
                "split": "leave_one_case_out",
                "positive_source": "control",
                "seeds": 2,
                "epochs": 10,
            },
            "classification": {
                name: {
                    "mean_state_auc": 0.5,
                    "pooled_auc": 0.5,
                    "top1_safe_rate": 0.5,
                }
                for name in ("incumbent", *ARMS)
            },
            "regression": {"d_norm": {arm: 0.1 for arm in ARMS}},
            "interpretation": "ok",
        }

        text = markdown(report)

        self.assertIn("Positives from: `control`", text)
        self.assertIn("| incumbent |", text)

    def test_an_insufficient_corpus_still_renders(self):
        text = markdown(
            {"verdict": "insufficient_corpus", "rows": 4, "cases": ["a"]}
        )

        self.assertIn("insufficient_corpus", text)


class PositiveSourceTests(unittest.TestCase):
    def examples(self):
        return [
            {"arm": "candidates", "safe": 1.0},
            {"arm": "control", "safe": 1.0},
            {"arm": "risk", "safe": 0.0},
        ]

    def test_control_only_drops_the_diversity_selected_positives(self):
        # The confound this exists for: safe rows in `candidates` are the ones
        # the swap optimizer picked to spread out, while every unsafe row is
        # kept. A model could read the selection instead of the safety.
        kept = filter_positive_source(self.examples(), "control")

        self.assertEqual(
            [e["arm"] for e in kept], ["control", "risk"]
        )

    def test_all_keeps_everything(self):
        self.assertEqual(
            len(filter_positive_source(self.examples(), "all")), 3
        )

    def test_an_unknown_source_is_refused(self):
        with self.assertRaises(ValueError):
            filter_positive_source(self.examples(), "positives")


if __name__ == "__main__":
    unittest.main()
