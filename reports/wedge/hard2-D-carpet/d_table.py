"""d_table.py: the D episodes at a glance (records only), markdown on stdout."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import D_V50, load_record, scene_of
S = json.load(open(os.path.join(HERE, 'data', 'course_summary.json')))
print('| scene | order | ctrs (P = priority) | margin | soft placed: floor / on soft / shelf | soft floor share (end) | step soft share passed 0.4 | first big hard item in stream / threshold | hard placed | declined on |')
print('|---|---|---|---:|---|---:|---:|---|---:|---|')
for rec in ('gate0-hard2', 'gate0-hard2-b'):
    rows = {s['scene']: s for s in S[rec]}
    for sc in D_V50[rec]:
        s = rows[sc]
        r = load_record(rec, sc)
        scn = scene_of(r['scene_spec'])
        pc = ''.join('P' if c.get('is_prioritized') else '.' for c in scn.containers)
        items = scn.items
        fs = next((p for p, i in enumerate(items) if i['is_soft']), 0)
        big = next((p for p, i in enumerate(items) if p > fs and not i['is_soft'] and i['length'] * i['width'] >= 0.2), None)
        placed = {st['item_index'] for st in r['steps'] if st.get('event') == 'step' and st.get('is_placed_safe')}
        if r['scene_spec']['task'] == 'C':
            nxt = items[s['placed']] if s['placed'] < len(items) else None
        else:
            nxt = next((i for i in items if i['index'] not in placed), None)
        dn = '' if nxt is None else (('soft ' if nxt['is_soft'] else '') + 'x'.join(str(v) for v in (nxt['length'], nxt['width'], nxt['height'])))
        w = s['soft_where']
        print(f"| {sc} | {s['order']} | {pc} | {s['mg']:+d} | {s['n_soft']}: {w.get('floor', 0)} / {w.get('soft', 0)} / {w.get('shelf', 0)} | {s['soft_share_end']:.2f} | {s['k_soft40']} | {big} / {s['thr']} | {s['n_hard']} | {dn} |")
