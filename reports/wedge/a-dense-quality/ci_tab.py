"""ci_tab.py <base_dir> <new_dir>: per-scene placed / threshold, the count_secure pick (plain / dense / dense on edge
planned), topples and the optimize seconds, and a by-count table (counted, placed, soft, priority, topples, picks, time)."""
import glob
import json
import os
import sys

base, new = sys.argv[1], sys.argv[2]
EDGE = "dense@plan_standing_rows_max_height=0.4"
STRIP = EDGE + "&plan_count_secure_dense_priority_rows=1&plan_count_secure_dense_soft_thin=0.25"
NAMES = {EDGE: "dense-edge", STRIP: "dense-edge+strip", "dense": "dense", "plain": "plain", "base": "base"}


def load(d):
    out = {}
    for f in sorted(glob.glob(os.path.join(d, "a-*.json"))):
        r = json.load(open(f))
        out[os.path.basename(f)[:-5]] = (r, r["metrics"])
    return out


B, N = load(base), load(new)
tot = {}
print("| scene | threshold | base placed / soft / prio | new placed / soft / prio | pick (plain / dense / dense-edge / strip planned) | topples base -> new | optimize s base -> new (planner) |")
print("|---|---:|---|---|---|---|---|")
for k in sorted(N):
    r, m = N[k]
    rb, mb = B.get(k, (None, None))
    thr = m["total_items"] // 2 + 1
    cs = m.get("count_secure") or {}
    v = {x["side"]: x for x in cs.get("variants", [])}
    chosen = NAMES.get(cs.get("chosen"), cs.get("chosen"))
    pl = v.get("plain", {}).get("planned", "-")
    de = v.get("dense", {}).get("planned", "-")
    ed = v.get(EDGE, {}).get("planned", "-")
    st = v.get(STRIP, {}).get("planned", "-")
    ob = (mb or {}).get("optimize", {}) or {}
    on = m.get("optimize", {}) or {}
    bp = f"{mb['placed_count']} / {mb['soft_count']} / {mb['priority_count']}" if mb else "-"
    print(f"| {k} | {thr} | {bp}{' X' if mb and mb['placed_count'] >= thr else ''} | "
          f"{m['placed_count']} / {m['soft_count']} / {m['priority_count']}{' X' if m['placed_count'] >= thr else ''} | "
          f"{chosen} ({pl} / {de} / {ed} / {st}) | {(mb or {}).get('shake_topples', '-')} -> {m.get('shake_topples')} | "
          f"{ob.get('seconds', '-')} -> {on.get('seconds', '-')} ({on.get('planner_seconds', '-')}) |")
    grp = k.split("-")[1] if "-" in k else k
    t = tot.setdefault(grp, dict(n=0, cb=0, cn=0, pb=0, pn=0, sb=0, sn=0, qb=0, qn=0, tb=0, tn=0, picks=0, ob=0.0,
                                 on=0.0, omax=0.0))
    t["n"] += 1
    t["cn"] += int(m["placed_count"] >= thr)
    t["pn"] += m["placed_count"]
    t["sn"] += m["soft_count"]
    t["qn"] += m["priority_count"]
    t["tn"] += m.get("shake_topples", 0) or 0
    t["picks"] += int(str(cs.get("chosen", "")).startswith("dense"))
    t["strips"] = t.get("strips", 0) + int(cs.get("chosen") == STRIP)
    t["on"] += on.get("seconds", 0) or 0
    t["omax"] = max(t["omax"], on.get("seconds", 0) or 0)
    if mb:
        t["cb"] += int(mb["placed_count"] >= thr)
        t["pb"] += mb["placed_count"]
        t["sb"] += mb["soft_count"]
        t["qb"] += mb["priority_count"]
        t["tb"] += mb.get("shake_topples", 0) or 0
        t["ob"] += ob.get("seconds", 0) or 0
print()
print("| group | n | counted base -> new | placed base -> new | soft base -> new | priority base -> new | topples base -> new | dense picked (strip) | optimize s base -> new (max) |")
print("|---|---:|---|---|---|---|---|---:|---|")
for g, t in tot.items():
    n = t["n"]
    print(f"| {g} | {n} | {t['cb']} -> {t['cn']} | {t['pb']/n:.2f} -> {t['pn']/n:.2f} | {t['sb']/n:.2f} -> {t['sn']/n:.2f} | "
          f"{t['qb']/n:.2f} -> {t['qn']/n:.2f} | {t['tb']} -> {t['tn']} | {t["picks"]} ({t.get("strips", 0)}) | "
          f"{t['ob']/n:.1f} -> {t['on']/n:.1f} ({t['omax']:.1f}) |")
