"""Prepare one preregistered Diversity Cup dispatch from repository state.

This is the machine-readable half of ``cup-hosting-runbook.md``.  It resolves
the current promoted champion, allocates six unused source-specific streams,
appends the ledger row *before* dispatch, and emits the workflow inputs.  It
does not call GitHub itself; the one-click hosting workflow owns commit/push
and dispatch so the preregistration ordering remains inspectable.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

COURSE_PATTERN = (
    ("dual-preloaded-dedicated", "000"),
    ("dual-empty", "000"),
    ("single-empty-noshelf", "000"),
    ("dual-shelf-mixed", "001"),
    ("single-empty-shelf", "001"),
    ("single-preloaded", "000"),
)
LEDGER_ROW = re.compile(r"^\|\s*(\d{3})\s*\|", re.MULTILINE)
SOURCE_PRIMES = re.compile(
    r"000:\s*([0-9,]+)\s*·\s*001:\s*([0-9,]+)"
)
PENDING_LEDGER_ROW = re.compile(
    r"^\|\s*\d{3}\s*\|.*\|\s*pending\s*\|\s*pending\s*\|\s*pending\s*\|",
    re.MULTILINE,
)


def resolve_champion(state: dict[str, Any]) -> tuple[str, str]:
    champion = str(state.get("champion") or "")
    for row in reversed(state.get("history") or []):
        if (
            bool(row.get("promoted"))
            and str(row.get("champion_after")) == champion
        ):
            learning = str((row.get("runs") or {}).get("learning") or "")
            if learning:
                return champion, learning
    raise ValueError(
        f"no promoted history row resolves champion model: {champion!r}"
    )


def next_cup_id(ledger_text: str) -> str:
    values = [int(value) for value in LEDGER_ROW.findall(ledger_text)]
    return f"{(max(values) if values else 0) + 1:03d}"


def _available_primes() -> dict[str, list[int]]:
    from scripts.build_scenario_matrix import STREAM_VARIANTS

    result = {"000": [], "001": []}
    for variant in STREAM_VARIANTS:
        match = re.fullmatch(r"permute-(000|001)-(\d+)", variant)
        if match and 401 <= int(match.group(2)) <= 599:
            result[match.group(1)].append(int(match.group(2)))
    return {source: sorted(set(values)) for source, values in result.items()}


def used_primes(ledger_text: str) -> dict[str, set[int]]:
    used = {"000": set(), "001": set()}
    for match in SOURCE_PRIMES.finditer(ledger_text):
        for source, group in (("000", match.group(1)), ("001", match.group(2))):
            used[source].update(
                int(value) for value in group.split(",") if value.strip()
            )
    return used


def allocate_course(ledger_text: str) -> list[dict[str, str]]:
    available = _available_primes()
    used = used_primes(ledger_text)
    remaining = {
        source: [value for value in available[source] if value not in used[source]]
        for source in available
    }
    required = {
        source: sum(1 for _scenario, row_source in COURSE_PATTERN
                    if row_source == source)
        for source in remaining
    }
    for source, count in required.items():
        if len(remaining[source]) < count:
            raise ValueError(
                f"Diversity Cup stream pool exhausted for source {source}: "
                f"need {count}, have {len(remaining[source])}"
            )
    offsets = {"000": 0, "001": 0}
    course = []
    for scenario, source in COURSE_PATTERN:
        prime = remaining[source][offsets[source]]
        offsets[source] += 1
        stream = f"permute-{source}-{prime}"
        course.append({
            "cell": f"{scenario}-{stream}",
            "scenario": scenario,
            "stream": stream,
        })
    return course


def _display_name(champion: str, names: dict[str, Any] | None) -> str:
    entries = (names or {}).get("names") or {}
    if champion in entries:
        return str(entries[champion].get("name") or champion)
    match = re.search(r"-w(\d+)$", champion)
    if match and f"w{match.group(1)}" in entries:
        return str(entries[f"w{match.group(1)}"].get("name") or champion)
    return champion


def preregister(
    ledger_path: pathlib.Path,
    state: dict[str, Any],
    *,
    date: str,
    display_name: str | None = None,
    model_run_id: str | None = None,
    cup_id: str | None = None,
) -> dict[str, Any]:
    text = ledger_path.read_text(encoding="utf-8")
    if PENDING_LEDGER_ROW.search(text):
        raise ValueError(
            "cup ledger already contains a pending preregistration; "
            "finish or recover it before allocating another course"
        )
    champion, resolved_run = resolve_champion(state)
    run_id = str(model_run_id or resolved_run)
    next_id = next_cup_id(text)
    selected_id = str(cup_id or next_id).zfill(3)
    if selected_id != next_id:
        raise ValueError(
            f"cup id must be the next ledger id {next_id}, got {selected_id}"
        )
    course = allocate_course(text)
    by_source = {"000": [], "001": []}
    for row in course:
        source, prime = row["stream"].split("-")[1:]
        by_source[source].append(int(prime))
    streams = (
        "000: " + ",".join(map(str, by_source["000"]))
        + " · 001: " + ",".join(map(str, by_source["001"]))
    )
    row = (
        f"| {selected_id} | {date} | {run_id} | {champion} "
        f"{display_name or champion} | {streams} | pending | pending | "
        "pending | preregistered six-horse field incl current-agent and "
        "rule-alpha@7908b09 |\n"
    )
    marker = "\nPool allocation note:"
    if marker not in text:
        raise ValueError("cup ledger footer marker is missing")
    ledger_path.write_text(
        text.replace(marker, "\n" + row + marker, 1),
        encoding="utf-8",
    )
    return {
        "cup_id": selected_id,
        "champion": champion,
        "model_run_id": run_id,
        "cells": course,
        "cells_json": json.dumps(
            course, ensure_ascii=False, separators=(",", ":")
        ),
    }


def _write_github_output(path: pathlib.Path, result: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for key in ("cup_id", "champion", "model_run_id", "cells_json"):
            handle.write(f"{key}={result[key]}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ledger", type=pathlib.Path,
        default=ROOT / "reports" / "league" / "cup-ledger.md",
    )
    parser.add_argument(
        "--state", type=pathlib.Path,
        default=ROOT / "reports" / "league" / "season" / "state.json",
    )
    parser.add_argument(
        "--names", type=pathlib.Path,
        default=ROOT / "reports" / "league" / "spectator" / "names.json",
    )
    parser.add_argument("--model-run-id", default=None)
    parser.add_argument("--cup-id", default=None)
    parser.add_argument("--date", default=dt.date.today().isoformat())
    parser.add_argument("--github-output", type=pathlib.Path, default=None)
    args = parser.parse_args()
    state = json.loads(args.state.read_text(encoding="utf-8"))
    names = json.loads(args.names.read_text(encoding="utf-8"))
    result = preregister(
        args.ledger,
        state,
        date=args.date,
        display_name=_display_name(str(state.get("champion")), names),
        model_run_id=args.model_run_id,
        cup_id=args.cup_id,
    )
    if args.github_output is not None:
        _write_github_output(args.github_output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
