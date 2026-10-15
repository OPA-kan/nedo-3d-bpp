"""shadepath.py -- how often a C G sealing placement came through "the ladder's
pose shade-vetoed, then a rescue stage placed" (why.py logs; shade recomputed with
wedge_rl.stack.shade_area on the recorded board for every pose the shadow refused)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sealkit as K, branch as B
from rule_alpha import layer1
from rule_alpha.config import DEFAULT_CONFIG
from rule_alpha._reuse import AABB
from wedge_rl.stack import shade_area, skyline
S = '/home/user/inv-G-scratch/why/gate0-hard2'
RESCUE = ('physics-resort', 'grid-rescue', 'grid-rescue-cover', 'count-mode', 'fallback', 'last-resort')
rows = []
for f in sorted(os.listdir(S)):
    sc = f[:-5]
    ep = K.Episode(K.load_record('gate0-hard2', sc))
    for w in json.load(open(os.path.join(S, f))):
        if not w['patches_sealed_here']:
            continue
        cs = B.containers_for(ep, w['t'])
        board = layer1.Board(cs, DEFAULT_CONFIG)
        refused = []
        for e in w['emits']:
            if e['accepted']:
                continue
            m = board.model(e['ci'])
            sh = shade_area(AABB(tuple(e['centre']), tuple(e['size']), 'x'), skyline(board.container(e['ci']), m), float(m.z_ceiling))
            refused.append((e['arch'], round(sh, 3)))
        rec_arch = w['record']['arch'].split('/')[0]
        agent_arch = (w.get('action') or {}).get('arch')
        vetoed = [r for r in refused if r[1] > 0.15]
        path = bool(vetoed) and (agent_arch in RESCUE)
        rows.append(dict(scene=sc, t=w['t'], record=rec_arch, agent=agent_arch, same=w.get('same'), refused=refused, path=path,
                         ladder_first=(w['ladders'][0]['archetype'] if w['ladders'] else None)))
        print(sc, w['t'], 'record', rec_arch, 'agent', agent_arch, 'same', w.get('same'), 'refused(shade)', refused, 'PATH' if path else '')
n = len(rows); p = sum(r['path'] for r in rows)
rr = sum(1 for r in rows if r['record'] in RESCUE)
print(f'{p} of {n} C sealing placements came through shade veto -> rescue stage (re-run); record placed by a rescue stage: {rr}')
json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'shadepath.json'), 'w'), indent=0)
