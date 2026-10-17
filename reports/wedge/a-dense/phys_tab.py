"""phys_tab.py <base_dir> <record.json>...: the local physics records against the base run's records of the same
scenes: placed / soft / priority, the plan picked, the planned count, replayed poses, topples, the optimize seconds."""
import json
import os
import sys

base = sys.argv[1]
EDGE = "dense@plan_standing_rows_max_height=0.4"
print("| scene | threshold | v57 placed / soft / prio | dense placed / soft / prio | pick | plan (plain / dense / edge) | plan poses replayed | topples | CoM | optimize s v57 -> dense |")
print("|---|---:|---|---|---|---|---:|---:|---:|---|")
for f in sys.argv[2:]:
    r = json.load(open(f))
    m = r["metrics"]
    name = os.path.basename(f)[:-5]
    thr = m["total_items"] // 2 + 1
    cs = m.get("count_secure") or {}
    v = {x["side"]: x for x in cs.get("variants", [])}
    pick = {EDGE: "dense on edge"}.get(cs.get("chosen"), cs.get("chosen"))
    replayed = sum(1 for s in r["steps"] if s.get("event") == "step" and s.get("archetype") == "plan")
    steps = sum(1 for s in r["steps"] if s.get("event") == "step")
    bf = os.path.join(base, name + ".json")
    bm = json.load(open(bf))["metrics"] if os.path.exists(bf) else None
    bp = f"{bm['placed_count']} / {bm['soft_count']} / {bm['priority_count']}" if bm else "-"
    bo = ((bm or {}).get("optimize") or {}).get("seconds", "-")
    print(f"| {name} | {thr} | {bp} | **{m['placed_count']}** / {m['soft_count']} / {m['priority_count']}"
          f"{' (counted)' if m['placed_count'] >= thr else ''} | {pick} | "
          f"{v.get('plain', {}).get('planned', '-')} / {v.get('dense', {}).get('planned', '-')} / {v.get(EDGE, {}).get('planned', '-')} | "
          f"{replayed} of {steps} | {m.get('shake_topples')} | {m.get('com_z_above_floor_ratio', 0):.3f} | "
          f"{bo} -> {(m.get('optimize') or {}).get('seconds', '-')} |")
