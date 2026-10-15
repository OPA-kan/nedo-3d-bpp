"""cf_orient.py: the counterfactual branches by how the pose at k differs
from the agent's own (null) pose: lying -> standing, standing -> lying, the
same class turned (footprint rotated), or the same orientation moved, or a
different item / raised pose.  Crossing rate and mean change of the margin
against the null, H scenes and crossings separately."""
import json, glob, os, collections
HERE = os.path.dirname(os.path.abspath(__file__))
HSET = {h['scene'] for h in json.load(open(f'{HERE}/hlist.json'))}
def standing(sz): return sz[2] > min(sz[0], sz[1]) + 1e-6 and sz[2] > 0.3
def floor(p, sz): return p[2] - sz[2] / 2 < 0.14
def change(a, b):
    if not a.get('size') or not b.get('size') or a.get('item_index') != b.get('item_index'):
        return 'other item'
    if not floor(b['pos_local'], b['size']) or not floor(a['pos_local'], a['size']):
        return 'raised involved'
    sa, sb = standing(a['size']), standing(b['size'])
    if sa != sb:
        return 'lying -> standing' if sb else 'standing -> lying'
    if [round(x, 2) for x in a['size']] != [round(x, 2) for x in b['size']]:
        return 'same class, turned'
    return 'same orientation, moved'
st = collections.defaultdict(lambda: [0, 0, 0.0])
seen = set()
for f in sorted(glob.glob('/home/user/inv-H-scratch/cf/cf-[bc]-*.json')):
    d = json.load(open(f)); g = 'H' if d['scene'] in HSET else 'X'
    for k, B in d['branches'].items():
        if 'null' not in B: continue
        a = B['null']['at_k']
        for lab, v in B.items():
            if lab.startswith('_') or lab == 'null' or not isinstance(v, dict) or 'margin' not in v: continue
            b = v['at_k']
            if b.get('pos_local') == a.get('pos_local') and b.get('size') == a.get('size'): continue
            key = (d['scene'], k, b.get('item_index'), tuple(round(x / 0.02) for x in b['pos_local']) if b.get('pos_local') else None, tuple(b['size']) if b.get('size') else None)
            if key in seen: continue
            seen.add(key)
            c = change(a, b)
            s = st[(g, c)]; s[0] += 1; s[1] += int(v['margin'] >= 0 and B['null']['margin'] < 0); s[2] += v['margin'] - B['null']['margin']
L = ['| group | change at k (floor poses of the same item) | distinct poses (scene, k) | rescued (null missed, branch crosses) | mean margin change vs null |', '|---|---|---:|---:|---:|']
for (g, c), (n, r, dm) in sorted(st.items()):
    L.append(f'| {g} | {c} | {n} | {r} | {dm / n:+.2f} |')
open(f'{HERE}/cf_orient.md', 'w').write('# Counterfactual branches by the kind of change at k (cf_orient.py)\n\n' + '\n'.join(L) + '\n')
print('\n'.join(L))
