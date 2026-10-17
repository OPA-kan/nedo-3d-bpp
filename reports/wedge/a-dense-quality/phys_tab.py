"""phys_tab.py <base_dir> <new_dir>: the local physics records of the two arms on the same scenes, priced by
bench.platform_score: placed / soft / priority (covered), the plan picked and its layers, the plan poses
replayed, topples, the centre of mass, the score and its delta, the optimize seconds."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from bench.platform_score import score_episode  # noqa: E402

base, new = sys.argv[1], sys.argv[2]
EDGE = "dense@plan_standing_rows_max_height=0.4"


def row(d, name):
    r = json.load(open(os.path.join(d, name + ".json")))
    m = r["metrics"]
    cs = m.get("count_secure") or {}
    v = {x["side"]: x for x in cs.get("variants", [])}
    pick = {EDGE: "dense on edge"}.get(cs.get("chosen"), cs.get("chosen"))
    chosen = v.get(cs.get("chosen"), {})
    replayed = sum(1 for s in r["steps"] if s.get("event") == "step" and s.get("archetype") == "plan")
    steps = sum(1 for s in r["steps"] if s.get("event") == "step")
    return m, pick, chosen, replayed, steps, score_episode(r)


print("| scene | threshold | arm | placed / soft / prio (covered) | pick (planned; flat / ledge / standing / soft) | plan poses replayed | topples | CoM | score | optimize s |")
print("|---|---:|---|---|---|---:|---:|---:|---:|---:|")
for f in sorted(os.listdir(new)):
    if not f.startswith("a-"):
        continue
    name = f[:-5]
    thr = None
    rows = []
    for d, arm in ((base, "v58"), (new, "quality")):
        m, pick, chosen, replayed, steps, sc = row(d, name)
        thr = m["total_items"] // 2 + 1
        layers = chosen.get("layers") or {}
        rows.append((arm, m, pick, chosen, layers, replayed, steps, sc))
    s0 = rows[0][7]["score"]
    for arm, m, pick, chosen, layers, replayed, steps, sc in rows:
        delta = "" if arm == "v58" else f" ({sc['score'] - s0:+.2f})"
        print(f"| {name} | {thr} | {arm} | {m['placed_count']} / {m['soft_count']} / {m['priority_count']} "
              f"({m['priority_covered']}) | {pick} ({chosen.get('planned', '-')}; "
              f"{layers.get('flat', '-')} / {layers.get('ledge', '-')} / {layers.get('standing', '-')} / {layers.get('soft', '-')}) | "
              f"{replayed} of {steps} | {m.get('shake_topples')} | {m.get('com_z_above_floor_ratio', 0):.3f} | "
              f"{sc['score']:.2f}{delta} | {m.get('optimize_seconds', '-')} |")
