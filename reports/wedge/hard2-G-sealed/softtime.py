"""softtime.py -- the oldest deferred soft box on the B G boards: from the step it
entered the pool, at every prefix, how many level spots and how many reachable
(exact sweep) spots it had (sealkit; soft support as the taxonomy allows).
Reports when it first had a reachable level spot and when the last one went."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sealkit as K, branch as B
G_B = ['b-hard2-s0007', 'b-hard2-s0009', 'b-hard2-s0077', 'b-hard2-s0026', 'b-hard2-s0064', 'b-hard2-s0004', 'b-hard2-s0081',
       'b-hard2-s0056', 'b-hard2-s0030', 'b-hard2-s0055', 'b-hard2-s0073', 'b-hard2-s0071', 'b-hard2-s0075', 'b-hard2-s0086']
out = []
for sc in G_B:
    ep = K.Episode(K.load_record('gate0-hard2-b', sc))
    seq = B.pool_sequence(ep)
    T = len(ep.placements)
    soft_end = [i for i in ep.visible if i['is_soft']]
    if not soft_end:
        continue
    it = min(soft_end, key=lambda i: i['index'])
    enter = next(t for t in range(T + 1) if any(p['index'] == it['index'] for p in seq[t][0]))
    traj = []
    for t in range(enter, T + 1):
        cs = ep.containers_at(t)
        lv = rc = 0
        for ci in range(len(cs)):
            spots, _ = K.enumerate_spots(ep, cs, ci, it)
            for sp, (cl, _fb) in zip(spots, K.reach_exact(ep, cs, ci, spots)):
                lv += int(sp['origins'].sum()); rc += int(cl.sum())
        traj.append((t, lv, rc))
    first = next((t for t, l, r in traj if r > 0), None)
    last = max((t for t, l, r in traj if r > 0), default=None)
    soft_share = sum(1 for i in ep.visible if i['is_soft']) / len(ep.visible)
    out.append(dict(scene=sc, item=it['index'], dims=[it['length'], it['width'], it['height']], enter=enter, T=T,
                    first_reach=first, last_reach=last, reach_steps=sum(1 for t, l, r in traj if r > 0),
                    end_soft_share=round(soft_share, 2), traj=traj))
    print(sc, 'item', it['index'], out[-1]['dims'], 'in pool from', enter, 'T', T, '| reachable spot first', first,
          'last', last, 'steps with one', out[-1]['reach_steps'], '| end pool soft', round(soft_share, 2), flush=True)
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'softtime.json'), 'w'))
