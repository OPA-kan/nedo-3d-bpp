"""strips.py <record> [<record> ...]: floor-strip formation, step by step.

For every episode of a bench record the floor is rebuilt after every placed
step from the agent's commanded boxes (``pos_local`` and ``size`` of the
step, local frame; settle drift ignored, which is small on the floor), and
the free floor is split into

* usable floor: free cells covered by some free window of the smallest hard
  footprint (0.55 x 0.40 m, either way round) plus 3 cm (the surface
  model's clearance), i.e. where at least a class-A box could still go down;
* dead floor ("strips"): free cells no such window covers.

Per step it records the floor area newly occupied, the usable floor newly
killed without being occupied (the strip a placement creates), the usable
top surface (the taxonomy's 0.40 x 0.55 x 0.24 window over every level), and
the step's rung, item class, pose, shadow outcome.  At the end it describes
each dead component: its bounding box, narrow side, direction, and the walls
it touches.

Output: data/strips-<record>.json (compact, one entry per episode).
"""

from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "../../.."))
sys.path.insert(0, REPO)
from bench.scenes import make_scene  # noqa: E402
from rule_alpha.config import DEFAULT_CONFIG  # noqa: E402
from rule_alpha.geometry import AABB, ContainerModel  # noqa: E402
from rule_alpha.surface import _Load, _covered  # noqa: E402

CELL = 0.02
CLEAR = 0.03
A_FP = (0.55, 0.40)
WIN = ((0.40, 0.55), 0.24)
FLOOR_BAND = 0.10
OUTD = '/home/user/inv-H-scratch/data'


def cls_of(item):
    dims = tuple(sorted((item["length"], item["width"], item["height"]), reverse=True))
    tag = {
        (0.55, 0.4, 0.24): "A",
        (0.65, 0.45, 0.25): "B",
        (0.75, 0.56, 0.27): "C",
        (0.5, 0.4, 0.4): "D",
        (0.45, 0.3, 0.2): "E",
        (0.65, 0.35, 0.23): "F",
        (0.6, 0.3, 0.25): "G",
    }.get(tuple(round(d, 2) for d in dims), "?")
    if item["is_soft"] and item["is_prioritized"]:
        return "softprio-" + tag
    if item["is_soft"]:
        return "soft-" + tag
    if item["is_prioritized"]:
        return "prio-" + tag
    return "hard-" + tag


def window_cover(free, fp):
    a = int(round((fp[0] + CLEAR) / CELL))
    b = int(round((fp[1] + CLEAR) / CELL))
    return _covered(free, a, b) | _covered(free, b, a)


def max_rect(mask):
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
                if hh * (j - s) > best[0]:
                    best = (hh * (j - s), hh, j - s)
                start = s
            st.append((start, cur))
    return best


def components(mask):
    nx, ny = mask.shape
    lab = np.zeros(mask.shape, dtype=int)
    n = 0
    for i in range(nx):
        for j in range(ny):
            if mask[i, j] and not lab[i, j]:
                n += 1
                st = [(i, j)]
                lab[i, j] = n
                while st:
                    a, b = st.pop()
                    for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        x, y = a + da, b + db
                        if 0 <= x < nx and 0 <= y < ny and mask[x, y] and not lab[x, y]:
                            lab[x, y] = n
                            st.append((x, y))
    return lab, n


class CState:
    """One container's packed boxes (local frame) and the derived floor."""

    def __init__(self, model):
        self.model = model
        self.boxes = []  # (AABB, soft)

    def load(self):
        L = _Load(self.model, CELL)
        for b, soft in self.boxes:
            L.add(b, soft)
        return L

    def floor(self):
        L = self.load()
        occ = np.zeros((L.nx, L.ny), dtype=bool)
        zf = self.model.z_floor
        for b, _s in self.boxes:
            if float(b.minimum[2]) < zf + FLOOR_BAND:
                occ |= L.mask(b)
        free = L.floor & ~occ
        usable = window_cover(free, A_FP)
        return L, occ, free, usable


def runs(mask, axis):
    """For every True cell, the length (cells) of the True run through it along ``axis``,
    and whether each end of the run is the grid's edge (a wall) or not (a box)."""
    m = mask if axis == 0 else mask.T
    nx, ny = m.shape
    length = np.zeros(m.shape, dtype=int)
    lo_wall = np.zeros(m.shape, dtype=bool); hi_wall = np.zeros(m.shape, dtype=bool)
    for j in range(ny):
        i = 0
        while i < nx:
            if not m[i, j]:
                i += 1
                continue
            k = i
            while k < nx and m[k, j]:
                k += 1
            length[i:k, j] = k - i
            lo_wall[i:k, j] = i == 0
            hi_wall[i:k, j] = k == nx
            i = k
    if axis == 1:
        return length.T, lo_wall.T, hi_wall.T
    return length, lo_wall, hi_wall


def describe_cells(cells, free):
    """A set of free floor cells by its local width: through every cell the
    free run along x and along y; the shorter is the strip's width, its
    direction the strip's cross-section.  'runs_x' = a strip lying along x
    (narrow in y: depth left over in front of / behind a row); 'runs_y' =
    narrow in x (width left over beside a box or at a side wall).  The ends
    of the short run say what bounds the strip: wall-wall, wall-box or
    box-box ('wall' = the floor rectangle's edge)."""
    if not cells.any():
        return {'area': 0.0}
    rx, lx, hx = runs(free, 0)
    ry, ly, hy = runs(free, 1)
    short_is_x = rx <= ry
    width = np.where(short_is_x, rx, ry) * CELL
    walls = np.where(short_is_x, lx.astype(int) + hx.astype(int), ly.astype(int) + hy.astype(int))
    a = CELL * CELL
    out = {'area': round(float(cells.sum()) * a, 3),
           'runs_x': round(float((cells & ~short_is_x).sum()) * a, 3),
           'runs_y': round(float((cells & short_is_x).sum()) * a, 3),
           'bound_box_box': round(float((cells & (walls == 0)).sum()) * a, 3),
           'bound_wall_box': round(float((cells & (walls == 1)).sum()) * a, 3),
           'bound_wall_wall': round(float((cells & (walls == 2)).sum()) * a, 3)}
    hist = {}
    for lo, hi in ((0, .1), (.1, .2), (.2, .3), (.3, .45), (.45, 9)):
        hist[f'{lo}-{hi}'] = round(float((cells & (width > lo - 1e-9) & (width < hi - 1e-9)).sum()) * a, 3)
    out['width_hist'] = hist
    out['median_width'] = round(float(np.median(width[cells])), 2)
    return out


def describe_dead(L, free, usable, model):
    return describe_cells(free & ~usable, free)


def killed_where(killed, L, box):
    """Where the killed cells lie relative to the new box: in front of it
    (door side), behind, beside it (left/right in x), or apart (no overlap
    with the box's x or y span)."""
    if not killed.any():
        return {}
    a = CELL * CELL
    xs, ys = L.xx, L.yy
    x0, x1 = float(box.minimum[0]), float(box.maximum[0])
    y0, y1 = float(box.minimum[1]), float(box.maximum[1])
    in_x = (xs >= x0) & (xs <= x1)
    in_y = (ys >= y0) & (ys <= y1)
    out = {'front': killed & in_x & (ys < y0), 'back': killed & in_x & (ys > y1),
           'side': killed & in_y & ~in_x}
    out['apart'] = killed & ~in_x & ~in_y
    return {k: round(float(v.sum()) * a, 3) for k, v in out.items()}


def analyse(path):
    r = json.load(open(path))
    sp = r["scene_spec"]
    m = r["metrics"]
    sc = make_scene(sp["seed"], sp["layout"], sp["task"])
    byidx = {i["index"]: i for i in sc.items}
    models = [
        ContainerModel(dict(c, packed_items=[]), DEFAULT_CONFIG) for c in sc.containers
    ]
    cs = [CState(md) for md in models]
    N = m["total_items"]
    thr = N // 2 + 1
    floor_area = 0.0
    prev = []
    for c in cs:
        L, occ, free, usable = c.floor()
        prev.append((occ, free, usable))
        floor_area += float(L.floor.sum()) * CELL * CELL
    usable_top = [float(c.load().usable(*WIN, None, 1).sum()) * CELL * CELL for c in cs]
    steps = []
    placed_vol = 0.0
    cvol = sum(md.usable_volume for md in models)
    for s in r["steps"]:
        if (
            s.get("event") != "step"
            or not s.get("is_placed_safe")
            or "pos_local" not in s
        ):
            continue
        ci = s["container_idx"]
        it = byidx[s["item_index"]]
        box = AABB(center=tuple(s["pos_local"]), size=tuple(s["size"]))
        cs[ci].boxes.append((box, bool(it["is_soft"])))
        L, occ, free, usable = cs[ci].floor()
        p_occ, p_free, p_usable = prev[ci]
        newly_occ = occ & ~p_occ
        killed = p_usable & ~usable & free  # usable floor turned dead, not occupied
        lost_usable = p_usable & ~usable
        prev[ci] = (occ, free, usable)
        u = float(cs[ci].load().usable(*WIN, None, 1).sum()) * CELL * CELL
        du = usable_top[ci] - u
        usable_top[ci] = u
        placed_vol += it["length"] * it["width"] * it["height"]
        sz = s["size"]
        bottom = s["pos_local"][2] - sz[2] / 2.0
        md = models[ci]
        lo = [s["pos_local"][0] - sz[0] / 2.0, s["pos_local"][1] - sz[1] / 2.0]
        hi = [s["pos_local"][0] + sz[0] / 2.0, s["pos_local"][1] + sz[1] / 2.0]
        steps.append(
            {
                "step": s["step"],
                "ci": ci,
                "arch": str(s.get("archetype")).split("/")[0],
                "shadow": (s.get("shadow") or {}).get("outcome"),
                "cls": cls_of(it),
                "standing": sz[2] > min(sz[0], sz[1]) + 1e-6 and sz[2] > 0.3,
                "floor": bottom < md.z_floor + FLOOR_BAND,
                "bottom": round(bottom - md.z_floor, 3),
                "size": sz,
                "gap": {
                    "left": round(lo[0] - md.floor_rect.x_min, 3),
                    "right": round(md.floor_rect.x_max - hi[0], 3),
                    "door": round(lo[1] - md.floor_rect.y_min, 3),
                    "back": round(md.floor_rect.y_max - hi[1], 3),
                },
                "occ_m2": round(float(newly_occ.sum()) * CELL * CELL, 3),
                "killed_m2": round(float(killed.sum()) * CELL * CELL, 3),
                "killed_desc": describe_cells(killed, free) if killed.any() else None,
                "killed_where": killed_where(killed, L, box),
                "dead_now": describe_cells(free & ~usable, free) if (free & ~usable).any() else None,
                "lost_usable_m2": round(float(lost_usable.sum()) * CELL * CELL, 3),
                "free_m2": round(sum(float(p[1].sum()) for p in prev) * CELL * CELL, 3),
                "usable_floor_m2": round(
                    sum(float(p[2].sum()) for p in prev) * CELL * CELL, 3
                ),
                "usable_top_m2": round(sum(usable_top), 3),
                "dtop_m2": round(du, 3),
                "fill": round(placed_vol / cvol, 3),
                "considered": s.get("considered"),
                "survivors": s.get("survivors"),
            }
        )
    end = []
    for ci, c in enumerate(cs):
        L, occ, free, usable = c.floor()
        a, hx, hy = max_rect(free)
        end.append(
            {
                "free_m2": round(float(free.sum()) * CELL * CELL, 3),
                "usable_m2": round(float(usable.sum()) * CELL * CELL, 3),
                "dead_m2": round(float((free & ~usable).sum()) * CELL * CELL, 3),
                "floor_m2": round(float(L.floor.sum()) * CELL * CELL, 3),
                "floor_rect": [
                    round(models[ci].floor_rect.x_max - models[ci].floor_rect.x_min, 3),
                    round(models[ci].floor_rect.y_max - models[ci].floor_rect.y_min, 3),
                ],
                "ler": [round(hx * CELL, 2), round(hy * CELL, 2)],
                "dead": describe_dead(L, free, usable, models[ci]),
            }
        )
    return {
        "scene": r["scene"],
        "task": sp["task"],
        "stratum": sp["stratum"],
        "order": sp["order"],
        "mix": sp["mix"],
        "N": N,
        "thr": thr,
        "placed": m["placed_count"],
        "margin": m["placed_count"] - thr,
        "end_reason": m["end_reason"],
        "floor_m2": round(floor_area, 3),
        "steps": steps,
        "end": end,
    }


def main():
    os.makedirs(OUTD, exist_ok=True)
    for rec in sys.argv[1:]:
        out = []
        for f in sorted(glob.glob(f"{REPO}/reports/bench/{rec}/[bc]-hard2-s*.json")):
            out.append(analyse(f))
        json.dump(
            out, open(f"{OUTD}/strips-{rec}.json", "w"), separators=(",", ":")
        )
        print(rec, len(out), flush=True)


if __name__ == "__main__":
    main()
