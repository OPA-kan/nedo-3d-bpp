from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
TASK_B_WORKFLOW = ROOT / ".github" / "workflows" / "task-b-benchmark.yml"
CPU_WORKFLOW = ROOT / ".github" / "workflows" / "cpu-ci.yml"


class TaskBAggregatePersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.task_b = TASK_B_WORKFLOW.read_text(encoding="utf-8")
        cls.cpu = CPU_WORKFLOW.read_text(encoding="utf-8")

    def test_only_the_aggregate_job_gets_write_permission(self) -> None:
        self.assertIn("permissions:\n  contents: read", self.task_b)
        aggregate = self.task_b.split("\n  aggregate:\n", 1)[1]
        self.assertIn("    permissions:\n      contents: write", aggregate)

    def test_compact_aggregate_is_saved_by_run_id_on_the_live_trunk(
        self,
    ) -> None:
        self.assertIn(
            "if: github.ref == 'refs/heads/experiment/anchor-recall-oracle'",
            self.task_b,
        )
        self.assertIn(
            "HISTORY_DIR: reports/task-b/history/${{ github.run_id }}",
            self.task_b,
        )
        self.assertIn('"$HISTORY_DIR/aggregate.md"', self.task_b)
        self.assertIn('"$HISTORY_DIR/aggregate.json"', self.task_b)

    def test_push_conflicts_fetch_rebase_and_retry(self) -> None:
        self.assertIn('git fetch origin "$GITHUB_REF_NAME"', self.task_b)
        self.assertIn('git rebase "origin/$GITHUB_REF_NAME"', self.task_b)
        self.assertIn(
            'git push origin "HEAD:$GITHUB_REF_NAME"',
            self.task_b,
        )

    def test_reusable_workflow_caller_grants_write_permission(self) -> None:
        caller = self.cpu.split("\n  task-b-benchmark:\n", 1)[1]
        self.assertIn("    permissions:\n      contents: write", caller)


if __name__ == "__main__":
    unittest.main()
