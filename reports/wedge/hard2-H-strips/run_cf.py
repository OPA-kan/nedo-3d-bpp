"""Run cf.py over the H episodes (near misses first).  Branch steps from the
reference run: the last 1, 2, 3, 5, 8 placements before the end, the step
that takes the last usable floor ("floor gone") and two before it."""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REF = '/home/user/inv-H-scratch/ref'
H = json.load(open(f'{HERE}/hlist.json'))
only = [a for a in sys.argv[1:] if not a.startswith('--')]
order = sorted(H, key=lambda h: (h['mg'] < -3, h['scene']))
if only:
    order = [h for h in order if h['scene'] in only]
for h in order:
    p = f"{REF}/ref-{h['scene']}.json"
    if not os.path.exists(p):
        continue
    d = json.load(open(p))
    n = len(d['actions'])
    uf = [sum(f['usable'] for f in x['floor_before']) for x in d['dumps']]
    # floor gone: the first step whose placement leaves < 0.26 m^2 usable for good
    gone = next((i for i in range(len(uf) - 1) if all(u < 0.26 for u in uf[i + 1:])), None)
    ks = {n - 1, n - 2, n - 3, n - 5, n - 8}
    if gone is not None:
        ks |= {gone, gone - 2}
    ks = sorted(k for k in ks if 0 <= k < n)[::-1]
    print(f"[run_cf] {h['scene']} n {n} gone {gone} ks {ks}", flush=True)
    subprocess.run([sys.executable, f'{HERE}/cf.py', h['scene'], '--ks', ','.join(map(str, ks))], check=False)
