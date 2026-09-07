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
    box: AABB
    orientation: int
    dims: tuple
    bottom: float
    on_floor: bool
    strip_gain: float
    support_ratio: float
    margin: float

    def features(self, env: "WedgeEnv") -> np.ndarray:
        m = env.model
        return np.asarray([
            (float(self.box.center[0]) - m.x_wall_min) / max(env.x_max_play - m.x_wall_min, 1e-9),
            (float(self.box.center[1]) - m.y_opening) / max(m.y_back - m.y_opening, 1e-9),
            (self.bottom - m.z_floor) / max(env.z_top - m.z_floor, 1e-9),
            self.dims[0], self.dims[1], self.dims[2],
            self.strip_gain / 0.2,
            self.support_ratio, min(self.margin, 0.3) / 0.3,
            1.0 if self.on_floor else 0.0,
            float(self.box.maximum[2] - m.z_floor) / max(env.z_top - m.z_floor, 1e-9),
            (m.x_floor_min - float(self.box.minimum[0])) / 0.415,   # how far it reaches into the wedge
        ], dtype=np.float32)


FEATURE_SIZE = 12


class WedgeEnv:
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
        m = self.model
        self.x_max_play = m.x_floor_min + x_extent
        self.z_top = float(m.small_shelf.minimum[2]) if m.small_shelf is not None else m.z_ceiling
        self.nx = int(np.ceil((self.x_max_play - m.x_wall_min) / CELL))
        self.ny = int(np.ceil((m.y_back - m.y_opening) / CELL))
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
        m = self.model
        h = np.zeros((self.nx, self.ny), dtype=np.float32)
        xs = m.x_wall_min + (np.arange(self.nx) + 0.5) * CELL
        ys = m.y_opening + (np.arange(self.ny) + 0.5) * CELL
        for box, _s, _p in packed_aabbs_local(self.container):
            ix = (xs >= box.minimum[0]) & (xs <= box.maximum[0])
            iy = (ys >= box.minimum[1]) & (ys <= box.maximum[1])
            top = float(box.maximum[2]) - m.z_floor
            h[np.ix_(ix, iy)] = np.maximum(h[np.ix_(ix, iy)], top)
        return h

    def observation(self) -> dict:
        item = self.item
        h = self.heightmap() / max(self.z_top - self.model.z_floor, 1e-9)
        chamfer = np.zeros(self.nx, dtype=np.float32)
        xs = self.model.x_wall_min + (np.arange(self.nx) + 0.5) * CELL
        # height of the chamfer surface above the floor at each x column
        for i, x in enumerate(xs):
            chamfer[i] = self._chamfer_height_at(x)
        return {
            "heightmap": h,
            "chamfer": chamfer / max(self.z_top - self.model.z_floor, 1e-9),
            "item": np.asarray([item["length"], item["width"], item["height"], item["mass"] / 20.0,
                                1.0 if item["is_soft"] else 0.0] if item else [0, 0, 0, 0, 0], dtype=np.float32),
            "remaining": (len(self.stream) - self.cursor) / max(len(self.stream), 1),
        }

    def _chamfer_height_at(self, x: float) -> float:
        """Height above the floor of the chamfer plane at column x (0 right of the floor line)."""
        m = self.model
        if x >= m.x_floor_min:
            return 0.0
        lo, hi = m.z_floor, m.z_chamfer_top
        for _ in range(30):
            mid = 0.5 * (lo + hi)
            if m.x_limit_at_height(mid) <= x:
                hi = mid
            else:
                lo = mid
        return hi - m.z_floor

    # ------------------------------------------------------------------
    def strip_gain(self, box: AABB) -> float:
        m = self.model
        left = min(float(box.maximum[0]), m.x_floor_min) - float(box.minimum[0])
        if left <= 0:
            return 0.0
        return left * float(box.size[1]) * float(box.size[2])

    def candidates(self) -> list[Candidate]:
        if self._cands is not None:
            return self._cands
        item = self.item
        if item is None:
            self._cands = []
            return self._cands
        m, cfg = self.model, self.config
        profile = cls.classify_item(int(item["index"]), item, cfg)
        packed = [box for box, _s, _p in packed_aabbs_local(self.container)]
        gap = cfg.settled_clearance + cfg.anchor_slack
        # the commanded pose (settled + release lift) must clear every wall by
        # the inclusion clearance, so wall anchors use that, not the settled one
        wall = cfg.inclusion_clearance + cfg.anchor_slack
        # the chamfer is inclined: a clearance c from its plane needs a
        # horizontal offset c / |n_x| from the x limit, not c
        chamfer_nx = max(abs(float(n[0])) for n in m.plane_normals if abs(float(n[0])) > 1e-6 and abs(float(n[2])) > 1e-6)
        wall_x = wall / chamfer_nx
        supports = [(m.z_floor, True, None)] + [(float(b.maximum[2]), False, b) for b in packed]
        out: list[Candidate] = []
        seen = set()
        for o in profile.orientations:
            dx, dy, dz = o.dx, o.dy, o.dz
            for bottom, on_floor, base in supports:
                if bottom + dz > self.z_top - wall:
                    continue
                x_left = m.x_limit_at_height(bottom) + dx / 2.0 + wall_x
                xs = {x_left, self.x_max_play - dx / 2.0}
                ys = {m.y_back - dy / 2.0 - wall, m.y_opening + dy / 2.0 + wall}
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
                for x in xs:
                    if x - dx / 2.0 < m.x_wall_min or x + dx / 2.0 > self.x_max_play + 1e-9:
                        continue
                    for y in ys:
                        if y - dy / 2.0 < m.y_opening or y + dy / 2.0 > m.y_back:
                            continue
                        key = (o.index, round(x, 3), round(y, 3), round(bottom, 3))
                        if key in seen:
                            continue
                        seen.add(key)
                        box = AABB((x, y, bottom + dz / 2.0), (dx, dy, dz), "wedge")
                        ok, _why = layer1.validate(box, m, self.container, cfg)
                        if not ok:
                            continue
                        st = stability.evaluate(box, self.container, cfg)
                        out.append(Candidate(
                            box=box, orientation=int(o.index), dims=(dx, dy, dz), bottom=bottom,
                            on_floor=on_floor, strip_gain=self.strip_gain(box),
                            support_ratio=min(1.0, st.contact_area / max(dx * dy, 1e-9)),
                            margin=float(st.margin) if np.isfinite(st.margin) else 0.0,
                        ))
        # deterministic order: most wedge volume first, then back-most (a box
        # at the front seals the column behind it), then lowest, then left
        out.sort(key=lambda c: (-round(c.strip_gain, 6), -round(float(c.box.center[1]), 3),
                                round(c.bottom, 3), round(float(c.box.center[0]), 3)))
        self._cands = out[: self.max_candidates]
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
            reward = c.strip_gain
        self.cursor += 1
        self._cands = None
        return self.observation(), reward, self.done, info

    def strip_volume(self) -> float:
        return sum(c.strip_gain for c in self.placed)

    def placed_volume(self) -> float:
        return sum(float(np.prod(c.dims)) for c in self.placed)
