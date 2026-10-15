"""Run cf.py over the H episodes (near misses first).  Branch steps from the
reference run: the last 1, 2, 3, 5, 8 placements before the end, the step
that takes the last usable floor ("floor gone") and two before it."""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REF = '/home/user/inv-H-scratch/ref'
H = json.load(open(f'{HERE}/hlist.json'))
only = [a for a in sys.argv[1:] if not a.startswith('--')]
def ref_margin(h):
    p = f"{REF}/ref-{h['scene']}.json"
    if not os.path.exists(p):
        return -999
    d = json.load(open(p))
    return d['margin'] if d['end'] == 'declined' else d['margin'] - 100


order = sorted(H, key=lambda h: (-ref_margin(h), h['scene']))  # the reference's near misses first
if only:
    # explicit scenes (H or not: the crossings are branched the same way as a control)
    order = [{'scene': sc} for sc in only]
for h in order:
    p = f"{REF}/ref-{h['scene']}.json"
    if not os.path.exists(p):
        continue
    d = json.load(open(p))
    n = len(d['actions'])
    uf = [sum(f['usable'] for f in x['floor_before']) for x in d['dumps']]
    # floor gone: the first step whose placement leaves < 0.26 m^2 usable for good
    gone = next((i for i in range(len(uf) - 1) if all(u < 0.26 for u in uf[i + 1:])), None)
    # the pilot (c-hard2-s0007) found the decisive step one before "floor
    # gone"; the steps around it and the last placements
    ks = {n - 1, n - 3}
    if gone is not None:
        ks |= {gone, gone - 1, gone - 2, gone - 4}
    else:
        ks |= {n - 5, n - 8}
    ks = sorted(k for k in ks if 0 <= k < n)[::-1]
    extra = ["--veto", "2", "--vetoed", "2", "--other", "1"] if n > 40 else []
    print(f"[run_cf] {h['scene']} n {n} gone {gone} ks {ks}", flush=True)
    subprocess.run([sys.executable, f'{HERE}/cf.py', h['scene'], '--ks', ','.join(map(str, ks))] + extra, check=False)
