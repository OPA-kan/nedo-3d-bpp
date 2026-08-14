from __future__ import annotations

import unittest

from scripts.develop_distributional_fill_preaction_v2 import (
    build_v2,
    deduplicate_rows,
)
from tests.test_evaluate_counterfactual_afterstate_value import run
from scripts.build_distributional_fill_shadow_model import build_model


class DistributionalFillPreactionV2Tests(unittest.TestCase):
    def test_deduplicates_exact_preaction_inputs(self) -> None:
        row = run("one")["discovery"][0]
        row["source_state_tensor"] = row["lower_afterstate_tensor"]
        row["scenario_axes"] = {"stream_variant": "stream"}

        result = deduplicate_rows([row, row.copy()])

        self.assertEqual(result["raw_rows"], 2)
        self.assertEqual(result["unique_rows"], 1)

    def test_selects_l2_with_whole_streams_held_out(self) -> None:
        runs = [run("one"), run("two")]
        for index, physical_run in enumerate(runs):
            physical_run["discovery"] = [physical_run["discovery"][0]]
            for row in physical_run["discovery"]:
                row["source_state_tensor"] = row["lower_afterstate_tensor"]
                row["scenario_axes"] = {"stream_variant": f"stream-{index}"}
                row["higher_action_tensor"]["values"][0] += index

        shadow = build_model(runs)
        model = build_v2(runs, shadow)

        self.assertEqual(
            model["model_selection"]["selection"],
            "leave_one_stream_variant_out_unique-signature accuracy with "
            "per-stream nonregression",
        )


if __name__ == "__main__":
    unittest.main()
