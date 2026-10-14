"""nextfit.py <record_dir>: for the C misses that end on a decline, the final board rebuilt and the
reachable-patch check run for the declined item and the 9 items after it in the stream (what a pool of
ten would have offered on the same board), plus the declined item's class."""
import sys, json, glob, statistics, collections
sys.path.insert(0, '.')
from extract import *

def board_of(r, sc):
    byidx = {i['index']: i for i in sc.items}
    ok = [s for s in r['steps'] if s.get('event') == 'step' and s.get('is_placed_safe')]
    final = {it['index']: it for it in r['final_items']}
    off = collections.defaultdict(list)
    for s in ok:
        f = final.get(s['item_index'])
        if f is not None: off[s['container_idx']].append(f['pos'][0] - s['pos_local'][0])
    off = {k: statistics.median(v) for k, v in off.items()}
    containers = [dict(c, packed_items=[]) for c in sc.containers]; board = Board(containers)
    for s in ok:
        f = final.get(s['item_index'])
        if f is None: continue
        it = byidx[s['item_index']]; ci = s['container_idx']
        containers[ci]['packed_items'].append({'index': s['item_index'], 'pos': [f['pos'][0] - off.get(ci, 0.0), f['pos'][1], f['pos'][2]],
                                               'dims': s['size'], 'is_soft': it['is_soft'], 'is_prioritized': it['is_prioritized']})
    return board

out = []
cls = collections.Counter()
for f in sorted(glob.glob(sys.argv[1] + '/c-hard2-s*.json')):
    r = json.load(open(f)); m = r['metrics']; thr = m['total_items'] // 2 + 1
    if m['placed_count'] >= thr or m['end_reason'] != 'declined': continue
    sp = r['scene_spec']; sc = make_scene(sp['seed'], 'hard2', 'C')
    board = board_of(r, sc)
    nxt = sc.items[m['placed_count']: m['placed_count'] + 10]
    reach = [sum(reach_fit(load_of(board, ci), board.models[ci], it, soft_support=bool(it['is_soft'])) for ci in range(len(board.containers))) > 0 for it in nxt]
    d = nxt[0]; key = ('soft ' if d['is_soft'] else '') + ('prio ' if d['is_prioritized'] else '') + f"{d['length']:g}x{d['width']:g}x{d['height']:g}"
    cls[key] += 1
    first_ok = next((k for k, v in enumerate(reach) if v), None)
    out.append((r['scene'], m['placed_count'] - thr, key, ''.join('1' if v else '.' for v in reach), first_ok))
for row in out: print(row)
print('declined class:', cls.most_common())
print('misses with a reachable patch for one of the next 10 items:', sum(1 for o in out if o[4] is not None), 'of', len(out),
      '; for the declined item itself:', sum(1 for o in out if o[4] == 0))
