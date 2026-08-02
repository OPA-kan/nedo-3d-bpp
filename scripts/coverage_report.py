"""
Coverage report over the reverse-lookup registries.

Joins context/axes.json, context/questions.json, context/measurements.json
and context/evidence.json into one table so that imbalance is visible
rather than inferred:

- questions with no instrument   -> asking something nothing can answer
- knobs with no questions        -> instrumentation without a hypothesis
- evidence but still open        -> a positive result left unfollowed
- no knobs at all                -> the axis cannot be experimented on, so
                                    its emptiness is structural, not a
                                    judgement that it does not matter

The last one is the whole point. The set of knobs defines the set of
hypotheses anyone can test, so an axis with zero knobs will look
uninteresting forever, no matter how important it is.

    python3 scripts/coverage_report.py
    python3 scripts/coverage_report.py --question item-cap-omits-useful-items
"""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTEXT = ROOT / "context"


def _load(name: str) -> dict[str, Any]:
    with (CONTEXT / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def load_all() -> dict[str, Any]:
    return {
        "axes": _load("axes.json"),
        "questions": _load("questions.json"),
        "measurements": _load("measurements.json"),
        "evidence": _load("evidence.json"),
    }


def coverage_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    axes = data["axes"]["axes"]
    questions = data["questions"]["questions"]
    instruments = data["measurements"]["instruments"]
    active = {
        entry["id"]
        for entry in data["evidence"]["entries"]
        if entry.get("status") == "active"
    }

    rows = []
    for name, axis in axes.items():
        axis_questions = [q for q in questions if q["axis"] == name]
        axis_instruments = [
            path for path, spec in instruments.items()
            if name in spec.get("varied_axis", [])
        ]
        cited = axis.get("evidence", [])
        rows.append({
            "axis": name,
            "questions": len(axis_questions),
            "open": sum(1 for q in axis_questions if q["status"] == "open"),
            "instruments": len(axis_instruments),
            "knobs": len(axis.get("knobs", [])),
            "evidence": len(cited),
            "evidence_active": sum(1 for e in cited if e in active),
            "blind_spots": len(axis.get("blind_spots", [])),
            "unanswerable": sum(
                1 for q in axis_questions
                if q["status"] == "open" and not q.get("existing_instruments")
            ),
        })
    return rows


def alarms(rows: list[dict[str, Any]]) -> list[str]:
    out = []
    for row in rows:
        axis = row["axis"]
        if row["knobs"] == 0 and row["questions"] > 0:
            out.append(
                f"{axis}: {row['questions']} question(s) and ZERO knobs -- "
                "nothing on this axis can be varied, so no hypothesis about "
                "it can be tested. Its emptiness is structural."
            )
        if row["unanswerable"]:
            out.append(
                f"{axis}: {row['unanswerable']} open question(s) with no "
                "instrument that varies this axis -- the honest answer is "
                "'insufficient evidence', not a hedge from a neighbouring "
                "instrument."
            )
        if row["evidence_active"] and row["open"] and row["knobs"] == 0:
            out.append(
                f"{axis}: {row['evidence_active']} active finding(s) but no "
                "intervention knob -- the evidence here is observational or "
                "diagnostic only, and no registered knob can test a policy "
                "on this axis. Read this as 'cannot be acted on yet', NOT "
                "as 'a promising result waiting to be shipped'."
            )
        elif row["evidence_active"] and row["open"] and row["knobs"] == 1:
            out.append(
                f"{axis}: {row['evidence_active']} active finding(s) and "
                f"{row['open']} open question on a single knob -- narrow "
                "intervention surface relative to what has been measured."
            )
        if row["questions"] == 0 and row["knobs"] >= 3:
            out.append(
                f"{axis}: {row['knobs']} knobs and no registered question -- "
                "instrumentation without a hypothesis."
            )
    return out


def render(data: dict[str, Any]) -> str:
    rows = coverage_rows(data)
    width = max(len(r["axis"]) for r in rows)
    lines = [
        f"{'axis'.ljust(width)}  quest  open  instr  knobs  evid  active  blind",
        f"{'-' * width}  -----  ----  -----  -----  ----  ------  -----",
    ]
    for row in sorted(rows, key=lambda r: (-r["open"], r["axis"])):
        lines.append(
            f"{row['axis'].ljust(width)}  {row['questions']:5d}  "
            f"{row['open']:4d}  {row['instruments']:5d}  {row['knobs']:5d}  "
            f"{row['evidence']:4d}  {row['evidence_active']:6d}  "
            f"{row['blind_spots']:5d}"
        )
    found = alarms(rows)
    lines.append("")
    lines.append(f"ALARMS ({len(found)})")
    lines.extend(f"  - {a}" for a in found) if found else lines.append("  none")
    return "\n".join(lines) + "\n"


def answer(data: dict[str, Any], question_id: str) -> str:
    questions = {q["id"]: q for q in data["questions"]["questions"]}
    if question_id not in questions:
        available = ", ".join(sorted(questions))
        raise KeyError(f"unknown question '{question_id}'; have: {available}")
    q = questions[question_id]
    instruments = data["measurements"]["instruments"]

    lines = [
        f"Question:  {q['question']}",
        f"Axis:      {q['axis']}",
        f"Status:    {q['status']} (priority {q['priority']})",
        f"Unit:      {q['observation_unit']}",
        "",
    ]
    if q.get("existing_instruments"):
        lines.append("Existing instruments:")
        for path in q["existing_instruments"]:
            spec = instruments.get(path, {})
            lines.append(f"  {path}")
            for limit in spec.get("cannot_answer", []):
                lines.append(f"      cannot answer: {limit}")
    else:
        lines.append("Existing evidence:  INSUFFICIENT")
    lines += [
        "",
        f"Reason:             {q.get('why_unobserved', q['rationale'])}",
        f"Required instrument: {q['missing_instrument']}",
        f"Intervention:        {q['intervention']}",
        f"Required variation:  {q['required_variation']}",
        "",
        "Closure criteria:",
    ]
    lines += [f"  - {c}" for c in q["closure_criteria"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--question",
        help="Reverse-lookup one question instead of the coverage table.",
    )
    args = parser.parse_args()
    data = load_all()
    print(answer(data, args.question) if args.question else render(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
