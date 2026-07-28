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


def load_json(path: pathlib.Path) -> Any:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


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
        if process_ok and physics_ok:
            simulator_status = "PASS"
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
    lines.extend(
        [
            "",
            "## Captured output",
            "",
            "<details><summary>unit tests</summary>",
            "",
            "```text",
            (tests["stdout"] + tests["stderr"]).strip(),
            "```",
            "</details>",
        ]
    )
    if simulator is not None:
        lines.extend(
            [
                "",
                "<details><summary>simulator</summary>",
                "",
                "```text",
                (simulator["stdout"] + simulator["stderr"]).strip(),
                "```",
                "</details>",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulator", action="store_true")
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
        payload["simulator_validation"] = evaluation_passed(payload["evaluation"])

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
    simulator_ok = (
        payload.get("simulator", {}).get("returncode", 0) == 0
        and payload.get("simulator_validation", True)
    )
    print(latest_md)
    return 0 if test_ok and simulator_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
