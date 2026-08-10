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
    board: int = 0,
) -> None:
    """``board`` moves the placed items, i.e. makes it a different state."""
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
            json.dumps(
                {
                    "case_id": case_id,
                    "step": step,
                    "physics": {
                        "packed_items": [
                            {
                                "container_index": 0,
                                "item_index": index,
                                "position": [0.1 * index + board, 0.0, 0.5],
                            }
                            for index in range(step)
                        ]
                    },
                    "observation": {
                        "pool_list": [{"index": step + 1}, {"index": step + 2}]
                    },
                }
            ),
            encoding="utf-8",
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

    def test_two_runs_of_one_scenario_are_counted_as_different_states(self):
        # The defect this exists for: the policy is deadline-limited, so the
        # same (case, step) label is a different board on each run. Counting
        # labels would say a re-run adds nothing.
        for index, run in enumerate(("run-1", "run-2")):
            write_dataset(
                self.run_dir(run) / "alpha",
                case_id="m-alpha",
                steps=[3, 9],
                swap_rounds=64,
                positives=5,
                board=index,
            )

        summary = summarize(scan_runs(self.root))

        self.assertEqual(summary["runs"], 2)
        self.assertEqual(summary["rows_all_runs"]["positive_transition"], 20)
        self.assertEqual(summary["case_step_slots"], 2)
        self.assertEqual(summary["distinct_states"], 4)
        self.assertEqual(summary["states_shared_by_more_than_one_run"], 0)
        self.assertEqual(summary["slots"], ["m-alpha:003", "m-alpha:009"])

    def test_two_runs_that_land_on_one_board_are_not_counted_twice(self):
        for run in ("run-1", "run-2"):
            write_dataset(
                self.run_dir(run) / "alpha",
                case_id="m-alpha",
                steps=[3],
                swap_rounds=64,
                positives=5,
                board=0,
            )

        summary = summarize(scan_runs(self.root))

        self.assertEqual(summary["distinct_states"], 1)
        self.assertEqual(summary["states_shared_by_more_than_one_run"], 1)

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
            board=1,
        )

        summary = summarize(scan_runs(self.root))

        self.assertEqual(sorted(summary["by_arm"]), ["0", "64"])
        self.assertEqual(
            summary["by_arm"]["0"]["rows"]["positive_transition"], 6
        )
        self.assertEqual(
            summary["by_arm"]["64"]["rows"]["positive_transition"], 6
        )
        self.assertEqual(summary["by_arm"]["0"]["distinct_states"], 1)
        self.assertEqual(summary["by_arm"]["64"]["distinct_states"], 1)
        self.assertEqual(summary["distinct_states"], 2)

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


class IncompleteRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_an_unfinished_dataset_is_named_not_absorbed(self):
        # A cancelled scenario job still uploads what it wrote. The rows are
        # labelled correctly, so they are kept -- but a corpus that counts
        # them silently reports partial coverage as a finished run.
        dataset = self.root / "run-1" / "dataset"
        write_dataset(
            dataset / "alpha",
            case_id="m-alpha",
            steps=[3],
            swap_rounds=64,
            positives=4,
        )
        manifest = json.loads(
            (dataset / "alpha" / "manifest.json").read_text(encoding="utf-8")
        )
        manifest["status"] = "running"
        (dataset / "alpha" / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

        summary = summarize(scan_runs(self.root))

        self.assertEqual(
            summary["runs_with_incomplete_datasets"], ["run-1"]
        )
        self.assertEqual(summary["rows_all_runs"]["positive_transition"], 4)
        self.assertIn("(partial)", markdown(summary))

    def test_a_finished_run_is_not_marked_partial(self):
        write_dataset(
            self.root / "run-1" / "dataset" / "alpha",
            case_id="m-alpha",
            steps=[3],
            swap_rounds=64,
            positives=4,
        )

        summary = summarize(scan_runs(self.root))

        self.assertEqual(summary["runs_with_incomplete_datasets"], [])
        self.assertNotIn("(partial)", markdown(summary))


if __name__ == "__main__":
    unittest.main()
