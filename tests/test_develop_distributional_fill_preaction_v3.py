from __future__ import annotations

import unittest

from scripts.develop_distributional_fill_preaction_v3 import (
    _oriented_action,
    local_pair_vector,
)
from tests.test_evaluate_counterfactual_afterstate_value import run


class DistributionalFillPreactionV3Tests(unittest.TestCase):
    def test_candidate_dimensions_follow_command_orientation(self) -> None:
        action = run("orientation")["late"][0]["lower_action_tensor"]
        names = action["feature_names"]
        values = {name: action["values"][index] for index, name in enumerate(names)}
        action["values"][names.index("orientation")] = 3.0

        oriented = _oriented_action(action)
        result = {
            name: oriented["values"][index] for index, name in enumerate(names)
        }

        self.assertEqual(result["length"], values["width"])
        self.assertEqual(result["width"], values["length"])
        self.assertEqual(result["height"], values["height"])

    def test_local_vector_ignores_immediate_score(self) -> None:
        row = run("local")["late"][0]
        row["source_state_tensor"] = row["lower_afterstate_tensor"]
        before = local_pair_vector(row)
        score_index = row["lower_action_tensor"]["feature_names"].index(
            "immediate_score"
        )
        row["lower_action_tensor"]["values"][score_index] += 1000.0

        self.assertEqual(local_pair_vector(row), before)


if __name__ == "__main__":
    unittest.main()
