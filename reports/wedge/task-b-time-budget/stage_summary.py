"""stage_summary.py <dir>: mean seconds per stage by the kind of call."""
import collections
import glob
import json
import os
import sys

RESCUE = {"physics-resort", "count-mode", "grid-rescue", "grid-rescue-cover"}
STAGES = ["ladder", "pocket", "checkmate", "stack", "last_resort", "resort", "grid", "shadow", "other"]


def kind(r):
    if not r["placed"]:
        return "decline"
    a = r["archetype"] or ""
    if a in RESCUE:
        return "rescue placement"
    if a == "stack-rl":
        return "stack placement"
    return "ladder placement"


for d in sys.argv[1:]:
    rows = []
    for f in sorted(glob.glob(os.path.join(d, "*.stages.json"))):
        name = os.path.basename(f).split(".")[0]
        for i, r in enumerate(json.load(open(f))):
            r["scene"] = name; r["i"] = i
            rows.append(r)
    groups = collections.defaultdict(list)
    for r in rows:
        groups[kind(r)].append(r)
    print("| call | n | total | " + " | ".join(STAGES) + " |")
    print("|---|---|---|" + "---|" * len(STAGES))
    for k in ("ladder placement", "stack placement", "rescue placement", "decline"):
        xs = groups.get(k, [])
        if not xs:
            continue
        tot = sum(r["total"] for r in xs) / len(xs)
        cells = [f"{sum(r['stages'].get(s, 0.0) for r in xs) / len(xs):.2f}" for s in STAGES]
        print(f"| {k} | {len(xs)} | {tot:.2f} | " + " | ".join(cells) + " |")
    print()
    for r in rows:
        if kind(r) in ("decline",) or (kind(r) == "rescue placement" and r["total"] > 5.5):
            st = ", ".join(f"{k} {v:.2f}" for k, v in sorted(r["stages"].items(), key=lambda kv: -kv[1]) if v >= 0.05)
            print(f"  {r['scene']} call {r['i']} ({kind(r)}, {r['archetype']}) {r['total']:.2f}s: {st}")
