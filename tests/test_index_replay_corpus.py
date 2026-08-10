from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from scripts.index_replay_corpus import markdown, scan_runs, summarize


def write_dataset(
    directory: pathlib.Path,
    *,
    case_id: str,
    steps: list[int],
    swap_rounds: int,
    positives: int,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 3,
                "dataset_id": f"{case_id}-{swap_rounds}",
                "status": "complete",
                "sampling_mode": "residual_diversity_safe_split",
                "overdraw_factor": 3,
                "observed_swap_rounds": swap_rounds,
                "split": "development",
                "case": {
                    "case_id": case_id,
                    "steps": [{"step": step} for step in steps],
                },
            }
        ),
        encoding="utf-8",
    )
    for step in steps:
        (directory / f"step-{step:03d}-state.json").write_text(
            "{}", encoding="utf-8"
        )
        (directory / f"step-{step:03d}-candidates.jsonl").write_text(
            "".join('{"a":1}\n' for _ in range(positives)), encoding="utf-8"
        )
        (directory / f"step-{step:03d}-negative-risk.jsonl").write_text(
            '{"a":0}\n\n', encoding="utf-8"
        )
        (directory / f"step-{step:03d}-random-control.jsonl").write_text(
            '{"a":2}\n', encoding="utf-8"
        )


class CorpusIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def run_dir(self, name: str, verdict: str = "pass") -> pathlib.Path:
        path = self.root / name
        path.mkdir(parents=True, exist_ok=True)
        (path / "summary.json").write_text(
            json.dumps({"acceptance": {"verdict": verdict}}),
            encoding="utf-8",
        )
        return path / "dataset"

    def test_rows_add_up_across_runs_but_distinct_states_do_not(self):
        for run in ("run-1", "run-2"):
            write_dataset(
                self.run_dir(run) / "alpha",
                case_id="m-alpha",
                steps=[3, 9],
                swap_rounds=64,
                positives=5,
            )

        summary = summarize(scan_runs(self.root))

        self.assertEqual(summary["runs"], 2)
        self.assertEqual(summary["rows_all_runs"]["positive_transition"], 20)
        # The same two (case, step) pairs, measured twice.
        self.assertEqual(summary["distinct_states"], 2)
        self.assertEqual(summary["states"], ["m-alpha:003", "m-alpha:009"])

    def test_blank_lines_are_not_counted_as_rows(self):
        write_dataset(
            self.run_dir("run-1") / "alpha",
            case_id="m-alpha",
            steps=[3],
            swap_rounds=64,
            positives=4,
        )

        summary = summarize(scan_runs(self.root))

        self.assertEqual(
            summary["rows_all_runs"]["negative_physical_risk"], 1
        )

    def test_arms_are_counted_separately_and_never_merged(self):
        write_dataset(
            self.run_dir("seeded") / "alpha",
            case_id="m-alpha",
            steps=[3],
            swap_rounds=64,
            positives=6,
        )
        write_dataset(
            self.run_dir("ablation") / "alpha",
            case_id="m-alpha",
            steps=[3],
            swap_rounds=0,
            positives=6,
        )

        summary = summarize(scan_runs(self.root))

        self.assertEqual(sorted(summary["by_arm"]), ["0", "64"])
        self.assertEqual(
            summary["by_arm"]["0"]["rows"]["positive_transition"], 6
        )
        self.assertEqual(
            summary["by_arm"]["64"]["rows"]["positive_transition"], 6
        )
        self.assertEqual(summary["distinct_states"], 1)

    def test_a_run_whose_scenarios_disagree_about_the_arm_is_flagged(self):
        dataset = self.run_dir("mixed")
        write_dataset(
            dataset / "alpha",
            case_id="m-alpha",
            steps=[3],
            swap_rounds=64,
            positives=2,
        )
        write_dataset(
            dataset / "beta",
            case_id="m-beta",
            steps=[3],
            swap_rounds=0,
            positives=2,
        )

        summary = summarize(scan_runs(self.root))

        run = summary["run_index"][0]
        self.assertFalse(run["uniform_arm"])
        self.assertIsNone(run["observed_swap_rounds"])
        self.assertIn("**mixed**", markdown(summary))

    def test_a_run_directory_without_rows_is_skipped(self):
        path = self.root / "summary-only"
        path.mkdir(parents=True)
        (path / "summary.json").write_text("{}", encoding="utf-8")

        self.assertEqual(scan_runs(self.root), [])


if __name__ == "__main__":
    unittest.main()
