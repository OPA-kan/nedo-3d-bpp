"""extract.py <record_dir> [<record_dir> ...] -> <out_dir>/<record_dir_name>.json

Per hard2 episode (misses in full, crossings with the cheap fields only) the
end state, the course and the scene attributes, read from the bench record and
the scene rebuilt with bench.scenes.make_scene.  Read-only on the repository.

Board reconstruction: the settled poses of final_items (world frame; the
container's x offset is recovered as the median of final.x - pos_local.x over
its steps), dims from the step's oriented size, soft/priority flags from the
scene's items.
"""
import glob, json, os, sys, statistics, collections
import numpy as np

REPO = '/home/user/nedo-3d-bpp'
sys.path.insert(0, REPO)
from bench.scenes import make_scene
from rule_alpha.config import DEFAULT_CONFIG
from rule_alpha.geometry import ContainerModel
from rule_alpha.surface import _Load, _covered
from rule_alpha._reuse import packed_aabbs_local

CELL = 0.02
WIN = ((0.40, 0.55), 0.24)
RESCUE = {'physics-resort', 'count-mode', 'grid-rescue', 'grid-rescue-cover', 'fallback'}
OUT = os.path.dirname(os.path.abspath(__file__)) + '/data'


def vol(i):
    return i['length'] * i['width'] * i['height']


def max_rect(mask):
    """Largest all-True axis-aligned rectangle (cells): (area, nx, ny)."""
    nx, ny = mask.shape
    h = np.zeros(ny, dtype=int)
    best = (0, 0, 0)
    for i in range(nx):
        h = np.where(mask[i], h + 1, 0)
        st = []
        for j in range(ny + 1):
            cur = h[j] if j < ny else 0
            start = j
            while st and st[-1][1] >= cur:
                s, hh = st.pop()
                a = hh * (j - s)
                if a > best[0]:
                    best = (a, hh, j - s)
                start = s
            st.append((start, cur))
    return best


def components(mask, min_cells):
    nx, ny = mask.shape
    seen = np.zeros_like(mask)
    n = 0
    for i in range(nx):
        for j in range(ny):
            if mask[i, j] and not seen[i, j]:
                stack = [(i, j)]; seen[i, j] = True; c = 0
                while stack:
                    a, b = stack.pop(); c += 1
                    for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        x, y = a + da, b + db
                        if 0 <= x < nx and 0 <= y < ny and mask[x, y] and not seen[x, y]:
                            seen[x, y] = True; stack.append((x, y))
                if c >= min_cells:
                    n += 1
    return n


class Board:
    def __init__(self, containers):
        self.containers = containers
        self.models = [ContainerModel(c, DEFAULT_CONFIG) for c in containers]


def load_of(board, ci):
    load = _Load(board.models[ci], CELL)
    for box, soft, _p in packed_aabbs_local(board.containers[ci]):
        load.add(box, soft)
    return load


def usable_area(load, fp, h):
    return float(load.usable(fp, h, None, 1).sum()) * CELL * CELL


def item_fits(load, item):
    """m^2 of level patch (hard support, clearance) that holds the item in some orientation."""
    d = (item['length'], item['width'], item['height'])
    best = 0.0
    for k in range(3):
        h = d[k]; fp = tuple(d[j] for j in range(3) if j != k)
        best = max(best, usable_area(load, fp, h))
    return best


def _prefix(m):
    s = np.zeros((m.shape[0] + 1, m.shape[1] + 1), dtype=np.int32)
    s[1:, 1:] = np.cumsum(np.cumsum(m.astype(np.int32), axis=0), axis=1)
    return s


def _rect_sum(s, i0, i1, j0, j1):
    """sum over rows [i0, i1), cols [j0, j1) (arrays broadcast)."""
    return s[i1, j1] - s[i0, j1] - s[i1, j0] + s[i0, j0]


def reach_fit(load, model, item, soft_support=False):
    """Window origins (count) of a level patch holding the item (as _Load.usable) whose
    transport sweep is clear: the y-leg from the door (y min) to the target at the
    transport height (target bottom + 0.08 off the floor/shelf, + 0.02 on them, capped
    under the ceiling), and the x-leg when the target lies left of the sweep's start
    (the chamfer pocket).  Packed boxes of every kind block; no stability check."""
    from rule_alpha.surface import _close_gaps, TOL, CLEAR
    d = (item['length'], item['width'], item['height'])
    n_ok = 0
    L = model.length; T = model.thickness; cut = model.cut_x
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
                support = load.floor.copy() if on_floor else np.zeros((load.nx, load.ny), dtype=bool)
                on_shelf = False
                for m, top, _b in load.shelves:
                    if abs(top - z) <= TOL:
                        support |= m; on_shelf = True
                for m, _b, top, soft in load.boxes:
                    if abs(top - z) <= TOL and (not soft or (soft_support and z + h <= load.z_floor + 0.7 + 1e-6)):
                        support |= m
                if not on_floor:
                    support = _close_gaps(support, 1)
                free = load.local_ceiling(z) >= z + need - 1e-9
                for m, bottom, top, _soft in load.boxes:
                    if top > z + 1e-3 and bottom < z + need - 1e-3:
                        free &= ~m
                ok = support & free & (load.xx >= load.x_limit(z) + CLEAR / 2.0)
                if ok.sum() < a * b:
                    continue
                s_ok = _prefix(ok)
                I, J = np.meshgrid(np.arange(load.nx - a + 1), np.arange(load.ny - b + 1), indexing='ij')
                origins = _rect_sum(s_ok, I, I + a, J, J + b) == a * b
                if not origins.any():
                    continue
                lift = 0.02 if (on_floor or on_shelf) else 0.08
                lo = min(z + lift, load.z_ceiling - h - 0.01); hi = lo + h
                blocked = np.zeros((load.nx, load.ny), dtype=bool)
                for m, bottom, top, _soft in load.boxes:
                    if top > lo + 0.005 and bottom < hi - 0.005:
                        blocked |= m
                for m, top, bottom in load.shelves:
                    if top > lo + 0.005 and bottom < hi - 0.005:
                        blocked |= m
                s_bl = _prefix(blocked)
                # y-leg: rows of the window, columns from the door (j=0) to the window's far edge
                xs0 = load.xx[:, 0]
                ycl = _rect_sum(s_bl, I, I + a, np.zeros_like(J), J + b) == 0
                # x-leg: the sweep starts at x >= -L/2 + T + cut + fx/2 + 0.01
                x_start_min = -L / 2.0 + T + cut + fx / 2.0 + 0.01
                cx = xs0[I] + (a * CELL) / 2.0 - CELL / 2.0
                left = cx < x_start_min
                i_start = np.clip(np.searchsorted(xs0, x_start_min + fx / 2.0), 0, load.nx)
                xcl = np.where(left, _rect_sum(s_bl, I, np.maximum(i_start, I + a), J, J + b) == 0, True)
                # the y-leg runs at the start x when the target is left of it
                ycl_start = np.where(left, _rect_sum(s_bl, np.clip(i_start - a, 0, None), np.clip(i_start, a, None),
                                                     np.zeros_like(J), J + b) == 0, ycl)
                n_ok += int((origins & ycl_start & xcl).sum())
    return n_ok


def floor_state(board, ci, items_by_idx):
    model = board.models[ci]
    load = load_of(board, ci)
    zf = model.z_floor
    occ = np.zeros((load.nx, load.ny), dtype=bool)
    soft_a = prio_a = hard_a = 0.0
    for (box, soft, prio) in packed_aabbs_local(board.containers[ci]):
        if float(box.minimum[2]) < zf + 0.10:
            m = load.mask(box)
            occ |= m
            a = float(m.sum()) * CELL * CELL
            if soft:
                soft_a += a
            elif prio:
                prio_a += a
            else:
                hard_a += a
    free = ~occ
    floor_area = float(load.floor.sum()) * CELL * CELL
    a, hx, hy = max_rect(free)
    win = int(round(0.30 / CELL))
    roomy = _covered(free, win, win)
    return dict(floor_area=floor_area, free_floor=float(free.sum()) * CELL * CELL,
                ler=(round(hx * CELL, 2), round(hy * CELL, 2)), ler_area=a * CELL * CELL,
                strip_free=float((free & ~roomy).sum()) * CELL * CELL,
                pieces=components(free, int(0.02 / CELL / CELL)),
                soft_floor=soft_a, prio_floor=prio_a, hard_floor=hard_a,
                usable=usable_area(load, *WIN), load=load)


def analyse(path, full):
    r = json.load(open(path)); sp = r['scene_spec']; m = r['metrics']
    sc = make_scene(sp['seed'], sp['layout'], sp['task'])
    items = sc.items; byidx = {i['index']: i for i in items}
    N = m['total_items']; thr = N // 2 + 1; placed = m['placed_count']; mg = placed - thr
    models = [ContainerModel(dict(c, packed_items=[]), DEFAULT_CONFIG) for c in sc.containers]
    cvol = sum(md.usable_volume for md in models)
    steps = [s for s in r['steps'] if s.get('event') == 'step']
    ok = [s for s in steps if s.get('is_placed_safe')]
    placed_idx = {s['item_index'] for s in ok}
    failed = [s for s in steps if not s.get('is_placed_safe')]
    first_vol = sum(vol(i) for i in items[:thr])
    rec = dict(scene=r['scene'], seed=sp['seed'], task=sp['task'], stratum=sp['stratum'], demand=sp['demand'],
               order=sp['order'], mix=sp['mix'], n=sp['containers_n'], shelves=sp['shelves'], pool=sp['pool'],
               soft_share=sp['soft_share'], prio_rate=sp['priority_rate'], base=sp['base_count'],
               total=N, thr=thr, placed=placed, mg=mg, end=m['end_reason'], fill=m['fill_volume'] / 100.0,
               cvol=cvol, placed_vol=m['placed_volume_m3'], first_vol=first_vol,
               ptmax=m['policy_time_max'], ptmean=m['policy_time_mean'], over_budget=m['over_budget_steps'],
               shadow=m.get('shadow', {}), phase=m.get('phase', {}),
               soft_covered=m.get('soft_covered'), prio_covered=m.get('priority_covered'),
               soft_count=m.get('soft_count'), prio_count=m.get('priority_count'),
               per_container=m.get('per_container_count'))
    arch = collections.Counter(str(s.get('archetype')).split('/')[0] for s in ok)
    rec['arch'] = dict(arch)
    rec['rescue_share'] = sum(v for k, v in arch.items() if k in RESCUE) / max(1, len(ok))
    rec['last_arch'] = [str(s.get('archetype')).split('/')[0] for s in ok[-5:]]
    decl = [s for s in r['steps'] if s.get('event') == 'declined']
    rec['last_call_s'] = (decl[-1].get('policy_seconds') if decl and r['steps'][-1].get('event') == 'declined'
                          else (failed[-1].get('policy_seconds') if failed else None))
    # the stream at the end
    unplaced = [i for i in items if i['index'] not in placed_idx]
    if sp['task'] == 'C':
        nxt = [i for i in items if i['index'] >= placed]  # C: prefix placed
        need_items = nxt[:max(0, thr - placed)]
        visible = nxt[:1]
    else:
        visible = unplaced[:sp['pool']]
        k = max(0, thr - placed)
        need_items = sorted(unplaced[:k + sp['pool'] - 1], key=vol)[:k]
    rec['need_vol'] = sum(vol(i) for i in need_items)
    rec['left_vol'] = sum(vol(i) for i in unplaced)
    rec['free_vol'] = cvol - m['placed_volume_m3']
    rec['fill_at_thr'] = (m['placed_volume_m3'] + rec['need_vol']) / cvol
    rec['visible'] = [dict(idx=i['index'], dims=[i['length'], i['width'], i['height']], soft=i['is_soft'],
                           prio=i['is_prioritized'], vol=round(vol(i), 4)) for i in visible]
    if failed:
        fi = byidx[failed[-1]['item_index']]
        rec['failed_item'] = dict(idx=fi['index'], dims=[fi['length'], fi['width'], fi['height']], soft=fi['is_soft'],
                                  prio=fi['is_prioritized'], arch=str(failed[-1].get('archetype')),
                                  outcome=(failed[-1].get('shadow') or {}).get('outcome'))
    if not full:
        return rec
    # rebuild the board
    final = {it['index']: it for it in r['final_items']}
    off = collections.defaultdict(list)
    for s in ok:
        f = final.get(s['item_index'])
        if f is not None and 'pos_local' in s:
            off[s['container_idx']].append(f['pos'][0] - s['pos_local'][0])
    off = {k: statistics.median(v) for k, v in off.items()}
    containers = [dict(c, packed_items=[]) for c in sc.containers]
    board = Board(containers)
    floor_tot = sum(float(_Load(md, CELL).floor.sum()) * CELL * CELL for md in board.models)
    per_ci_usable = [usable_area(load_of(board, ci), *WIN) for ci in range(len(containers))]
    traj = [sum(per_ci_usable) / floor_tot]
    zf = [md.z_floor for md in board.models]
    floor_steps = []
    for s in ok:
        f = final.get(s['item_index'])
        if f is None or 'size' not in s:
            continue
        ci = s['container_idx']; it = byidx[s['item_index']]
        pos = [f['pos'][0] - off.get(ci, 0.0), f['pos'][1], f['pos'][2]]
        containers[ci]['packed_items'] = containers[ci]['packed_items'] + [
            {'index': s['item_index'], 'pos': pos, 'dims': s['size'], 'is_soft': it['is_soft'],
             'is_prioritized': it['is_prioritized']}]
        per_ci_usable[ci] = usable_area(load_of(board, ci), *WIN)
        traj.append(sum(per_ci_usable) / floor_tot)
        floor_steps.append(pos[2] - s['size'][2] / 2.0 < zf[ci] + 0.10)
    n = len(traj) - 1
    d1 = [traj[i - 1] - traj[i] for i in range(1, len(traj))]
    if d1:
        k = max(range(len(d1)), key=lambda i: d1[i])
        rec['drop'] = round(d1[k], 3); rec['drop_lead'] = n - (k + 1)
        rec['drop_arch'] = str(ok[k].get('archetype')).split('/')[0]; rec['drop_floor'] = floor_steps[k]
        rec['drop_door'] = ok[k]['pos_local'][1] < -0.2
        rec['drop_standing'] = ok[k]['size'][2] > max(ok[k]['size'][:2])
    low = next((i for i, v in enumerate(traj) if v < 0.2), None)
    rec['low_lead'] = (n - low) if low is not None else None
    rec['traj'] = [round(v, 3) for v in traj]
    # the end state
    fs = [floor_state(board, ci, byidx) for ci in range(len(containers))]
    rec['floor_area'] = sum(x['floor_area'] for x in fs)
    rec['free_floor'] = sum(x['free_floor'] for x in fs)
    rec['free_floor_share'] = rec['free_floor'] / rec['floor_area']
    rec['ler'] = max((x['ler'] for x in fs), key=lambda t: t[0] * t[1])
    rec['ler_area'] = max(x['ler_area'] for x in fs)
    rec['strip_free'] = sum(x['strip_free'] for x in fs)
    rec['pieces'] = sum(x['pieces'] for x in fs)
    rec['soft_floor_share'] = sum(x['soft_floor'] for x in fs) / rec['floor_area']
    rec['prio_floor_share'] = sum(x['prio_floor'] for x in fs) / rec['floor_area']
    rec['hard_floor_share'] = sum(x['hard_floor'] for x in fs) / rec['floor_area']
    rec['soft_floor_max_ci'] = max(x['soft_floor'] / x['floor_area'] for x in fs)
    rec['usable_end'] = sum(x['usable'] for x in fs) / rec['floor_area']
    rec['per_ci'] = [dict(free_floor=round(x['free_floor'] / x['floor_area'], 3), usable=round(x['usable'] / x['floor_area'], 3),
                          soft_floor=round(x['soft_floor'] / x['floor_area'], 3), n=len(containers[ci]['packed_items']),
                          fill=round(sum(p['dims'][0] * p['dims'][1] * p['dims'][2] for p in containers[ci]['packed_items']) / board.models[ci].usable_volume, 3))
                     for ci, x in enumerate(fs)]
    # does a visible item find a level patch anywhere (geometric, no sweep)?
    fit = []
    for v in visible:
        it = v
        fit.append(max(item_fits(x['load'], it) for x in fs))
    rec['visible_fit_m2'] = [round(a, 3) for a in fit]
    rec['next_fit'] = fit[0] if fit else None
    rec['any_fit'] = max(fit) if fit else 0.0
    # the same with soft tops counted as support (the gate's soft-as-structure, for a soft item)
    loads_s = []
    for ci in range(len(containers)):
        ls = _Load(board.models[ci], CELL)
        for box, soft, _p in packed_aabbs_local(board.containers[ci]):
            ls.add(box, soft and float(box.maximum[2]) > 0.7 + board.models[ci].z_floor)
        loads_s.append(ls)
    fit_s = [max(item_fits(ls, v) for ls in loads_s) if v['is_soft'] else f for v, f in zip(visible, fit)]
    rec['visible_fit_soft_m2'] = [round(a, 3) for a in fit_s]
    rec['any_fit_soft'] = max(fit_s) if fit_s else 0.0
    # the same patches with the transport sweep from the door clear (window origins)
    reach = [sum(reach_fit(load_of(board, ci), board.models[ci], v, soft_support=bool(v['is_soft'])) for ci in range(len(containers)))
             for v in visible]
    rec['visible_reach'] = reach
    rec['any_reach'] = max(reach) if reach else 0
    # thickness of the free volume: free volume above the tops (headroom columns) is not computed; free share
    rec['free_vol_share'] = rec['free_vol'] / cvol
    return rec


def main():
    dirs = sys.argv[1:]
    os.makedirs(OUT, exist_ok=True)
    for d in dirs:
        name = os.path.basename(d.rstrip('/'))
        out = []
        for f in sorted(glob.glob(d + '/[bc]-hard2-s*.json')):
            r = json.load(open(f)); m = r['metrics']
            miss = m['placed_count'] < m['total_items'] // 2 + 1
            out.append(analyse(f, full=True))
        json.dump(out, open(f'{OUT}/{name}.json', 'w'), default=float)
        print(name, len(out), 'misses', sum(1 for x in out if x['mg'] < 0), flush=True)


if __name__ == '__main__':
    main()
