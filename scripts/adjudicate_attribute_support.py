"""Adjudicate the rule-faithful attribute support against its frozen gates.

Protocol: `reports/hazard/attribute-support-protocol.md`. Every placed
threshold comes from `reports/benchmarks/baseline.json`, frozen long
before this change existed; none is chosen here.

Gates:

  P  placed, per config, against that config's own
     `minimum_resolvable_placed.paired_3v3_same_run`. Positive clearance
     on >= 3 configs and no negative breach anywhere.
  A  attribute cost, one-directional: violations PER PLACED ITEM must
     not rise. Raw counts rising while the rate is flat is the expected
     shape of carrying more cargo, not a new violation.
  S  stability, per HANDOFF item 6: pooled shake_max_shift and
     shake_peak_kinetic_energy reported beside placed; a worsening
     blocks adoption even if placed rises.
  C  channel shift, the mechanism check: the change is claimed to work
     by opening candidates on boards that were exhausting, so physical
     endings should fall and surrender endings rise. A placed gain
     without that shift did not come from the stated mechanism.

Development only. Adoption needs a fresh-permutation confirmation.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import pathlib
import statistics
from typing import Any

ARMS = ("base", "attr_support_rule")
PHYSICAL = ("topple", "slide")
MIN_CONFIGS_CLEARING = 3


def load(rows_globs) -> dict[str, dict[str, list[dict]]]:
    by_case: dict[str, dict[str, list[dict]]] = collections.defaultdict(
        lambda: {arm: [] for arm in ARMS}
    )
    for pattern in rows_globs:
        for rows_path in sorted(glob.glob(pattern)):
            for line in open(rows_path, encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                label = row["label"]
                arm = (
                    "attr_support_rule"
                    if "attr_support_rule" in label
                    else "base"
                )
                for case_id, summary in (row.get("cases") or {}).items():
                    by_case[case_id][arm].append(summary)
    return by_case


def mean_of(rows, path):
    values = []
    for row in rows:
        value = row
        for key in path:
            value = (value or {}).get(key) if isinstance(value, dict) else None
        if isinstance(value, (int, float)):
            values.append(float(value))
    return statistics.fmean(values) if values else None


def adjudicate(by_case, floors) -> dict[str, Any]:
    per_config = {}
    cleared = 0
    breached = []
    for case_id, arms in sorted(by_case.items()):
        base, rule = arms["base"], arms["attr_support_rule"]
        if not base or not rule:
            continue
        base_placed = mean_of(base, ("placed_count",))
        rule_placed = mean_of(rule, ("placed_count",))
        delta = rule_placed - base_placed
        floor = floors.get(case_id)
        verdict = "no_floor" if floor is None else (
            "clears" if delta >= floor
            else ("breaches" if delta <= -floor else "inside_floor")
        )
        if verdict == "clears":
            cleared += 1
        if verdict == "breaches":
            breached.append(case_id)
        per_config[case_id] = {
            "episodes": {"base": len(base), "attr_support_rule": len(rule)},
            "placed_base": base_placed,
            "placed_rule": rule_placed,
            "placed_delta": delta,
            "fill_base": mean_of(base, ("fill_score",)),
            "fill_rule": mean_of(rule, ("fill_score",)),
            "floor": floor,
            "verdict": verdict,
        }

    pooled = {}
    for arm in ARMS:
        rows = [r for arms in by_case.values() for r in arms[arm]]
        placed = sum(r.get("placed_count") or 0 for r in rows)
        soft_v = sum(
            (r.get("attribute_placement") or {}).get(
                "soft_covered_by_other"
            )
            or 0
            for r in rows
        )
        prio_v = sum(
            (r.get("attribute_placement") or {}).get(
                "priority_covered_by_other"
            )
            or 0
            for r in rows
        )
        channels = collections.Counter(
            r.get("terminal_channel") for r in rows
        )
        pooled[arm] = {
            "episodes": len(rows),
            "placed_total": placed,
            "soft_violations": soft_v,
            "priority_violations": prio_v,
            "soft_per_placed": (soft_v / placed) if placed else None,
            "priority_per_placed": (prio_v / placed) if placed else None,
            "shake_max_shift": mean_of(
                rows, ("shake_response", "shake_max_shift")
            ),
            "shake_peak_kinetic_energy": mean_of(
                rows, ("shake_response", "shake_peak_kinetic_energy")
            ),
            "physical_endings": sum(
                channels.get(channel, 0) for channel in PHYSICAL
            ),
            "channels": dict(channels),
        }

    def worsened(key):
        b, r = pooled["base"][key], pooled["attr_support_rule"][key]
        if b is None or r is None:
            return None
        return r > b

    gate_p = cleared >= MIN_CONFIGS_CLEARING and not breached
    gate_a = (
        pooled["attr_support_rule"]["soft_per_placed"]
        <= pooled["base"]["soft_per_placed"]
        and pooled["attr_support_rule"]["priority_per_placed"]
        <= pooled["base"]["priority_per_placed"]
    )
    shift = worsened("shake_max_shift")
    energy = worsened("shake_peak_kinetic_energy")
    gate_s = not (shift or energy)
    base_phys = pooled["base"]["physical_endings"] / max(
        1, pooled["base"]["episodes"]
    )
    rule_phys = pooled["attr_support_rule"]["physical_endings"] / max(
        1, pooled["attr_support_rule"]["episodes"]
    )
    gate_c = rule_phys < base_phys

    return {
        "per_config": per_config,
        "configs_clearing": cleared,
        "configs_breaching": breached,
        "min_configs_clearing": MIN_CONFIGS_CLEARING,
        "pooled": pooled,
        "physical_ending_rate": {"base": base_phys, "rule": rule_phys},
        "gate_P_placed": gate_p,
        "gate_A_attribute_rate": gate_a,
        "gate_S_stability": gate_s,
        "gate_C_channel_shift": gate_c,
        "development_pass": bool(gate_p and gate_a and gate_s and gate_c),
    }


def render_markdown(result: dict) -> str:
    pooled = result["pooled"]
    lines = [
        "# Rule-faithful attribute support: development adjudication",
        "",
        "Protocol: `reports/hazard/attribute-support-protocol.md`, which "
        "discloses that it was written after the wave launched and takes "
        "every placed threshold from `reports/benchmarks/baseline.json` "
        "rather than choosing one.",
        "",
        "## Per config (paired, same run)",
        "",
        "| config | base placed | rule placed | delta | floor | verdict | "
        "base fill | rule fill |",
        "|---|---:|---:|---:|---:|---|---:|---:|",
    ]
    for case_id, stats in result["per_config"].items():
        floor = stats["floor"]
        lines.append(
            f"| `{case_id}` | {stats['placed_base']:.2f} | "
            f"{stats['placed_rule']:.2f} | {stats['placed_delta']:+.2f} | "
            f"{'-' if floor is None else f'{floor:.2f}'} | "
            f"{stats['verdict']} | {stats['fill_base']:.2f} | "
            f"{stats['fill_rule']:.2f} |"
        )
    lines += [
        "",
        "## Pooled",
        "",
        "| quantity | base | attr_support_rule |",
        "|---|---:|---:|",
        f"| episodes | {pooled['base']['episodes']} | "
        f"{pooled['attr_support_rule']['episodes']} |",
        f"| placed total | {pooled['base']['placed_total']} | "
        f"{pooled['attr_support_rule']['placed_total']} |",
        f"| soft violations per placed item | "
        f"{pooled['base']['soft_per_placed']:.4f} | "
        f"{pooled['attr_support_rule']['soft_per_placed']:.4f} |",
        f"| priority violations per placed item | "
        f"{pooled['base']['priority_per_placed']:.4f} | "
        f"{pooled['attr_support_rule']['priority_per_placed']:.4f} |",
        f"| shake max shift | "
        f"{pooled['base']['shake_max_shift']:.4f} | "
        f"{pooled['attr_support_rule']['shake_max_shift']:.4f} |",
        f"| shake peak kinetic energy | "
        f"{pooled['base']['shake_peak_kinetic_energy']:.2f} | "
        f"{pooled['attr_support_rule']['shake_peak_kinetic_energy']:.2f} |",
        f"| physical ending rate | "
        f"{result['physical_ending_rate']['base']:.1%} | "
        f"{result['physical_ending_rate']['rule']:.1%} |",
        "",
        "## Gates",
        "",
        "| gate | result |",
        "|---|---|",
        f"| P placed, >= {result['min_configs_clearing']} configs clearing "
        f"their own floor, none breaching | "
        f"{result['configs_clearing']} clearing, "
        f"{len(result['configs_breaching'])} breaching -> "
        f"{'pass' if result['gate_P_placed'] else '**fail**'} |",
        f"| A violations per placed item do not rise | "
        f"{'pass' if result['gate_A_attribute_rate'] else '**fail**'} |",
        f"| S shake shift and peak energy do not worsen | "
        f"{'pass' if result['gate_S_stability'] else '**fail**'} |",
        f"| C physical endings fall (mechanism) | "
        f"{'pass' if result['gate_C_channel_shift'] else '**fail**'} |",
        "",
        f"## Development verdict: "
        f"**{'PASS' if result['development_pass'] else 'FAIL'}**",
        "",
    ]
    if result["development_pass"]:
        lines += [
            "Development only. Adoption requires a fresh-permutation "
            "confirmation on never-used streams with a new seed, no "
            "retuning, and the same gates -- the last-resort precedent. "
            "Nothing here may be quoted as an official soft or placement "
            "score gain: the violation-count to 0-100 mapping is "
            "unpublished.",
        ]
    else:
        lines += [
            "Not adopted. The failing gate is the finding; no threshold "
            "moves and no arm is retuned on this stream.",
        ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", action="append", required=True)
    parser.add_argument(
        "--baseline",
        type=pathlib.Path,
        default=pathlib.Path("reports/benchmarks/baseline.json"),
    )
    parser.add_argument("--output-json", type=pathlib.Path, required=True)
    parser.add_argument("--output-md", type=pathlib.Path)
    args = parser.parse_args()

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    floors = {
        case_id: (
            (stats.get("minimum_resolvable_placed") or {}).get(
                "paired_3v3_same_run"
            )
        )
        for case_id, stats in baseline["cases"].items()
    }
    by_case = load(args.rows)
    if not by_case:
        raise SystemExit("no rows matched --rows")
    result = adjudicate(by_case, floors)
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
                "configs_clearing": result["configs_clearing"],
                "configs_breaching": result["configs_breaching"],
                "P": result["gate_P_placed"],
                "A": result["gate_A_attribute_rate"],
                "S": result["gate_S_stability"],
                "C": result["gate_C_channel_shift"],
                "development_pass": result["development_pass"],
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
