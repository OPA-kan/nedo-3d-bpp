"""The usable surface a pose closes, read at decision time.

The levelness instrument (``scripts/levelness.py``; findings, "The
levelness of the load as it is built") reads the *usable surface* of a
load -- the cells of its top surface (the floor, the shelf plates, the
hard tops) that lie in a level patch (tops within 2 cm) holding a
footprint's window with 3 cm of clearance and the class's height plus
3 cm free above it -- and finds it halved by the middle of every
episode and five sixths gone by three quarters, on every task alike.
The ladder's keys rank by footprint, row waste and plateau; none reads
the surface a pose closes.  ``level_key`` (the neighbouring tops' step
as a tie-break) did not move the curve: the rungs' leading terms
decide.

``arbitrate_surface`` is the instrument as an arbiter: the first few
candidates of the rung the ladder chose, in the rung's own order, are
each stamped on a 2 cm heightmap of the container and the usable
surface after each is measured (``SurfaceScorer``), with the surface
the pose's own footprint stood on credited back (the instrument's
waste, reversed: a flat box on a level patch costs nothing for the
cells under it, so a standing pose cannot win by closing less floor);
the candidate after which the most is kept replaces the rung's pick
when it keeps more by ``surface_arbiter_margin`` square metres.  The rung's
choice of archetype stands, as does its order among near-equal
surfaces; only a pick that closes a window's worth more than its
neighbour in the same rung is replaced.  (The room selector of
``rule_alpha.room`` re-ranked the survivors of every rung and lost the
ladder's structure; this one never crosses a rung.)

A soft top carries no hard cargo (the cover rule), so a soft box offers
no surface back; a standing pose offers its narrow top; a pose that
breaks a patch into pieces narrower than the window closes the pieces.
The sweep's reachability is not modelled: the surface is the geometric
necessary condition, as in the instrument.
"""

from __future__ import annotations

import time

import numpy as np

from ._reuse import AABB, packed_aabbs_local

TOL = 0.02
CLEAR = 0.03


def _covered(ok: np.ndarray, a: int, b: int) -> np.ndarray:
    """The cells covered by some a x b window of all-True cells of ``ok``."""
    nx, ny = ok.shape
    if a > nx or b > ny:
        return np.zeros_like(ok)
    s = np.zeros((nx + 1, ny + 1), dtype=np.int32)
    s[1:, 1:] = np.cumsum(np.cumsum(ok.astype(np.int32), axis=0), axis=1)
    origins = (s[a:, b:] - s[:-a, b:] - s[a:, :-b] + s[:-a, :-b]) == a * b
    if not origins.any():
        return np.zeros_like(ok)
    # a cell (i, j) is covered when an origin lies in [i-a+1, i] x [j-b+1, j]
    o = np.zeros((nx + 1, ny + 1), dtype=np.int32)
    o[1:nx - a + 2, 1:ny - b + 2] = np.cumsum(np.cumsum(origins.astype(np.int32), axis=0), axis=1)
    i = np.arange(nx)
    j = np.arange(ny)
    hi_i = np.minimum(i, nx - a) + 1
    lo_i = np.maximum(i - a + 1, 0)
    hi_j = np.minimum(j, ny - b) + 1
    lo_j = np.maximum(j - b + 1, 0)
    cover = (o[np.ix_(hi_i, hi_j)] - o[np.ix_(lo_i, hi_j)] - o[np.ix_(hi_i, lo_j)] + o[np.ix_(lo_i, lo_j)])
    return cover > 0


def _box_sum(mask: np.ndarray, g: int) -> np.ndarray:
    """For every cell, the count of True cells in the (2g+1)-square around it."""
    nx, ny = mask.shape
    p = np.zeros((nx + 2 * g, ny + 2 * g), dtype=np.int32)
    p[g:g + nx, g:g + ny] = mask
    s = np.zeros((p.shape[0] + 1, p.shape[1] + 1), dtype=np.int32)
    s[1:, 1:] = np.cumsum(np.cumsum(p, axis=0), axis=1)
    w = 2 * g + 1
    return s[w:, w:] - s[:-w, w:] - s[w:, :-w] + s[:-w, :-w]


def _close_gaps(mask: np.ndarray, g: int) -> np.ndarray:
    """Morphological closing: the gaps of up to about ``2g`` cells between
    the mask's parts are filled (dilate by g, then erode by g).  Two tops
    at one height with the settled clearance between them are one patch
    to a box that spans the gap, as the plateau-merge rung's bridges do."""
    if g <= 0 or not mask.any():
        return mask
    w = 2 * g + 1
    dilated = _box_sum(mask, g) > 0
    # erode the dilated mask: a cell stays when its whole square is dilated;
    # cells whose square reaches past the grid count the outside as dilated
    nx, ny = mask.shape
    p = np.ones((nx + 2 * g, ny + 2 * g), dtype=bool)
    p[g:g + nx, g:g + ny] = dilated
    s = np.zeros((p.shape[0] + 1, p.shape[1] + 1), dtype=np.int32)
    s[1:, 1:] = np.cumsum(np.cumsum(p.astype(np.int32), axis=0), axis=1)
    full = s[w:, w:] - s[:-w, w:] - s[w:, :-w] + s[:-w, :-w]
    return full == w * w


class _Load:
    """One container's load on the cell grid: the floor and the shelf
    plates from the model, the packed boxes as columns."""

    def __init__(self, model, cell: float):
        self.model = model
        self.cell = cell
        rect = model.floor_rect
        self.nx = max(1, int(round((rect.x_max - rect.x_min) / cell)))
        self.ny = max(1, int(round((rect.y_max - rect.y_min) / cell)))
        xs = rect.x_min + (np.arange(self.nx) + 0.5) * cell
        ys = rect.y_min + (np.arange(self.ny) + 0.5) * cell
        self.xx, self.yy = np.meshgrid(xs, ys, indexing="ij")
        self.floor = np.ones((self.nx, self.ny), dtype=bool)
        self.z_floor = float(model.z_floor)
        self.z_ceiling = float(model.z_ceiling)
        self.shelves = []  # (mask, top, bottom)
        for s in model.shelves:
            m = ((self.xx >= float(s.minimum[0])) & (self.xx <= float(s.maximum[0]))
                 & (self.yy >= float(s.minimum[1])) & (self.yy <= float(s.maximum[1])))
            self.shelves.append((m, float(s.maximum[2]), float(s.minimum[2])))
        self.boxes = []  # (mask, bottom, top, soft)
        self._ceilings: dict = {}
        self._xlim: dict = {}

    def mask(self, box: AABB) -> np.ndarray:
        return ((self.xx >= float(box.minimum[0])) & (self.xx <= float(box.maximum[0]))
                & (self.yy >= float(box.minimum[1])) & (self.yy <= float(box.maximum[1])))

    def add(self, box: AABB, soft: bool) -> None:
        self.boxes.append((self.mask(box), float(box.minimum[2]), float(box.maximum[2]), bool(soft)))

    def local_ceiling(self, z: float) -> np.ndarray:
        key = round(z, 3)
        out = self._ceilings.get(key)
        if out is None:
            out = np.full((self.nx, self.ny), self.z_ceiling)
            for m, _top, bottom in self.shelves:
                under = m & (z < bottom - 1e-6)
                out[under] = np.minimum(out[under], bottom)
            self._ceilings[key] = out
        return out

    def x_limit(self, z: float) -> float:
        key = round(z, 3)
        out = self._xlim.get(key)
        if out is None:
            out = self._xlim[key] = float(self.model.x_limit_at_height(z + 1e-3))
        return out

    def levels(self, extra=None) -> list[float]:
        zs = {round(self.z_floor, 2)}
        for _m, top, _b in self.shelves:
            zs.add(round(top, 2))
        for _m, _b, top, soft in self.boxes:
            if not soft:
                zs.add(round(top, 2))
        if extra is not None and not extra[3]:
            zs.add(round(extra[2], 2))
        return sorted(zs)

    def usable(self, footprint, height: float, extra=None, gap_cells: int = 1) -> np.ndarray:
        """The cells of the top surface in a level patch holding the
        footprint's window (either way round) with the clearance, and the
        height plus the clearance free above it.  ``extra`` is one more
        box, ``(mask, bottom, top, soft)``, stamped for this reading.
        Gaps of up to ``2 * gap_cells`` between tops at one height are
        part of the patch (``_close_gaps``)."""
        w, l = sorted(footprint)
        need = height + CLEAR
        a, b = int(round((l + CLEAR) / self.cell)), int(round((w + CLEAR) / self.cell))
        boxes = self.boxes if extra is None else self.boxes + [extra]
        usable = np.zeros((self.nx, self.ny), dtype=bool)
        for z in self.levels(extra):
            if z + need > self.z_ceiling + 1e-9:
                continue
            on_floor = abs(z - self.z_floor) <= TOL
            support = self.floor.copy() if on_floor else np.zeros((self.nx, self.ny), dtype=bool)
            for m, top, _b in self.shelves:
                if abs(top - z) <= TOL:
                    support |= m
            for m, _b, top, soft in boxes:
                if abs(top - z) <= TOL and not soft:
                    support |= m
            if not on_floor:
                support = _close_gaps(support, gap_cells)
            free = self.local_ceiling(z) >= z + need - 1e-9
            for m, bottom, top, _soft in boxes:
                if top > z + 1e-3 and bottom < z + need - 1e-3:
                    free &= ~m
            ok = support & free & (self.xx >= self.x_limit(z) + CLEAR / 2.0)
            if ok.sum() < a * b:
                continue
            usable |= _covered(ok, a, b)
            usable |= _covered(ok, b, a)
        return usable


class SurfaceScorer:
    def __init__(self, config):
        self.cell = float(getattr(config, "surface_arbiter_cell", 0.02))
        spec = str(getattr(config, "surface_arbiter_window", "0.40x0.55x0.24"))
        l, w, h = (float(v) for v in spec.lower().split("x"))
        self.footprint = (l, w)
        self.height = h
        self.gap_cells = max(0, int(round(float(getattr(config, "surface_arbiter_gap", 0.05)) / self.cell / 2.0)))
        self.calls = 0
        self.overrides = 0
        self.seconds = 0.0

    def load(self, board, container_idx: int) -> _Load:
        load = _Load(board.model(container_idx), self.cell)
        for box, soft, _prio in packed_aabbs_local(board.container(container_idx)):
            load.add(box, soft)
        return load

    def mask(self, load: _Load, box: AABB | None = None, soft: bool = False) -> np.ndarray:
        extra = None
        if box is not None:
            extra = (load.mask(box), float(box.minimum[2]), float(box.maximum[2]), bool(soft))
        return load.usable(self.footprint, self.height, extra, self.gap_cells)

    def area(self, load: _Load, box: AABB | None = None, soft: bool = False) -> float:
        return float(self.mask(load, box, soft).sum()) * load.cell * load.cell

    def kept(self, load: _Load, base: np.ndarray, box: AABB, soft: bool = False) -> float:
        """The usable surface after the box, plus the usable surface its
        own footprint stood on: the instrument's waste, with its sign
        reversed.  A flat box on a level patch is charged nothing for the
        cells under it, so a standing pose does not win by closing less
        floor; what counts is the surface closed beyond the footprint and
        the surface the top offers back."""
        after = self.mask(load, box, soft)
        credit = load.mask(box) & base
        return (float(after.sum()) + float(credit.sum())) * load.cell * load.cell


_SCORERS: dict = {}


def scorer_for(config) -> SurfaceScorer:
    key = (float(getattr(config, "surface_arbiter_cell", 0.02)),
           str(getattr(config, "surface_arbiter_window", "0.40x0.55x0.24")),
           float(getattr(config, "surface_arbiter_gap", 0.05)))
    scorer = _SCORERS.get(key)
    if scorer is None:
        if len(_SCORERS) > 16:
            _SCORERS.clear()
        scorer = _SCORERS[key] = SurfaceScorer(config)
    return scorer


def arbitrate_surface(chosen, chosen_archetype: str, ordered: list, board, container_idx: int, config):
    """Among the first ``surface_arbiter_k`` candidates of the chosen
    rung (``ordered``, the rung's own order, the pick first), the one
    after which the most usable surface remains, when it keeps more
    than the pick by ``surface_arbiter_margin`` m^2.  Returns
    ``(candidate, archetype)`` or None."""
    k = int(getattr(config, "surface_arbiter_k", 4))
    pool = list(ordered[:k])
    if chosen not in pool:
        pool.insert(0, chosen)
    if len(pool) < 2:
        return None
    scorer = scorer_for(config)
    scorer.calls += 1
    t0 = time.perf_counter()
    budget = float(getattr(config, "surface_arbiter_seconds", 0.4))
    load = scorer.load(board, container_idx)
    soft = bool(chosen.profile.is_soft)
    base = scorer.mask(load)
    areas = []
    for c in pool:
        if c is not chosen and time.perf_counter() - t0 > budget:
            areas.append(-1.0)
            continue
        areas.append(scorer.kept(load, base, c.box, soft))
    scorer.seconds += time.perf_counter() - t0
    i_chosen = next(i for i, c in enumerate(pool) if c is chosen)
    best = int(np.argmax(areas))
    if best == i_chosen or areas[best] <= areas[i_chosen] + float(getattr(config, "surface_arbiter_margin", 0.05)):
        return None
    scorer.overrides += 1
    return pool[best], f"surface/{chosen_archetype}"
