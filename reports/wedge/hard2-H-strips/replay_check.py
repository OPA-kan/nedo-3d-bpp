"""replay_check.py <scene> [<scene> ...]: how faithful is a forced replay?

All recorded actions are forced in the official simulator (the agent is not
asked); the run reports the first step whose forced action fails, and the
largest distance between the replay's settled poses and the record's
final_items (per item, at the end of the replay)."""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H

def check(name, record=None):
    scene, rec, arm = H.load(name, record)
    acts = H.recorded_actions(rec)
    ep = H.PhysicsEpisode(scene, arm)
    first_fail = None
    try:
        for i, a in enumerate(acts):
            info = ep.step(a)
            if not info['ok']:
                first_fail = (i, info['status'])
                break
        final = {f['index']: f['pos'] for f in ep.settled()}
    finally:
        ep.close()
    recf = {f['index']: f['pos'] for f in rec['final_items']}
    d = [float(np.linalg.norm(np.subtract(final[i], recf[i]))) for i in final if i in recf]
    return {'scene': name, 'n': len(acts), 'first_fail': first_fail, 'max_dev': round(max(d), 4) if d else None,
            'n_dev_1cm': sum(1 for x in d if x > 0.01), 'n_dev_1mm': sum(1 for x in d if x > 0.001)}

if __name__ == '__main__':
    rec = None
    names = sys.argv[1:]
    if names and names[0].startswith('--record='):
        rec = names[0].split('=', 1)[1]; names = names[1:]
    out = []
    for n in names:
        r = check(n, rec)
        print(json.dumps(r), flush=True)
        out.append(r)
