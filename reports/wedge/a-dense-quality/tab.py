"""tab.py <sweep.jsonl> [base variant]: per layout and variant, the plans' means and an analytic price.

The price is the platform's arithmetic on the plan itself (bench.platform_score's weights: placement 0.143 x the
priority share, soft 0.141 x the soft share, cog 0.219 x (125 - 137 x the plan's com ratio), fill 0.287 x the
planned volume over the container's 3.17 m^3 nominal (c1: 1.6 x 1.4 x 1.57 ... the tolerant evaluator's level is read off the
records, not here) -- gated by the plan holding the threshold; relative to the base variant per scene.
"""
import collections
import json
import statistics
import sys

rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
base_name = sys.argv[2] if len(sys.argv) > 2 else "base"
CAP = 4.0  # the evaluator's effective denominator on c1 (record x80-s0003: 2.47 m^3 placed = fill 61.65)


def price(r):
    counted = r["planned"] >= r["threshold"]
    fill = 0.287 * 100.0 * r["volume"] / CAP
    if not counted:
        return fill
    return (fill + 0.143 * 100.0 * r["priority"] / max(1, r["priority_total"])
            + 0.141 * 100.0 * r["soft"] / max(1, r["soft_total"]) + 0.219 * (125.0 - 137.0 * r["com"]))


by = collections.defaultdict(list)
for r in rows:
    by[(r["layout"], r["variant"])].append(r)
base = {(r["layout"], r["seed"]): r for r in rows if r["variant"] == base_name}
variants = []
for r in rows:
    if r["variant"] not in variants:
        variants.append(r["variant"])
layouts = sorted({r["layout"] for r in rows})
print("| layout | variant | n | planned | over threshold | soft | priority (hard) | com | com swap | price vs base | s |")
print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
for layout in layouts:
    for v in variants:
        rs = by.get((layout, v), [])
        if not rs:
            continue
        d = [price(r) - price(base[(r["layout"], r["seed"])]) for r in rs if (r["layout"], r["seed"]) in base]
        swaps = [r["com_swap"] for r in rs if r.get("com_swap") is not None]
        print(f"| {layout} | {v} | {len(rs)} | {statistics.mean(r['planned'] for r in rs):.1f} | "
              f"{sum(1 for r in rs if r['planned'] >= r['threshold'])} | {statistics.mean(r['soft'] for r in rs):.1f} | "
              f"{statistics.mean(r['priority'] for r in rs):.1f} ({statistics.mean(r['priority_hard'] for r in rs):.1f}) | "
              f"{statistics.mean(r['com'] for r in rs):.3f} | {statistics.mean(swaps) if swaps else float('nan'):.3f} | "
              f"{statistics.mean(d) if d else 0.0:+.2f} | {statistics.mean(r['seconds'] for r in rs):.1f} |")
print()
print("| variant | n | planned | over threshold | soft | priority (hard) | com | price vs base | up / down |")
print("|---|---:|---:|---:|---:|---:|---:|---:|---|")
for v in variants:
    rs = [r for r in rows if r["variant"] == v]
    d = [price(r) - price(base[(r["layout"], r["seed"])]) for r in rs if (r["layout"], r["seed"]) in base]
    print(f"| {v} | {len(rs)} | {statistics.mean(r['planned'] for r in rs):.1f} | "
          f"{sum(1 for r in rs if r['planned'] >= r['threshold'])} | {statistics.mean(r['soft'] for r in rs):.1f} | "
          f"{statistics.mean(r['priority'] for r in rs):.1f} ({statistics.mean(r['priority_hard'] for r in rs):.1f}) | "
          f"{statistics.mean(r['com'] for r in rs):.3f} | {statistics.mean(d) if d else 0.0:+.2f} | "
          f"{sum(1 for x in d if x > 1e-9)} / {sum(1 for x in d if x < -1e-9)} |")
