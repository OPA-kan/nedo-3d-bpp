"""bridge_scan.py <record_dir>... : on the boards that end on a decline, does a
visible item have a reachable spot that rests on two (or more) tops at one
level with a dip between them -- a bridge -- where no fully supported level
patch exists?

Criteria for a window (footprint a x b cells at level z, item height h):
  free   every cell's local ceiling >= z + h + CLEAR and no packed box intrudes
         into [z, z + h + CLEAR); x >= the chamfer limit.
  full   every cell is a support cell at level z (the taxonomy's level patch;
         gaps of one cell closed off the floor).
  bridge not full, and the support cells at level z straddle the window's
         centre by >= COM_CELLS cells on both sides along x and along y (a
         proxy for the centre of mass sitting >= com_margin inside the convex
         hull of the contacts, which is the agent's own stability criterion).
  reach  the sweep from the door is clear (the taxonomy's travel path).
Reported per episode: reachable full windows, reachable bridge-only windows,
those of the bridge windows that pass over <= 0.06 m^2 of bare floor (the
production bridge veto), and one example dip depth.
"""
import collections
import glob
import json
import os
import statistics
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from extract import (CELL, Board, _Load, _prefix, _rect_sum, load_of, make_scene,  # noqa: E402
                     packed_aabbs_local, vol)
from rule_alpha.surface import _close_gaps, TOL, CLEAR  # noqa: E402

COM_CELLS = 2  # 0.04 m >= com_margin 0.03
BRIDGE_TOL = 0.01  # a rigid box touches only the higher of two tops: same level means within 1 cm (contact_tolerance 6 mm plus drift)
FLOOR_VETO = 0.06  # m^2 of bare floor a bridge may pass over


def rebuild(path):
    r = json.load(open(path)); sp = r['scene_spec']; m = r['metrics']
    sc = make_scene(sp['seed'], sp['layout'], sp['task'])
    items = sc.items; byidx = {i['index']: i for i in items}
    N = m['total_items']; thr = N // 2 + 1; placed = m['placed_count']
    steps = [s for s in r['steps'] if s.get('event') == 'step']
    ok = [s for s in steps if s.get('is_placed_safe')]
    placed_idx = {s['item_index'] for s in ok}
    final = {it['index']: it for it in r['final_items']}
    off = collections.defaultdict(list)
    for s in ok:
        f = final.get(s['item_index'])
        if f is not None and 'pos_local' in s:
            off[s['container_idx']].append(f['pos'][0] - s['pos_local'][0])
    off = {k: statistics.median(v) for k, v in off.items()}
    containers = [dict(c, packed_items=[]) for c in sc.containers]
    for s in ok:
        f = final.get(s['item_index'])
        if f is None or 'size' not in s:
            continue
        ci = s['container_idx']; it = byidx[s['item_index']]
        pos = [f['pos'][0] - off.get(ci, 0.0), f['pos'][1], f['pos'][2]]
        containers[ci]['packed_items'].append(
            {'index': s['item_index'], 'pos': pos, 'dims': s['size'], 'is_soft': it['is_soft'],
             'is_prioritized': it['is_prioritized']})
    board = Board(containers)
    unplaced = [i for i in items if i['index'] not in placed_idx]
    if sp['task'] == 'C':
        visible = [i for i in items if i['index'] >= placed][:1]
    else:
        visible = unplaced[:int(sp.get('pool') or getattr(sc, 'look_ahead', 1) or 1)]
    return dict(scene=r['scene'], task=sp['task'], stratum=sp.get('stratum'), total=N, thr=thr,
                placed=placed, mg=placed - thr, end=m['end_reason'], board=board, visible=visible,
                last_call=(r['steps'][-1].get('policy_seconds') if r['steps'] else None))


def scan(load, model, item, soft_support):
    d = (item['length'], item['width'], item['height'])
    out = dict(full=0, bridge=0, bridge_ok=0, bridge_shallow=0, dips=[], levels=set())
    L = model.length; T = model.thickness; cut = model.cut_x
    g = COM_CELLS
    # the highest surface under each cell, per level: built lazily
    for k in range(3):
        h = d[k]; fp = [d[j] for j in range(3) if j != k]
        need = h + CLEAR
        for (fx, fy) in ((fp[0], fp[1]), (fp[1], fp[0])):
            a = int(round((fx + CLEAR) / CELL)); b = int(round((fy + CLEAR) / CELL))
            if a > load.nx or b > load.ny:
                continue
            for z in load.levels():
                if z + need > load.z_ceiling + 1e-9:
                    continue
                on_floor = abs(z - load.z_floor) <= TOL
                if on_floor:
                    continue  # a bridge needs a dip under it; floor patches are the taxonomy's
                support = np.zeros((load.nx, load.ny), dtype=bool)
                on_shelf = False
                for m, top, _b in load.shelves:
                    if abs(top - z) <= TOL:
                        support |= m; on_shelf = True
                tight = np.zeros((load.nx, load.ny), dtype=bool)
                for m, _b, top, soft in load.boxes:
                    if abs(top - z) <= TOL and (not soft or (soft_support and z + h <= load.z_floor + 0.7 + 1e-6)):
                        support |= m
                        if abs(top - z) <= BRIDGE_TOL:
                            tight |= m
                for m, top, _b in load.shelves:
                    if abs(top - z) <= BRIDGE_TOL:
                        tight |= m
                if not support.any():
                    continue
                free = load.local_ceiling(z) >= z + need - 1e-9
                for m, bottom, top, _soft in load.boxes:
                    if top > z + 1e-3 and bottom < z + need - 1e-3:
                        free &= ~m
                free &= (load.xx >= load.x_limit(z) + CLEAR / 2.0)
                # the highest surface below z under each cell (floor baseline)
                below = np.full((load.nx, load.ny), load.z_floor)
                for m, top, _b in load.shelves:
                    if top <= z + TOL:
                        below = np.where(m, np.maximum(below, top), below)
                for m, _b, top, _s in load.boxes:
                    if top <= z + TOL:
                        below = np.where(m, np.maximum(below, top), below)
                bare = free & (below <= load.z_floor + 1e-6)  # bare floor under the window
                s_free = _prefix(free)
                I, J = np.meshgrid(np.arange(load.nx - a + 1), np.arange(load.ny - b + 1), indexing='ij')
                all_free = _rect_sum(s_free, I, I + a, J, J + b) == a * b
                if not all_free.any():
                    continue
                sup_full = _close_gaps(support, 1) & free
                s_full = _prefix(sup_full)
                full = all_free & (_rect_sum(s_full, I, I + a, J, J + b) == a * b)
                s_sup = _prefix(tight & free)
                ci = I + a // 2; cj = J + b // 2
                left = _rect_sum(s_sup, I, np.maximum(ci - g + 1, I), J, J + b) > 0
                right = _rect_sum(s_sup, np.minimum(ci + g, I + a), I + a, J, J + b) > 0
                front = _rect_sum(s_sup, I, I + a, J, np.maximum(cj - g + 1, J)) > 0
                back = _rect_sum(s_sup, I, I + a, np.minimum(cj + g, J + b), J + b) > 0
                bridge = all_free & ~full & left & right & front & back
                if not (full.any() or bridge.any()):
                    continue
                # reach: the sweep from the door
                lift = 0.02 if on_shelf else 0.08
                lo = min(z + lift, load.z_ceiling - h - 0.01); hi = lo + h
                blocked = np.zeros((load.nx, load.ny), dtype=bool)
                for m, bottom, top, _soft in load.boxes:
                    if top > lo + 0.005 and bottom < hi - 0.005:
                        blocked |= m
                for m, top, bottom in load.shelves:
                    if top > lo + 0.005 and bottom < hi - 0.005:
                        blocked |= m
                s_bl = _prefix(blocked)
                xs0 = load.xx[:, 0]
                ycl = _rect_sum(s_bl, I, I + a, np.zeros_like(J), J + b) == 0
                x_start_min = -L / 2.0 + T + cut + fx / 2.0 + 0.01
                cx = xs0[I] + (a * CELL) / 2.0 - CELL / 2.0
                lft = cx < x_start_min
                i_start = np.clip(np.searchsorted(xs0, x_start_min + fx / 2.0), 0, load.nx)
                xcl = np.where(lft, _rect_sum(s_bl, I, np.maximum(i_start, I + a), J, J + b) == 0, True)
                ycl_start = np.where(lft, _rect_sum(s_bl, np.clip(i_start - a, 0, None), np.clip(i_start, a, None),
                                                    np.zeros_like(J), J + b) == 0, ycl)
                reach = ycl_start & xcl
                out['full'] += int((full & reach).sum())
                br = bridge & reach
                nbr = int(br.sum())
                if nbr:
                    out['bridge'] += nbr
                    s_bare = _prefix(bare)
                    bare_cells = _rect_sum(s_bare, I, I + a, J, J + b)
                    ok = br & (bare_cells * CELL * CELL <= FLOOR_VETO)
                    out['bridge_ok'] += int(ok.sum())
                    s_sh = _prefix(below >= z - 0.20 - 1e-6)
                    out['bridge_shallow'] += int((br & (_rect_sum(s_sh, I, I + a, J, J + b) == a * b)).sum())
                    out['levels'].add(round(float(z), 2))
                    # an example dip: the deepest gap under one bridge window
                    ii, jj = np.argwhere(br)[0]
                    win = below[ii:ii + a, jj:jj + b]
                    out['dips'].append(round(float(z - win.min()), 3))
                    wins = np.argwhere(br)
                    for ii2, jj2 in wins[:: max(1, len(wins) // 6)][:6]:
                        out.setdefault('poses', []).append(dict(
                            z=round(float(z), 4), x=round(float(load.xx[ii2, 0] + (a * CELL) / 2.0 - CELL / 2.0), 4),
                            y=round(float(load.yy[0, jj2] + (b * CELL) / 2.0 - CELL / 2.0), 4), fx=fx, fy=fy, h=h,
                            bare_m2=round(float(bare_cells[ii2, jj2]) * CELL * CELL, 3),
                            support_share=round(float((tight & free)[ii2:ii2 + a, jj2:jj2 + b].sum()) / (a * b), 2)))
                    out.setdefault('examples', []).append(dict(
                        z=round(float(z), 3), x=round(float(load.xx[ii, 0] + (a * CELL) / 2.0 - CELL / 2.0), 3),
                        y=round(float(load.yy[0, jj] + (b * CELL) / 2.0 - CELL / 2.0), 3), fx=fx, fy=fy, h=h,
                        dip=round(float(z - win.min()), 3), bare_m2=round(float(bare_cells[ii, jj]) * CELL * CELL, 3),
                        support_share=round(float((tight & free)[ii:ii + a, jj:jj + b].sum()) / (a * b), 2),
                        n_windows=nbr))
    out['levels'] = sorted(out['levels'])
    return out


def main():
    rows = []
    for d in sys.argv[1:]:
        name = os.path.basename(d.rstrip('/'))
        for f in sorted(glob.glob(d + '/[abc]-*-s*.json')):
            r = json.load(open(f)); m = r['metrics']
            if m['end_reason'] != 'declined':
                continue
            ep = rebuild(f)
            board = ep['board']
            res = []
            for v in ep['visible']:
                tot = dict(full=0, bridge=0, bridge_ok=0, bridge_shallow=0, dips=[], levels=[], examples=[], poses=[])
                for ci in range(len(board.containers)):
                    s = scan(load_of(board, ci), board.models[ci], v, soft_support=bool(v['is_soft']))
                    for k in ('full', 'bridge', 'bridge_ok', 'bridge_shallow'):
                        tot[k] += s[k]
                    tot['dips'] += s['dips']; tot['levels'] += s['levels']; tot['examples'] += [dict(e, ci=ci) for e in s.get('examples', [])]; tot['poses'] += [dict(e, ci=ci) for e in s.get('poses', [])]
                tot['item'] = [v['length'], v['width'], v['height']]; tot['soft'] = v['is_soft']
                res.append(tot)
            row = dict(record=name, scene=ep['scene'], task=ep['task'], stratum=ep['stratum'], mg=ep['mg'],
                       placed=ep['placed'], thr=ep['thr'], last_call=ep['last_call'],
                       any_full=max((x['full'] for x in res), default=0),
                       any_bridge=max((x['bridge'] for x in res), default=0),
                       any_bridge_ok=max((x['bridge_ok'] for x in res), default=0),
                       any_bridge_shallow=max((x['bridge_shallow'] for x in res), default=0),
                       dips=sorted({dd for x in res for dd in x['dips']}), items=res)
            rows.append(row)
            print(f"{name} {ep['scene']} mg {ep['mg']:+d} full {row['any_full']} bridge {row['any_bridge']} "
                  f"bridge_ok {row['any_bridge_ok']} shallow {row['any_bridge_shallow']} dips {row['dips'][:6]}", flush=True)
    json.dump(rows, open(HERE + '/bridge_scan.json', 'w'), default=float)
    # summary
    print()
    print('| record | declines | full spot | bridge-only spot | bridge-only, floor veto passed | misses: full / bridge-only / veto-passed | near misses (-1..-3): full / bridge-only |')
    print('|---|---:|---:|---:|---:|---|---|')
    for name in sorted({r['record'] for r in rows}):
        rs = [r for r in rows if r['record'] == name]
        nf = sum(1 for r in rs if r['any_full'] > 0)
        nb = sum(1 for r in rs if r['any_full'] == 0 and r['any_bridge'] > 0)
        nbo = sum(1 for r in rs if r['any_full'] == 0 and r['any_bridge_ok'] > 0)
        ms = [r for r in rs if r['mg'] < 0]
        nm = [r for r in ms if -3 <= r['mg'] <= -1]
        print(f"| {name} | {len(rs)} | {nf} | {nb} | {nbo} | "
              f"{sum(1 for r in ms if r['any_full'] > 0)} / {sum(1 for r in ms if r['any_full'] == 0 and r['any_bridge'] > 0)} / "
              f"{sum(1 for r in ms if r['any_full'] == 0 and r['any_bridge_ok'] > 0)} (of {len(ms)}) | "
              f"{sum(1 for r in nm if r['any_full'] > 0)} / {sum(1 for r in nm if r['any_full'] == 0 and r['any_bridge'] > 0)} (of {len(nm)}) |")


if __name__ == '__main__':
    main()
