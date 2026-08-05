import json
import pathlib
import tempfile
import unittest

import numpy as np

from scripts.measure_step_confound import (
    auc,
    residualise,
    within_step_auc,
)


def corpus(cases=("a", "b"), length=30, horizon=3):
    """One row per step, labelled by nearness to the end -- the real shape."""
    rows = []
    for case in cases:
        for step in range(length):
            rows.append(
                {
                    "case": case,
                    "step": step,
                    "y": 1.0 if length - step <= horizon else 0.0,
                }
            )
    return rows


class StepConfoundTests(unittest.TestCase):
    def setUp(self):
        self.rows = corpus()
        self.labels = np.array([r["y"] for r in self.rows], dtype=np.float64)
        self.step = np.array([r["step"] for r in self.rows], dtype=np.float64)
        self.group = np.array([r["case"] for r in self.rows])

    def test_a_pure_clock_scores_perfectly_and_residualises_to_chance(self):
        """
        The whole point: a feature that is nothing but the step index looks
        like a perfect board descriptor on this label, and must be revealed
        as chance once the clock is removed. If this ever fails, the
        instrument has stopped protecting against the confound it exists for.
        """
        clock = self.step.copy()
        raw, _ = auc(clock, self.labels)
        self.assertAlmostEqual(raw, 1.0, places=6)
        residual, _ = auc(
            residualise(clock, self.step, self.group), self.labels
        )
        self.assertAlmostEqual(residual, 0.5, places=6)

    def test_signal_on_top_of_the_clock_survives_residualisation(self):
        values = self.step + 5.0 * self.labels
        residual, _ = auc(
            residualise(values, self.step, self.group), self.labels
        )
        self.assertGreater(residual, 0.9)

    def test_residualisation_is_per_case(self):
        # two cases with opposite trends must not cancel into a global fit
        group = np.array(["a"] * 30 + ["b"] * 30)
        step = np.concatenate([np.arange(30.0), np.arange(30.0)])
        values = np.concatenate([step[:30], -step[30:]])
        out = residualise(values, step, group)
        self.assertLess(float(np.abs(out).max()), 1e-6)

    def test_within_step_reports_zero_pairs_when_steps_are_unique(self):
        # the corpus records one row per step, so the confound-free contrast
        # has nothing to work with -- it must say so rather than return 0.5
        values = np.arange(float(len(self.rows)))
        score, pairs = within_step_auc(values, self.labels, self.step, self.group)
        self.assertEqual(pairs, 0)
        self.assertNotEqual(score, score)  # NaN

    def test_within_step_uses_only_same_step_pairs(self):
        labels = np.array([1.0, 0.0, 1.0, 0.0])
        step = np.array([5.0, 5.0, 9.0, 9.0])
        group = np.array(["a", "a", "a", "a"])
        values = np.array([2.0, 1.0, 0.0, 3.0])
        score, pairs = within_step_auc(values, labels, step, group)
        self.assertEqual(pairs, 2)
        self.assertAlmostEqual(score, 0.5)

    def test_auc_reports_no_pairs_when_a_class_is_missing(self):
        score, pairs = auc(np.arange(4.0), np.zeros(4))
        self.assertEqual(pairs, 0)
        self.assertNotEqual(score, score)

    def test_end_to_end_on_a_written_file(self):
        rows = []
        for row in self.rows:
            rows.append({**row, "f": {"clock": float(row["step"])}})
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "rows.jsonl"
            path.write_text(
                "\n".join(json.dumps(r) for r in rows), encoding="utf-8"
            )
            out = pathlib.Path(directory) / "report.json"
            from scripts.measure_step_confound import main

            import sys

            argv = sys.argv
            sys.argv = [
                "measure_step_confound",
                "--rows",
                str(path),
                "--output",
                str(out),
            ]
            try:
                self.assertEqual(main(), 0)
            finally:
                sys.argv = argv
            report = json.loads(out.read_text(encoding="utf-8"))
        self.assertAlmostEqual(report["step_auc"], 1.0, places=6)
        self.assertAlmostEqual(
            report["features"]["clock"]["residual"], 0.5, places=6
        )


if __name__ == "__main__":
    unittest.main()
