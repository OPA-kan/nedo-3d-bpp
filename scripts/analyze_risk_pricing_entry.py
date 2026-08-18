"""Does a materially safer retained alternative exist at the fatal step?

Protocol: `reports/hazard/risk-pricing-entry-protocol.md`, which fixes
every threshold below before any number exists. This is the entry gate
`HANDOFF.md` item 3 already set for state-dependent risk pricing:

> re-derive the 57-death postmortem with candidate alternatives and
> show that at fatal steps a materially lower-P accepted alternative
> existed. Without that, the lever is empty.

No lambda is designed or fitted here. The only question is whether the
lever exists, and a negative answer closes item 3 rather than
prompting a search for a kinder statistic.

## What is read

Each episode's harness row gives `terminal_channel`. For an episode
that died physically, the FATAL step is the last decision, and the
multi-axis shadow attached to it carries every retained candidate's
`rotation_probability`, `slide_probability` and `adjusted_score`. The
channel selects which probability matters: `topple` reads rotation,
`slide` reads slide.

E4 is the negative control and it is not optional. A lever that reaches
just as many alternatives at an ordinary step as at a fatal one is not
about death, whatever its absolute rate. The control step is chosen
deterministically -- the median-indexed decision of the same episode --
so the comparison does not depend on a random seed.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import pathlib
import statistics
from typing import Any

MATERIAL_DROP = 0.10
E2_GATE = 0.30

CHANNEL_KEY = {
    "topple": "rotation_probability",
    "slide": "slide_probability",
}


def shadow_of(decision) -> dict | None:
    shadow = (decision.get("candidate_diagnostics") or {}).get(
        "multi_axis_selector"
    )
    if not isinstance(shadow, dict):
        return None
    if not shadow.get("candidates"):
        return None
    return shadow


def chosen_of(shadow):
    rank = shadow.get("selected_rank")
    for candidate in shadow["candidates"]:
        if rank is not None and candidate.get("rank") == rank:
            return candidate
    return shadow["candidates"][0]


def best_alternative(shadow, key: str):
    """The retained alternative with the lowest P on the fatal channel."""
    chosen = chosen_of(shadow)
    if chosen is None or chosen.get(key) is None:
        return None, None
    best = None
    for candidate in shadow["candidates"]:
        if candidate is chosen or candidate.get(key) is None:
            continue
        if best is None or candidate[key] < best[key]:
            best = candidate
    return chosen, best


def episode_rows(rows_path: str) -> list[dict[str, Any]]:
    base = os.path.dirname(rows_path)
    out = []
    for line in open(rows_path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        trace = os.path.join(
            base, "runs", row["label"], "policy-trace.jsonl"
        )
        if not os.path.exists(trace):
            continue
        decisions = []
        for entry in open(trace, encoding="utf-8"):
            if '"decision"' not in entry:
                continue
            try:
                event = json.loads(entry)
            except json.JSONDecodeError:
                continue
            if event.get("event") == "decision":
                decisions.append(event)
        for case_id, summary in (row.get("cases") or {}).items():
            out.append(
                {
                    "label": row["label"],
                    "case_id": case_id,
                    "channel": summary.get("terminal_channel"),
                    "decisions": decisions,
                }
            )
    return out


def measure_step(decision, key: str) -> dict | None:
    shadow = shadow_of(decision)
    if shadow is None:
        return None
    chosen, best = best_alternative(shadow, key)
    if chosen is None or best is None:
        return None
    drop = float(chosen[key]) - float(best[key])
    return {
        "step": decision.get("step"),
        "candidates": len(shadow["candidates"]),
        "chosen_p": float(chosen[key]),
        "best_p": float(best[key]),
        "drop": drop,
        "lower": drop > 0.0,
        "materially_lower": drop >= MATERIAL_DROP,
        "score_given_up": (
            float(chosen.get("adjusted_score", 0.0))
            - float(best.get("adjusted_score", 0.0))
        ),
    }


def analyze(episodes) -> dict[str, Any]:
    fatal = []
    control = []
    for episode in episodes:
        key = CHANNEL_KEY.get(episode["channel"])
        if key is None or not episode["decisions"]:
            continue
        measured = measure_step(episode["decisions"][-1], key)
        if measured is not None:
            measured["label"] = episode["label"]
            measured["channel"] = episode["channel"]
            fatal.append(measured)
        # Deterministic control: the median-indexed decision of the same
        # episode, so the comparison carries no seed.
        if len(episode["decisions"]) > 1:
            middle = episode["decisions"][len(episode["decisions"]) // 2]
            measured = measure_step(middle, key)
            if measured is not None:
                measured["label"] = episode["label"]
                measured["channel"] = episode["channel"]
                control.append(measured)

    def fractions(rows):
        total = len(rows)
        lower = sum(1 for r in rows if r["lower"])
        material = sum(1 for r in rows if r["materially_lower"])
        return {
            "steps": total,
            "lower": lower,
            "materially_lower": material,
            "fraction_lower": (lower / total) if total else 0.0,
            "fraction_materially_lower": (
                (material / total) if total else 0.0
            ),
        }

    e1_e2 = fractions(fatal)
    e4 = fractions(control)
    material_hits = [r for r in fatal if r["materially_lower"]]
    e3 = {
        "hits": len(material_hits),
        "mean_score_given_up": (
            statistics.fmean(r["score_given_up"] for r in material_hits)
            if material_hits
            else None
        ),
        "median_score_given_up": (
            statistics.median(r["score_given_up"] for r in material_hits)
            if material_hits
            else None
        ),
    }
    passes_rate = e1_e2["fraction_materially_lower"] >= E2_GATE
    passes_control = (
        e1_e2["fraction_materially_lower"]
        > e4["fraction_materially_lower"]
    )
    return {
        "physical_deaths_measured": e1_e2["steps"],
        "material_drop": MATERIAL_DROP,
        "e2_gate": E2_GATE,
        "E1_E2_fatal": e1_e2,
        "E3_score_given_up": e3,
        "E4_control_non_fatal": e4,
        "gate_rate": passes_rate,
        "gate_control": passes_control,
        "lever_exists": bool(passes_rate and passes_control),
        "fatal_steps": fatal,
    }


def render_markdown(result: dict) -> str:
    fatal = result["E1_E2_fatal"]
    control = result["E4_control_non_fatal"]
    e3 = result["E3_score_given_up"]
    verdict = "EXISTS" if result["lever_exists"] else "EMPTY"
    lines = [
        "# State-dependent risk pricing: does the lever exist?",
        "",
        "Protocol: `reports/hazard/risk-pricing-entry-protocol.md`. "
        "Thresholds fixed before the wave. No lambda is designed or "
        "fitted here.",
        "",
        f"- physical deaths measured: **{result['physical_deaths_measured']}**",
        f"- \"materially lower\" is an absolute drop of "
        f"{result['material_drop']:.2f} in the channel's own probability",
        "",
        "| measurement | steps | hits | fraction |",
        "|---|---:|---:|---:|",
        f"| E1 some retained alternative is lower | {fatal['steps']} | "
        f"{fatal['lower']} | {fatal['fraction_lower']:.1%} |",
        f"| **E2 materially lower, at the fatal step** | {fatal['steps']} "
        f"| {fatal['materially_lower']} | "
        f"**{fatal['fraction_materially_lower']:.1%}** |",
        f"| E4 control: materially lower at an ordinary step | "
        f"{control['steps']} | {control['materially_lower']} | "
        f"{control['fraction_materially_lower']:.1%} |",
        "",
        "| E3 what the safer alternative gives up | value |",
        "|---|---:|",
        f"| hits | {e3['hits']} |",
        f"| mean score given up | "
        + (
            f"{e3['mean_score_given_up']:.4f}"
            if e3["mean_score_given_up"] is not None
            else "-"
        )
        + " |",
        f"| median score given up | "
        + (
            f"{e3['median_score_given_up']:.4f}"
            if e3["median_score_given_up"] is not None
            else "-"
        )
        + " |",
        "",
        f"## Gate: E2 >= {result['e2_gate']:.0%} AND E2 > E4 -- "
        f"**{'PASS' if result['lever_exists'] else 'FAIL'}**",
        "",
        f"- rate: {'pass' if result['gate_rate'] else 'fail'}",
        f"- control: {'pass' if result['gate_control'] else 'fail'}",
        "",
    ]
    if result["lever_exists"]:
        lines += [
            "The lever EXISTS. A lambda form may now be designed, in a "
            "separate preregistration with its own gates, and subject to "
            "`AGENT_OPERATIONS.md` §5.1 -- a coefficient is admissible "
            "only if externally determined or chosen by a preregistered "
            "ablation with the losing values recorded. Nothing here "
            "licenses an adoption or a default change, and E3 bounds "
            "what any reweighting must overcome.",
        ]
    else:
        lines += [
            "The lever is EMPTY on this evidence and item 3 closes with "
            "the measurement recorded, which is what the handoff's own "
            "wording requires. A global lambda raise was already refuted "
            "(lambda=2 loses everywhere); this says the state-dependent "
            "version has nothing better to reach either, at least among "
            "retained candidates.",
        ]
    lines += [
        "",
        "## Scope, stated rather than quietly widened",
        "",
        "This reads RETAINED candidates only. If a materially safer "
        "alternative exists among candidates the policy never retained, "
        "that is a different lever with a different protocol -- and the "
        "soft line has just finished demonstrating that retention is "
        "where the diversity is lost.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", action="append", required=True)
    parser.add_argument("--output-json", type=pathlib.Path, required=True)
    parser.add_argument("--output-md", type=pathlib.Path)
    args = parser.parse_args()

    episodes = []
    for pattern in args.rows:
        for rows_path in sorted(glob.glob(pattern)):
            episodes.extend(episode_rows(rows_path))
    if not episodes:
        raise SystemExit("no episodes matched --rows")

    result = analyze(episodes)
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
                "deaths": result["physical_deaths_measured"],
                "E2": result["E1_E2_fatal"]["fraction_materially_lower"],
                "E4": result["E4_control_non_fatal"][
                    "fraction_materially_lower"
                ],
                "lever_exists": result["lever_exists"],
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
