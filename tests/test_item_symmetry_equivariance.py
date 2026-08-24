import json
import pathlib
import tempfile
import unittest

from scripts.aggregate_item_symmetry_equivariance import aggregate
from scripts.audit_item_symmetry_equivariance import (
    compare_traces,
    metric_mismatches,
    transposed_order,
)


def trace_row(
    step, *, exact="exact", symmetry="symmetry", selected=1,
    fill=1.0, safe=True,
):
    return {
        "step": step,
        "selected_item_index": selected,
        "status": {
            "is_included": safe,
            "is_valid": safe,
            "is_placed_safe": safe,
        },
        "safe": safe,
        "terminated": False,
        "truncated": False,
        "before_exact": exact + "-before",
        "before_symmetry": symmetry + "-before",
        "after_exact": exact + "-after",
        "after_symmetry": symmetry + "-after",
        "metrics": {"fill_score_proxy": fill, "optional": None},
    }


class ItemSymmetryEquivarianceTests(unittest.TestCase):
    def test_transposition_is_an_involution(self):
        order = [1, 2, 3, 4]
        swapped = transposed_order(order, 2, 4)
        self.assertEqual(swapped, [1, 4, 3, 2])
        self.assertEqual(transposed_order(swapped, 2, 4), order)

    def test_equivalent_transition_passes_only_when_nonvacuous(self):
        baseline = [trace_row(0, exact="labels-a", selected=1)]
        relabelled = [trace_row(0, exact="labels-b", selected=2)]

        result = compare_traces(baseline, relabelled, witness_step=0)

        self.assertTrue(result["passed"])
        self.assertTrue(result["nonvacuous"])
        self.assertEqual(result["false_merge_steps"], 0)

    def test_same_exact_labels_are_rejected_as_vacuous(self):
        trace = [trace_row(0)]

        result = compare_traces(trace, trace, witness_step=0)

        self.assertFalse(result["passed"])
        self.assertFalse(result["nonvacuous"])

    def test_child_or_metric_difference_is_a_false_merge(self):
        baseline = [trace_row(0, exact="a", selected=1)]
        relabelled = [trace_row(
            0, exact="b", symmetry="different", selected=2, fill=1.1,
        )]

        result = compare_traces(baseline, relabelled, witness_step=0)

        self.assertFalse(result["passed"])
        self.assertEqual(result["false_merge_steps"], 1)
        self.assertIn(
            "fill_score_proxy", result["steps"][0]["metric_mismatches"]
        )

    def test_trace_length_mismatch_is_an_explicit_false_merge(self):
        result = compare_traces(
            [trace_row(0, exact="a", selected=1)], [], witness_step=0,
        )

        self.assertFalse(result["passed"])
        self.assertFalse(result["nonvacuous"])
        self.assertEqual(result["reason"], "trace_length_mismatch")
        self.assertEqual(result["equivariant_steps"], 0)
        self.assertEqual(result["false_merge_steps"], 1)

    def test_metric_tolerance_is_explicit(self):
        self.assertEqual(metric_mismatches({"x": 1.0}, {"x": 1.0 + 1e-7}), {})
        self.assertIn("x", metric_mismatches({"x": 1.0}, {"x": 1.01}))

    def test_aggregate_requires_every_cell_and_zero_false_merges(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            for cell in ("a", "b"):
                path = root / cell / "audit.json"
                path.parent.mkdir()
                path.write_text(json.dumps({
                    "contract": "identical_item_transposition_equivariance_v1",
                    "case_id": cell,
                    "passed": True,
                    "nonvacuous": True,
                    "steps": [{}, {}],
                    "equivariant_steps": 2,
                    "false_merge_steps": 0,
                    "pair": {},
                }), encoding="utf-8")

            result = aggregate(root)

        self.assertTrue(result["passed"])
        self.assertEqual(result["cell_count"], 2)
        self.assertEqual(result["equivariant_steps"], 4)

    def test_aggregate_rejects_a_vacuous_cell(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "unsupported" / "audit.json"
            path.parent.mkdir()
            path.write_text(json.dumps({
                "contract": "identical_item_transposition_equivariance_v1",
                "case_id": "unsupported",
                "passed": False,
                "nonvacuous": False,
                "steps": [],
                "equivariant_steps": 0,
                "false_merge_steps": 0,
            }), encoding="utf-8")

            result = aggregate(pathlib.Path(directory))

        self.assertFalse(result["passed"])
        self.assertEqual(result["nonvacuous_cells"], 0)


if __name__ == "__main__":
    unittest.main()
