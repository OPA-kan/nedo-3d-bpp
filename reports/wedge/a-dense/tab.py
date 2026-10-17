"""tab.py <sweep.jsonl>: the analytic sweep by scene and by count (base, plain, dense, dense on edge planned; the pick;
the plans at or over the threshold; the soft and priority boxes planned; the planner's seconds)."""
import json
import sys

EDGE = "dense@plan_standing_rows_max_height=0.4"
rows = [json.loads(l) for l in open(sys.argv[1])]
tot = {}
print("| scene | threshold | base | plain | dense | dense on edge | chosen | final plan (soft / priority) | planner s |")
print("|---|---:|---:|---:|---:|---:|---|---|---:|")
for r in rows:
    cs = r["cs"] or {}
    v = {x["side"]: x for x in cs.get("variants", [])}

    def n(side):
        x = v.get(side, {})
        return "skip" if x.get("skipped") else x.get("planned", "-")
    base = cs.get("base")
    thr = r["thr"]
    chosen = {EDGE: "dense on edge"}.get(cs.get("chosen"), cs.get("chosen"))
    ps = (r["opt"] or {}).get("planner_seconds")
    print(f"| {r['scene']} | {thr} | {base} | {n('plain')} | {n('dense')} | {n(EDGE)} | {chosen} | "
          f"{r['planned']}{' (over)' if r['planned'] >= thr else ''} ({r['soft']} / {r['prio']}) | {ps} |")
    k = r["scene"].split(":")[0]
    t = tot.setdefault(k, dict(n=0, base=0, plain=0, final=0, cross_base=0, cross_plain=0, cross_final=0, dense_wins=0,
                               planner_s=0.0, soft=0, prio=0, plain_soft=0, plain_prio=0))
    p = v.get("plain", {}).get("planned")
    p = base if p is None else p
    t["n"] += 1
    t["base"] += base or 0
    t["plain"] += p or 0
    t["final"] += r["planned"]
    t["cross_base"] += int((base or 0) >= thr)
    t["cross_plain"] += int(p >= thr)
    t["cross_final"] += int(r["planned"] >= thr)
    t["dense_wins"] += int(str(cs.get("chosen", "")).startswith("dense"))
    t["planner_s"] += ps or 0
    t["soft"] += r["soft"]
    t["prio"] += r["prio"]
    t["plain_soft"] += v.get("plain", {}).get("soft", r["soft"]) if "plain" in v else r["soft"]
    t["plain_prio"] += v.get("plain", {}).get("priority", r["prio"]) if "plain" in v else r["prio"]
print()
print("| items | base plan | plain re-plan | with the dense plans | plans over the threshold: base / plain / with dense | dense chosen | soft planned: plain / with dense | priority planned: plain / with dense | planner s |")
print("|---|---:|---:|---:|---|---:|---|---|---:|")
for k, t in tot.items():
    m = t["n"]
    print(f"| {k} | {t['base']/m:.1f} | {t['plain']/m:.1f} | {t['final']/m:.1f} | {t['cross_base']} / {t['cross_plain']} / "
          f"{t['cross_final']} of {m} | {t['dense_wins']} | {t['plain_soft']/m:.1f} / {t['soft']/m:.1f} | "
          f"{t['plain_prio']/m:.1f} / {t['prio']/m:.1f} | {t['planner_s']/m:.1f} |")
