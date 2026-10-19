"""sw_tab.py <sweep.jsonl> [--full]: the two arms' plans per scene side by side (planned / soft / priority, the
token chosen, the derived cap, whether the plans are identical), and the totals."""
import collections
import json
import sys

rows = [json.loads(l) for l in open(sys.argv[1])]
full = "--full" in sys.argv
by = collections.defaultdict(dict)
for r in rows:
    by[r["scene"]][r["arm"]] = r
same = diff = 0
over = collections.Counter()
tot = collections.defaultdict(float)
print("| scene | mix | items (thr) | base planned / soft / prio (chosen) | amix planned / soft / prio (chosen) | cap (layers; est.) | same plan | s base -> amix |")
print("|---|---|---|---|---|---|---|---|")
for scene in sorted(by):
    b, a = by[scene].get("base"), by[scene].get("amix")
    if not b or not a:
        continue
    cap = ""
    for v in a["variants"]:
        if v.get("standing_cap") and v["side"] == a["chosen"]:
            c = v["standing_cap"]
            cap = f"{c['cap']:.2f} ({c.get('layers')}; {c.get('standing')}+{c.get('soft')})"
    if not cap:
        for v in a["variants"]:
            if v.get("standing_cap"):
                c = v["standing_cap"]
                cap = f"[{c['cap']:.2f} ({c.get('layers')}; {c.get('standing')}+{c.get('soft')})]"
                break
    eq = b["digest"] == a["digest"]
    same += eq
    diff += not eq
    for name, r in (("base", b), ("amix", a)):
        over[name] += r["planned"] >= r["thr"]
        tot[name + "_planned"] += r["planned"]
        tot[name + "_soft"] += r["soft"]
        tot[name + "_prio"] += r["prio"]
        tot[name + "_secs"] += r["secs"]
    mix = (b.get("spec") or {}).get("mix", "")
    short = lambda t: {"plain": "plain", "dense": "dense", "base": "base"}.get(t, "edge+strip" if "priority_rows" in t else "edge")
    if full or not eq:
        print(f"| {scene} | {mix} | {b['items']} ({b['thr']}) | {b['planned']} / {b['soft']} / {b['prio']} ({short(b['chosen'] or 'base')}) | "
              f"{a['planned']} / {a['soft']} / {a['prio']} ({short(a['chosen'] or 'base')}) | {cap} | {'yes' if eq else 'no'} | {b['secs']} -> {a['secs']} |")
n = same + diff
print()
print(f"scenes {n}: identical plans {same}, different {diff}; over the threshold base {over['base']} amix {over['amix']}")
for name in ("base", "amix"):
    print(f"{name}: planned {tot[name + '_planned'] / n:.1f} soft {tot[name + '_soft'] / n:.1f} prio {tot[name + '_prio'] / n:.1f} "
          f"planner s mean {tot[name + '_secs'] / n:.1f} max {max(r['secs'] for r in rows if r['arm'] == name):.1f}")
mixes = collections.defaultdict(lambda: collections.Counter())
for scene in by:
    b, a = by[scene].get("base"), by[scene].get("amix")
    if not b or not a:
        continue
    m = (b.get("spec") or {}).get("mix", "all")
    mixes[m]["n"] += 1
    mixes[m]["base_over"] += b["planned"] >= b["thr"]
    mixes[m]["amix_over"] += a["planned"] >= a["thr"]
    mixes[m]["base_planned"] += b["planned"]
    mixes[m]["amix_planned"] += a["planned"]
    mixes[m]["same"] += b["digest"] == a["digest"]
if len(mixes) > 1:
    print()
    print("| mix | n | over the threshold base / amix | planned base / amix | identical plans |")
    print("|---|---:|---|---|---:|")
    for m, c in sorted(mixes.items()):
        print(f"| {m} | {c['n']} | {c['base_over']} / {c['amix_over']} | {c['base_planned'] / c['n']:.1f} / {c['amix_planned'] / c['n']:.1f} | {c['same']} |")
