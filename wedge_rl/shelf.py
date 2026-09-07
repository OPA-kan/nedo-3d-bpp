"""The main shelf as a region environment.

Same shape as the chamfer strip: the container is empty except what this
episode has put on the shelf, items arrive one at a time from the official
seven types, an action is one of the generated candidate poses on the shelf
(on the shelf plate or on the top of something already up there) or PASS,
and the reward is the volume the placement adds to the shelf.  Validity is
rule-alpha's analytic ``validate``: inclusion, the transport sweep from the
opening past the shelf edge, static stability, ceiling clearance.

What the policy has to learn here is different from the wedge: there is no
geometric trick to discover, the shelf is a flat 0.7 m deep tray with 0.7 m
of headroom.  The question is which items to accept and where, so that the
tray ends full instead of blocked by a badly placed early box.
"""

from __future__ import annotations

import random

import numpy as np

from bench.scenes import SKUS, make_scene
from rule_alpha import classify as cls
from rule_alpha import layer1, stability
from rule_alpha._reuse import AABB, packed_aabbs_local
from rule_alpha.geometry import ContainerModel

from .env import CELL, PASS, Candidate


def shelf_candidates(model: ContainerModel, container: dict, cfg, profile, max_candidates: int = 96):
    shelf = model.main_shelf
    if shelf is None:
        return []
    rect = layer1.usable_shelf_rect(shelf, model, cfg)
    top = float(shelf.maximum[2])
    gap = cfg.settled_clearance + cfg.anchor_slack
    slack = cfg.anchor_slack
    z_top = model.z_ceiling
    wall = cfg.inclusion_clearance + slack
    on_shelf = [b for b, _s, _p in packed_aabbs_local(container) if float(b.minimum[2]) >= top - 0.03]
    supports = [(top, True, None)] + [(float(b.maximum[2]), False, b) for b in on_shelf]
    out = []
    seen = set()
    for o in profile.orientations:
        dx, dy, dz = o.dx, o.dy, o.dz
        if dx > rect.x_max - rect.x_min or dy > rect.y_max - rect.y_min:
            continue
        for bottom, on_base, base in supports:
            if bottom + dz > z_top - wall:
                continue
            xs = {rect.x_min + dx / 2.0 + slack, rect.x_max - dx / 2.0 - slack}
            ys = {rect.y_max - dy / 2.0 - slack, rect.y_min + dy / 2.0 + slack}
            for b in on_shelf:
                xs.update((float(b.maximum[0]) + dx / 2.0 + gap, float(b.minimum[0]) - dx / 2.0 - gap,
                           float(b.minimum[0]) + dx / 2.0, float(b.maximum[0]) - dx / 2.0))
                ys.update((float(b.maximum[1]) + dy / 2.0 + gap, float(b.minimum[1]) - dy / 2.0 - gap,
                           float(b.minimum[1]) + dy / 2.0, float(b.maximum[1]) - dy / 2.0))
            for x in xs:
                if x - dx / 2.0 < rect.x_min - 1e-9 or x + dx / 2.0 > rect.x_max + 1e-9:
                    continue
                for y in ys:
                    if y - dy / 2.0 < rect.y_min - 1e-9 or y + dy / 2.0 > rect.y_max + 1e-9:
                        continue
                    key = (o.index, round(x, 3), round(y, 3), round(bottom, 3))
                    if key in seen:
                        continue
                    seen.add(key)
                    box = AABB((x, y, bottom + dz / 2.0), (dx, dy, dz), "shelf")
                    ok, _why = layer1.validate(box, model, container, cfg)
                    if not ok:
                        continue
                    st = stability.evaluate(box, container, cfg)
                    out.append(Candidate(
                        box=box, orientation=int(o.index), dims=(dx, dy, dz), bottom=bottom,
                        on_floor=on_base, gain=dx * dy * dz,
                        support_ratio=min(1.0, st.contact_area / max(dx * dy, 1e-9)),
                        margin=float(st.margin) if np.isfinite(st.margin) else 0.0,
                    ))
    # lowest first, then back-most, then left: the order a shelf is packed by hand
    out.sort(key=lambda c: (round(c.bottom, 3), -round(float(c.box.center[1]), 3),
                            round(float(c.box.center[0]), 3), -round(c.gain, 6)))
    return out[:max_candidates]


class ShelfEnv:
    region = "shelf"

    def __init__(self, layout: str = "c1s", n_items: int = 14, config=None, sku_weights=None,
                 max_candidates: int = 96, seed: int = 0):
        from bench.arms import make_arm

        self.config = config or make_arm("ladder-stable").config
        self.layout = layout
        self.n_items = n_items
        self.max_candidates = max_candidates
        self.sku_weights = list(sku_weights) if sku_weights else [s[7] for s in SKUS]
        self.rng = random.Random(seed)
        scene = make_scene(1, layout, "C")
        self.template = scene.rule_alpha_containers()[0]
        self.model = ContainerModel(self.template, self.config)
        if self.model.main_shelf is None:
            raise ValueError(f"layout {layout!r} has no main shelf")
        self.rect = layer1.usable_shelf_rect(self.model.main_shelf, self.model, self.config)
        self.shelf_top = float(self.model.main_shelf.maximum[2])
        self.z_top = self.model.z_ceiling
        self.x_max_play = self.rect.x_max
        self.nx = int(np.ceil((self.rect.x_max - self.rect.x_min) / CELL))
        self.ny = int(np.ceil((self.rect.y_max - self.rect.y_min) / CELL))
        self.container = None
        self.stream = []
        self.cursor = 0
        self.placed = []
        self._cands = None

    # the strip's feature code reads these three through the env
    def reach_of(self, box: AABB) -> float:
        """How deep the box sits from the shelf's open edge, 0 at the edge, 1 at the back."""
        depth = max(self.rect.y_max - self.rect.y_min, 1e-9)
        return (float(box.minimum[1]) - self.rect.y_min) / depth

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
    def item(self):
        return None if self.done else self.stream[self.cursor]

    def heightmap(self) -> np.ndarray:
        h = np.zeros((self.nx, self.ny), dtype=np.float32)
        xs = self.rect.x_min + (np.arange(self.nx) + 0.5) * CELL
        ys = self.rect.y_min + (np.arange(self.ny) + 0.5) * CELL
        for box, _s, _p in packed_aabbs_local(self.container):
            if float(box.minimum[2]) < self.shelf_top - 0.03:
                continue
            ix = (xs >= box.minimum[0]) & (xs <= box.maximum[0])
            iy = (ys >= box.minimum[1]) & (ys <= box.maximum[1])
            top = float(box.maximum[2]) - self.shelf_top
            h[np.ix_(ix, iy)] = np.maximum(h[np.ix_(ix, iy)], top)
        return h

    def observation(self) -> dict:
        item = self.item
        headroom = max(self.z_top - self.shelf_top, 1e-9)
        # the profile along x: how much of each column's headroom is still
        # free at the shelf's open edge (the delivery side); 1 = fully open
        h = self.heightmap()
        front = h[:, 0] if self.ny else np.zeros(self.nx, dtype=np.float32)
        return {
            "heightmap": h / headroom,
            "profile": (1.0 - front / headroom).astype(np.float32),
            "item": np.asarray([item["length"], item["width"], item["height"], item["mass"] / 20.0,
                                1.0 if item["is_soft"] else 0.0] if item else [0, 0, 0, 0, 0], dtype=np.float32),
            "remaining": (len(self.stream) - self.cursor) / max(len(self.stream), 1),
        }

    def candidates(self):
        if self._cands is not None:
            return self._cands
        item = self.item
        if item is None:
            self._cands = []
            return self._cands
        profile = cls.classify_item(int(item["index"]), item, self.config)
        self._cands = shelf_candidates(self.model, self.container, self.config, profile, self.max_candidates)
        return self._cands

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

    def placed_volume(self) -> float:
        return sum(float(np.prod(c.dims)) for c in self.placed)
