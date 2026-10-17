"""rank_picks.py <rank.jsonl> <base variant> <new variant>: per layout, the plan the new arm picked, and the scenes
whose analytic price (tab.py's) fell against the base."""
import collections
import json
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from tab import price  # noqa: E402

rows = [json.loads(line) for line in open(sys.argv[1]) if line.strip()]
base_name, new_name = sys.argv[2], sys.argv[3]
base = {(r["layout"], r["seed"]): r for r in rows if r["variant"] == base_name}


def short(side):
    name = (side or "-").split("@")[0]
    if "max_height=0.4" in (side or ""):
        name += "-edge"
    if "priority_rows" in (side or ""):
        name += "+strip"
    return name


picks = collections.defaultdict(collections.Counter)
for r in rows:
    if r["variant"] == new_name:
        picks[r["layout"]][short(r["chosen"])] += 1
for layout in sorted(picks):
    print(layout, dict(picks[layout]))
print()
for r in rows:
    if r["variant"] != new_name:
        continue
    b = base[(r["layout"], r["seed"])]
    d = price(r) - price(b)
    if d < -1e-9:
        print(f"{r['layout']} s{r['seed']:02d}: {b['planned']} -> {r['planned']} planned (thr {r['threshold']}), soft "
              f"{b['soft']} -> {r['soft']}, priority {b['priority']} -> {r['priority']}, {short(b['chosen'])} -> "
              f"{short(r['chosen'])}, {d:+.2f}")
