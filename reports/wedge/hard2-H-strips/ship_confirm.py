"""ship_confirm.py [scene ...]: every branch that reached the threshold on the
record's arm (cf-<scene>.json) re-run with the shipped form's arm
(arm_ship_c.txt / arm_ship_b.txt from origin/claude/rl-packing-policy-ftogt3
9e4ada85, + deterministic budgets), together with its unchanged baseline
(null) at the same k.  The prefix is the same reference run (record arm); only
the decision at k and the continuation use the shipped arm.
Output: cf-ship-<scene>.json beside the cf files."""
import glob, json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
CF = '/home/user/inv-H-scratch/cf'
only = set(sys.argv[1:])
HSET = {h['scene'] for h in json.load(open(f'{HERE}/hlist.json'))}
for f in sorted(glob.glob(f'{CF}/cf-[bc]-*.json')):
    d = json.load(open(f)); sc = d['scene']
    if (only and sc not in only) or (not only and sc not in HSET):
        continue
    wanted = {}
    for k, B in d['branches'].items():
        labs = [lab for lab, v in B.items() if not lab.startswith('_') and lab != 'null' and isinstance(v, dict) and v.get('margin', -99) >= 0]
        if labs:
            wanted[k] = labs
    if not wanted:
        continue
    arm = f"{HERE}/arm_ship_{'c' if sc[0] == 'c' else 'b'}.txt"
    print(f'[ship] {sc} {wanted}', flush=True)
    subprocess.run([sys.executable, f'{HERE}/cf.py', sc, '--ks', ','.join(sorted(wanted, key=int, reverse=True)), '--veto', '4',
                    '--arm-file', arm, '--from-cf', f, '--labels', json.dumps(wanted)], check=False)
