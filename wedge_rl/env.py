"""The chamfer-strip environment.

State: the container is empty except for what this episode has placed in the
play region, which is the strip along the chamfer plus ``x_extent`` metres of
floor to its right (so a base box can stand at the floor line and carry a
step that overhangs the wedge).  Items arrive one at a time from the official
seven types.  An action is one of the generated candidate placements, or
PASS (the item goes elsewhere in the container; no reward, no penalty).

Reward: the volume of the placed box that lies left of the floor line
``x_floor_min`` -- the part of the container floor placements can never use.
Everything else about validity (inclusion, transport sweep from the opening,
static stability, shelf clearance) is rule-alpha's analytic ``validate``.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import numpy as np

from bench.scenes import SKUS, make_scene
from rule_alpha import classify as cls
from rule_alpha import layer1, stability
from rule_alpha._reuse import AABB, packed_aabbs_local
from rule_alpha.geometry import ContainerModel

PASS = -1
CELL = 0.04


@dataclass
class Candidate:
    """One legal pose in a region.  ``gain`` is what the region pays for it
    (wedge volume in the strip, box volume on the shelf); ``on_floor`` means
    it rests on the region's base surface rather than on another box."""

    box: AABB
    orientation: int
    dims: tuple
    bottom: float
    on_floor: bool
    gain: float
    support_ratio: float
    margin: float

    def features(self, env) -> np.ndarray:
        """Read through the env: ``model``, ``x_max_play``, ``z_top`` and
        ``reach_of`` are what a region has to provide."""
        m = env.model
        return np.asarray([
            (float(self.box.center[0]) - m.x_wall_min) / max(env.x_max_play - m.x_wall_min, 1e-9),
            (float(self.box.center[1]) - m.y_opening) / max(m.y_back - m.y_opening, 1e-9),
            (self.bottom - m.z_floor) / max(env.z_top - m.z_floor, 1e-9),
            self.dims[0], self.dims[1], self.dims[2],
            self.gain / 0.2,
            self.support_ratio, min(self.margin, 0.3) / 0.3,
            1.0 if self.on_floor else 0.0,
            float(self.box.maximum[2] - m.z_floor) / max(env.z_top - m.z_floor, 1e-9),
            env.reach_of(self.box),
        ], dtype=np.float32)


FEATURE_SIZE = 12


# ---------------------------------------------------------------------------
# The strip as functions of (model, container), so the same generator and
# observation serve the training environment (empty container) and the
# option that runs inside rule-alpha (whatever the container holds).
# ---------------------------------------------------------------------------
def play_region(model: ContainerModel, x_extent: float) -> tuple[float, float]:
    """(x_max_play, z_top): the strip's right edge and the height under the small shelf."""
    x_max_play = model.x_floor_min + x_extent
    z_top = float(model.small_shelf.minimum[2]) if model.small_shelf is not None else model.z_ceiling
    return x_max_play, z_top


def grid_shape(model: ContainerModel, x_max_play: float) -> tuple[int, int]:
    nx = int(np.ceil((x_max_play - model.x_wall_min) / CELL))
    ny = int(np.ceil((model.y_back - model.y_opening) / CELL))
    return nx, ny


def chamfer_height_at(model: ContainerModel, x: float) -> float:
    """Height above the floor of the chamfer plane at column x (0 right of the floor line)."""
    if x >= model.x_floor_min:
        return 0.0
    lo, hi = model.z_floor, model.z_chamfer_top
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        if model.x_limit_at_height(mid) <= x:
            hi = mid
        else:
            lo = mid
    return hi - model.z_floor


def strip_heightmap(model: ContainerModel, container: dict, nx: int, ny: int) -> np.ndarray:
    h = np.zeros((nx, ny), dtype=np.float32)
    xs = model.x_wall_min + (np.arange(nx) + 0.5) * CELL
    ys = model.y_opening + (np.arange(ny) + 0.5) * CELL
    for box, _s, _p in packed_aabbs_local(container):
        ix = (xs >= box.minimum[0]) & (xs <= box.maximum[0])
        iy = (ys >= box.minimum[1]) & (ys <= box.maximum[1])
        top = float(box.maximum[2]) - model.z_floor
        h[np.ix_(ix, iy)] = np.maximum(h[np.ix_(ix, iy)], top)
    return h


def strip_observation(model: ContainerModel, container: dict, nx: int, ny: int, z_top: float,
                      item: dict | None, remaining: float) -> dict:
    scale = max(z_top - model.z_floor, 1e-9)
    xs = model.x_wall_min + (np.arange(nx) + 0.5) * CELL
    chamfer = np.asarray([chamfer_height_at(model, x) for x in xs], dtype=np.float32)
    return {
        "heightmap": strip_heightmap(model, container, nx, ny) / scale,
        "profile": chamfer / scale,
        "item": np.asarray([item["length"], item["width"], item["height"], item["mass"] / 20.0,
                            1.0 if item["is_soft"] else 0.0] if item else [0, 0, 0, 0, 0], dtype=np.float32),
        "remaining": float(remaining),
    }


def strip_gain_of(model: ContainerModel, box: AABB) -> float:
    left = min(float(box.maximum[0]), model.x_floor_min) - float(box.minimum[0])
    if left <= 0:
        return 0.0
    return left * float(box.size[1]) * float(box.size[2])


def prefilter(model: ContainerModel, cfg, container: dict, dx: float, dy: float, dz: float,
              bottom: float, xs, ys, on_floor: bool) -> list[tuple[float, float]]:
    """The (x, y) centres of a grid of poses that can still pass ``validate``.

    Three of the validator's own rejections are evaluated for the whole grid
    at once: the settled pose outside the container planes (``model.inside``
    with the settled wall clearance), penetration of a packed item or shelf
    (``fastgeom._penetrates_any``), and a raised pose that touches no top at
    its own bottom (which stability rejects as no-support).  Every pose that
    survives is then validated exactly as before, so the candidate set is
    unchanged; only the thousands of poses that were going to fail are no
    longer sent through the full validator one at a time."""
    from rule_alpha import fastgeom
    from rule_alpha._reuse import CONTACT_TOLERANCE, EPS

    xs = np.asarray(sorted(xs), dtype=np.float64)
    ys = np.asarray(sorted(ys), dtype=np.float64)
    if xs.size == 0 or ys.size == 0:
        return []
    gx, gy = np.meshgrid(xs, ys, indexing="ij")
    centres = np.stack([gx.ravel(), gy.ravel(), np.full(gx.size, bottom + dz / 2.0)], axis=1)
    half = np.asarray([dx, dy, dz]) / 2.0
    # 1. settled pose inside every plane (floor plane at zero clearance)
    normals = model.plane_normals
    points = model.plane_points
    signed = centres @ normals.T - np.sum(normals * points, axis=1)[None, :] + (np.abs(normals) @ half)[None, :]
    limits = np.full(normals.shape[0], -float(cfg.settled_wall_clearance))
    if model.floor_plane_index >= 0:
        limits[model.floor_plane_index] = 0.0
    keep = np.all(signed <= limits[None, :] + 1e-9, axis=1)
    if not keep.any():
        return []
    # 2. penetration of shelves or packed items
    obs = fastgeom.obstacles(container)
    cmin = centres - half
    cmax = centres + half
    clearance = float(cfg.settled_clearance)
    for omin, omax in ((obs["shelf_min"], obs["shelf_max"]), (obs["packed_min"], obs["packed_max"])):
        if omin.shape[0] == 0:
            continue
        vgap = np.maximum(omin[None, :, 2] - cmax[:, None, 2], cmin[:, None, 2] - omax[None, :, 2])
        xgap = np.maximum(omin[None, :, 0] - cmax[:, None, 0], cmin[:, None, 0] - omax[None, :, 0])
        ygap = np.maximum(omin[None, :, 1] - cmax[:, None, 1], cmin[:, None, 1] - omax[None, :, 1])
        hit = (vgap < -CONTACT_TOLERANCE) & (xgap < clearance - EPS) & (ygap < clearance - EPS)
        keep &= ~hit.any(axis=1)
    # 3. a raised pose must overlap some top at its bottom height
    if not on_floor:
        pmin, pmax = obs["packed_min"], obs["packed_max"]
        tops = np.abs(pmax[:, 2] - bottom) <= CONTACT_TOLERANCE if pmin.shape[0] else np.zeros(0, dtype=bool)
        if tops.any():
            tmin, tmax = pmin[tops], pmax[tops]
            ox = np.minimum(cmax[:, None, 0], tmax[None, :, 0]) - np.maximum(cmin[:, None, 0], tmin[None, :, 0])
            oy = np.minimum(cmax[:, None, 1], tmax[None, :, 1]) - np.maximum(cmin[:, None, 1], tmin[None, :, 1])
            keep &= ((ox > 1e-9) & (oy > 1e-9)).any(axis=1)
        else:
            keep[:] = False
    return [(float(c[0]), float(c[1])) for c in centres[keep]]


def strip_candidates(model: ContainerModel, container: dict, cfg, profile, x_max_play: float,
                     z_top: float, max_candidates: int = 96, fast: bool = True) -> list[Candidate]:
    """Every legal pose of ``profile`` in the strip, most wedge volume first."""
    packed = [box for box, _s, _p in packed_aabbs_local(container)]
    gap = cfg.settled_clearance + cfg.anchor_slack
    # the commanded pose (settled + release lift) must clear every wall by
    # the inclusion clearance, so wall anchors use that, not the settled one
    wall = cfg.inclusion_clearance + cfg.anchor_slack
    # the chamfer is inclined: a clearance c from its plane needs a
    # horizontal offset c / |n_x| from the x limit, not c
    chamfer_nx = max(abs(float(n[0])) for n in model.plane_normals
                     if abs(float(n[0])) > 1e-6 and abs(float(n[2])) > 1e-6)
    wall_x = wall / chamfer_nx
    supports = [(model.z_floor, True, None)] + [(float(b.maximum[2]), False, b) for b in packed]
    out: list[Candidate] = []
    seen = set()
    for o in profile.orientations:
        dx, dy, dz = o.dx, o.dy, o.dz
        for bottom, on_floor, base in supports:
            if bottom + dz > z_top - wall:
                continue
            x_left = model.x_limit_at_height(bottom) + dx / 2.0 + wall_x
            xs = {x_left, x_max_play - dx / 2.0}
            ys = {model.y_back - dy / 2.0 - wall, model.y_opening + dy / 2.0 + wall}
            if base is not None:
                # the step of a staircase: overhang the support's left edge
                # by a fraction of the box's own width, as far as the
                # chamfer allows -- the mechanism that recovers the wedge
                for frac in (0.1, 0.2, 0.3, 0.4, 0.5):
                    xs.add(max(x_left, float(base.minimum[0]) - frac * dx + dx / 2.0))
            for b in packed:
                xs.update((float(b.maximum[0]) + dx / 2.0 + gap, float(b.minimum[0]) - dx / 2.0 - gap,
                           float(b.minimum[0]) + dx / 2.0, float(b.maximum[0]) - dx / 2.0))
                ys.update((float(b.maximum[1]) + dy / 2.0 + gap, float(b.minimum[1]) - dy / 2.0 - gap,
                           float(b.minimum[1]) + dy / 2.0, float(b.maximum[1]) - dy / 2.0))
            xs = {x for x in xs if x - dx / 2.0 >= model.x_wall_min and x + dx / 2.0 <= x_max_play + 1e-9}
            ys = {y for y in ys if y - dy / 2.0 >= model.y_opening and y + dy / 2.0 <= model.y_back}
            if fast:
                pairs = prefilter(model, cfg, container, dx, dy, dz, bottom, xs, ys, on_floor)
            else:
                pairs = [(x, y) for x in sorted(xs) for y in sorted(ys)]
            for x, y in pairs:
                key = (o.index, round(x, 3), round(y, 3), round(bottom, 3))
                if key in seen:
                    continue
                seen.add(key)
                box = AABB((x, y, bottom + dz / 2.0), (dx, dy, dz), "wedge")
                ok, _why = layer1.validate(box, model, container, cfg)
                if not ok:
                    continue
                st = stability.evaluate(box, container, cfg)
                out.append(Candidate(
                    box=box, orientation=int(o.index), dims=(dx, dy, dz), bottom=bottom,
                    on_floor=on_floor, gain=strip_gain_of(model, box),
                    support_ratio=min(1.0, st.contact_area / max(dx * dy, 1e-9)),
                    margin=float(st.margin) if np.isfinite(st.margin) else 0.0,
                ))
    # deterministic order: most wedge volume first, then back-most (a box
    # at the front seals the column behind it), then lowest, then left
    out.sort(key=lambda c: (-round(c.gain, 6), -round(float(c.box.center[1]), 3),
                            round(c.bottom, 3), round(float(c.box.center[0]), 3)))
    return out[:max_candidates]


def wedge_reach(model: ContainerModel, box: AABB) -> float:
    """How far the box reaches into the wedge, in units of the chamfer's run (0.415 m)."""
    return (model.x_floor_min - float(box.minimum[0])) / 0.415


class WedgeEnv:
    region = "wedge"
    def __init__(self, layout: str = "c1", n_items: int = 14, config=None,
                 x_extent: float = 0.80, sku_weights=None, max_candidates: int = 96,
                 seed: int = 0):
        # x_extent: floor to the right of the floor line that the episode may
        # use for bases.  The largest item is 0.75 m long, and a base has to
        # lie flat at the line for a step to overhang the wedge, so anything
        # narrower than that forces standing poses (measured: 0.45 left only
        # 0.25 x 0.65 x 0.45 standing poses, which closed the strip in two).
        from bench.arms import make_arm

        self.config = config or make_arm("ladder-stable").config
        self.layout = layout
        self.n_items = n_items
        self.x_extent = x_extent
        self.max_candidates = max_candidates
        self.sku_weights = list(sku_weights) if sku_weights else [s[7] for s in SKUS]
        self.rng = random.Random(seed)
        scene = make_scene(1, layout, "C")
        self.template = scene.rule_alpha_containers()[0]
        self.model = ContainerModel(self.template, self.config)
        self.x_max_play, self.z_top = play_region(self.model, x_extent)
        self.nx, self.ny = grid_shape(self.model, self.x_max_play)
        self.container = None
        self.stream = []
        self.cursor = 0
        self.placed = []
        self._cands: list[Candidate] | None = None

    # ------------------------------------------------------------------
    def reset(self, seed: int | None = None):
        if seed is not None:
            self.rng = random.Random(seed)
        self.container = dict(self.template)
        self.container["packed_items"] = []
        self.stream = []
        for index in range(self.n_items):
            sku = self.rng.choices(SKUS, weights=self.sku_weights, k=1)[0]
            _n, length, width, height, mass, soft, _phys, _w = sku
            self.stream.append({"index": index, "length": length, "width": width, "height": height,
                                "mass": mass, "is_soft": soft, "is_prioritized": False, "sku": _n})
        self.cursor = 0
        self.placed = []
        self._cands = None
        return self.observation()

    @property
    def done(self) -> bool:
        return self.cursor >= len(self.stream)

    @property
    def item(self) -> dict | None:
        return None if self.done else self.stream[self.cursor]

    # ------------------------------------------------------------------
    def heightmap(self) -> np.ndarray:
        return strip_heightmap(self.model, self.container, self.nx, self.ny)

    def observation(self) -> dict:
        return strip_observation(self.model, self.container, self.nx, self.ny, self.z_top, self.item,
                                 (len(self.stream) - self.cursor) / max(len(self.stream), 1))

    # ------------------------------------------------------------------
    def strip_gain(self, box: AABB) -> float:
        return strip_gain_of(self.model, box)

    def reach_of(self, box: AABB) -> float:
        return wedge_reach(self.model, box)

    def candidates(self) -> list[Candidate]:
        if self._cands is not None:
            return self._cands
        item = self.item
        if item is None:
            self._cands = []
            return self._cands
        profile = cls.classify_item(int(item["index"]), item, self.config)
        self._cands = strip_candidates(self.model, self.container, self.config, profile,
                                       self.x_max_play, self.z_top, self.max_candidates)
        return self._cands

    # ------------------------------------------------------------------
    def step(self, action: int):
        item = self.item
        cands = self.candidates()
        reward = 0.0
        info = {"passed": action == PASS or not cands}
        if action != PASS and cands:
            c = cands[action]
            self.container["packed_items"].append({
                "index": int(item["index"]), "length": item["length"], "width": item["width"],
                "height": item["height"], "mass": item["mass"], "is_soft": bool(item["is_soft"]),
                "is_prioritized": False, "orientation": c.orientation, "dims": tuple(c.dims),
                "pos": tuple(float(v) for v in c.box.center), "layer": 1,
            })
            self.placed.append(c)
            reward = c.gain
        self.cursor += 1
        self._cands = None
        return self.observation(), reward, self.done, info

    def gain_total(self) -> float:
        return sum(c.gain for c in self.placed)

    strip_volume = gain_total

    def placed_volume(self) -> float:
        return sum(float(np.prod(c.dims)) for c in self.placed)
