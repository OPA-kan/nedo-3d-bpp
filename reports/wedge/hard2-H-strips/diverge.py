"""diverge.py: the H scenes against the same scene where it crosses.

Pairs: v49 det (bandntdet-hard2) against v50 det (gate0det-hard2) on the C
scenes the gate lost (s0007, s0040, s0076: same stream, same arm but the
soft gate), and C against B on the same seed (same items and containers; B
chooses from a pool).  For each pair: the first step where the placements
differ (item or pose by more than 1 cm), the usable floor and the fill along
the course, and the step where the floor is gone."""
import json, os, sys
DATA = '/home/user/inv-H-scratch/data'
def load(rec):
    return {e['scene']: e for e in json.load(open(f'{DATA}/strips-{rec}.json'))}
R = {r: load(r) for r in ('gate0-hard2', 'gate0-hard2-b', 'gate0det-hard2', 'bandntdet-hard2')}
def gone(e):
    st = e['steps']; uf = [s['usable_floor_m2'] for s in st]
    return next((i for i in range(len(st)) if all(u < 0.26 for u in uf[i:])), None)
def first_diff(a, b):
    for i, (x, y) in enumerate(zip(a['steps'], b['steps'])):
        if x['size'] != y['size'] or x['arch'] != y['arch'] or abs(x['gap']['left'] - y['gap']['left']) > 0.01 or abs(x['gap']['door'] - y['gap']['door']) > 0.01:
            return i
    return min(len(a['steps']), len(b['steps']))
def line(e, label):
    g = gone(e); st = e['steps']
    traj = ' '.join(f"{s['usable_floor_m2']:.2f}" for s in st)
    return (f"  {label}: placed {e['placed']} (margin {e['margin']:+d}), floor gone at step {g} "
            f"(fill {st[g]['fill'] if g is not None else '-'}), end fill {st[-1]['fill']}\n    usable floor by step: {traj}")
pairs = [('c-hard2-s0007', 'bandntdet-hard2', 'gate0det-hard2'), ('c-hard2-s0040', 'bandntdet-hard2', 'gate0det-hard2'),
         ('c-hard2-s0076', 'bandntdet-hard2', 'gate0det-hard2')]
for sc, a, b in pairs:
    A, B = R[a][sc], R[b][sc]
    i = first_diff(A, B)
    print(f"{sc}: {a} vs {b}: first differing placement at step {i}")
    print(f"    {a} step {i}: {A['steps'][i]['arch']} {A['steps'][i]['cls']} {A['steps'][i]['size']} gaps {A['steps'][i]['gap']}" if i < len(A['steps']) else '')
    print(f"    {b} step {i}: {B['steps'][i]['arch']} {B['steps'][i]['cls']} {B['steps'][i]['size']} gaps {B['steps'][i]['gap']}" if i < len(B['steps']) else '')
    print(line(A, a)); print(line(B, b))
print()
for seed in ('0028', '0076', '0078', '0039', '0040', '0065', '0067', '0083', '0062', '0066'):
    c, b = R['gate0-hard2'][f'c-hard2-s{seed}'], R['gate0-hard2-b'][f'b-hard2-s{seed}']
    print(f"s{seed}: C vs B")
    print(line(c, 'C')); print(line(b, 'B'))
