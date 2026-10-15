"""ship_compare.py: the 21 H scenes in the shipped-form records
(origin/claude/rl-packing-policy-ftogt3: reports/bench/ship-hard2, ship-hard2-b)
against the v50 records and the reference runs."""
import json, os, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
H = json.load(open(f'{HERE}/hlist.json'))
def show(path):
    try:
        return json.loads(subprocess.run(['git', 'show', f'origin/claude/rl-packing-policy-ftogt3:{path}'], capture_output=True, text=True, check=True).stdout)
    except Exception:
        return None
L = ['| scene | thr | v50 record | reference (det) | shipped-form record | shipped end |', '|---|---:|---:|---:|---:|---|']
for h in sorted(H, key=lambda h: h['scene']):
    sc = h['scene']; rec = 'ship-hard2' if sc[0] == 'c' else 'ship-hard2-b'
    d = show(f'reports/bench/{rec}/{sc}.json')
    ref = json.load(open(f'/home/user/inv-H-scratch/ref/ref-{sc}.json'))
    sp = d['metrics']['placed_count'] if d else None
    L.append(f"| {sc} | {h['thr']} | {h['placed']} ({h['mg']:+d}) | {ref['placed']} ({ref['margin']:+d}) | "
             + (f"{sp} ({sp - h['thr']:+d}) | {d['metrics']['end_reason']}" if d else '- | -') + ' |')
open(f'{HERE}/ship_compare.md', 'w').write('# H scenes in the shipped-form records\n\n' + '\n'.join(L) + '\n')
print('\n'.join(L))
