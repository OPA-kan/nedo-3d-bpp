"""scene_diff.py <base_dir> <new_dir>: episodes whose placed count, plan source or crossing differ, with the
re-plan's pick and the race's decision of the new run."""
import sys, json, glob


def load(d):
    out = {}
    for f in glob.glob(d + "/[abc]-*.json"):
        r = json.load(open(f))
        m = r["metrics"]
        out[r["scene"]] = (m["placed_count"], m["total_items"] // 2 + 1, r.get("plan_source"), m["soft_count"],
                           m["priority_count"], m.get("count_secure") or {})
    return out


a, b = load(sys.argv[1]), load(sys.argv[2])
for s in sorted(set(a) & set(b)):
    x, y = a[s], b[s]
    if x[0] != y[0] or x[2] != y[2]:
        cs = y[5]
        race = cs.get("race") or {}
        flag = "IN" if y[0] >= y[1] > x[0] else ("OUT" if x[0] >= x[1] > y[0] else "")
        print(f"{s:16s} thr {x[1]:3d} placed {x[0]:3d} -> {y[0]:3d} {flag:3s} source {x[2]} -> {y[2]} soft {x[3]} -> {y[3]} "
              f"prio {x[4]} -> {y[4]} | base plan {cs.get('base')} pick {cs.get('chosen')} "
              f"race {race.get('decision')} (planner {race.get('planner')}, dry {race.get('dry_run')}, score {race.get('score_pick')})")
