"""hard_why.py <dir>: why each hard scene is hard -- the count the threshold demands against the room, by scene attribute."""
import json, glob, sys, collections, statistics as st
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1]))
from bench.scenes import make_scene
d = sys.argv[1]
rows = []
for f in sorted(glob.glob(d + '/[bc]-*.json')):
    r = json.load(open(f)); m = r['metrics']; spec = r['scene_spec']
    sc = make_scene(spec['seed'], spec.get('layout') or 'hard', spec['task'])
    thr = m['total_items'] // 2 + 1; mg = m['placed_count'] - thr
    cvol = sum(c['length'] * c['width'] * c['height'] for c in sc.containers)
    ivol = lambda i: i['length'] * i['width'] * i['height']
    first = sum(ivol(i) for i in sc.items[:thr])            # Task C: the first thr of the stream must all go
    smallest = sum(sorted(ivol(i) for i in sc.items)[:thr])  # any agent: at least this volume
    placed_vol = m.get('placed_volume_m3', 0.0)
    rows.append(dict(scene=r['scene'], mg=mg, total=m['total_items'], thr=thr, placed=m['placed_count'], fill=m.get('fill_volume', 0),
                     need_first=100 * first / cvol, need_small=100 * smallest / cvol, got=100 * placed_vol / cvol,
                     n=spec['containers_n'], base=spec['base_count'], soft=spec['soft_share'], prio=spec['priority_rate'],
                     mix=spec['mix'], order=spec['order'], pool=spec['pool'], shelves=spec['shelves'], pc=spec['priority_container'], **({'stratum': spec['stratum']} if 'stratum' in spec else {}),
                     per=round(m['total_items'] / spec['containers_n'])))
cross = lambda rs: f"{sum(1 for r in rs if r['mg'] >= 0)}/{len(rs)}"
print(f"{d}: crossings {cross(rows)}; the need (fill the threshold demands, first-thr items / smallest-thr items) against the fill reached (container volume basis)")
for key in (('stratum',) if any('stratum' in r for r in rows) else ()) + ('base', 'n', 'mix', 'order', 'soft', 'prio', 'shelves', 'pc', 'pool'):
    groups = collections.defaultdict(list)
    for r in rows: groups[r[key]].append(r)
    print(f"  by {key:8s}", '  '.join(f"{k}: {cross(v)} (need {st.mean(x['need_first'] for x in v):.0f}/{st.mean(x['need_small'] for x in v):.0f}, got {st.mean(x['got'] for x in v):.0f}, mg {st.mean(x['mg'] for x in v):+.1f})" for k, v in sorted(groups.items(), key=lambda kv: str(kv[0]))))
print("  need_first vs crossing:", '  '.join(f"[{lo},{hi}): {cross([r for r in rows if lo <= r['need_first'] < hi])}" for lo, hi in ((0, 30), (30, 40), (40, 50), (50, 60), (60, 200))))
print("  need_small vs crossing:", '  '.join(f"[{lo},{hi}): {cross([r for r in rows if lo <= r['need_small'] < hi])}" for lo, hi in ((0, 30), (30, 40), (40, 50), (50, 60), (60, 200))))
print("  per-scene (mg, need_first, need_small, got, base, mix, order):")
for r in sorted(rows, key=lambda r: r['mg']):
    print(f"    {r['scene']} mg {r['mg']:+3d} {r['placed']:>3}/{r['total']:<3} need {r['need_first']:4.0f}/{r['need_small']:4.0f} got {r['got']:4.0f}  base {r['base']} n{r['n']} {r['mix']:6s} {r['order']:11s} soft {r['soft']} prio {r['prio']} pool {r['pool']} shelves {r['shelves']} pc {int(r['pc'])}")
