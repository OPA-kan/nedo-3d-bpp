"""Seeded scenes: containers plus an item stream plus the task shape.

A scene is fully determined by its seed and layout, so two arms can be run on
exactly the same input and compared pairwise.  Item sizes and physical
parameters are drawn from the SKU table of the official ``sample_config.json``
with the frequencies observed there, because the official streams are made of
repeated SKUs rather than of uniformly random boxes.
"""

from __future__ import annotations

import json
import pathlib
import random
from dataclasses import dataclass, field

from rule_alpha.geometry import make_container_dict


# Official ULDs used by sample_config 000 (no shelf) and 001 (shelf).
ULD = dict(length=2.0, width=1.45, height=1.61, thickness=0.04, cut_x=0.44, cut_y=0.40)
ULD_SHELF = dict(length=2.0, width=1.52, height=1.62, thickness=0.05, cut_x=0.43, cut_y=0.40)
SPACING = 2.5

HARD_PHYSICS = dict(lateralFriction=0.4, rollingFriction=0.01,
                    spinningFriction=0.01, restitution=0.2)

# (length, width, height, mass, soft, physics, weight in the sample stream)
SKUS = [
    ("A", 0.55, 0.40, 0.24, 8, False, HARD_PHYSICS, 13),
    ("B", 0.65, 0.45, 0.25, 13, False, HARD_PHYSICS, 11),
    ("C", 0.75, 0.56, 0.27, 18, False, HARD_PHYSICS, 4),
    ("D", 0.50, 0.40, 0.40, 10, True, dict(
        lateralFriction=0.6, rollingFriction=0.01, spinningFriction=0.01,
        restitution=0.1, contactStiffness=3000, contactDamping=800,
        linearDamping=0.8), 2),
    ("E", 0.45, 0.30, 0.20, 5, True, dict(
        lateralFriction=0.8, rollingFriction=0.02, spinningFriction=0.02,
        restitution=0, contactStiffness=2000, contactDamping=600,
        linearDamping=0.8), 2),
    ("F", 0.65, 0.35, 0.23, 12, True, dict(
        lateralFriction=0.8, rollingFriction=0.02, spinningFriction=0.02,
        restitution=0, contactStiffness=2500, contactDamping=800,
        linearDamping=0.8), 5),
    ("G", 0.60, 0.30, 0.25, 7, True, dict(
        lateralFriction=0.8, rollingFriction=0.02, spinningFriction=0.02,
        restitution=0, contactStiffness=3000, contactDamping=800,
        linearDamping=0.8), 4),
]

SOFT_PHYSICS = dict(lateralFriction=0.7, rollingFriction=0.02, spinningFriction=0.02,
                    restitution=0, contactStiffness=2500, contactDamping=800, linearDamping=0.8)

# SKUs outside the sample's table, for the hard suites (weight 0 in the
# sample mix): a big hard box, a small hard box, a tall soft bag
EXTRA_SKUS = [
    ("H", 0.80, 0.60, 0.50, 22, False, HARD_PHYSICS, 0),
    ("I", 0.35, 0.25, 0.15, 3, False, HARD_PHYSICS, 0),
    ("J", 0.40, 0.40, 0.60, 8, True, SOFT_PHYSICS, 0),
]

PRIORITY_RATE = 4 / 41  # sample 000: 3 hard + 1 soft priority items out of 41

# layout name -> list of (shelf, prioritized) per container
LAYOUTS = {
    "c1": [(False, False)],
    "c1s": [(True, False)],
    "c2": [(True, False), (False, False)],
    "c2p": [(True, True), (False, False)],
}

TASK_LOOKAHEAD = {"A": 1, "B": 10, "C": 1}


@dataclass
class Scene:
    name: str
    seed: int
    layout: str
    task: str
    look_ahead: int
    items: list[dict]
    containers: list[dict] = field(default_factory=list)   # simulator specs
    notes: str = ""
    spacing: float = SPACING
    spec: dict = field(default_factory=dict)   # the hard suites' situation (totals, mix, order, pool)

    @property
    def optimize(self) -> bool:
        """Only Task A hands the manifest to the agent (official app flow)."""
        return self.task == "A"

    def sim_config(self, policy_timeout: float = 8.0) -> dict:
        return {
            "containers": {"spacing": self.spacing, "container_list": [dict(c) for c in self.containers]},
            "item_stream": {
                "item_list": [dict(item) for item in self.items],
                "look_ahead": int(self.look_ahead),
                # sample_config uses max_space 1: the pool is topped up after
                # every pick, which is what the competition text describes
                "max_space": 1,
                "visible_pool": [],
            },
            "camera": {
                "num_containers": len(self.containers),
                "target_pos": [0, 0, 0], "distance": 3.0,
                "yaw": 0, "pitch": 0, "roll": 0,
                "img_width": 64, "img_height": 64,
                "fov": 60, "near_val": 0.1, "far_val": 10.0,
            },
            "validator": {
                "inclusion_margin": -0.005,
                "start_z": 0.08,
                "safety_margin": 0.015,
                "ceiling_margin": 0.018,
                "displacement_threshold": 0.3,
                "angle_displacement_threshold": 45,
                "settle_wait_step": 300,
            },
            "action": {
                "keys": {"item_idx": "int", "container_idx": "int",
                         "place_pos": "float", "orientation": "int"},
                "pos_lim": {"low": -100, "high": 100},
                "orientations": [0, 1, 2, 3, 4, 5],
            },
            "agent": {
                "optimize": self.optimize,
                "init_timeout": 10.0,
                "optimization_timeout": 180.0,
                "policy_timeout": policy_timeout,
                "allowed_methods": ["get_init_states", "optimize", "policy"],
                "max_mem": 12,
            },
            "visualizer": {"vis": False, "camera": {"yaw": 0, "pitch": -20}},
        }

    def rule_alpha_containers(self) -> list[dict]:
        """Observation-shaped container dicts for the analytic model."""
        out = []
        for position, spec in enumerate(self.containers):
            out.append(make_container_dict(
                index=spec["index"], length=spec["length"], width=spec["width"],
                height=spec["height"], thickness=spec["thickness"],
                cut_x=spec["cut_x"], cut_y=spec["cut_y"], buffer=spec["buffer"],
                require_shelf=spec["require_shelf"],
                is_prioritized=spec["is_prioritized"],
                offset_x=position * self.spacing,
            ))
        return out

    def to_dict(self) -> dict:
        return {
            "name": self.name, "seed": self.seed, "layout": self.layout,
            "task": self.task, "look_ahead": self.look_ahead,
            "optimize": self.optimize, "item_count": len(self.items),
            "containers": self.containers, "items": self.items, "notes": self.notes,
            "soft_total": sum(1 for i in self.items if i.get("is_soft")),
            "priority_total": sum(1 for i in self.items if i.get("is_prioritized")),
            **self.spec,
        }


def _container_spec(index: int, shelf: bool, prioritized: bool) -> dict:
    spec = ULD_SHELF if shelf else ULD
    return {
        "index": index, **spec, "buffer": 0.0, "packed_items": [],
        "require_shelf": shelf, "is_prioritized": prioritized,
    }


def make_stream(seed: int, count: int, priority_rate: float = PRIORITY_RATE) -> list[dict]:
    rng = random.Random(seed)
    weights = [s[7] for s in SKUS]
    items = []
    for index in range(count):
        sku = rng.choices(SKUS, weights=weights, k=1)[0]
        _name, length, width, height, mass, soft, physics, _w = sku
        priority = rng.random() < priority_rate
        items.append({
            "index": index, "length": length, "width": width, "height": height,
            "mass": mass, "is_prioritized": priority, "is_soft": soft, **physics,
        })
    return items


def make_hard_scene(seed: int, task: str = "C") -> Scene:
    """A situation the sample does not show, drawn by the seed: one to three
    containers scaled from the ULDs (length 0.85-1.25x, width 0.85-1.15x,
    height 0.85-1.2x, the chamfer 0.7-1.3x), a shelf or a priority
    container at random; 28-70 items a container scaled by the container's
    volume; the soft share 10-60 %, the priority rate 0-30 %, the SKU mix
    the sample's, big-heavy, small, or with the extra SKUs; the stream in
    random, big-first, small-first, soft-first or soft-last order; a Task B
    pool of 3, 5, 10 or 20.  The platform's cases differ from the sample in
    all of these (README), and the C suite did not predict the platform
    (v33, v37)."""
    if task not in TASK_LOOKAHEAD:
        raise KeyError(f"unknown task {task!r}; known: A, B, C")
    rng = random.Random(10_000 + seed)
    n = rng.choice([1, 1, 2, 2, 3])
    prio_idx = rng.randrange(n) if rng.random() < 0.4 else None
    containers = []
    vol_ref = ULD["length"] * ULD["width"] * ULD["height"]
    total = 0
    counts = []
    base_count = rng.choice([28, 41, 41, 55, 70])
    for i in range(n):
        shelf = rng.random() < 0.4
        base = ULD_SHELF if shelf else ULD
        length = round(base["length"] * rng.uniform(0.85, 1.25), 2)
        width = round(base["width"] * rng.uniform(0.85, 1.15), 2)
        height = round(base["height"] * rng.uniform(0.85, 1.2), 2)
        containers.append({
            "index": i, "length": length, "width": width, "height": height,
            "thickness": base["thickness"],
            "cut_x": round(base["cut_x"] * rng.uniform(0.7, 1.3), 2),
            "cut_y": round(base["cut_y"] * rng.uniform(0.7, 1.3), 2),
            "buffer": 0.0, "packed_items": [], "require_shelf": shelf, "is_prioritized": i == prio_idx,
        })
        counts.append(max(10, round(base_count * (length * width * height) / vol_ref)))
    total = sum(counts)
    soft_share = rng.choice([0.1, 0.2, 0.32, 0.45, 0.6])
    prio_rate = rng.choice([0.0, 0.05, 0.1, 0.2, 0.3])
    mix = rng.choice(["sample", "sample", "big", "small", "extra"])
    skus = SKUS + EXTRA_SKUS
    weights = [s[7] for s in SKUS] + [0, 0, 0]
    if mix == "big":
        weights = [2, 8, 12, 2, 1, 5, 3, 6, 0, 2]
    elif mix == "small":
        weights = [14, 4, 1, 2, 8, 3, 6, 0, 10, 1]
    elif mix == "extra":
        weights = [8, 6, 3, 2, 2, 4, 3, 5, 5, 4]
    soft_pool = [(w, sk) for w, sk in zip(weights, skus) if sk[5]]
    hard_pool = [(w, sk) for w, sk in zip(weights, skus) if not sk[5]]
    items = []
    for index in range(total):
        pool = soft_pool if rng.random() < soft_share else hard_pool
        sku = rng.choices([sk for _w, sk in pool], weights=[w for w, _sk in pool], k=1)[0]
        _name, length, width, height, mass, soft, physics, _w = sku
        items.append({"index": index, "length": length, "width": width, "height": height, "mass": mass,
                      "is_prioritized": rng.random() < prio_rate, "is_soft": soft, **physics})
    order = rng.choice(["random", "random", "big-first", "small-first", "soft-first", "soft-last"])
    if order == "big-first":
        items.sort(key=lambda i: -(i["length"] * i["width"] * i["height"]))
    elif order == "small-first":
        items.sort(key=lambda i: i["length"] * i["width"] * i["height"])
    elif order == "soft-first":
        items.sort(key=lambda i: 0 if i["is_soft"] else 1)
    elif order == "soft-last":
        items.sort(key=lambda i: 1 if i["is_soft"] else 0)
    for index, item in enumerate(items):
        item["index"] = index
    pool_size = rng.choice([3, 5, 10, 20]) if task == "B" else TASK_LOOKAHEAD[task]
    spacing = max(c["length"] for c in containers) + 0.5
    name = f"{task.lower()}-hard-s{seed:04d}"
    spec = {"containers_n": n, "priority_container": prio_idx is not None,
            "shelves": sum(1 for c in containers if c["require_shelf"]),
            "dims": [(c["length"], c["width"], c["height"]) for c in containers],
            "base_count": base_count, "soft_share": soft_share, "priority_rate": prio_rate,
            "mix": mix, "order": order, "pool": pool_size}
    return Scene(name=name, seed=seed, layout="hard", task=task, look_ahead=pool_size,
                 items=items, containers=containers, spacing=spacing, spec=spec)


# the hard2 suite's strata by seed: the demand the count threshold makes
# (the volume of the first threshold items of the stream over the
# containers' volume), drawn uniformly in the band
HARD2_STRATA = [
    (range(1, 49), "sample", (0.26, 0.34)),     # the sample's band (28 %), varied
    (range(49, 81), "stretch", (0.34, 0.42)),   # where the v43 form crosses a quarter
    (range(81, 89), "edge", (0.42, 0.50)),      # a near-perfect packer's band
    (range(89, 97), "fill-only", (0.55, 0.80)), # no agent crosses: the fill alone counts
]


def hard2_stratum(seed: int) -> tuple[str, tuple[float, float]]:
    for seeds, name, band in HARD2_STRATA:
        if seed in seeds:
            return name, band
    return "stretch", (0.34, 0.42)


def _order_items(items: list[dict], order: str) -> list[dict]:
    items = list(items)
    if order == "big-first":
        items.sort(key=lambda i: -(i["length"] * i["width"] * i["height"]))
    elif order == "small-first":
        items.sort(key=lambda i: i["length"] * i["width"] * i["height"])
    elif order == "soft-first":
        items.sort(key=lambda i: 0 if i["is_soft"] else 1)
    elif order == "soft-last":
        items.sort(key=lambda i: 1 if i["is_soft"] else 0)
    return items


def threshold_demand(items: list[dict], containers: list[dict]) -> float:
    """The volume of the first ``len(items) // 2 + 1`` items of the stream
    over the containers' volume: what the count threshold asks of a Task C
    agent, which must place them all."""
    thr = len(items) // 2 + 1
    vol = sum(i["length"] * i["width"] * i["height"] for i in items[:thr])
    cap = sum(c["length"] * c["width"] * c["height"] for c in containers)
    return vol / max(cap, 1e-9)


def make_hard2_scene(seed: int, task: str = "C") -> Scene:
    """The hard suite redrawn with the count chosen for the demand it makes.

    The hard suite draws the count by the container's volume whatever the
    SKU mix, so a quarter of its scenes ask the first half of the stream
    to fill 50-130 % of the container and no agent crosses them, while the
    sample's demand is 28 %.  Here the containers, the mix, the shares and
    the order are drawn as there (its own seed), a long stream is drawn and
    ordered, and the count is the one whose first-threshold volume comes
    closest to a demand drawn in the seed's stratum (``HARD2_STRATA``):
    seeds 1-48 the sample's band, 49-80 the stretch band, 81-88 the edge,
    89-96 the fill-only scenes kept for the fill component's sake.  The
    stratum and the realised demand travel in the spec."""
    if task not in TASK_LOOKAHEAD:
        raise KeyError(f"unknown task {task!r}; known: A, B, C")
    rng = random.Random(20_000 + seed)
    stratum, band = hard2_stratum(seed)
    target = rng.uniform(*band)
    n = rng.choice([1, 1, 2, 2, 3])
    prio_idx = rng.randrange(n) if rng.random() < 0.4 else None
    containers = []
    for i in range(n):
        shelf = rng.random() < 0.4
        base = ULD_SHELF if shelf else ULD
        length = round(base["length"] * rng.uniform(0.85, 1.25), 2)
        width = round(base["width"] * rng.uniform(0.85, 1.15), 2)
        height = round(base["height"] * rng.uniform(0.85, 1.2), 2)
        containers.append({
            "index": i, "length": length, "width": width, "height": height,
            "thickness": base["thickness"],
            "cut_x": round(base["cut_x"] * rng.uniform(0.7, 1.3), 2),
            "cut_y": round(base["cut_y"] * rng.uniform(0.7, 1.3), 2),
            "buffer": 0.0, "packed_items": [], "require_shelf": shelf, "is_prioritized": i == prio_idx,
        })
    soft_share = rng.choice([0.1, 0.2, 0.32, 0.45, 0.6])
    prio_rate = rng.choice([0.0, 0.05, 0.1, 0.2, 0.3])
    mix = rng.choice(["sample", "sample", "big", "small", "extra"])
    skus = SKUS + EXTRA_SKUS
    weights = [s[7] for s in SKUS] + [0, 0, 0]
    if mix == "big":
        weights = [2, 8, 12, 2, 1, 5, 3, 6, 0, 2]
    elif mix == "small":
        weights = [14, 4, 1, 2, 8, 3, 6, 0, 10, 1]
    elif mix == "extra":
        weights = [8, 6, 3, 2, 2, 4, 3, 5, 5, 4]
    soft_pool = [(w, sk) for w, sk in zip(weights, skus) if sk[5]]
    hard_pool = [(w, sk) for w, sk in zip(weights, skus) if not sk[5]]
    order = rng.choice(["random", "random", "big-first", "small-first", "soft-first", "soft-last"])
    stream = []
    for index in range(320 * n):
        pool = soft_pool if rng.random() < soft_share else hard_pool
        sku = rng.choices([sk for _w, sk in pool], weights=[w for w, _sk in pool], k=1)[0]
        _name, length, width, height, mass, soft, physics, _w = sku
        stream.append({"index": index, "length": length, "width": width, "height": height, "mass": mass,
                       "is_prioritized": rng.random() < prio_rate, "is_soft": soft, **physics})
    best = None
    for count in range(max(16, 8 * n), len(stream) + 1):
        demand = threshold_demand(_order_items(stream[:count], order), containers)
        gap = abs(demand - target)
        if best is None or gap < best[0] - 1e-12:
            best = (gap, count, demand)
    _gap, total, demand = best
    items = _order_items(stream[:total], order)
    for index, item in enumerate(items):
        item["index"] = index
    pool_size = rng.choice([3, 5, 10, 20]) if task == "B" else TASK_LOOKAHEAD[task]
    spacing = max(c["length"] for c in containers) + 0.5
    name = f"{task.lower()}-hard2-s{seed:04d}"
    spec = {"containers_n": n, "priority_container": prio_idx is not None,
            "shelves": sum(1 for c in containers if c["require_shelf"]),
            "dims": [(c["length"], c["width"], c["height"]) for c in containers],
            "base_count": total, "soft_share": soft_share, "priority_rate": prio_rate,
            "mix": mix, "order": order, "pool": pool_size,
            "stratum": stratum, "target": round(target, 3), "demand": round(demand, 3)}
    return Scene(name=name, seed=seed, layout="hard2", task=task, look_ahead=pool_size,
                 items=items, containers=containers, spacing=spacing, spec=spec)


DMIX_MIXES = ["sample", "big", "small", "extra"]
DMIX_DEMAND_MAX = 0.55
DMIX_DEMAND_BAND = (0.30, 0.50)   # dense-a's: c1x50 about 0.30, c1x80 0.45
DMIX_COUNTS = (60, 70, 80, 90, 100, 110, 120)


def frame_demand(items: list[dict], containers: list[dict]) -> float:
    """The volume of the smallest ``len(items) // 2 + 1`` items over the
    containers' volume: what the count threshold asks of a Task A agent,
    which orders the manifest itself and can take the smallest items
    first (``threshold_demand`` reads the stream's order, Task C's)."""
    thr = len(items) // 2 + 1
    vols = sorted(i["length"] * i["width"] * i["height"] for i in items)
    cap = sum(c["length"] * c["width"] * c["height"] for c in containers)
    return sum(vols[:thr]) / max(cap, 1e-9)


def make_dmix_scene(seed: int, task: str = "A") -> Scene:
    """The dense single-container manifests of ``dense-a`` with the SKU
    mix varied (``dense-mix-a``): the mix one of the hard suite's four
    (the sample's, big-heavy, small, or with the extra SKUs) at equal
    odds; one container scaled from the ULDs as the hard suite scales
    them (length 0.85-1.25x, width 0.85-1.15x, height 0.85-1.2x, the
    chamfer 0.7-1.3x; a shelf one time in four), no priority container;
    the soft share 10-60 %, the priority rate 0-30 %; the items in a
    random order, their count the one of ``DMIX_COUNTS`` (60-120) whose
    smallest half-plus-one items by volume come closest to a demand drawn
    in ``DMIX_DEMAND_BAND`` (``frame_demand``: the share of the
    container's volume the count asks of a Task A agent, which orders
    the manifest itself; dense-a's c1x50-c1x80 ask 0.30-0.45, the small
    mix's 90 items 0.16-0.26).  A draw whose demand still exceeds
    ``DMIX_DEMAND_MAX`` (a big mix with little soft cargo) is redrawn
    with the same mix, so the suite reads the planner, not the volume;
    the demand and the draws travel in the spec.  The dense plan's
    numbers (reports/wedge/a-dense.md) were tuned on the sample mix;
    this suite asks what they are worth on another
    (reports/wedge/a-mix.md)."""
    if task not in TASK_LOOKAHEAD:
        raise KeyError(f"unknown task {task!r}; known: A, B, C")
    rng = random.Random(40_000 + seed)
    skus = SKUS + EXTRA_SKUS
    mix = rng.choice(DMIX_MIXES)
    weights = [s[7] for s in SKUS] + [0, 0, 0]
    if mix == "big":
        weights = [2, 8, 12, 2, 1, 5, 3, 6, 0, 2]
    elif mix == "small":
        weights = [14, 4, 1, 2, 8, 3, 6, 0, 10, 1]
    elif mix == "extra":
        weights = [8, 6, 3, 2, 2, 4, 3, 5, 5, 4]
    soft_pool = [(w, sk) for w, sk in zip(weights, skus) if sk[5]]
    hard_pool = [(w, sk) for w, sk in zip(weights, skus) if not sk[5]]
    for attempt in range(1, 100):
        shelf = rng.random() < 0.25
        base = ULD_SHELF if shelf else ULD
        container = {
            "index": 0,
            "length": round(base["length"] * rng.uniform(0.85, 1.25), 2),
            "width": round(base["width"] * rng.uniform(0.85, 1.15), 2),
            "height": round(base["height"] * rng.uniform(0.85, 1.2), 2),
            "thickness": base["thickness"],
            "cut_x": round(base["cut_x"] * rng.uniform(0.7, 1.3), 2),
            "cut_y": round(base["cut_y"] * rng.uniform(0.7, 1.3), 2),
            "buffer": 0.0, "packed_items": [], "require_shelf": shelf, "is_prioritized": False,
        }
        soft_share = rng.choice([0.1, 0.2, 0.32, 0.45, 0.6])
        prio_rate = rng.choice([0.0, 0.05, 0.1, 0.2, 0.3])
        target = rng.uniform(*DMIX_DEMAND_BAND)
        stream = []
        for index in range(max(DMIX_COUNTS)):
            pool = soft_pool if rng.random() < soft_share else hard_pool
            sku = rng.choices([sk for _w, sk in pool], weights=[w for w, _sk in pool], k=1)[0]
            _name, length, width, height, mass, soft, physics, _w = sku
            stream.append({"index": index, "length": length, "width": width, "height": height, "mass": mass,
                           "is_prioritized": rng.random() < prio_rate, "is_soft": soft, **physics})
        total, demand = min(((n, frame_demand(stream[:n], [container])) for n in DMIX_COUNTS),
                            key=lambda t: (abs(t[1] - target), t[0]))
        items = stream[:total]
        if demand <= DMIX_DEMAND_MAX:
            break
    pool_size = rng.choice([3, 5, 10, 20]) if task == "B" else TASK_LOOKAHEAD[task]
    name = f"{task.lower()}-dmix-s{seed:04d}"
    spec = {"containers_n": 1, "priority_container": False, "shelves": int(shelf),
            "dims": [(container["length"], container["width"], container["height"])],
            "base_count": total, "soft_share": soft_share, "priority_rate": prio_rate,
            "mix": mix, "order": "random", "pool": pool_size, "demand": round(demand, 3), "draws": attempt}
    return Scene(name=name, seed=seed, layout="dmix", task=task, look_ahead=pool_size,
                 items=items, containers=[container], spacing=container["length"] + 0.5, spec=spec)


HUGE_COUNTS = (100, 130, 160)


def make_huge_scene(seed: int, task: str = "A") -> Scene:
    """The huge single-container Task A manifests (``huge-a``): the
    platform's mean optimize time (52 s against 7.5 s on the sample's 41
    items here, 30 s on 80, 50 s on 120, 65 s on 160) reads as A manifests
    of 90-100 c1-equivalent items on average, so its uncounted A
    episodes are probably 100 items and more, where the count threshold
    is out of reach of any plan (the best dense plans hold 41-44 in c1)
    and the fill is the one component scored.  Seed s draws 100, 130 or
    160 items (s mod 3), the mix the sample's one time in two and the
    hard suite's big-heavy, small or extra mixes otherwise, the
    container, the soft share and the priority rate as ``make_dmix_scene``
    draws them, no demand check (the demand travels in the spec).  The
    verdict there is the fill and the optimize time, not the count
    (reports/wedge/a-mix.md)."""
    if task not in TASK_LOOKAHEAD:
        raise KeyError(f"unknown task {task!r}; known: A, B, C")
    rng = random.Random(50_000 + seed)
    skus = SKUS + EXTRA_SKUS
    total = HUGE_COUNTS[(seed - 1) % len(HUGE_COUNTS)]
    mix = rng.choice(["sample", "sample", "big", "small", "extra"])
    weights = [s[7] for s in SKUS] + [0, 0, 0]
    if mix == "big":
        weights = [2, 8, 12, 2, 1, 5, 3, 6, 0, 2]
    elif mix == "small":
        weights = [14, 4, 1, 2, 8, 3, 6, 0, 10, 1]
    elif mix == "extra":
        weights = [8, 6, 3, 2, 2, 4, 3, 5, 5, 4]
    soft_pool = [(w, sk) for w, sk in zip(weights, skus) if sk[5]]
    hard_pool = [(w, sk) for w, sk in zip(weights, skus) if not sk[5]]
    shelf = rng.random() < 0.25
    base = ULD_SHELF if shelf else ULD
    container = {
        "index": 0,
        "length": round(base["length"] * rng.uniform(0.85, 1.25), 2),
        "width": round(base["width"] * rng.uniform(0.85, 1.15), 2),
        "height": round(base["height"] * rng.uniform(0.85, 1.2), 2),
        "thickness": base["thickness"],
        "cut_x": round(base["cut_x"] * rng.uniform(0.7, 1.3), 2),
        "cut_y": round(base["cut_y"] * rng.uniform(0.7, 1.3), 2),
        "buffer": 0.0, "packed_items": [], "require_shelf": shelf, "is_prioritized": False,
    }
    soft_share = rng.choice([0.1, 0.2, 0.32, 0.45, 0.6])
    prio_rate = rng.choice([0.0, 0.05, 0.1, 0.2, 0.3])
    items = []
    for index in range(total):
        pool = soft_pool if rng.random() < soft_share else hard_pool
        sku = rng.choices([sk for _w, sk in pool], weights=[w for w, _sk in pool], k=1)[0]
        _name, length, width, height, mass, soft, physics, _w = sku
        items.append({"index": index, "length": length, "width": width, "height": height, "mass": mass,
                      "is_prioritized": rng.random() < prio_rate, "is_soft": soft, **physics})
    demand = frame_demand(items, [container])
    pool_size = rng.choice([3, 5, 10, 20]) if task == "B" else TASK_LOOKAHEAD[task]
    name = f"{task.lower()}-huge-s{seed:04d}"
    spec = {"containers_n": 1, "priority_container": False, "shelves": int(shelf),
            "dims": [(container["length"], container["width"], container["height"])],
            "base_count": total, "soft_share": soft_share, "priority_rate": prio_rate,
            "mix": mix, "order": "random", "pool": pool_size, "demand": round(demand, 3)}
    return Scene(name=name, seed=seed, layout="huge", task=task, look_ahead=pool_size,
                 items=items, containers=[container], spacing=container["length"] + 0.5, spec=spec)


SAMPLE_CONFIG = pathlib.Path(__file__).resolve().parents[1] / "reports" / "submission" / "abc_config.json"
SAMPLE_ENTRY = {"A": "000", "B": "001", "C": "002"}


def make_sample_scene(seed: int, task: str = "A") -> Scene:
    """The official sample's scene of the task (``reports/submission/
    abc_config.json``: 000 is Task A, 001 Task B, 002 Task C), the one
    input where the platform's own result is known (reports/submission/
    official-results.md).  Seed 0 is the sample itself, item order and all;
    a seed above 0 draws the same number of items from the sample's items
    with replacement (a bootstrap of its manifest: the same SKUs at about
    the same shares and demand, a different multiset) in a random order.
    A shuffle alone would not do for Task A, where the agent orders the
    manifest itself and the same items give the same episode."""
    if task not in SAMPLE_ENTRY:
        raise KeyError(f"unknown task {task!r}; known: A, B, C")
    entry = json.loads(SAMPLE_CONFIG.read_text(encoding="utf-8"))[SAMPLE_ENTRY[task]]
    containers = [dict(c) for c in entry["containers"]["container_list"]]
    items = [dict(i) for i in entry["item_stream"]["item_list"]]
    if seed:
        rng = random.Random(30_000 + seed)
        items = [dict(rng.choice(items)) for _ in items]
    for index, item in enumerate(items):
        item["index"] = index
    look_ahead = int(entry["item_stream"].get("look_ahead", TASK_LOOKAHEAD[task]))
    name = f"{task.lower()}-sample-s{seed:04d}"
    return Scene(name=name, seed=seed, layout="sample", task=task, look_ahead=look_ahead,
                 items=items, containers=containers, spacing=float(entry["containers"].get("spacing", SPACING)),
                 spec={"sample_entry": SAMPLE_ENTRY[task], "resampled": bool(seed)})


def make_scene(seed: int, layout: str = "c1", task: str = "C",
               items_per_container: int = 41, look_ahead: int | None = None) -> Scene:
    if layout == "hard":
        return make_hard_scene(seed, task)
    if layout == "hard2":
        return make_hard2_scene(seed, task)
    if layout == "sample":
        return make_sample_scene(seed, task)
    if layout == "dmix":
        return make_dmix_scene(seed, task)
    if layout == "huge":
        return make_huge_scene(seed, task)
    base = layout
    if layout.startswith("c1x") and layout[3:].isdigit():
        # the dense single-container manifests (``dense-a``): ``c1x60`` is
        # the c1 container with 60 items, named apart so the records of
        # one seed at several counts do not collide
        base = "c1"
        items_per_container = int(layout[3:])
    if base not in LAYOUTS:
        raise KeyError(f"unknown layout {layout!r}; known: {sorted(LAYOUTS)}")
    if task not in TASK_LOOKAHEAD:
        raise KeyError(f"unknown task {task!r}; known: A, B, C")
    containers = [
        _container_spec(index, shelf, prioritized)
        for index, (shelf, prioritized) in enumerate(LAYOUTS[base])
    ]
    count = items_per_container * len(containers)
    la = int(look_ahead) if look_ahead is not None else TASK_LOOKAHEAD[task]
    name = f"{task.lower()}-{layout}-s{seed:04d}"
    return Scene(name=name, seed=seed, layout=layout, task=task, look_ahead=la,
                 items=make_stream(seed, count), containers=containers)


SUITES = {
    # four scenes, one per layout, for a quick end-to-end check
    "smoke": [("C", layout, seed) for seed, layout in enumerate(("c1", "c1s", "c2", "c2p"), start=1)],
    # the same four streams under the Task A and Task B flows, so the effect
    # of handing over the manifest, or of a pool of ten, can be read off
    "smoke-a": [("A", layout, seed) for seed, layout in enumerate(("c1", "c1s", "c2", "c2p"), start=1)],
    "smoke-b": [("B", layout, seed) for seed, layout in enumerate(("c1", "c1s", "c2", "c2p"), start=1)],
    # the paired-comparison suite: 12 seeds x 4 layouts on Task C
    "core": [("C", layout, seed) for seed in range(1, 13) for layout in ("c1", "c1s", "c2", "c2p")],
    # Task B with the sample pool of ten
    "core-b": [("B", layout, seed) for seed in range(1, 13) for layout in ("c1", "c1s", "c2", "c2p")],
    # Task A: the manifest is handed to optimize()
    "core-a": [("A", layout, seed) for seed in range(1, 13) for layout in ("c1", "c1s", "c2", "c2p")],
    # the hard suites: 48 situations a task the sample does not show
    "hard": [("C", "hard", seed) for seed in range(1, 49)],
    "hard-b": [("B", "hard", seed) for seed in range(1, 49)],
    "hard-a": [("A", "hard", seed) for seed in range(1, 49)],
    # Task A on dense single-container manifests (50-80 items in the c1
    # container, the manifest 0.8-1.3 of its volume): the regime the
    # platform's Task A episodes under the count look like
    # (reports/wedge/stability-lattice.md)
    "dense-a": [("A", f"c1x{n}", seed) for n in (50, 60, 70, 80) for seed in range(1, 13)],
    # dense single-container Task A manifests with the SKU mix varied
    # (make_dmix_scene): the dense plan's numbers off the sample mix
    "dense-mix-a": [("A", "dmix", seed) for seed in range(1, 49)],
    # huge single-container Task A manifests (100 / 130 / 160 items, the
    # sample mix one time in two): the count out of reach, the fill and
    # the optimize time the verdict (make_huge_scene)
    "huge-a": [("A", "huge", seed) for seed in range(1, 37)],
    # the hard2 suites: 96 situations a task, the count chosen for the
    # demand the threshold makes (HARD2_STRATA)
    "hard2": [("C", "hard2", seed) for seed in range(1, 97)],
    "hard2-b": [("B", "hard2", seed) for seed in range(1, 97)],
    "hard2-a": [("A", "hard2", seed) for seed in range(1, 97)],
    # the official sample's scene of each task (seed 0, the platform's own
    # result known) and eleven shuffles of its items: the sample's kind of
    # manifest, where Task A's count sits a few items over the threshold
    "sample-a": [("A", "sample", seed) for seed in range(0, 12)],
    "sample-b": [("B", "sample", seed) for seed in range(0, 12)],
    "sample-c": [("C", "sample", seed) for seed in range(0, 12)],
    # training streams for a learned ranker: disjoint seeds from every
    # evaluation suite above
    "train-small": [("C", layout, seed) for seed in range(101, 107) for layout in ("c1", "c1s", "c2", "c2p")],
    "train": [("C", layout, seed) for seed in range(101, 125) for layout in ("c1", "c1s", "c2", "c2p")],
}


def build_suite(name: str) -> list[Scene]:
    if name not in SUITES:
        raise KeyError(f"unknown suite {name!r}; known: {sorted(SUITES)}")
    return [make_scene(seed, layout, task) for task, layout, seed in SUITES[name]]
