"""
Lateral gaps between stowed items, against the clearance that forces them.

The sections show cargo sitting apart from its neighbours. Some of that is
mandatory: `SETTLED_ITEM_CLEARANCE` is 26 mm (official transport clearance
15 mm + 1 mm float guard + a self-imposed 10 mm settle margin), and the
candidate contract refuses anything closer. Anything WIDER than that is
slack the packing chose, and it is the part a better placement could take
back.

So this histograms the face-to-face gap between every pair of items that
overlap in the other two axes -- the pairs that are actually neighbours --
and splits them at the clearance. Reported per axis, because the transport
path runs along y and the container is long in x, so the two are not the
same question.

The measurement is pure geometry over a dump from
`scripts/dump_packing_geometry.py`. No replay, no physics.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CLEARANCE = 0.026


def span(item, axis):
    centre = item["c"][axis]
    half = item["s"][axis] / 2.0
    return centre - half, centre + half


def overlaps(a, b, axis, tolerance=0.0):
    a0, a1 = span(a, axis)
    b0, b1 = span(b, axis)
    return min(a1, b1) - max(a0, b0) > tolerance


def neighbour_gaps(items, axis):
    """
    Face-to-face gaps along `axis` for pairs that overlap in both others.

    Only the nearest neighbour in each direction counts: without that, a
    column of five items reports ten pairs and the far ones inflate the
    tail with gaps nothing could ever fill.
    """
    others = [i for i in (0, 1, 2) if i != axis]
    gaps = []
    for index, item in enumerate(items):
        lo, hi = span(item, axis)
        nearest = None
        for other_index, other in enumerate(items):
            if other_index == index:
                continue
            if not all(overlaps(item, other, a) for a in others):
                continue
            other_lo, _other_hi = span(other, axis)
            gap = other_lo - hi
            if gap < -1e-9:
                continue
            if nearest is None or gap < nearest:
                nearest = gap
        if nearest is not None:
            gaps.append(nearest)
    return gaps


def summarise(gaps):
    if not gaps:
        return None
    ordered = sorted(gaps)
    forced = [g for g in ordered if g <= CLEARANCE + 1e-6]
    slack = [g for g in ordered if g > CLEARANCE + 1e-6]
    return {
        "pairs": len(ordered),
        "at_clearance": len(forced),
        "wider": len(slack),
        "median": statistics.median(ordered),
        "slack_median": statistics.median(slack) if slack else None,
        "slack_total": sum(g - CLEARANCE for g in slack),
        "max": ordered[-1],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dumps", nargs="+")
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    print(f"clearance the contract forces: {CLEARANCE * 1000:.0f} mm\n")
    print(
        f'{"case / container":28s} {"axis":>5s} {"pairs":>6s} '
        f'{"at clr":>7s} {"wider":>6s} {"median":>8s} {"slack med":>10s} {"max":>7s}'
    )
    report = []
    for path in args.dumps:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        for container in data["containers"]:
            items = container["items"]
            if len(items) < 2:
                continue
            label = f'{data["case"]}/c{container["index"]}'
            for axis, name in ((0, "x"), (1, "y"), (2, "z")):
                entry = summarise(neighbour_gaps(items, axis))
                if entry is None:
                    continue
                slack_median = (
                    "-" if entry["slack_median"] is None
                    else f'{entry["slack_median"] * 1000:.0f}mm'
                )
                print(
                    f'{label:28s} {name:>5s} {entry["pairs"]:6d} '
                    f'{entry["at_clearance"]:7d} {entry["wider"]:6d} '
                    f'{entry["median"] * 1000:7.0f}mm {slack_median:>10s} '
                    f'{entry["max"] * 1000:6.0f}mm'
                )
                report.append({"case": label, "axis": name, **entry})
    if report:
        by_axis = {}
        for row in report:
            by_axis.setdefault(row["axis"], []).append(row)
        print()
        for axis, rows in sorted(by_axis.items()):
            pairs = sum(r["pairs"] for r in rows)
            wider = sum(r["wider"] for r in rows)
            slack = sum(r["slack_total"] for r in rows)
            print(
                f"{axis}: {wider}/{pairs} neighbour gaps are wider than the "
                f"forced clearance, {slack * 1000:.0f} mm of slack in total"
            )
        print(
            "\nslack is summed over nearest-neighbour pairs, so it is a "
            "length, not a volume -- it says where the packing is loose, "
            "not how many more items would fit."
        )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
