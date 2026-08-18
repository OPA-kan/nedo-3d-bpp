"""Stage 1 of the stack-aware soft protocol: does the rule reach anything?

Protocol: `reports/hazard/soft-stack-protocol.md`, which fixes these four
measurements and the entry gate BEFORE the wave ran.

The attribute filter was preregistered, waved and closed inert at 0 of 16
swaps -- a wave spent to learn that an intervention built on a predicate
which is zero on four fifths of episodes does nothing. This script exists
so that cannot happen twice: it reads the log-only multi-axis shadow and
asks, over decisions with more than one retained candidate, how often a
stack-aware tie-break would have had something to choose.

  R1  some retained candidate has strictly fewer stack-aware soft
      violations than the chosen one
  R2  such a candidate ALSO has adjusted_score no worse than the chosen
      one -- the dominance-eligible fraction, and the reach of the rule
      Stage 2 would actually implement
  R3  the same as R2 for priority
  R4  the same counts under the SHIPPED contact reading, as a negative
      control; expected near zero, and if it is not then the attribute
      filter's inert verdict is what needs revisiting, not this line

Entry gate for Stage 2: R2 >= 0.05.
"""

from __future__ import annotations

import argparse
import glob
import json
import pathlib
from typing import Any

R2_ENTRY_GATE = 0.05


def load_shadow_records(trace_globs) -> list[dict[str, Any]]:
    """Every multi-axis shadow record that saw more than one candidate."""
    records = []
    for pattern in trace_globs:
        for trace in sorted(glob.glob(pattern)):
            for line in open(trace, encoding="utf-8"):
                if "multi_axis_selector" not in line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                shadow = (event.get("candidate_diagnostics") or {}).get(
                    "multi_axis_selector"
                )
                if not isinstance(shadow, dict):
                    continue
                candidates = shadow.get("candidates")
                if not candidates or len(candidates) < 2:
                    continue
                records.append(
                    {
                        "trace": trace,
                        "step": event.get("step"),
                        "candidates": candidates,
                        "selected_rank": shadow.get("selected_rank"),
                    }
                )
    return records


def chosen_of(record) -> dict | None:
    rank = record.get("selected_rank")
    for candidate in record["candidates"]:
        if rank is not None and candidate.get("rank") == rank:
            return candidate
    # The shipped selector plays rank 0 when the shadow did not name one.
    return record["candidates"][0] if record["candidates"] else None


def reach(records, violation_key: str, require_score: bool) -> dict:
    hits = 0
    usable = 0
    examples = []
    for record in records:
        chosen = chosen_of(record)
        if chosen is None or violation_key not in chosen:
            continue
        usable += 1
        for candidate in record["candidates"]:
            if candidate is chosen:
                continue
            if candidate.get(violation_key) is None:
                continue
            if candidate[violation_key] >= chosen[violation_key]:
                continue
            if require_score and candidate.get(
                "adjusted_score", float("-inf")
            ) < chosen.get("adjusted_score", float("inf")):
                continue
            hits += 1
            if len(examples) < 10:
                examples.append(
                    {
                        "trace": pathlib.Path(record["trace"]).parent.name,
                        "step": record["step"],
                        "chosen_violations": chosen[violation_key],
                        "alternative_violations": candidate[violation_key],
                        "chosen_score": chosen.get("adjusted_score"),
                        "alternative_score": candidate.get("adjusted_score"),
                    }
                )
            break
    return {
        "decisions": usable,
        "hits": hits,
        "fraction": (hits / usable) if usable else 0.0,
        "examples": examples,
    }


def analyze(records) -> dict:
    r1 = reach(records, "soft_cover_violations_stack", require_score=False)
    r2 = reach(records, "soft_cover_violations_stack", require_score=True)
    r3 = reach(
        records, "priority_cover_violations_stack", require_score=True
    )
    r4_soft = reach(records, "soft_cover_violations", require_score=True)
    r4_priority = reach(
        records, "priority_cover_violations", require_score=True
    )
    return {
        "records": len(records),
        "R1_any_better_stack_soft": r1,
        "R2_dominance_eligible_stack_soft": r2,
        "R3_dominance_eligible_stack_priority": r3,
        "R4_control_contact_soft": r4_soft,
        "R4_control_contact_priority": r4_priority,
        "entry_gate": R2_ENTRY_GATE,
        "stage2_licensed": r2["fraction"] >= R2_ENTRY_GATE,
    }


def render_markdown(result: dict) -> str:
    def row(name, stats):
        return (
            f"| {name} | {stats['hits']}/{stats['decisions']} | "
            f"{stats['fraction']:.1%} |"
        )

    lines = [
        "# Stack-aware soft coverage: Stage 1 reach",
        "",
        "Protocol: `reports/hazard/soft-stack-protocol.md`. The four "
        "measurements and the entry gate were fixed before this wave ran. "
        "Log-only: the shadow records both readings and selects on "
        "neither.",
        "",
        f"- multi-candidate decisions observed: {result['records']}",
        "",
        "| measurement | hits | fraction |",
        "|---|---:|---:|",
        row("R1 some candidate better on stack-aware soft",
            result["R1_any_better_stack_soft"]),
        row("**R2 dominance-eligible on stack-aware soft**",
            result["R2_dominance_eligible_stack_soft"]),
        row("R3 dominance-eligible on stack-aware priority",
            result["R3_dominance_eligible_stack_priority"]),
        row("R4 control: dominance-eligible on CONTACT soft",
            result["R4_control_contact_soft"]),
        row("R4 control: dominance-eligible on CONTACT priority",
            result["R4_control_contact_priority"]),
        "",
        f"## Entry gate: R2 >= {result['entry_gate']:.0%} -- "
        f"**{'PASS' if result['stage2_licensed'] else 'FAIL'}**",
        "",
    ]
    if result["stage2_licensed"]:
        lines += [
            "Stage 2 is licensed: the dominance tie-break has something "
            "to act on. Its gates are already frozen in the protocol and "
            "none of them may be re-read from this wave.",
        ]
    else:
        lines += [
            "Stage 2 is NOT built. The rule cannot reach the gate "
            "fraction of decisions, so an arm would spend a wave to "
            "reproduce the attribute filter's inert verdict. The line "
            "closes as measured-inert-with-a-reason and the shadow "
            "columns stay as telemetry.",
        ]
    control = result["R4_control_contact_soft"]
    lines += [
        "",
        "## Reading the control",
        "",
        f"R4 is the shipped contact reading, and it is "
        f"{control['fraction']:.1%}. A near-zero value is the direct "
        "confirmation that the attribute filter's 0-of-16 result was "
        "mechanically guaranteed rather than informative. A large value "
        "would mean the inert verdict, not this line, is what needs "
        "revisiting.",
    ]
    examples = result["R2_dominance_eligible_stack_soft"]["examples"]
    if examples:
        lines += ["", "## Sample dominance-eligible decisions", ""]
        for item in examples:
            lines.append(
                f"- `{item['trace']}` step {item['step']}: chosen "
                f"{item['chosen_violations']} violations at score "
                f"{item['chosen_score']}, alternative "
                f"{item['alternative_violations']} at "
                f"{item['alternative_score']}"
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traces", action="append", required=True)
    parser.add_argument("--output-json", type=pathlib.Path, required=True)
    parser.add_argument("--output-md", type=pathlib.Path)
    args = parser.parse_args()

    records = load_shadow_records(args.traces)
    if not records:
        raise SystemExit(
            "no multi-axis shadow records with more than one candidate; "
            "was the wave run with MULTI_AXIS_SELECTOR_MODE=shadow?"
        )
    result = analyze(records)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(args.output_json)
    if args.output_md:
        args.output_md.write_text(
            render_markdown(result), encoding="utf-8"
        )
        print(args.output_md)
    print(
        json.dumps(
            {
                "records": result["records"],
                "R2": result["R2_dominance_eligible_stack_soft"]["fraction"],
                "stage2_licensed": result["stage2_licensed"],
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
