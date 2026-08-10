"""
Read any paired ablation against its own noise floor.

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

# Arms are read off the data, not declared here. A hardcoded allow-list was
# the previous design and it fails silently in the one direction that
# matters: a newly added arm is simply absent from the table, which reads as
# "the experiment did not run" rather than "the summariser does not know
# this name". Only the two control names are fixed, because the whole
# reading is defined relative to them.
CONTROL = ("base", "base_null")


def load(root: pathlib.Path):
    """
    Every ablation row under `root`, in either layout the queue produces.

    `run_queue.py` writes one directory per job with a `rows.jsonl` inside;
    the ad-hoc serial runs write `<scenario>-<arm>-r<n>.jsonl` flat. Both
    have been committed under `reports/`, and reading only the first meant
    no shipped verdict could be regenerated from the repository -- the
    command printed in the reports returned an empty table.
    """
    seen = set()
    paths = sorted(glob.glob(f"{root}/**/rows.jsonl", recursive=True))
    paths += sorted(glob.glob(f"{root}/**/*.jsonl", recursive=True))
    rows = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and "arm" in row:
                rows.append(row)
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
        "policy_seconds": case.get("policy_seconds"),
        "terminal_included": (
            float(case["is_included"])
            if isinstance(case.get("is_included"), bool)
            else None
        ),
        "terminal_valid": (
            float(case["is_valid"])
            if isinstance(case.get("is_valid"), bool)
            else None
        ),
        "terminal_placed_safe": (
            float(case["is_placed_safe"])
            if isinstance(case.get("is_placed_safe"), bool)
            else None
        ),
    }
    attribute = case.get("attribute_placement") or {}
    for key in (
        "priority_covered_by_other",
        "soft_covered_by_other",
        "priority_clean_ratio",
        "soft_clean_ratio",
    ):
        if attribute.get(key) is not None:
            out[key] = float(attribute[key])
    shake = case.get("shake_response") or {}
    for key in (
        "shake_max_shift",
        "shake_peak_kinetic_energy",
        "shake_items_shifted",
        "shake_items_toppled",
    ):
        if shake.get(key) is not None:
            out[key] = float(shake[key])
    shake_items = shake.get("shake_items")
    shake_shifted = shake.get("shake_items_shifted")
    if (
        isinstance(shake_items, (int, float))
        and shake_items > 0
        and isinstance(shake_shifted, (int, float))
    ):
        out["shake_shifted_fraction"] = float(shake_shifted) / float(
            shake_items
        )
    official = case.get("score_components") or {}
    for key in (
        "cog_score",
        "stability_score",
        "placement_score",
        "soft_item_score",
    ):
        if isinstance(official.get(key), (int, float)):
            out[key] = float(official[key])
    return {k: v for k, v in out.items() if v is not None}


def collect(rows):
    """(scenario, arm) -> metric -> list of per-repeat values."""
    table = collections.defaultdict(lambda: collections.defaultdict(list))
    for row in rows:
        arm = row.get("arm")
        if not arm:
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
        found = sorted({a for s, a in table if s == scenario})
        present = [a for a in CONTROL if a in found] + [
            a for a in found if a not in CONTROL
        ]
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
        #
        # The control is base and base_null POOLED. Using |base - base_null|
        # as the floor and base_null alone as the baseline double-counts the
        # same two observations: whichever of the identical pair landed low
        # became the reference, so any arm sitting near the other one cleared
        # its own noise. That is exactly how item_cap16 read +6.000 CLEARS in
        # one run and -5.000 within in the next, while tracking base in both.
        control = [a for a in CONTROL if a in present]
        if control:
            print("\n  against the pooled base + base_null control:")
            for name in names:
                pool = []
                for arm in control:
                    pool.extend(table[(scenario, arm)].get(name) or [])
                if len(pool) < 2:
                    continue
                centre = statistics.fmean(pool)
                floor = max(pool) - min(pool)
                verdicts = []
                for arm in [a for a in present if a not in CONTROL]:
                    series = table[(scenario, arm)].get(name) or []
                    if not series:
                        continue
                    delta = statistics.fmean(series) - centre
                    mark = "CLEARS" if abs(delta) > floor else "within"
                    verdicts.append(f"{arm} {delta:+.3f} [{mark}]")
                if verdicts:
                    print(
                        f"    {name:24s} control {centre:8.3f} "
                        f"spread {floor:.3f}   " + "   ".join(verdicts)
                    )

    print(
        "\nfloor = the full spread of base and base_null POOLED, and the "
        "centre is their pooled mean. This sentence used to describe the "
        "older rule -- |base - base_null| with base_null as the baseline -- "
        "which double-counts the same two observations and let item_cap16 "
        "read +6.000 CLEARS in one run and -5.000 within in the next while "
        "tracking base in both. A knob inside the floor has not been shown "
        "to do anything; it has NOT been shown to do nothing."
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
