"""arch_report.py <scene> [--back N] [--maps s1,s2]: the run-in of a reference
run (ref.py output), one line per step, and floor maps at chosen steps.

Columns: step, item (class), what placed it (stage/rung, shadow outcome),
why (the trace: shade vetoes of the ladder's pick, shadow refusals, how many
poses the resort tried), the ladder's own view (candidates considered ->
shortlist survivors, top vetoes, the chosen rung and its best pose's shade
and verdict), and the floor before/after (usable floor, usable surface for
the 0.40 x 0.55 x 0.24 window)."""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from strips import cls_of  # noqa: E402

REF = "/home/user/inv-H-scratch/ref"


def item_cls(it):
    return cls_of(it)


def stage_of(a):
    """'LR-relaxed: ' / 'LR-any: ' when the last resort's ladder placed it (the
    reason string carries the stage; the record's archetype does not)."""
    r = a.get("reason") or ""
    if r.startswith("last-resort relaxed"):
        return "LR-relaxed: "
    if r.startswith("last-resort any-container"):
        return "LR-any: "
    if r.startswith("shadow: "):
        return "shadow-alt: "
    return ""


def trace_summary(tr):
    shades = [e for e in tr if e["ev"] == "shade"]
    ver = [e for e in tr if e["ev"] == "verdict"]
    sv = sum(1 for e in shades if e["area"] > 0.15)
    hard = sum(1 for e in ver if e["hard"])
    soft = sum(1 for e in ver if not e["ok"] and not e["hard"])
    archs = collections.Counter(e["arch"] for e in shades if e["area"] > 0.15)
    s = f"shade>0.15 x{sv}" + (
        f" ({', '.join(f'{k} {v}' for k, v in archs.items())})" if archs else ""
    )
    s += f"; verdicts {len(ver)} (hard {hard}, soft {soft})"
    return s


def ladder_summary(lad):
    if lad.get("none"):
        return "ladder: no candidate in any container"
    vc = sorted((lad.get("veto_counts") or {}).items(), key=lambda kv: -kv[1])[:3]
    s = f"{lad.get('considered')}->{lad.get('survivors')} [{', '.join(f'{k} {v}' for k, v in vc)}] rung {lad.get('chosen_rung')}"
    rd = lad.get("rung_detail") or []
    for r in rd:
        if r["rung"] == lad.get("chosen_rung") and r["top"]:
            c = r["top"][0]
            v = c.get("verdict") or {}
            s += (
                f" best {c['size']}@{[round(x, 2) for x in c['center']]} shade {c.get('shade')} "
                f"{'ok' if v.get('ok') else ('HARD' if v.get('hard') else 'soft-veto') if v else '?'}"
            )
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene")
    ap.add_argument("--back", type=int, default=12)
    ap.add_argument("--maps", default="")
    ap.add_argument("--from", dest="k0", type=int, default=None)
    args = ap.parse_args()
    d = json.load(open(f"{REF}/ref-{args.scene}.json"))
    dumps = d["dumps"]
    n = len(dumps)
    k0 = args.k0 if args.k0 is not None else max(0, n - 1 - args.back)
    print(
        f"## {args.scene}: ref placed {d['placed']} (thr {d['thr']}, margin {d['margin']}, end {d['end']}); record {d['record_placed']}"
    )
    print()
    print(
        "| step | item | placed by | why (trace) | ladder | usable floor / surface before -> after |"
    )
    print("|---:|---|---|---|---|---|")
    for i in range(k0, n):
        x = dumps[i]
        a = x["agent"]
        it = x["pool"][a["pool_index"]] if a else x["pool"][0]
        fb = x["floor_before"]
        fa = dumps[i + 1]["floor_before"] if i + 1 < n else None
        uf = (
            "+".join(f"{f['usable']:.2f}" for f in fb)
            + " / "
            + "+".join(f"{f['usable_top']:.2f}" for f in fb)
        )
        if fa:
            uf += (
                " -> "
                + "+".join(f"{f['usable']:.2f}" for f in fa)
                + " / "
                + "+".join(f"{f['usable_top']:.2f}" for f in fa)
            )
        placed = (
            "DECLINE"
            if a is None
            else f"{stage_of(a)}{a['arch']} ({a['shadow']}) {a['size']}@{[round(v, 2) for v in a['pos_local']]} c{a['ci']}"
        )
        print(
            f"| {i} | {item_cls(it)} | {placed} | {trace_summary(x['trace'])} | {ladder_summary(x['ladder'])} | {uf} |"
        )
    for s in [int(v) for v in args.maps.split(",") if v]:
        print()
        print(
            f"Floor before step {s} (back at the top, door at the bottom; # hard, s soft, . usable, - dead):"
        )
        for ci, f in enumerate(dumps[s]["floor_before"]):
            print(f"container {ci}:")
            print("```")
            print("\n".join(f["map"]))
            print("```")


if __name__ == "__main__":
    main()
