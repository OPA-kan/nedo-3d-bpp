"""
Sequential, resumable experiment queue.

One launch runs a whole JSON plan of jobs; per-job logs and the queue
state live under reports/raw/queue/<plan-name>/ (gitignored, uploaded by
CI artifact steps where configured). Re-running the same plan skips jobs
that already succeeded, so an interrupted queue continues instead of
restarting -- and an agent driving experiments gets one launch and one
completion summary instead of a notification round-trip per job.

Plan format:

    {
      "name": "replay-gen-20260801",
      "jobs": [
        {
          "id": "b000-k15-late",
          "command": ["python", "scripts/build_replay_dataset.py",
                       "--case", "b000-k15", "--steps", "13", "14"],
          "env": {"RELEASE_RISK_SHADOW_RERANK": "1"},
          "timeout_seconds": 1800
        }
      ]
    }

Commands run from the repository root. ``env`` entries overlay the
inherited environment. A failing or timed-out job is recorded and the
queue continues (use --stop-on-failure to halt instead).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
QUEUE_ROOT = ROOT / "reports" / "raw" / "queue"


def repo_relative(path: pathlib.Path) -> str:
    """Repository-relative when inside the repo, absolute otherwise."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)
DEFAULT_JOB_TIMEOUT_SECONDS = 3600


def load_plan(path: pathlib.Path) -> dict[str, Any]:
    plan = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(plan.get("name"), str) or not plan["name"]:
        raise ValueError("plan needs a non-empty 'name'")
    jobs = plan.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("plan needs a non-empty 'jobs' list")
    seen: set[str] = set()
    for job in jobs:
        job_id = job.get("id")
        if not isinstance(job_id, str) or not job_id:
            raise ValueError("every job needs a non-empty string 'id'")
        if job_id in seen:
            raise ValueError(f"duplicate job id: {job_id}")
        seen.add(job_id)
        command = job.get("command")
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(part, str) for part in command)
        ):
            raise ValueError(f"job {job_id}: 'command' must be a list of strings")
    return plan


def state_path(queue_dir: pathlib.Path) -> pathlib.Path:
    return queue_dir / "state.json"


def load_state(queue_dir: pathlib.Path) -> dict[str, Any]:
    path = state_path(queue_dir)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"jobs": {}}


def save_state(queue_dir: pathlib.Path, state: dict[str, Any]) -> None:
    state_path(queue_dir).write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def run_job(
    job: dict[str, Any],
    queue_dir: pathlib.Path,
) -> dict[str, Any]:
    log_path = queue_dir / f"{job['id']}.log"
    env = os.environ.copy()
    env.update({str(k): str(v) for k, v in (job.get("env") or {}).items()})
    timeout = float(job.get("timeout_seconds", DEFAULT_JOB_TIMEOUT_SECONDS))
    started = time.perf_counter()
    record: dict[str, Any] = {
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(
            timespec="seconds"
        ),
        "command": job["command"],
        "log": repo_relative(log_path),
    }
    with log_path.open("w", encoding="utf-8") as handle:
        try:
            completed = subprocess.run(
                job["command"],
                cwd=ROOT,
                env=env,
                stdout=handle,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
            record["returncode"] = completed.returncode
            record["status"] = "ok" if completed.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            record["returncode"] = None
            record["status"] = "timeout"
        except FileNotFoundError as error:
            record["returncode"] = None
            record["status"] = "failed"
            handle.write(f"launcher error: {error}\n")
    record["seconds"] = round(time.perf_counter() - started, 1)
    return record


def run_plan(
    plan: dict[str, Any],
    *,
    resume: bool = True,
    stop_on_failure: bool = False,
    queue_root: pathlib.Path = QUEUE_ROOT,
) -> dict[str, Any]:
    queue_dir = queue_root / plan["name"]
    queue_dir.mkdir(parents=True, exist_ok=True)
    state = load_state(queue_dir) if resume else {"jobs": {}}

    for job in plan["jobs"]:
        job_id = job["id"]
        previous = state["jobs"].get(job_id)
        if resume and previous and previous.get("status") == "ok":
            print(f"skip (already ok): {job_id}", flush=True)
            continue
        print(f"run: {job_id}", flush=True)
        record = run_job(job, queue_dir)
        state["jobs"][job_id] = record
        save_state(queue_dir, state)
        print(
            f"  -> {record['status']} ({record['seconds']}s, "
            f"log {record['log']})",
            flush=True,
        )
        if stop_on_failure and record["status"] != "ok":
            break

    summary = {
        "name": plan["name"],
        "total": len(plan["jobs"]),
        "ok": sum(
            1
            for job in plan["jobs"]
            if state["jobs"].get(job["id"], {}).get("status") == "ok"
        ),
        "failed": [
            job["id"]
            for job in plan["jobs"]
            if state["jobs"].get(job["id"], {}).get("status")
            in {"failed", "timeout"}
        ],
        "not_run": [
            job["id"]
            for job in plan["jobs"]
            if job["id"] not in state["jobs"]
        ],
        "state": repo_relative(state_path(queue_dir)),
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=pathlib.Path, help="JSON plan file.")
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore previous state and rerun every job.",
    )
    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="Halt the queue at the first non-ok job.",
    )
    args = parser.parse_args()
    try:
        plan = load_plan(args.plan)
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as error:
        raise SystemExit(f"invalid plan: {error}") from error
    summary = run_plan(
        plan,
        resume=not args.no_resume,
        stop_on_failure=args.stop_on_failure,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not summary["failed"] and not summary["not_run"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
