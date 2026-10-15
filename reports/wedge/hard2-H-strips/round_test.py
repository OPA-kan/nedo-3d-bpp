import sys, json, numpy as np
sys.path.insert(0, '/home/user/inv-H/reports/wedge/hard2-H-strips')
import harness as H
name = sys.argv[1]
scene, rec, arm = H.load(name, 'gate0det-hard2')
ep = H.PhysicsEpisode(scene, arm)
acts, poses = [], []
for i in range(200):
    obs = ep.observation()
    a = ep.agent.policy(obs)
    if a is None: break
    acts.append({k: (np.asarray(v).copy() if k == 'place_pos' else v) for k, v in a.items()})
    info = ep.step(a)
    poses.append({f['index']: f['pos'] for f in ep.settled()})
    if ep.done: break
ep.close()
print('free run', len(acts), 'placed', flush=True)
for dec in (None, 4):
    ep = H.PhysicsEpisode(scene, arm)
    worst = []
    for i, a in enumerate(acts):
        b = dict(a)
        if dec is not None:
            b['place_pos'] = [round(float(v), dec) for v in a['place_pos']]
        info = ep.step(b)
        p = {f['index']: f['pos'] for f in ep.settled()}
        d = max((np.linalg.norm(np.subtract(p[k], poses[i][k])) for k in p if k in poses[i]), default=0)
        worst.append(round(float(d), 5))
        if not info['ok']:
            print('fail at', i); break
    ep.close()
    print('decimals', dec, 'max dev per step', worst, flush=True)
