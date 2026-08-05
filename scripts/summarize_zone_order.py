"""
Read the zone-order ablation against its own noise floor.

Every arm-vs-arm reading taken today without a control was unreadable, so
this one refuses to report a difference without one. `base` and `base_null`
are the SAME configuration; whatever separates them is the run's own spread,
and an arm whose distance from `base_null` does not clear that spread has
not been shown to do anything.

Reported per scenario and per component the local simulator actually
computes. `fill_score` and `num_placed_items` are the only two of the six
official components that exist locally -- cog, stability, placement and soft
are evaluation-side -- so the proxies for the other four are carried
alongside, unweighted and never summed. Collapsing them into a total is the
mechanism by which a policy exploits a misspecified objective, and
`docs/AGENT_OPERATIONS.md` section 5.1 forbids it.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARMS = ("base", "base_null", "zone_doctrine", "zone_reversed")


def load(root: pathlib.Path):
    rows = []
    for path in sorted(glob.glob(f"{root}/**/rows.jsonl", recursive=True)):
        for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def metrics(case: dict) -> dict:
    # The ablation writes these at the top of the case record, not under an
    # `evaluation` key. Reading the wrong one silently dropped placed and
    # fill -- the two components that exist locally -- from the first
    # summary, leaving only proxies.
    out = {
        "placed": case.get("placed_count"),
        "placed_fraction": case.get("placed_fraction"),
        "fill": case.get("fill_score"),
        "com_z": case.get("final_com_z"),
    }
    attribute = case.get("attribute_placement") or {}
    for key in ("priority_covered_by_other", "soft_covered_by_other"):
        if attribute.get(key) is not None:
            out[key] = float(attribute[key])
    shake = case.get("shake_response") or {}
    for key in ("shake_max_shift", "shake_items_toppled"):
        if shake.get(key) is not None:
            out[key] = float(shake[key])
    return {k: v for k, v in out.items() if v is not None}


def collect(rows):
    """(scenario, arm) -> metric -> list of per-repeat values."""
    table = collections.defaultdict(lambda: collections.defaultdict(list))
    for row in rows:
        arm = row.get("arm")
        if arm not in ARMS:
            continue
        for case_id, case in (row.get("cases") or {}).items():
            if case.get("status") != "success":
                continue
            for name, value in metrics(case).items():
                if value is not None:
                    table[(case_id, arm)][name].append(float(value))
    return table


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    rows = load(args.root)
    table = collect(rows)
    scenarios = sorted({key[0] for key in table})
    report = {"rows": len(rows), "scenarios": {}}

    for scenario in scenarios:
        print(f"\n=== {scenario} ===")
        present = [a for a in ARMS if (scenario, a) in table]
        names = sorted(
            {n for a in present for n in table[(scenario, a)]}
        )
        header = f'{"metric":26s}' + "".join(f"{a:>16s}" for a in present)
        print(header)
        entry = {}
        for name in names:
            line = f"{name:26s}"
            values = {}
            for arm in present:
                series = table[(scenario, arm)].get(name) or []
                values[arm] = series
                if series:
                    mean = statistics.fmean(series)
                    spread = (max(series) - min(series)) if len(series) > 1 else 0.0
                    line += f"{mean:11.3f}±{spread:<4.2f}"
                else:
                    line += f'{"-":>16s}'
            print(line)
            entry[name] = {a: values[a] for a in present}
        report["scenarios"][scenario] = entry

        # the reading
        if {"base", "base_null"} <= set(present):
            print("\n  against the run's own noise floor (base - base_null):")
            for name in names:
                b = table[(scenario, "base")].get(name) or []
                n = table[(scenario, "base_null")].get(name) or []
                if not b or not n:
                    continue
                floor = abs(statistics.fmean(b) - statistics.fmean(n))
                # the within-arm spread matters as much as the gap between
                # the two identical arms: a floor computed only from means
                # cancels to nothing and reported knobs as adoptable once
                # already today.
                spreads = [
                    max(s) - min(s)
                    for s in (b, n)
                    if len(s) > 1
                ]
                floor = max([floor] + spreads)
                verdicts = []
                for arm in ("zone_doctrine", "zone_reversed"):
                    series = table[(scenario, arm)].get(name) or []
                    if not series:
                        continue
                    delta = statistics.fmean(series) - statistics.fmean(n)
                    mark = "CLEARS" if abs(delta) > floor else "within"
                    verdicts.append(f"{arm} {delta:+.3f} [{mark}]")
                if verdicts:
                    print(
                        f"    {name:24s} floor {floor:.3f}   "
                        + "   ".join(verdicts)
                    )

    print(
        "\nfloor = max(|base - base_null|, the widest within-arm spread of "
        "either). A knob inside the floor has not been shown to do anything; "
        "it has NOT been shown to do nothing."
    )
    print(
        "placed and fill are the only two of the six official components "
        "that exist locally. The rest are proxies, carried unweighted and "
        "never summed."
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
