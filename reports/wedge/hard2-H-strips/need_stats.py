"""need_stats.py: H against crossings by the volume they need (fill basis of
the taxonomy: the first-threshold items' volume over the container volume)."""
import json, os, sys, statistics as stx, collections
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '../../..'))
sys.path.insert(0, REPO); sys.path.insert(0, HERE)
from bench.scenes import make_scene
from rule_alpha.config import DEFAULT_CONFIG
from rule_alpha.geometry import ContainerModel
from strip_stats import causes, group_of
DATA = '/home/user/inv-H-scratch/data'

def need_of(e):
    sc = make_scene(int(e['scene'].split('s')[-1]), 'hard2', e['task'])
    cvol = sum(ContainerModel(dict(c, packed_items=[]), DEFAULT_CONFIG).usable_volume for c in sc.containers)
    thr = len(sc.items) // 2 + 1
    return sum(i['length'] * i['width'] * i['height'] for i in sc.items[:thr]) / cvol

cz = causes()
rows = []
for rec in ('gate0-hard2', 'gate0-hard2-b'):
    for e in json.load(open(f'{DATA}/strips-{rec}.json')):
        g = group_of(e, cz)
        if g not in ('H', 'X'):
            continue
        st = e['steps']; uf = [s['usable_floor_m2'] for s in st]
        gone = next((i for i in range(len(st)) if all(u < 0.26 for u in uf[i:])), None)
        rows.append(dict(scene=e['scene'], task=e['task'], g=g, need=need_of(e), end=st[-1]['fill'] if st else 0,
                         gone_fill=st[gone]['fill'] if gone is not None else None, n=len(st),
                         after=(len(st) - gone - 1) if gone is not None else None,
                         gain=(st[-1]['fill'] - st[gone]['fill']) if gone is not None else None, margin=e['margin']))
json.dump(rows, open('/home/user/inv-H-scratch/need_rows.json', 'w'))
def med(xs):
    xs = [x for x in xs if x is not None]
    return f'{stx.median(xs):.3f}' if xs else '-'
print('| group | task | need band | n | need | fill at floor-gone | fill gained after | fill at end | placements after floor-gone |')
print('|---|---|---|---:|---:|---:|---:|---:|---:|')
for task in ('C', 'B'):
    for band in ((0, 0.38), (0.38, 0.44), (0.44, 0.51)):
        for g in ('H', 'X'):
            R = [r for r in rows if r['task'] == task and r['g'] == g and band[0] <= r['need'] < band[1]]
            if not R: continue
            print(f"| {g} | {task} | {band[0]}-{band[1]} | {len(R)} | {med([r['need'] for r in R])} | {med([r['gone_fill'] for r in R])} | {med([r['gain'] for r in R])} | {med([r['end'] for r in R])} | {med([r['after'] for r in R])} |")

# what the floor holds when it is gone: height of the floor layer, soft share, stacking so far
print()
print('| group | task | need band | n | floor boxes at floor-gone | of them standing | mean floor-box height (m) | soft share of floor-box area | raised boxes before floor-gone | raised volume share |')
print('|---|---|---|---:|---:|---:|---:|---:|---:|---:|')
E = {}
for rec in ('gate0-hard2', 'gate0-hard2-b'):
    for e in json.load(open(f'{DATA}/strips-{rec}.json')):
        E[e['scene']] = e
for task in ('C', 'B'):
    for band in ((0, 0.38), (0.38, 0.44), (0.44, 0.51)):
        for g in ('H', 'X'):
            R = [r for r in rows if r['task'] == task and r['g'] == g and band[0] <= r['need'] < band[1] and r['gone_fill'] is not None]
            if not R: continue
            nf, ns, hh, soft, nr, rv = [], [], [], [], [], []
            for r in R:
                st = E[r['scene']]['steps']; uf = [s['usable_floor_m2'] for s in st]
                gone = next(i for i in range(len(st)) if all(u < 0.26 for u in uf[i:]))
                fl = [s for s in st[:gone + 1] if s['floor']]; ra = [s for s in st[:gone + 1] if not s['floor']]
                area = lambda s: s['size'][0] * s['size'][1]
                vol = lambda s: s['size'][0] * s['size'][1] * s['size'][2]
                nf.append(len(fl)); ns.append(sum(1 for s in fl if s['standing']))
                hh.append(sum(vol(s) for s in fl) / max(1e-9, sum(area(s) for s in fl)))
                soft.append(sum(area(s) for s in fl if s['cls'].startswith('soft')) / max(1e-9, sum(area(s) for s in fl)))
                nr.append(len(ra)); rv.append(sum(vol(s) for s in ra) / max(1e-9, sum(vol(s) for s in st[:gone + 1])))
            m = lambda xs: stx.median(xs)
            print(f"| {g} | {task} | {band[0]}-{band[1]} | {len(R)} | {m(nf):.0f} | {m(ns):.0f} | {m(hh):.3f} | {m(soft):.2f} | {m(nr):.0f} | {m(rv):.2f} |")
