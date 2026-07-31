from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

from scripts.run_queue import load_plan, run_plan


def plan_dict(jobs):
    return {"name": "test-plan", "jobs": jobs}


def python_job(job_id, code, **extra):
    return {"id": job_id, "command": [sys.executable, "-c", code], **extra}


class PlanValidationTests(unittest.TestCase):
    def _write(self, tmp, payload):
        path = pathlib.Path(tmp) / "plan.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_valid_plan_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                tmp, plan_dict([python_job("a", "print('x')")])
            )
            plan = load_plan(path)
            self.assertEqual(plan["name"], "test-plan")

    def test_duplicate_ids_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                tmp,
                plan_dict(
                    [python_job("a", "1"), python_job("a", "2")]
                ),
            )
            with self.assertRaises(ValueError):
                load_plan(path)

    def test_non_string_command_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                tmp,
                plan_dict([{"id": "a", "command": ["echo", 1]}]),
            )
            with self.assertRaises(ValueError):
                load_plan(path)


class QueueExecutionTests(unittest.TestCase):
    def test_queue_runs_records_and_resumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue_root = pathlib.Path(tmp)
            marker = queue_root / "ran-count.txt"
            plan = plan_dict(
                [
                    python_job(
                        "ok-job",
                        "import pathlib;"
                        f"p = pathlib.Path({marker.as_posix()!r});"
                        "p.write_text("
                        "str(int(p.read_text()) + 1) "
                        "if p.exists() else '1')",
                    ),
                    python_job("fail-job", "raise SystemExit(3)"),
                ]
            )
            first = run_plan(plan, queue_root=queue_root)
            self.assertEqual(first["ok"], 1)
            self.assertEqual(first["failed"], ["fail-job"])
            self.assertEqual(marker.read_text(), "1")

            second = run_plan(plan, queue_root=queue_root)
            # ok job is skipped on resume, failed job retried.
            self.assertEqual(marker.read_text(), "1")
            self.assertEqual(second["failed"], ["fail-job"])
            state = json.loads(
                (queue_root / "test-plan" / "state.json").read_text()
            )
            self.assertEqual(state["jobs"]["fail-job"]["returncode"], 3)
            log_name = state["jobs"]["ok-job"]["log"]
            self.assertTrue(log_name.endswith("ok-job.log"))

    def test_stop_on_failure_halts_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue_root = pathlib.Path(tmp)
            plan = plan_dict(
                [
                    python_job("boom", "raise SystemExit(1)"),
                    python_job("later", "print('never')"),
                ]
            )
            summary = run_plan(
                plan, queue_root=queue_root, stop_on_failure=True
            )
            self.assertEqual(summary["failed"], ["boom"])
            self.assertEqual(summary["not_run"], ["later"])

    def test_timeout_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue_root = pathlib.Path(tmp)
            plan = plan_dict(
                [
                    python_job(
                        "slow",
                        "import time; time.sleep(5)",
                        timeout_seconds=0.3,
                    )
                ]
            )
            summary = run_plan(plan, queue_root=queue_root)
            self.assertEqual(summary["failed"], ["slow"])
            state = json.loads(
                (queue_root / "test-plan" / "state.json").read_text()
            )
            self.assertEqual(state["jobs"]["slow"]["status"], "timeout")




class ParallelExecutionTests(unittest.TestCase):
    def test_parallel_runs_all_jobs_and_resumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue_root = pathlib.Path(tmp)
            plan = plan_dict(
                [python_job(f"j{i}", "print('x')") for i in range(4)]
            )
            summary = run_plan(plan, queue_root=queue_root, parallel=3)
            self.assertEqual(summary["ok"], 4)
            self.assertEqual(summary["failed"], [])
            again = run_plan(plan, queue_root=queue_root, parallel=3)
            self.assertEqual(again["ok"], 4)

    def test_parallel_records_failures_without_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue_root = pathlib.Path(tmp)
            plan = plan_dict(
                [
                    python_job("ok", "print('x')"),
                    python_job("bad", "raise SystemExit(3)"),
                ]
            )
            summary = run_plan(plan, queue_root=queue_root, parallel=2)
            self.assertEqual(summary["ok"], 1)
            self.assertEqual(summary["failed"], ["bad"])


if __name__ == "__main__":
    unittest.main()
