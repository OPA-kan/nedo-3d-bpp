"""State and reporting contracts for the preregistered league season.

This module is intentionally network-free.  GitHub Actions owns dispatching
the expensive collection/training/match workflows; this file makes every
round transition deterministic, reviewable and idempotent.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import pathlib
from typing import Any


STATE_CONTRACT = "league_season_state_v1"


def champion(registry: dict[str, Any]) -> dict[str, Any]:
    rows = [m for m in registry["members"] if m.get("role") == "champion"]
    if len(rows) != 1:
        raise ValueError(f"expected one champion, found {len(rows)}")
    return rows[0]


def challenger_identity(
    registry: dict[str, Any], wave: str | int, names: dict[str, Any]
) -> dict[str, Any]:
    wave = str(wave)
    generation = int(registry["generation_counter"]) + 1
    display = names.get("names", {}).get(f"w{wave}", {})
    return {
        "id": f"pi{generation}-pref-w{wave}",
        "display_name": display.get("name", f"wave {wave} challenger"),
        "generation": generation,
        "wave": int(wave),
    }


def _counts(report: dict[str, Any]) -> dict[str, int]:
    raw = report["matches"][report["champion"]]["counts"]
    return {
        "wins": int(raw.get("challenger_wins", 0)),
        "losses": int(raw.get("member_wins", 0)),
        "equal": int(raw.get("equal", 0)),
        "incomparable": int(raw.get("incomparable", 0)),
    }


def _benchmark(report: dict[str, Any]) -> str:
    standings = [
        row.get("standing", "unreported")
        for row in report.get("benchmarks", {}).values()
    ]
    return standings[0] if standings else "unreported"


def finish_round(
    *,
    state: dict[str, Any],
    plan: dict[str, Any],
    names: dict[str, Any],
    report: dict[str, Any],
    registry_before: dict[str, Any],
    registry_after: dict[str, Any],
    runs: dict[str, str],
    completed_at: str,
) -> dict[str, Any]:
    """Record one completed match and select the next preregistered wave.

    A repeated finalizer for the same match run is a no-op.  This matters
    because Actions jobs may be re-run after a network or push failure.
    """
    if state.get("contract") != STATE_CONTRACT:
        raise ValueError("unsupported league season state contract")
    result = copy.deepcopy(state)
    history = list(result.get("history", []))
    match_run = str(runs["match"])
    if any(str(row.get("runs", {}).get("match")) == match_run for row in history):
        return result

    wave = int(result["wave"])
    round_number = int(result["round"])
    before_champion = champion(registry_before)
    after_champion = champion(registry_after)
    identity = names.get("names", {}).get(f"w{wave}", {})
    entry = {
        "round": round_number,
        "wave": wave,
        "challenger": report["challenger"],
        "display_name": identity.get("name", report["challenger"]),
        "champion_before": before_champion["name"],
        "champion_after": after_champion["name"],
        "promoted": bool(report.get("promoted")),
        "counts": _counts(report),
        "benchmark": _benchmark(report),
        "runs": {key: str(value) for key, value in runs.items()},
        "completed_at": completed_at,
    }
    history.append(entry)
    result["history"] = history
    result["last_completed_wave"] = wave
    result["last_match_run"] = match_run
    result["updated_at"] = completed_at

    waves = sorted(int(value) for value in plan["waves"])
    future = [value for value in waves if value > wave]
    if not future:
        result.update({
            "active": False,
            "stage": "complete",
            "next_wave": None,
            "champion": after_champion["name"],
        })
        return result

    next_wave = future[0]
    next_spec = plan["waves"][str(next_wave)]
    challenger = challenger_identity(registry_after, next_wave, names)
    result.update({
        "active": True,
        "stage": "collecting",
        "wave": next_wave,
        "round": int(next_spec["round"]),
        "next_wave": next_wave,
        "expected_cells": int(next_spec["expected_cells"]),
        "challenger": challenger["id"],
        "display_name": challenger["display_name"],
        "champion": after_champion["name"],
        "runs": {"collection": None, "learning": None, "match": None},
    })
    return result


def render_season_log(state: dict[str, Any]) -> str:
    lines = [
        "# League season log — waves 5-14",
        "",
        "Generated from `state.json`; one immutable row per completed round.",
        "",
        "| round | wave | runs (collect/learn/match) | challenger | verdict | benchmark |",
        "|---:|---:|---|---|---|---|",
    ]
    for row in state.get("history", []):
        counts = row["counts"]
        score = (
            f"{counts['wins']}-{counts['losses']}-"
            f"{counts['equal']}-{counts['incomparable']}"
        )
        verdict = "👑 promoted" if row["promoted"] else "🛡 defended"
        runs = row["runs"]
        lines.append(
            f"| {row['round']} | {row['wave']} | "
            f"{runs['collection']} / {runs['learning']} / {runs['match']} | "
            f"{row['display_name']} (`{row['challenger']}`) | "
            f"{verdict} ({score}) | {row['benchmark']} |"
        )
    return "\n".join(lines) + "\n"


def render_season_summary(state: dict[str, Any]) -> str:
    history = list(state.get("history", []))
    promotions = [row for row in history if row.get("promoted")]
    title = "Season complete" if not state.get("active", True) else "Season progress"
    lines = [
        f"# {title}",
        "",
        f"- completed rounds: {len(history)} / 10",
        f"- promotions: {len(promotions)}",
        f"- current champion: `{state.get('champion', 'unknown')}`",
    ]
    if state.get("active"):
        lines.extend([
            f"- next round: {state.get('round')}",
            f"- next wave: {state.get('wave')}",
            f"- next challenger: `{state.get('challenger')}`",
        ])
    elif history:
        lines.append(f"- final match run: {history[-1]['runs']['match']}")
    lines.extend([
        "",
        "The frozen ten-cell arena was unchanged for the whole season. "
        "Individual promotions remain small-n results; interpret the season "
        "trajectory rather than one match in isolation.",
        "",
    ])
    return "\n".join(lines)


def render_match_report(entry: dict[str, Any]) -> str:
    c = entry["counts"]
    verdict = "PROMOTED" if entry["promoted"] else "NOT promoted — title defended"
    return "\n".join([
        f"# League season round {entry['round']}: {entry['display_name']}",
        "",
        f"Wave {entry['wave']}; match run `{entry['runs']['match']}`.",
        "",
        f"## Verdict: {verdict}",
        "",
        f"vs `{entry['champion_before']}`: **{c['wins']} wins – "
        f"{c['losses']} losses – {c['equal']} equal – "
        f"{c['incomparable']} incomparable**.",
        "",
        f"Benchmark standing: `{entry['benchmark']}`.",
        "",
        "This report is generated from the paired terminal league decision; "
        "no scalar utility is introduced.",
        "",
    ])


def _read(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    identity = sub.add_parser("identity")
    identity.add_argument("--registry", type=pathlib.Path, required=True)
    identity.add_argument("--names", type=pathlib.Path, required=True)
    identity.add_argument("--wave", required=True)

    finish = sub.add_parser("finish")
    for name in ("state", "plan", "names", "report", "registry-before",
                 "registry-after", "state-out", "log-out", "summary-out",
                 "match-report-out"):
        finish.add_argument(f"--{name}", type=pathlib.Path, required=True)
    finish.add_argument("--collection-run", required=True)
    finish.add_argument("--learning-run", required=True)
    finish.add_argument("--match-run", required=True)
    finish.add_argument("--completed-at", default=None)

    args = parser.parse_args()
    if args.command == "identity":
        print(json.dumps(challenger_identity(
            _read(args.registry), args.wave, _read(args.names)
        ), ensure_ascii=False))
        return 0

    completed_at = args.completed_at or (
        dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
        .replace("+00:00", "Z")
    )
    updated = finish_round(
        state=_read(args.state), plan=_read(args.plan), names=_read(args.names),
        report=_read(args.report), registry_before=_read(args.registry_before),
        registry_after=_read(args.registry_after),
        runs={"collection": args.collection_run,
              "learning": args.learning_run, "match": args.match_run},
        completed_at=completed_at,
    )
    _write_json(args.state_out, updated)
    args.log_out.write_text(render_season_log(updated), encoding="utf-8")
    args.summary_out.write_text(render_season_summary(updated), encoding="utf-8")
    entry = next(
        row for row in updated["history"]
        if str(row["runs"]["match"]) == str(args.match_run)
    )
    args.match_report_out.parent.mkdir(parents=True, exist_ok=True)
    args.match_report_out.write_text(render_match_report(entry), encoding="utf-8")
    print(json.dumps({
        "active": updated["active"],
        "next_wave": updated.get("next_wave"),
        "next_round": updated.get("round"),
        "challenger": updated.get("challenger"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
