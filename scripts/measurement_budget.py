"""
Warn when a line of work burns episodes without producing a shipping change.

Measurement is cheap to justify one experiment at a time and expensive in
aggregate. A session can run a hundred episodes, correct itself four times,
and end with nothing that changes what the agent does - each step defensible,
the total not. This makes that ratio visible while it is still happening
rather than in a retrospective.

The counter increments **automatically** from the episode runners; only a
person can add a candidate. So a line that keeps measuring degrades its own
ratio without anyone having to notice, and the warning fires at the moment of
maximum attention - inside the run that crossed the threshold.

## What counts as a shipping candidate

Deliberately strict, because a loose definition makes this decoration:

* a named, concrete change to `agent/agent.py` that alters **default**
  behaviour - a constant, a knob default, or a code path;
* with a paired measurement behind it.

These do **not** count: a new measurement script, a default-off knob, a
ledger entry, an instrument repair, a negative result, or "we learned that".
Those may all be valuable, and none of them changes what ships.

## What the warning means

Not "stop". It means: state, explicitly, why this line still deserves
episodes. A line can legitimately keep going - a hard negative can be worth
a hundred episodes - but it should be a decision made out loud rather than
by momentum.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEDGER = ROOT / "context" / "measurement_budget.json"
DEFAULT_THRESHOLD = 10
LINE_ENV = "MEASUREMENT_LINE"

CONTRACT = {
    "purpose": (
        "Make the episodes-spent to shipping-changes ratio visible while a "
        "line of work is still running."
    ),
    "shipping_candidate": (
        "A named concrete change to agent/agent.py that alters DEFAULT "
        "behaviour, with a paired measurement behind it. A new script, a "
        "default-off knob, a ledger entry, an instrument repair or a "
        "negative result does not count."
    ),
    "on_warning": (
        "Not an instruction to stop. State explicitly why the line still "
        "deserves episodes; a hard negative can be worth a hundred."
    ),
    "counter": (
        "Episodes are recorded by the runners; candidates are added by hand. "
        "A line that keeps measuring degrades its own ratio unattended."
    ),
}


def load() -> dict[str, Any]:
    if LEDGER.exists():
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    return {
        "version": 1,
        "contract": CONTRACT,
        "threshold_episodes": DEFAULT_THRESHOLD,
        "lines": {},
    }


def save(data: dict[str, Any]) -> None:
    data["contract"] = CONTRACT
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def line_status(data: dict[str, Any], name: str) -> dict[str, Any]:
    entry = data["lines"].get(name)
    if entry is None:
        return {"line": name, "known": False}
    threshold = int(data.get("threshold_episodes", DEFAULT_THRESHOLD))
    episodes = int(entry.get("episodes", 0))
    # Retracted candidates stay on the record but stop clearing the
    # warning. A candidate whose measurement did not survive replication
    # is not a change this line produced, and leaving it counted would
    # silence the budget for good on work that shipped nothing.
    candidates = entry.get("shipping_candidates", [])
    return {
        "line": name,
        "known": True,
        "episodes": episodes,
        "candidates": len(candidates),
        "threshold": threshold,
        "over_budget": episodes >= threshold and not candidates,
    }


def warn(status: dict[str, Any], stream=sys.stderr) -> None:
    print(
        "\n".join(
            [
                "",
                "=" * 68,
                f"MEASUREMENT BUDGET WARNING: line '{status['line']}'",
                f"  {status['episodes']} episodes spent, "
                f"{status['candidates']} shipping-change candidates "
                f"(threshold {status['threshold']}).",
                "  A shipping candidate is a concrete change to the DEFAULT",
                "  behaviour of agent/agent.py with a paired measurement.",
                "  Scripts, default-off knobs and negative results do not",
                "  count.",
                "",
                "  This is not an instruction to stop. State why this line",
                "  still deserves episodes, or move to one that can produce",
                "  a change.",
                "=" * 68,
                "",
            ]
        ),
        file=stream,
    )


def record(name: str, episodes: int, *, quiet: bool = False) -> dict[str, Any]:
    data = load()
    entry = data["lines"].setdefault(
        name,
        {
            "opened": dt.date.today().isoformat(),
            "episodes": 0,
            "shipping_candidates": [],
        },
    )
    entry["episodes"] = int(entry.get("episodes", 0)) + max(0, int(episodes))
    entry["last_recorded"] = dt.date.today().isoformat()
    save(data)
    status = line_status(data, name)
    if status["over_budget"] and not quiet:
        warn(status)
    return status


def record_from_env(episodes: int = 1) -> dict[str, Any] | None:
    """Runner hook: no-op unless the caller named a line."""
    name = os.environ.get(LINE_ENV, "").strip()
    if not name:
        return None
    return record(name, episodes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_record = sub.add_parser("record", help="add episodes to a line")
    p_record.add_argument("--line", required=True)
    p_record.add_argument("--episodes", type=int, default=1)

    p_cand = sub.add_parser(
        "candidate", help="register a shipping-change candidate"
    )
    p_cand.add_argument("--line", required=True)
    p_cand.add_argument(
        "--change", required=True,
        help="the concrete default-behaviour change in agent/agent.py",
    )
    p_cand.add_argument(
        "--evidence", required=True, help="the paired measurement behind it"
    )

    p_retract = sub.add_parser(
        "retract",
        help="a registered candidate did not survive; move it to the record",
    )
    p_retract.add_argument("--line", required=True)
    p_retract.add_argument(
        "--index", type=int, default=-1,
        help="which shipping candidate to retract (default: the last)",
    )
    p_retract.add_argument(
        "--reason", required=True,
        help="what the follow-up measurement showed",
    )

    p_check = sub.add_parser("check", help="report every line")
    p_check.add_argument(
        "--fail-on-warning", action="store_true",
        help="exit non-zero when any line is over budget",
    )

    p_open = sub.add_parser("open", help="declare a new line")
    p_open.add_argument("--line", required=True)
    p_open.add_argument("--note", default="")

    args = parser.parse_args()
    data = load()

    if args.command == "open":
        data["lines"].setdefault(
            args.line,
            {
                "opened": dt.date.today().isoformat(),
                "episodes": 0,
                "shipping_candidates": [],
            },
        )["note"] = args.note
        save(data)
        print(f"opened line: {args.line}")
        return 0

    if args.command == "record":
        status = record(args.line, args.episodes)
        print(json.dumps(status, indent=2))
        return 0

    if args.command == "candidate":
        entry = data["lines"].setdefault(
            args.line,
            {
                "opened": dt.date.today().isoformat(),
                "episodes": 0,
                "shipping_candidates": [],
            },
        )
        entry["shipping_candidates"].append(
            {
                "date": dt.date.today().isoformat(),
                "change": args.change,
                "evidence": args.evidence,
                "episodes_at_registration": int(entry.get("episodes", 0)),
            }
        )
        save(data)
        print(f"registered candidate on '{args.line}'")
        return 0

    if args.command == "retract":
        entry = data["lines"].get(args.line)
        if entry is None or not entry.get("shipping_candidates"):
            raise SystemExit(f"no candidate to retract on '{args.line}'")
        candidate = entry["shipping_candidates"].pop(args.index)
        candidate["retracted"] = dt.date.today().isoformat()
        candidate["retraction_reason"] = args.reason
        entry.setdefault("retracted_candidates", []).append(candidate)
        save(data)
        status = line_status(data, args.line)
        print(f"retracted on '{args.line}': {candidate['change']}")
        if status["over_budget"]:
            warn(status, stream=sys.stdout)
        return 0

    over = []
    print(f"threshold: {data.get('threshold_episodes', DEFAULT_THRESHOLD)} "
          "episodes without a shipping candidate")
    for name in sorted(data["lines"]):
        status = line_status(data, name)
        flag = "  <-- OVER BUDGET" if status["over_budget"] else ""
        print(
            f"  {name:38} episodes={status['episodes']:>4} "
            f"candidates={status['candidates']}{flag}"
        )
        if status["over_budget"]:
            over.append(status)
    for status in over:
        warn(status, stream=sys.stdout)
    return 1 if (over and args.fail_on_warning) else 0


if __name__ == "__main__":
    raise SystemExit(main())
