"""cf_flip.py: how often one changed placement flips the outcome, on the H
scenes (miss -> cross) and on the crossings branched as a control
(cross -> miss), by the lead of the branch step and by the kind of
alternative.  Distinct poses per (scene, k); the null of each k is the
baseline."""
import json, glob, os, collections
HERE = os.path.dirname(os.path.abspath(__file__))
HSET = {h['scene'] for h in json.load(open(f'{HERE}/hlist.json'))}
from cf_stats import kind
rows = collections.defaultdict(lambda: [0, 0, 0.0])
seen = set()
for f in sorted(glob.glob('/home/user/inv-H-scratch/cf/cf-[bc]-*.json')):
    d = json.load(open(f)); g = 'H' if d['scene'] in HSET else 'X'; n = d['n_steps']
    for k, B in d['branches'].items():
        if 'null' not in B: continue
        nm = B['null']['margin']
        if (g == 'H') != (nm < 0):
            continue  # baselines on the other side of the threshold (clock noise) are left out
        lead = n - int(k)
        lb = 'lead 1-3' if lead <= 3 else ('lead 4-9' if lead <= 9 else 'lead >= 10')
        for lab, v in B.items():
            if lab.startswith('_') or lab == 'null' or not isinstance(v, dict) or 'margin' not in v: continue
            a = v['at_k']
            key = (d['scene'], k, a.get('item_index'), tuple(round(x / 0.02) for x in a['pos_local']) if a.get('pos_local') else lab, tuple(a['size']) if a.get('size') else None)
            if key in seen: continue
            seen.add(key)
            flip = (v['margin'] >= 0) if g == 'H' else (v['margin'] < 0)
            for r in ((g, 'all', ''), (g, 'by lead', lb), (g, 'by kind', kind(lab))):
                s = rows[r]; s[0] += 1; s[1] += int(flip); s[2] += v['margin'] - nm
L = ['# One changed placement: flips, H against crossings (cf_flip.py)', '',
     'H: share of distinct alternatives that turn a miss into a crossing; X (crossings branched the same way): share that turn a crossing into a miss.', '',
     '| group | split | | distinct branches | flips | flip share | mean margin change |', '|---|---|---|---:|---:|---:|---:|']
for (g, sp, val), (nn, fl, dm) in sorted(rows.items()):
    L.append(f'| {g} | {sp} | {val} | {nn} | {fl} | {fl / nn:.2f} | {dm / nn:+.2f} |')
open(f'{HERE}/cf_flip.md', 'w').write('\n'.join(L) + '\n')
print('\n'.join(L))
