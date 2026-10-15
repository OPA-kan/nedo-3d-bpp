"""Run arch.py over every H episode, from 3 steps before the floor was gone
(strips data) or 12 steps before the end, whichever is earlier."""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
H = json.load(open(f'{HERE}/hlist.json'))
D = {}
for rec in ('gate0-hard2', 'gate0-hard2-b'):
    for e in json.load(open(f'/home/user/inv-H-scratch/data/strips-{rec}.json')):
        D[e['scene']] = e
order = sorted(H, key=lambda h: (h['mg'] < -3, h['scene']))  # near misses first
only = set(sys.argv[1:])
for h in order:
    if only and h['scene'] not in only:
        continue
    out = f"/home/user/inv-H-scratch/arch/arch-{h['scene']}.json"
    if os.path.exists(out) and not only:
        continue
    st = D[h['scene']]['steps']; n = len(st)
    uf = [s['usable_floor_m2'] for s in st]
    gone = next((i for i in range(n) if all(u < 0.26 for u in uf[i:])), n)
    k0 = max(0, min(gone - 3, n - 12))
    subprocess.run([sys.executable, f'{HERE}/arch.py', h['scene'], '--from', str(k0)], check=False)
