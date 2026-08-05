"""
Local stand-ins for all six official score components, as a VECTOR.

The bundled evaluator computes two of the six. The other four are not
unmeasurable -- their raw quantities exist in `diagnostics.py` and
`evaluator.py`, and COMPETITION_RULES states each one's direction. What is
unpublished is the 0-100 normalisation and the weights of the average.

So this reports a vector and refuses to collapse it. Inventing weights to
get one number is the failure AGENT_OPERATIONS section 5.1 exists to stop,
and it would also be the exact mechanism by which a learned policy
exploits a misspecified reward. Callers that need an ordering must state
their own rule (dominance, lexicographic, constrained) in the open.

Each component carries:
  raw        the measured quantity
  direction  "up" or "down" -- which way the official component moves
  fidelity   how much the local quantity is trusted, from the record

The placed gate is reported separately because it is not another component:
COMPETITION_RULES states that below a placement threshold every component
except fill is zero, which makes placed a CONSTRAINT rather than a term.
"""
from __future__ import annotations

import argparse
import glob
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

# fidelity, from the record. These are not opinions; each cites a measurement.
FIDELITY = {
    "fill": "exact -- the bundled evaluator is the official implementation",
    "placed": "exact -- same",
    "cog": (
        "direction only, and falsified once: on the trueenvelope->deathband"
        " pair com_z improved while official cog fell 20.7%"
        " (death-band-official-regression-15pct)"
    ),
    "stability": (
        "direction plausible, resolution poor: repeat-to-repeat spread on"
        " identical configs is 23-75%, so only pooled comparisons carry"
        " meaning (shake-veto-is-inside-its-own-noise-floor)"
    ),
    "placement": (
        "rule transcribed exactly, but priority routing is unexercised on"
        " the bundled suite (no dedicated container) and the clean ratio"
        " was falsified once against official placement_score"
    ),
    "soft": "rule transcribed exactly; soft is exercised (13 of 41 in case 000)",
}


def components(case: dict) -> dict:
    """The six stand-ins plus the gate, from one case's evaluation record."""
    evaluation = case.get("evaluation") or case
    steps = evaluation.get("step_metrics") or []
    final = steps[-1] if steps else {}
    shake = evaluation.get("shake_response") or case.get("shake_response") or {}
    # The attribute counts live per STEP (diagnostics stamps them into
    # settled_snapshot), not in the top-level report, so the final step is
    # the episode's answer. run_risk_ablation happens to lift a copy to
    # case level; accept either so this reads both harnesses' output.
    attributes = (
        case.get("attribute_placement")
        or evaluation.get("attribute_placement")
        or final
    )

    def violations(prefix):
        covered = attributes.get(f"{prefix}_covered_by_other")
        misrouted = attributes.get(f"{prefix}_misrouted")
        if covered is None and misrouted is None:
            return None
        return float(covered or 0) + float(misrouted or 0)

    return {
        "fill": {
            "raw": evaluation.get("fill_score"),
            "direction": "up",
            "fidelity": FIDELITY["fill"],
        },
        "cog": {
            # Lower centre of mass is better, per COMPETITION_RULES: the
            # component asks how LOW the centre of gravity sits.
            "raw": final.get("center_of_mass_z"),
            "direction": "down",
            "fidelity": FIDELITY["cog"],
        },
        "stability": {
            # Two quantities, kept separate: how far the worst item moved
            # and how much energy the stack absorbed. Combining them would
            # be a weight.
            "raw": {
                "max_shift": shake.get("shake_max_shift"),
                "peak_kinetic_energy": shake.get("shake_peak_kinetic_energy"),
                "items_shifted": shake.get("shake_items_shifted"),
                "items_toppled": shake.get("shake_items_toppled"),
            },
            "direction": "down",
            "fidelity": FIDELITY["stability"],
        },
        "placement": {
            "raw": violations("priority"),
            "direction": "down",
            "fidelity": FIDELITY["placement"],
        },
        "soft": {
            "raw": violations("soft"),
            "direction": "down",
            "fidelity": FIDELITY["soft"],
        },
        "gate": {
            # Not a sixth term. COMPETITION_RULES: below a placement
            # threshold every component except fill is zero, so this is a
            # constraint the other five sit behind.
            "raw": evaluation.get("num_placed_items"),
            "direction": "up",
            "fidelity": FIDELITY["placed"],
            "note": "constraint, not a term",
        },
    }


def dominates(a: dict, b: dict) -> bool:
    """
    Pareto dominance over the vector, with no weights.

    True when every comparable component of ``a`` is at least as good as
    ``b``'s and at least one is strictly better. Components missing on
    either side are skipped rather than assumed equal, and stability is
    compared on each of its quantities.
    """
    strictly_better = False
    for name, entry in a.items():
        other = b.get(name)
        if other is None:
            continue
        pairs = []
        if isinstance(entry["raw"], dict):
            for key, value in entry["raw"].items():
                pairs.append((value, (other["raw"] or {}).get(key)))
        else:
            pairs.append((entry["raw"], other["raw"]))
        for mine, theirs in pairs:
            if not isinstance(mine, (int, float)) or not isinstance(
                theirs, (int, float)
            ):
                continue
            better = mine > theirs if entry["direction"] == "up" else mine < theirs
            worse = mine < theirs if entry["direction"] == "up" else mine > theirs
            if worse:
                return False
            if better:
                strictly_better = True
    return strictly_better


def load_cases(run_dir: pathlib.Path):
    for path in sorted(glob.glob(f"{run_dir}/**/evaluation_results.json", recursive=True)):
        for case_id, case in json.loads(
            pathlib.Path(path).read_text(encoding="utf-8")
        ).items():
            yield case_id, case
    for path in sorted(glob.glob(f"{run_dir}/**/rows.jsonl", recursive=True)):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                for case_id, case in (json.loads(line).get("cases") or {}).items():
                    yield case_id, case


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=pathlib.Path, nargs="+")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    rows = []
    for run_dir in args.run_dir:
        for case_id, case in load_cases(run_dir):
            rows.append(
                {"run": str(run_dir), "case": case_id, "components": components(case)}
            )
    if not rows:
        print("no evaluation records found", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    print(
        f"{'case':22s} {'gate':>6s} {'fill':>7s} {'cog':>7s} "
        f"{'shift':>7s} {'peakKE':>8s} {'place':>6s} {'soft':>5s}"
    )
    for row in rows:
        c = row["components"]

        def fmt(value, width, spec=".3f"):
            if not isinstance(value, (int, float)):
                return f"{'-':>{width}}"
            return f"{value:>{width}{spec}}"

        stability = c["stability"]["raw"]
        print(
            f"{row['case'][:22]:22s} "
            f"{fmt(c['gate']['raw'], 6)} {fmt(c['fill']['raw'], 7, '.2f')} "
            f"{fmt(c['cog']['raw'], 7, '.4f')} "
            f"{fmt(stability.get('max_shift'), 7, '.4f')} "
            f"{fmt(stability.get('peak_kinetic_energy'), 8, '.2f')} "
            f"{fmt(c['placement']['raw'], 6, '.0f')} "
            f"{fmt(c['soft']['raw'], 5, '.0f')}"
        )
    print(
        "\ngate is a CONSTRAINT (fill survives below it, the rest go to zero)."
        "\ncog/shift/peakKE/place/soft: lower is better. fill/gate: higher."
        "\nNo weighted total is printed on purpose -- state an ordering rule"
        "\n(dominance, lexicographic, constrained) rather than inventing one."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
