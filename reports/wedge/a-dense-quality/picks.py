"""picks.py <rank.jsonl> [layout]: per scene and arm, the plan chosen and every variant's planned count."""
import json
import sys

only = sys.argv[2] if len(sys.argv) > 2 else None


def short(side):
    if side is None:
        return "-"
    name = side.split("@")[0]
    if "plan_standing_rows_max_height=0.4" in side:
        name += "-edge"
    if "priority_rows" in side:
        name += "+strip"
    return name


for line in open(sys.argv[1]):
    r = json.loads(line)
    if only and r["layout"] != only:
        continue
    vs = ", ".join(f"{short(v['side'])} {v.get('planned', 'skip')}" for v in r["variants"] or [])
    print(f"{r['layout']} s{r['seed']:02d} {r['variant']:7s} planned {r['planned']:2d} (thr {r['threshold']}) soft {r['soft']:2d} "
          f"prio {r['priority']:2d} chosen {short(r['chosen']):12s} [{vs}] {r['seconds']} s")
