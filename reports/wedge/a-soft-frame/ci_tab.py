"""ci_tab.py <base_dir> <new_dir>: per-scene placed / threshold, the count_secure pick and the optimize seconds, and a by-count table."""
import json, sys, glob, os
base, new = sys.argv[1], sys.argv[2]
def load(d):
    out = {}
    for f in sorted(glob.glob(os.path.join(d, 'a-*.json'))):
        r = json.load(open(f)); m = r['metrics']
        out[os.path.basename(f)[:-5]] = (r, m)
    return out
B, N = load(base), load(new)
tot = {}
print("| scene | threshold | base placed / soft / prio | new placed / soft / prio | new pick (plain / soft / ledge planned) | topples base -> new | optimize s base -> new |")
print("|---|---:|---|---|---|---|---|")
for k in sorted(N):
    r, m = N[k]; rb, mb = B.get(k, (None, None))
    thr = m['total_items'] // 2 + 1
    cs = m.get('count_secure') or {}
    v = {x['side']: x for x in cs.get('variants', [])}
    chosen = cs.get('chosen'); chosen = {'soft@plan_count_secure_soft_ledge=true': 'soft + ledge'}.get(chosen, chosen)
    pl = v.get('plain', {}).get('planned', '-'); so = v.get('soft', {}).get('planned', '-'); le = v.get('soft@plan_count_secure_soft_ledge=true', {}).get('planned', '-')
    ob = (mb or {}).get('optimize', {}) or {}; on = m.get('optimize', {}) or {}
    bp = f"{mb['placed_count']} / {mb['soft_count']} / {mb['priority_count']}" if mb else '-'
    print(f"| {k} | {thr} | {bp}{' X' if mb and mb['placed_count'] >= thr else ''} | {m['placed_count']} / {m['soft_count']} / {m['priority_count']}{' X' if m['placed_count'] >= thr else ''} | {chosen} ({pl} / {so} / {le}) | {(mb or {}).get('shake_topples', '-')} -> {m.get('shake_topples')} | {ob.get('seconds', '-')} -> {on.get('seconds', '-')} (planner {on.get('planner_seconds', '-')}) |")
    grp = k.split('-')[1] if '-' in k else k
    t = tot.setdefault(grp, dict(n=0, cb=0, cn=0, pb=0, pn=0, sb=0, sn=0, tb=0, tn=0, picks=0, ob=0.0, on=0.0, plb=0.0, pln=0.0))
    t['n'] += 1; t['cn'] += int(m['placed_count'] >= thr); t['pn'] += m['placed_count']; t['sn'] += m['soft_count']; t['tn'] += m.get('shake_topples', 0) or 0
    t['picks'] += int(str(cs.get('chosen', '')).startswith('soft')); t['on'] += on.get('seconds', 0) or 0; t['pln'] += on.get('planner_seconds', 0) or 0
    if mb:
        t['cb'] += int(mb['placed_count'] >= thr); t['pb'] += mb['placed_count']; t['sb'] += mb['soft_count']; t['tb'] += mb.get('shake_topples', 0) or 0
        t['ob'] += ob.get('seconds', 0) or 0; t['plb'] += ob.get('planner_seconds', 0) or 0
print()
print("| group | n | counted base -> new | placed base -> new | soft base -> new | topples base -> new | block picked | optimize s base -> new | planner s base -> new |")
print("|---|---:|---|---|---|---|---:|---|---|")
for g, t in tot.items():
    n = t['n']
    print(f"| {g} | {n} | {t['cb']} -> {t['cn']} | {t['pb']/n:.2f} -> {t['pn']/n:.2f} | {t['sb']/n:.2f} -> {t['sn']/n:.2f} | {t['tb']} -> {t['tn']} | {t['picks']} | {t['ob']/n:.1f} -> {t['on']/n:.1f} | {t['plb']/n:.1f} -> {t['pln']/n:.1f} |")
