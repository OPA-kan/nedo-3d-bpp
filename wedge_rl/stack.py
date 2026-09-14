"""Stacking as a region: what goes on top once the ladder has stopped.

rule-alpha's Layer 1 declines at about half the stream (24 % fill on the
core suite): it has no rule for building on the tops it made.  This region
starts from exactly that state.  A board is the container the stable
ladder leaves when it declines on a seeded stream, plus the items it never
placed, in their order.  The executor takes those items one at a time and
may put each on the floor gaps or on any top (or pass), with the same
analytic validator and stability rule as the other regions.  Reward is the
volume placed; every placement is volume the ladder would have left on
the apron.

Boards are built once per (layout, seed) and cached as JSON, because the
ladder's episode takes ten to twenty seconds and training reuses seeds.
"""

from __future__ import annotations

import json
import pathlib
import random

import numpy as np

from bench.scenes import make_scene
from rule_alpha import classify as cls
from rule_alpha import layer1, stability
from rule_alpha._reuse import AABB, packed_aabbs_local
from rule_alpha.geometry import ContainerModel

from .env import CELL, PASS, Candidate, chamfer_height_at, prefilter

BOARDS_DIR = pathlib.Path("reports/wedge/boards")


def build_board(layout: str, seed: int, config=None, task: str = "C") -> dict:
    """Run the stable ladder analytically on the seeded stream until it
    declines; return the container it leaves and the items still to come."""
    from bench.arms import make_arm

    arm = make_arm("ladder-stable")
    config = config or arm.config
    scene = make_scene(seed, layout, task)
    containers = scene.rule_alpha_containers()
    agent = arm(scene)
    agent.get_init_states({"optimize": scene.optimize, "lookahead_k": scene.look_ahead,
                           "container_list": containers})
    board = layer1.Board(containers, config)
    items = [dict(i) for i in scene.items]
    queue = list(items)
    pool = [queue.pop(0)] if queue else []
    placed = 0
    while pool:
        observation = {"optimize": scene.optimize, "lookahead_k": scene.look_ahead,
                       "container_list": board.containers, "pool_list": [dict(i) for i in pool]}
        action = agent.policy(observation)
        if action is None:
            break
        placement = agent.last_decision.placement
        pool.pop(int(action["item_idx"]))
        placement.step = placed + 1
        board.apply(placement)
        placed += 1
        if queue:
            pool.append(queue.pop(0))
    remaining = list(pool) + list(queue)
    container = dict(board.containers[0])
    container["packed_items"] = [dict(p) for p in container.get("packed_items", [])]
    return {"layout": layout, "seed": seed, "task": task, "placed": placed,
            "container": _jsonable(container), "remaining": remaining}


def _jsonable(container: dict) -> dict:
    out = {}
    for k, v in container.items():
        if k == "packed_items":
            out[k] = [{kk: (list(vv) if isinstance(vv, tuple) else vv) for kk, vv in p.items()} for p in v]
        elif isinstance(v, tuple):
            out[k] = list(v)
        elif hasattr(v, "tolist"):
            out[k] = v.tolist()
        else:
            out[k] = v
    return out


def board_path(boards_dir, layout: str, seed: int) -> pathlib.Path:
    return pathlib.Path(boards_dir) / layout / f"s{seed}.json"


def load_board(boards_dir, layout: str, seed: int, build: bool = True) -> dict:
    path = board_path(boards_dir, layout, seed)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if not build:
        raise FileNotFoundError(path)
    board = build_board(layout, seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(board), encoding="utf-8")
    return board


def build_boards(layout: str, seeds, boards_dir=BOARDS_DIR, workers: int = 1, log=print) -> list[dict]:
    seeds = [s for s in seeds if not board_path(boards_dir, layout, s).exists()]
    if workers <= 1:
        out = []
        for s in seeds:
            b = load_board(boards_dir, layout, s)
            out.append(b)
            if log:
                log(f"[board {layout} s{s}] ladder placed {b['placed']}, {len(b['remaining'])} remaining")
        return out
    import multiprocessing as mp

    with mp.get_context("spawn").Pool(workers) as pool:
        out = []
        for b in pool.imap_unordered(_build_one, [(layout, s, str(boards_dir)) for s in seeds]):
            out.append(b)
            if log:
                log(f"[board {layout} s{b['seed']}] ladder placed {b['placed']}, {len(b['remaining'])} remaining")
    return out


def _build_one(args):
    layout, seed, boards_dir = args
    return load_board(boards_dir, layout, seed)


# ---------------------------------------------------------------------------
# Two things the ladder-stable validator does not see, measured on 475
# stacked placements replayed in PyBullet (33 rejections):
#
# * A box put on a *stacked* box also loads that box.  The validator checks
#   the new box against its own support polygon; it never asks whether the
#   box underneath, now carrying the new one off-centre, still has its
#   combined centre of mass over *its* support.  Twenty of the 33 failures
#   were exactly that: the support was a stacked box every time, the pair
#   tipped 45-90 degrees at settle.  ``Tower`` walks the chain of supports
#   down to the floor and reports the smallest combined margin.
# * Boxes drift 1.5-3 cm after they are accepted (and much more when a
#   stack tips without failing the 0.3 m threshold), and the analytic
#   transport clearance (0.026 m) leaves only 1.1 cm over the simulator's
#   0.015 m.  The other 13 failures were sweeps that clipped a drifted box.
#   ``transport_gap`` is the smallest gap between the sweep and any packed
#   box, so the region can ask for more than the validator's clearance.
# ---------------------------------------------------------------------------
class Tower:
    """Who rests on whom in the container, and how far each box's combined
    load sits inside its own support polygon."""

    def __init__(self, container: dict, cfg):
        self.cfg = cfg
        self.container = container
        items = container.get("packed_items", [])
        self.bodies = []  # (box, mass, structural)
        for packed, (box, soft, prio) in zip(items, packed_aabbs_local(container)):
            self.bodies.append((box, float(packed.get("mass", 0.0)), not (soft or prio)))
        n = len(self.bodies)
        self.supports = [self.rests_on(b) for b, _m, _s in self.bodies]
        self.loads = [[] for _ in range(n)]
        for k, sup in enumerate(self.supports):
            for s in sup:
                self.loads[s].append(k)
        self._polygon = {}

    def rests_on(self, box: AABB) -> list[int]:
        """Indices of the structural bodies whose top carries ``box``."""
        tol = self.cfg.contact_tolerance
        bottom = float(box.minimum[2])
        out = []
        for k, (b, _m, structural) in enumerate(self.bodies):
            if not structural or abs(bottom - float(b.maximum[2])) > tol:
                continue
            if min(box.maximum[0], b.maximum[0]) - max(box.minimum[0], b.minimum[0]) <= 1e-9:
                continue
            if min(box.maximum[1], b.maximum[1]) - max(box.minimum[1], b.minimum[1]) <= 1e-9:
                continue
            out.append(k)
        return out

    def polygon(self, k: int):
        if k not in self._polygon:
            self._polygon[k] = stability.evaluate(self.bodies[k][0], self.container, self.cfg).polygon
        return self._polygon[k]

    def margin(self, box: AABB, mass: float) -> float:
        """Smallest combined centre-of-mass margin over every box the
        candidate loads, directly or through others; +inf on the floor.
        A body on several supports counts fully on each (conservative)."""
        direct = self.rests_on(box)
        if not direct:
            return float("inf")
        ancestors, frontier = [], list(direct)
        while frontier:
            k = frontier.pop()
            if k in ancestors:
                continue
            ancestors.append(k)
            frontier.extend(self.supports[k])
        worst = float("inf")
        for k in ancestors:
            carried, todo = set(), [k]
            while todo:
                j = todo.pop()
                if j in carried:
                    continue
                carried.add(j)
                todo.extend(self.loads[j])
            total = mass
            cx = mass * float(box.center[0])
            cy = mass * float(box.center[1])
            for j in carried:
                b, m, _s = self.bodies[j]
                total += m
                cx += m * float(b.center[0])
                cy += m * float(b.center[1])
            if total <= 1e-9:
                continue
            worst = min(worst, stability.point_margin(self.polygon(k), (cx / total, cy / total)))
        return worst


def transport_gap(box: AABB, container: dict) -> float:
    """Smallest gap between the transport sweep of ``box`` and any packed box
    (the simulator fails the sweep under 0.015 m; the validator asks 0.026)."""
    packed = [b for b, _s, _p in packed_aabbs_local(container)]
    if not packed:
        return float("inf")
    mins = np.asarray([b.minimum for b in packed], dtype=np.float64)
    maxs = np.asarray([b.maximum for b in packed], dtype=np.float64)
    best = float("inf")
    for sample in layer1.transport_samples(box, container):
        gaps = np.maximum(0.0, np.maximum(mins - np.asarray(sample.maximum), np.asarray(sample.minimum) - maxs))
        best = min(best, float(np.sqrt((gaps * gaps).sum(axis=1).min())))
    return best


def covers_priority(box: AABB, container: dict) -> bool:
    """True when the box would sit above a prioritized item (which has to
    stay reachable), whether or not it rests on it."""
    # the flag is read from the item itself: the AABB cache keys on the
    # container and would not see a flag changed in place
    for packed, (b, _soft, _prio) in zip(container.get("packed_items", []), packed_aabbs_local(container)):
        if not bool(packed.get("is_prioritized", False)) or float(b.maximum[2]) > float(box.minimum[2]) + 1e-6:
            continue
        if (min(box.maximum[0], b.maximum[0]) - max(box.minimum[0], b.minimum[0]) > 1e-9
                and min(box.maximum[1], b.maximum[1]) - max(box.minimum[1], b.minimum[1]) > 1e-9):
            return True
    return False


def sample_future(rng, n: int, start_index: int = 100000) -> list[dict]:
    """An imagined continuation of the stream: ``n`` items drawn from the
    official SKU mix (no priority cargo; the option does not place it)."""
    from bench.scenes import SKUS

    weights = [s[7] for s in SKUS]
    out = []
    for k in range(n):
        name, length, width, height, mass, soft, physics, _w = SKUS[int(rng.choice(len(SKUS), p=np.asarray(weights) / sum(weights)))]
        out.append({"index": start_index + k, "sku": name, "length": length, "width": width, "height": height,
                    "mass": mass, "is_prioritized": False, "is_soft": soft, **physics})
    return out


def stack_candidates(model: ContainerModel, container: dict, cfg, profile, max_candidates: int = 96,
                     fast: bool = True, mass: float = 0.0, tower_min: float | None = None,
                     extra_clearance: float = 0.0) -> list[Candidate]:
    """Every legal pose on the floor or on a packed top, lowest first.

    ``tower_min``: smallest combined centre-of-mass margin (``Tower``) a
    pose may leave on the boxes it loads; ``extra_clearance``: how much
    further than the validator's clearance the anchors step away from
    neighbours and the transport sweep must stay from packed boxes."""
    packed = [b for b, _s, _p in packed_aabbs_local(container)]
    gap = cfg.settled_clearance + cfg.anchor_slack + extra_clearance
    tower = Tower(container, cfg) if tower_min is not None else None
    min_gap = cfg.settled_clearance + extra_clearance if extra_clearance > 0 else None
    slack = cfg.anchor_slack
    wall = cfg.inclusion_clearance + slack
    rect = model.floor_rect
    z_top = model.z_ceiling
    # one support per distinct top height (tops within the contact tolerance
    # are the same level); the floor is its own support
    tops = {}
    for b in packed:
        z = round(float(b.maximum[2]), 3)
        tops.setdefault(z, []).append(b)
    supports = [(model.z_floor, True, [])] + [(z, False, bs) for z, bs in sorted(tops.items())]
    out: list[Candidate] = []
    seen = set()
    for o in profile.orientations:
        dx, dy, dz = o.dx, o.dy, o.dz
        for bottom, on_floor, bases in supports:
            if bottom + dz > z_top - wall:
                continue
            # under the main shelf nothing may rise above it; the prefilter
            # and validator reject penetration, so anchors need no special case
            x_left = model.x_limit_at_height(bottom) + dx / 2.0 + wall
            xs = {x_left, rect.x_max - dx / 2.0 - slack}
            ys = {rect.y_max - dy / 2.0 - slack, rect.y_min + dy / 2.0 + slack}
            for b in bases:
                # flush with the support's edges and stepped in by the gap
                xs.update((float(b.minimum[0]) + dx / 2.0, float(b.maximum[0]) - dx / 2.0))
                ys.update((float(b.minimum[1]) + dy / 2.0, float(b.maximum[1]) - dy / 2.0))
            for b in packed:
                xs.update((float(b.maximum[0]) + dx / 2.0 + gap, float(b.minimum[0]) - dx / 2.0 - gap))
                ys.update((float(b.maximum[1]) + dy / 2.0 + gap, float(b.minimum[1]) - dy / 2.0 - gap))
            xs = {x for x in xs if x - dx / 2.0 >= model.x_wall_min and x + dx / 2.0 <= rect.x_max + 1e-9}
            ys = {y for y in ys if y - dy / 2.0 >= rect.y_min - 1e-9 and y + dy / 2.0 <= rect.y_max + 1e-9}
            if fast:
                pairs = prefilter(model, cfg, container, dx, dy, dz, bottom, xs, ys, on_floor)
            else:
                pairs = [(x, y) for x in sorted(xs) for y in sorted(ys)]
            for x, y in pairs:
                key = (o.index, round(x, 3), round(y, 3), round(bottom, 3))
                if key in seen:
                    continue
                seen.add(key)
                box = AABB((x, y, bottom + dz / 2.0), (dx, dy, dz), "stack")
                ok, _why = layer1.validate(box, model, container, cfg)
                if not ok:
                    continue
                if covers_priority(box, container):
                    continue
                tw = tower.margin(box, mass) if tower is not None else float("inf")
                if tw < (tower_min if tower_min is not None else -float("inf")):
                    continue
                if min_gap is not None and not on_floor and transport_gap(box, container) < min_gap - 1e-9:
                    continue
                st = stability.evaluate(box, container, cfg)
                c = Candidate(
                    box=box, orientation=int(o.index), dims=(dx, dy, dz), bottom=bottom,
                    on_floor=on_floor, gain=dx * dy * dz,
                    support_ratio=min(1.0, st.contact_area / max(dx * dy, 1e-9)),
                    margin=float(st.margin) if np.isfinite(st.margin) else 0.0,
                )
                c.tower_margin = tw
                out.append(c)
    out.sort(key=lambda c: (round(c.bottom, 3), -round(float(c.box.center[1]), 3),
                            round(float(c.box.center[0]), 3), -round(c.gain, 6)))
    # the floor alone can fill the cap; keep a share of every support level
    # so the tops (the point of this region) are always on offer
    per_level = max(8, max_candidates // max(1, len({round(c.bottom, 3) for c in out})))
    kept, counts = [], {}
    for c in out:
        level = round(c.bottom, 3)
        if counts.get(level, 0) < per_level:
            kept.append(c)
            counts[level] = counts.get(level, 0) + 1
    return kept[:max_candidates]


# ---------------------------------------------------------------------------
# The stack as functions of (model, container), shared by the training
# environment and the option that runs inside rule-alpha.
# ---------------------------------------------------------------------------
def stack_grid_shape(model: ContainerModel) -> tuple[int, int]:
    return (int(np.ceil((model.x_wall_max - model.x_wall_min) / CELL)),
            int(np.ceil((model.y_back - model.y_opening) / CELL)))


def stack_profile(model: ContainerModel, nx: int) -> np.ndarray:
    """Chamfer height per column, as a fraction of the container height."""
    return np.asarray([chamfer_height_at(model, model.x_wall_min + (i + 0.5) * CELL) for i in range(nx)],
                      dtype=np.float32) / max(model.z_ceiling - model.z_floor, 1e-9)


def stack_reach(model: ContainerModel, box: AABB) -> float:
    return (float(box.minimum[1]) - model.y_opening) / max(model.y_back - model.y_opening, 1e-9)


def stack_heightmap(model: ContainerModel, container: dict, nx: int, ny: int) -> np.ndarray:
    h = np.zeros((nx, ny), dtype=np.float32)
    xs = model.x_wall_min + (np.arange(nx) + 0.5) * CELL
    ys = model.y_opening + (np.arange(ny) + 0.5) * CELL
    for box, _s, _p in packed_aabbs_local(container):
        ix = (xs >= box.minimum[0]) & (xs <= box.maximum[0])
        iy = (ys >= box.minimum[1]) & (ys <= box.maximum[1])
        h[np.ix_(ix, iy)] = np.maximum(h[np.ix_(ix, iy)], float(box.maximum[2]) - model.z_floor)
    return h


def stack_observation(model: ContainerModel, container: dict, nx: int, ny: int, profile: np.ndarray,
                      item: dict | None, remaining: float) -> dict:
    return {
        "heightmap": stack_heightmap(model, container, nx, ny) / max(model.z_ceiling - model.z_floor, 1e-9),
        "profile": profile,
        "item": np.asarray([item["length"], item["width"], item["height"], item["mass"] / 20.0,
                            1.0 if item["is_soft"] else 0.0] if item else [0, 0, 0, 0, 0], dtype=np.float32),
        "remaining": float(remaining),
    }


class StackEnv:
    region = "stack"

    # measured on 475 stacked placements: a combined margin of 0.04 m
    # removes every settle failure and keeps 73 % of the accepted poses;
    # 0.014 m more clearance is the drift the accepted boxes showed
    TOWER_MIN = 0.04
    EXTRA_CLEARANCE = 0.014

    def __init__(self, layout: str = "c1", n_items: int = 27, config=None, boards_dir=BOARDS_DIR,
                 max_candidates: int = 96, seed: int = 0, build_boards: bool = True,
                 tower_min: float | None = TOWER_MIN, extra_clearance: float = EXTRA_CLEARANCE):
        from bench.arms import make_arm

        self.config = config or make_arm("ladder-stable").config
        self.tower_min = tower_min
        self.extra_clearance = extra_clearance
        self.layout = layout
        self.n_items = n_items
        self.boards_dir = pathlib.Path(boards_dir)
        self.build = build_boards
        self.max_candidates = max_candidates
        scene = make_scene(1, layout, "C")
        self.template = scene.rule_alpha_containers()[0]
        self.model = ContainerModel(self.template, self.config)
        m = self.model
        self.x_max_play = m.x_wall_max
        self.z_top = m.z_ceiling
        self.nx, self.ny = stack_grid_shape(m)
        self.container = None
        self.board = None
        self.stream = []
        self.cursor = 0
        self.placed = []
        self._cands = None
        self._profile = stack_profile(m, self.nx)

    @classmethod
    def from_container(cls, container: dict, model: ContainerModel, config, **kw) -> "StackEnv":
        """A scratch environment over a live container (the option's
        look-ahead rolls imagined streams out on it); no boards involved."""
        env = cls.__new__(cls)
        env.config = config
        env.layout = ""
        env.n_items = 0
        env.boards_dir = pathlib.Path(kw.get("boards_dir", BOARDS_DIR))
        env.build = False
        env.max_candidates = kw.get("max_candidates", 96)
        env.tower_min = kw.get("tower_min", cls.TOWER_MIN)
        env.extra_clearance = kw.get("extra_clearance", cls.EXTRA_CLEARANCE)
        env.template = dict(container)
        env.template["packed_items"] = []
        env.model = model
        env.x_max_play = model.x_wall_max
        env.z_top = model.z_ceiling
        env.nx, env.ny = stack_grid_shape(model)
        env.container = dict(container)
        env.container["packed_items"] = [dict(p) for p in container.get("packed_items", [])]
        env.board = None
        env.stream = []
        env.cursor = 0
        env.placed = []
        env._cands = None
        env._profile = stack_profile(model, env.nx)
        return env

    def reach_of(self, box: AABB) -> float:
        return stack_reach(self.model, box)

    # training draws seeds from 1_000_000 upwards without bound; those map
    # onto a fixed pool of boards so the ladder's episode is not re-run for
    # every fresh seed.  Held-out and evaluation seeds (below the pool base)
    # are built and cached individually.
    POOL_BASE = 1_000_000
    POOL_SIZE = 256

    def reset(self, seed: int | None = None):
        seed = 0 if seed is None else int(seed)
        if seed >= self.POOL_BASE:
            seed = self.POOL_BASE + (seed - self.POOL_BASE) % self.POOL_SIZE
        self.board = load_board(self.boards_dir, self.layout, seed, build=self.build)
        self.container = dict(self.template)
        self.container["packed_items"] = [dict(p) for p in self.board["container"]["packed_items"]]
        self.stream = [dict(i) for i in self.board["remaining"][: self.n_items]]
        for i in self.stream:
            i.setdefault("sku", "")
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
        return stack_heightmap(self.model, self.container, self.nx, self.ny)

    def observation(self) -> dict:
        return stack_observation(self.model, self.container, self.nx, self.ny, self._profile, self.item,
                                 (len(self.stream) - self.cursor) / max(len(self.stream), 1))

    def candidates(self):
        if self._cands is not None:
            return self._cands
        item = self.item
        if item is None:
            self._cands = []
            return self._cands
        profile = cls.classify_item(int(item["index"]), item, self.config)
        self._cands = stack_candidates(self.model, self.container, self.config, profile, self.max_candidates,
                                       mass=float(item["mass"]), tower_min=self.tower_min,
                                       extra_clearance=self.extra_clearance)
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
                "is_prioritized": bool(item.get("is_prioritized", False)), "orientation": c.orientation,
                "dims": tuple(c.dims), "pos": tuple(float(v) for v in c.box.center), "layer": 2,
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
