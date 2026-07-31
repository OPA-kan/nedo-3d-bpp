from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import time
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
AGENT = ROOT / "agent" / "agent.py"
SIMULATOR = ROOT / "simulator"


def run(command: list[str], cwd: pathlib.Path, env: dict[str, str] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    return {
        "command": command,
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "seconds": round(time.perf_counter() - started, 3),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def git_sha() -> str | None:
    result = run(["git", "rev-parse", "HEAD"], ROOT)
    return result["stdout"].strip() if result["returncode"] == 0 else None


LOG_TAIL_LINES = 30


def externalize_output(step_payload, name, raw_dir) -> None:
    """
    Move a step's captured stdout/stderr into reports/raw/<name>.log
    (gitignored; uploaded as a CI artifact) and keep only a short tail in
    the committed payload. Full logs belong in artifacts, not in git:
    before this, every latest.json committed ~45 KB of raw test output.
    """
    if not isinstance(step_payload, dict):
        return
    combined = (
        step_payload.get("stdout", "") + step_payload.get("stderr", "")
    ).strip()
    raw_dir.mkdir(parents=True, exist_ok=True)
    log_path = raw_dir / f"{name}.log"
    log_path.write_text(combined + "\n", encoding="utf-8")
    tail_lines = combined.splitlines()[-LOG_TAIL_LINES:]
    step_payload["stdout"] = ""
    step_payload["stderr"] = ""
    step_payload["log_path"] = log_path.relative_to(ROOT).as_posix()
    step_payload["log_tail"] = "\n".join(tail_lines)


def load_json(path: pathlib.Path) -> Any:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def unit_test_environment() -> dict[str, str]:
    """Keep unit tests independent of simulator experiment controls."""
    env = os.environ.copy()
    for name in (
        "NEDO_POLICY_TRACE_PATH",
        "LOOKAHEAD_SELECTION_MODE",
        "ITEM_COVERAGE_MODE",
        "RELEASE_RISK_GATE_MODE",
    ):
        env.pop(name, None)
    return env


def evaluation_passed(evaluation: Any) -> bool:
    if not isinstance(evaluation, dict) or not evaluation:
        return False
    required_states = ("is_included", "is_valid", "is_placed_safe")
    for case in evaluation.values():
        if not isinstance(case, dict) or case.get("status") != "success":
            return False
        states = case.get("place_states")
        if not isinstance(states, dict):
            return False
        if not all(states.get(name) is True for name in required_states):
            return False
    return True


def evaluation_completed(evaluation: Any) -> bool:
    """Return whether the simulator produced structurally valid case results."""
    if not isinstance(evaluation, dict) or not evaluation:
        return False
    required_states = ("is_included", "is_valid", "is_placed_safe")
    for case in evaluation.values():
        if not isinstance(case, dict) or case.get("status") != "success":
            return False
        score = case.get("evaluation")
        if not isinstance(score, dict):
            return False
        if not isinstance(score.get("fill_score"), (int, float)):
            return False
        if not isinstance(score.get("num_placed_items"), (int, float)):
            return False
        if not isinstance(score.get("step_metrics"), list):
            return False
        states = case.get("place_states")
        if not isinstance(states, dict):
            return False
        if not all(isinstance(states.get(name), bool) for name in required_states):
            return False
        time_results = case.get("time_results")
        if not isinstance(time_results, dict):
            return False
        if not all(
            isinstance(time_results.get(name), (int, float))
            for name in ("optimization", "policy")
        ):
            return False
    return True


def simulator_result_passed(
    *,
    simulator_returncode: int,
    evaluation: Any,
    mode: str,
) -> bool:
    if simulator_returncode != 0:
        return False
    if mode == "strict":
        return evaluation_completed(evaluation) and evaluation_passed(evaluation)
    if mode == "benchmark":
        return evaluation_completed(evaluation)
    raise ValueError(f"unknown simulator mode: {mode}")


def report_markdown(payload: dict[str, Any]) -> str:
    tests = payload["tests"]
    simulator = payload.get("simulator")

    def display_command(command: list[str]) -> str:
        if command and pathlib.Path(command[0]).resolve() == pathlib.Path(sys.executable).resolve():
            command = ["python", *command[1:]]
        return " ".join(command)

    lines = [
        "# CPU verification report",
        "",
        f"- Timestamp: `{payload['timestamp']}`",
        f"- Git SHA: `{payload.get('git_sha') or 'uncommitted/no repository'}`",
        f"- Python: `{payload['environment']['python']}`",
        f"- Platform: `{payload['environment']['platform']}`",
        f"- Processor: `{payload['environment']['processor'] or 'unknown'}`",
        "",
        "## Unit tests",
        "",
        f"- Status: `{'PASS' if tests['returncode'] == 0 else 'FAIL'}`",
        f"- Runtime: `{tests['seconds']} s`",
        f"- Command: `{display_command(tests['command'])}`",
    ]
    if simulator is None:
        lines.extend(["", "## Simulator", "", "- Status: `SKIPPED`"])
    else:
        process_ok = simulator["returncode"] == 0
        physics_ok = payload.get("simulator_validation") is True
        execution_ok = payload.get("simulator_execution_valid") is True
        simulator_mode = payload.get("simulator_mode", "strict")
        if process_ok and not execution_ok:
            simulator_status = "FAIL (invalid evaluation result)"
        elif process_ok and physics_ok:
            simulator_status = "PASS"
        elif process_ok and execution_ok and simulator_mode == "benchmark":
            simulator_status = "BENCHMARK COMPLETE (packing incomplete)"
        elif process_ok:
            simulator_status = "FAIL (physics validation)"
        else:
            simulator_status = "FAIL (process)"
        lines.extend(
            [
                "",
                "## Simulator",
                "",
                f"- Status: `{simulator_status}`",
                f"- Exit policy: `{simulator_mode}`",
                f"- Runtime: `{simulator['seconds']} s`",
                f"- Command: `{display_command(simulator['command'])}`",
                "",
                "### Evaluation JSON",
                "",
                "```json",
                json.dumps(payload.get("evaluation"), ensure_ascii=False, indent=2),
                "```",
            ]
        )
    lines.extend(["", "## Captured output"])
    for name, step in (("unit tests", tests), ("simulator", simulator)):
        if step is None:
            continue
        if "log_tail" in step:
            body = step["log_tail"]
            location = step.get("log_path", "reports/raw/")
            summary = f"{name} (tail; full log: {location})"
        else:
            body = (step["stdout"] + step["stderr"]).strip()
            summary = name
        lines.extend(
            [
                "",
                f"<details><summary>{summary}</summary>",
                "",
                "```text",
                body,
                "```",
                "</details>",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulator", action="store_true")
    parser.add_argument(
        "--simulator-mode",
        choices=("strict", "benchmark"),
        default="strict",
        help=(
            "strict requires every case's final placement to be safe; "
            "benchmark accepts incomplete packing when execution and result "
            "structure are valid"
        ),
    )
    parser.add_argument("--keep-history", action="store_true")
    parser.add_argument(
        "--config",
        type=pathlib.Path,
        default=SIMULATOR / "configs" / "sample_config.json",
    )
    args = parser.parse_args()

    REPORTS.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    payload: dict[str, Any] = {
        "timestamp": timestamp,
        "git_sha": git_sha(),
        "environment": {
            "python": sys.version.replace("\n", " "),
            "platform": platform.platform(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
        },
    }

    payload["tests"] = run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        ROOT,
        unit_test_environment(),
    )

    if args.simulator:
        shutil.copy2(AGENT, SIMULATOR / "agent.py")
        raw_dir = REPORTS / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        result_name = "evaluation_results.json"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SIMULATOR)
        payload["simulator"] = run(
            [
                sys.executable,
                "scripts/run_test.py",
                "--config-path",
                str(args.config.resolve()),
                "--module-path",
                "",
                "--result-dir",
                str(raw_dir.resolve()),
                "--result-fname",
                result_name,
            ],
            SIMULATOR,
            env,
        )
        payload["evaluation"] = load_json(raw_dir / result_name)
        payload["simulator_execution_valid"] = evaluation_completed(
            payload["evaluation"]
        )
        payload["simulator_validation"] = (
            payload["simulator_execution_valid"]
            and evaluation_passed(payload["evaluation"])
        )
        payload["simulator_mode"] = args.simulator_mode

    raw_dir = REPORTS / "raw"
    externalize_output(payload.get("tests"), "unit-tests", raw_dir)
    externalize_output(payload.get("simulator"), "simulator", raw_dir)

    latest_json = REPORTS / "latest.json"
    latest_md = REPORTS / "latest.md"
    latest_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    latest_md.write_text(report_markdown(payload), encoding="utf-8")

    if args.keep_history:
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        history = REPORTS / "history"
        history.mkdir(parents=True, exist_ok=True)
        shutil.copy2(latest_json, history / f"{stamp}.json")
        shutil.copy2(latest_md, history / f"{stamp}.md")

    test_ok = payload["tests"]["returncode"] == 0
    simulator_ok = True
    if args.simulator:
        simulator_ok = simulator_result_passed(
            simulator_returncode=payload["simulator"]["returncode"],
            evaluation=payload.get("evaluation"),
            mode=args.simulator_mode,
        )
    print(latest_md)
    return 0 if test_ok and simulator_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
