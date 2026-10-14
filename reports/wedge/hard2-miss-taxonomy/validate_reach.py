"""validate_reach.py: how often the reach/fit checks find no patch for an item the agent did place
(the check's false-negative rate on real placements), on the last 10 placements of some episodes."""
import sys, json, glob, statistics, collections
sys.path.insert(0, '.')
import extract
from extract import *

def run(path, last=10):
    r = json.load(open(path)); sp = r['scene_spec']
    sc = make_scene(sp['seed'], sp['layout'], sp['task']); byidx = {i['index']: i for i in sc.items}
    ok = [s for s in r['steps'] if s.get('event') == 'step' and s.get('is_placed_safe')]
    final = {it['index']: it for it in r['final_items']}
    off = collections.defaultdict(list)
    for s in ok:
        f = final.get(s['item_index'])
        if f is not None: off[s['container_idx']].append(f['pos'][0] - s['pos_local'][0])
    off = {k: statistics.median(v) for k, v in off.items()}
    containers = [dict(c, packed_items=[]) for c in sc.containers]; board = Board(containers)
    res = []
    for n, s in enumerate(ok):
        it = byidx[s['item_index']]
        if n >= len(ok) - last:
            fit = max(item_fits(load_of(board, ci), it) for ci in range(len(containers)))
            rc = sum(reach_fit(load_of(board, ci), board.models[ci], it, soft_support=bool(it['is_soft'])) for ci in range(len(containers)))
            res.append((fit > 0, rc > 0, s['archetype'].split('/')[0], s.get('surface')))
        f = final[s['item_index']]; ci = s['container_idx']
        pos = [f['pos'][0] - off.get(ci, 0.0), f['pos'][1], f['pos'][2]]
        containers[ci]['packed_items'] = containers[ci]['packed_items'] + [{'index': s['item_index'], 'pos': pos, 'dims': s['size'], 'is_soft': it['is_soft'], 'is_prioritized': it['is_prioritized']}]
    return res

allr = []
for d in sys.argv[1:]:
    for f in sorted(glob.glob(d + '/*-hard2-s00[0-4]*.json'))[::3]:
        allr += run(f)
n = len(allr)
print('placements', n, 'fit found', sum(a for a, b, c, d in allr), 'reach found', sum(b for a, b, c, d in allr))
by = collections.defaultdict(lambda: [0, 0, 0])
for a, b, c, d in allr:
    by[c][0] += 1; by[c][1] += a; by[c][2] += b
for k, v in sorted(by.items(), key=lambda kv: -kv[1][0]): print(' ', k, v)
