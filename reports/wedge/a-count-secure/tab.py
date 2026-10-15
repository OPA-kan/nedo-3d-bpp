"""tab.py <jsonl>: planned (soft) per scene and config, crossings of thr and thr+2."""
import sys, json, collections
rows = [json.loads(l) for l in open(sys.argv[1])]
ovs = list(dict.fromkeys(r["ov"] for r in rows))
scenes = list(dict.fromkeys(r["scene"] for r in rows))
by = {(r["ov"], r["scene"]): r for r in rows}
print("scene      thr | " + " | ".join(f"{i}:{o[:40]}" for i, o in enumerate(ovs)))
for s in scenes:
    cells = []
    for o in ovs:
        r = by.get((o, s))
        if r is None:
            cells.append("   -    ")
            continue
        cs = r.get("cs") or {}
        extra = ""
        if cs and cs.get("variants"):
            extra = " " + "/".join(f"{v.get('side','?')[:14]}={v.get('planned','x')}" for v in cs["variants"]) + ("*" if cs.get("chosen") != "base" else "")
        cells.append(f"{r['planned']:3d} ({r['soft']:2d}s,{r['maxtop']:.2f},{r['secs']:.0f}s){extra}")
    thr = next(by[(o, s)]["thr"] for o in ovs if (o, s) in by)
    print(f"{s:10s} {thr:3d} | " + " | ".join(cells))
for i, o in enumerate(ovs):
    rs = [by[(o, s)] for s in scenes if (o, s) in by]
    print(i, o, "n", len(rs), "planned", sum(r["planned"] for r in rs), "soft", sum(r["soft"] for r in rs),
          ">=thr", sum(r["planned"] >= r["thr"] for r in rs), ">=thr+2", sum(r["planned"] >= r["thr"] + 2 for r in rs))
