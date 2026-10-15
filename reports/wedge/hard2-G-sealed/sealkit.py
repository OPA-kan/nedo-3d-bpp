"""sealkit.py -- shared helpers for the G (sealed patch) investigation.

Board rebuild from a bench record (as reports/wedge/hard2-miss-taxonomy/extract.py:
settled poses of final_items, container x offset recovered from pos_local), the
level-spot enumeration of rule_alpha/surface.py, and two transport checks:

* ``cells``: the taxonomy's cell model (extract.reach_fit), kept for comparison;
* ``exact``: the official validator's check_transport_path
  (simulator/src/ground_handling/validator.py:85-175) on axis-aligned boxes:
  - start at (clamp(x), -W/2, z_t) with x clamped to
    [-L/2+T+cut_x+hx+start_margin, L/2-T-hx-start_margin];
  - z_t = commanded centre + effective lift, capped at H+buffer-T-hz-start_margin;
    the lift is start_z (0.08) unless the commanded bottom is within [0, 0.05]
    above a resting surface (T, H/2+T+buffer), then 0; else clipped under a
    ceiling surface (H/2+buffer, H+buffer-T) when the clearance is < lift+0.018;
  - the commanded pose mirrors agent/agent.py simulator_action_center
    (+0.020 on the floor, +0.051 on a shelf) and the v49 band escape
    (band_lift 0.003: a bottom inside [H/2+T+buffer, +0.05] is commanded 3 mm
    over the band's top);
  - a y-leg then an x-leg; blocked when any packed box (or the big shelf of a
    require_shelf container) comes within safety_margin (0.015 m).
  Items are boxes, so the closest distance between the swept box and a packed
  box is the AABB distance.  The small shelf over the chamfer and the walls are
  not checked by the validator (validator.py:230-260) and are not checked here.

Read-only on the repository.
"""

from __future__ import annotations

import collections
import json
import os
import statistics
import sys

import numpy as np

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from bench.scenes import make_scene  # noqa: E402
from rule_alpha.config import DEFAULT_CONFIG  # noqa: E402
from rule_alpha.geometry import ContainerModel  # noqa: E402
from rule_alpha.surface import _Load, _close_gaps, TOL, CLEAR  # noqa: E402
from rule_alpha._reuse import packed_aabbs_local  # noqa: E402

CELL = 0.02
SAFETY = 0.015
START_Z = 0.08
START_MARGIN = 0.01
CEIL_MARGIN = 0.018
FLOOR_LIFT = 0.020
SHELF_LIFT = 0.051
BAND_LIFT = 0.003
RECORDS = os.path.join(REPO, "reports", "bench")


def vol(i):
    return i["length"] * i["width"] * i["height"]


def load_record(name, scene):
    return json.load(open(os.path.join(RECORDS, name, scene + ".json")))


class Episode:
    """A record with its scene, its placements in order (local settled poses)."""

    def __init__(self, rec):
        self.rec = rec
        sp = rec["scene_spec"]
        self.sp = sp
        self.scene = make_scene(sp["seed"], sp["layout"], sp["task"])
        self.items = self.scene.items
        self.byidx = {i["index"]: i for i in self.items}
        m = rec["metrics"]
        self.N = m["total_items"]
        self.thr = self.N // 2 + 1
        self.placed = m["placed_count"]
        self.margin = self.placed - self.thr
        steps = [s for s in rec["steps"] if s.get("event") == "step"]
        self.ok = [s for s in steps if s.get("is_placed_safe")]
        final = {it["index"]: it for it in rec["final_items"]}
        off = collections.defaultdict(list)
        for s in self.ok:
            f = final.get(s["item_index"])
            if f is not None and "pos_local" in s:
                off[s["container_idx"]].append(f["pos"][0] - s["pos_local"][0])
        self.off = {k: statistics.median(v) for k, v in off.items()}
        self.raw_containers = [dict(c, packed_items=[]) for c in self.scene.containers]
        self.models = [
            ContainerModel(dict(c), DEFAULT_CONFIG) for c in self.raw_containers
        ]
        # placements: (order, ci, item, pos, dims, step-record)
        self.placements = []
        for order, s in enumerate(self.ok):
            f = final.get(s["item_index"])
            if f is None or "size" not in s:
                continue
            ci = s["container_idx"]
            it = self.byidx[s["item_index"]]
            pos = [f["pos"][0] - self.off.get(ci, 0.0), f["pos"][1], f["pos"][2]]
            self.placements.append(
                dict(order=order, ci=ci, item=it, pos=pos, dims=list(s["size"]), step=s)
            )
        placed_idx = {s["item_index"] for s in self.ok}
        self.unplaced = [i for i in self.items if i["index"] not in placed_idx]
        if sp["task"] == "C":
            self.visible = [i for i in self.items if i["index"] >= self.placed][:1]
        else:
            self.visible = self.unplaced[: sp["pool"]]

    def containers_at(self, t, use_commanded=False):
        """Container dicts with the first t placements packed."""
        cs = [dict(c, packed_items=[]) for c in self.raw_containers]
        for p in self.placements[:t]:
            pos = p["step"]["pos_local"] if use_commanded else p["pos"]
            cs[p["ci"]]["packed_items"].append(
                {
                    "index": p["item"]["index"],
                    "pos": list(pos),
                    "dims": p["dims"],
                    "is_soft": p["item"]["is_soft"],
                    "is_prioritized": p["item"]["is_prioritized"],
                }
            )
        return cs

    def load(self, cs, ci):
        load = _Load(self.models[ci], CELL)
        for box, soft, _p in packed_aabbs_local(cs[ci]):
            load.add(box, soft)
        return load

    def boxes(self, cs, ci):
        """(N,3) lo, (N,3) hi, order index list of the packed boxes in container ci."""
        lo, hi = [], []
        for it in cs[ci]["packed_items"]:
            c = np.asarray(it["pos"], float)
            d = np.asarray(it["dims"], float)
            lo.append(c - d / 2)
            hi.append(c + d / 2)
        if not lo:
            return np.zeros((0, 3)), np.zeros((0, 3))
        return np.asarray(lo), np.asarray(hi)


def orientations(item):
    d = (item["length"], item["width"], item["height"])
    out = []
    seen = set()
    for k in range(3):
        h = d[k]
        fp = [d[j] for j in range(3) if j != k]
        for fx, fy in ((fp[0], fp[1]), (fp[1], fp[0])):
            key = (round(fx, 4), round(fy, 4), round(h, 4))
            if key in seen:
                continue
            seen.add(key)
            out.append((fx, fy, h))
    return out


def _prefix(m):
    s = np.zeros((m.shape[0] + 1, m.shape[1] + 1), dtype=np.int32)
    s[1:, 1:] = np.cumsum(np.cumsum(m.astype(np.int32), axis=0), axis=1)
    return s


def level_origins(load, fx, fy, h, z, soft_support=False):
    """Bool array (nx-a+1, ny-b+1) of window origins of a level patch at z for
    footprint fx (x) by fy (y) and height h, as surface._Load.usable (support within
    TOL, gaps of 2 cells closed off the floor, footprint+CLEAR, h+CLEAR free, chamfer)."""
    need = h + CLEAR
    a = int(round((fx + CLEAR) / CELL))
    b = int(round((fy + CLEAR) / CELL))
    if a > load.nx or b > load.ny or z + need > load.z_ceiling + 1e-9:
        return None
    on_floor = abs(z - load.z_floor) <= TOL
    support = (
        load.floor.copy() if on_floor else np.zeros((load.nx, load.ny), dtype=bool)
    )
    for m, top, _b in load.shelves:
        if abs(top - z) <= TOL:
            support |= m
    for m, _b, top, soft in load.boxes:
        if abs(top - z) <= TOL and (
            not soft or (soft_support and z + h <= load.z_floor + 0.7 + 1e-6)
        ):
            support |= m
    if not on_floor:
        support = _close_gaps(support, 1)
    free = load.local_ceiling(z) >= z + need - 1e-9
    for m, bottom, top, _soft in load.boxes:
        if top > z + 1e-3 and bottom < z + need - 1e-3:
            free &= ~m
    ok = support & free & (load.xx >= load.x_limit(z) + CLEAR / 2.0)
    if ok.sum() < a * b:
        return np.zeros((max(0, load.nx - a + 1), max(0, load.ny - b + 1)), dtype=bool)
    s = _prefix(ok)
    return (s[a:, b:] - s[:-a, b:] - s[a:, :-b] + s[:-a, :-b]) == a * b


def spot_centres(load, fx, fy, shape):
    a = int(round((fx + CLEAR) / CELL))
    b = int(round((fy + CLEAR) / CELL))
    I, J = np.meshgrid(np.arange(shape[0]), np.arange(shape[1]), indexing="ij")
    x0 = load.xx[0, 0] - CELL / 2
    y0 = load.yy[0, 0] - CELL / 2
    cx = x0 + (I + a / 2.0) * CELL
    cy = y0 + (J + b / 2.0) * CELL
    return cx, cy


def transport_z(container, bottom_planned, h, on_floor, on_shelf):
    """Centre z of the carried box, per validator.check_transport_path and the
    agent's commanded pose (floor +0.02, shelf +0.051, band escape +0.003)."""
    H = float(container["height"])
    T = float(container["thickness"])
    B = float(container.get("buffer", 0.0))
    if on_floor:
        bottom = bottom_planned + FLOOR_LIFT
    elif on_shelf:
        bottom = bottom_planned + SHELF_LIFT
    else:
        bottom = bottom_planned
        band = H / 2.0 + T + B
        if band <= bottom <= band + 0.05:
            bottom = band + 0.05 + BAND_LIFT
    lift = START_Z
    for r in (T, H / 2.0 + T + B):
        if 0 <= bottom - r <= 0.05:
            lift = 0.0
            break
    top = bottom + h
    if lift > 0:
        for c in (H / 2.0 + B, H + B - T):
            cl = c - top
            if 0 <= cl < lift + CEIL_MARGIN:
                lift = max(0.0, cl - CEIL_MARGIN - 0.0005)
                break
    zc = bottom + h / 2.0
    return min(H + B - T - h / 2.0 - START_MARGIN, zc + lift)


def _aabb_dist(lo1, hi1, lo2, hi2):
    """Distance between boxes; lo1/hi1 (...,3) broadcast against lo2/hi2 (M,3)."""
    g = np.maximum(0.0, np.maximum(lo2 - hi1, lo1 - hi2))
    return np.sqrt((g**2).sum(-1))


def exact_blockers(container, blo, bhi, cx, cy, fx, fy, h, ztc, shelf_box=None):
    """For spot centres (arrays), return a bool (n, M) matrix: box m blocks the sweep."""
    L = float(container["length"])
    W = float(container["width"])
    T = float(container["thickness"])
    cut = float(container.get("cut_x", 0.0))
    hx, hy, hz = fx / 2.0, fy / 2.0, h / 2.0
    xmin = -L / 2 + T + cut + hx + START_MARGIN
    xmax = L / 2 - T - hx - START_MARGIN
    cx = np.asarray(cx, float).ravel()
    cy = np.asarray(cy, float).ravel()
    sx = np.clip(cx, xmin, xmax)
    n = cx.size
    zt = np.full(n, ztc) if np.isscalar(ztc) else np.asarray(ztc, float).ravel()
    ylo = np.stack([sx - hx, np.full(n, -W / 2 - hy), zt - hz], -1)
    yhi = np.stack([sx + hx, cy + hy, zt + hz], -1)
    xlo = np.stack([np.minimum(sx, cx) - hx, cy - hy, zt - hz], -1)
    xhi = np.stack([np.maximum(sx, cx) + hx, cy + hy, zt + hz], -1)
    lo2 = blo
    hi2 = bhi
    if shelf_box is not None:
        lo2 = np.vstack([blo, shelf_box[0][None]])
        hi2 = np.vstack([bhi, shelf_box[1][None]])
    if lo2.shape[0] == 0:
        return np.zeros((n, 0), dtype=bool)
    dy = _aabb_dist(ylo[:, None, :], yhi[:, None, :], lo2[None], hi2[None])
    dx = _aabb_dist(xlo[:, None, :], xhi[:, None, :], lo2[None], hi2[None])
    return (dy < SAFETY - 1e-9) | (dx < SAFETY - 1e-9)


def big_shelf(container):
    """The require_shelf plate as (lo, hi) local, per agent.shelf_aabbs; None without one."""
    if not container.get("require_shelf"):
        return None
    L = float(container["length"])
    W = float(container["width"])
    H = float(container["height"])
    T = float(container["thickness"])
    B = float(container.get("buffer", 0.0))
    zc = H / 2.0 + T / 2.0 + B
    c = np.array([0.0, W / 4.0, zc])
    d = np.array([L - T, W / 2.0 - 2 * T, T])
    return (c - d / 2, c + d / 2)


def enumerate_spots(ep, cs, ci, item, soft_support=None):
    """All level spots for the item in container ci: list of dicts with arrays.
    Each entry: fx, fy, h, z, origins (bool array), cx, cy, on_floor, on_shelf."""
    if soft_support is None:
        soft_support = bool(item["is_soft"])
    load = ep.load(cs, ci)
    out = []
    for fx, fy, h in orientations(item):
        for z in load.levels():
            org = level_origins(load, fx, fy, h, z, soft_support)
            if org is None or not org.any():
                continue
            cx, cy = spot_centres(load, fx, fy, org.shape)
            on_floor = abs(z - load.z_floor) <= TOL
            on_shelf = (
                any(abs(top - z) <= TOL for _m, top, _b in load.shelves)
                and not on_floor
            )
            out.append(
                dict(
                    fx=fx,
                    fy=fy,
                    h=h,
                    z=z,
                    origins=org,
                    cx=cx,
                    cy=cy,
                    on_floor=on_floor,
                    on_shelf=on_shelf,
                )
            )
    return out, load


def reach_exact(ep, cs, ci, spots):
    """Per spot entry, bool array (same shape as origins) of exact-transport-clear origins,
    and for blocked ones the index (in cs[ci]['packed_items']) of the earliest-packed blocker."""
    cont = ep.raw_containers[ci]
    blo, bhi = ep.boxes(cs, ci)
    sb = big_shelf(cont)
    res = []
    for sp in spots:
        org = sp["origins"]
        I, J = np.nonzero(org)
        if I.size == 0:
            res.append((np.zeros_like(org), None))
            continue
        cx = sp["cx"][I, J]
        cy = sp["cy"][I, J]
        zt = transport_z(cont, sp["z"], sp["h"], sp["on_floor"], sp["on_shelf"])
        M = exact_blockers(cont, blo, bhi, cx, cy, sp["fx"], sp["fy"], sp["h"], zt, sb)
        clear = ~M.any(1)
        # earliest packed blocker (packing order); -1 when clear
        first = (
            np.where(M.any(1), np.argmax(M, axis=1), -1)
            if M.shape[1]
            else np.full(M.shape[0], -1)
        )
        cl = np.zeros_like(org)
        cl[I[clear], J[clear]] = True
        fb = np.full(org.shape, -1, dtype=int)
        fb[I, J] = first
        res.append((cl, fb))
    return res
