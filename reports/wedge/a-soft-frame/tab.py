"""tab.py <sweep.jsonl>: the analytic sweep by scene and by count (plain / soft / soft+ledge planned, the pick)."""
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
tot = {}
print("| scene | threshold | base | plain | soft | soft + ledge | chosen | final plan | planner s |")
print("|---|---:|---:|---:|---:|---:|---|---:|---:|")
for r in rows:
    cs = r['cs'] or {}
    v = {x['side']: x for x in cs.get('variants', [])}
    base = cs.get('base'); plain = v.get('plain', {}).get('planned'); soft = v.get('soft', {}).get('planned')
    ledge = v.get('soft@plan_count_secure_soft_ledge=true', {}).get('planned')
    thr = r['thr']
    chosen = cs.get('chosen')
    chosen = {'soft@plan_count_secure_soft_ledge=true': 'soft + ledge'}.get(chosen, chosen)
    ps = (r['opt'] or {}).get('planner_seconds')
    print(f"| {r['scene']} | {thr} | {base} | {plain if plain is not None else '-'} | {soft if soft is not None else '-'} | {ledge if ledge is not None else '-'} | {chosen} | {r['planned']}{' (over)' if r['planned'] >= thr else ''} | {ps} |")
    k = r['scene'].split(':')[0]
    t = tot.setdefault(k, dict(n=0, base=0, plain=0, final=0, cross_plain=0, cross_final=0, soft_wins=0, planner_s=0.0, soft_items=0, plain_soft=0))
    p = plain if plain is not None else base
    t['n'] += 1; t['base'] += base or 0; t['plain'] += p or 0; t['final'] += r['planned']
    t['cross_plain'] += int(p >= thr); t['cross_final'] += int(r['planned'] >= thr)
    t['soft_wins'] += int(str(cs.get('chosen', '')).startswith('soft')); t['planner_s'] += ps or 0
    t['soft_items'] += r['soft']; t['plain_soft'] += v.get('plain', {}).get('soft', r['soft']) if plain is not None else r['soft']
print()
print("| items | base plan | plain re-plan | with the soft block | plans over the threshold: plain / with block | block chosen | soft planned: plain / with block | planner s |")
print("|---|---:|---:|---:|---|---:|---|---:|")
for k, t in tot.items():
    n = t['n']
    print(f"| {k} | {t['base']/n:.1f} | {t['plain']/n:.1f} | {t['final']/n:.1f} | {t['cross_plain']} / {t['cross_final']} of {n} | {t['soft_wins']} | {t['plain_soft']/n:.1f} / {t['soft_items']/n:.1f} | {t['planner_s']/n:.1f} |")
