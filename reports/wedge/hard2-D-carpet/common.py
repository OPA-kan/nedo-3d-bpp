"""Shared helpers for the D (soft carpet) deep-dive.

Board reconstruction follows reports/wedge/hard2-miss-taxonomy/extract.py:
the settled poses of ``final_items`` (world frame; a container's x offset is
recovered as the median of final.x - pos_local.x over its steps), the step's
oriented ``size`` as the dims, the soft / priority flags from the scene.
"""

import collections
import glob
import json
import os
import statistics
import sys

import numpy as np

REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
)
if REPO not in sys.path:
    sys.path.insert(0, REPO)
os.chdir(REPO)  # the arms name their policy directories relative to the repository

from bench.scenes import make_scene  # noqa: E402
from rule_alpha.config import DEFAULT_CONFIG  # noqa: E402
from rule_alpha.geometry import ContainerModel  # noqa: E402
from rule_alpha.surface import _Load  # noqa: E402
from rule_alpha._reuse import packed_aabbs_local  # noqa: E402

BENCH = os.path.join(REPO, "reports", "bench")
CELL = 0.02
FLOOR_BAND = 0.10  # the taxonomy's "on the floor": bottom < z_floor + 0.10
SOFT_CARPET = 0.40
REACH = 0.506  # the taxonomy's volume line (highest need any crossing met)

# the taxonomy's v50 D lists (tables.md, "v50 C / B: every miss")
D_V50 = {
    "gate0-hard2": [
        "c-hard2-s0006",
        "c-hard2-s0036",
        "c-hard2-s0004",
        "c-hard2-s0053",
        "c-hard2-s0069",
        "c-hard2-s0072",
        "c-hard2-s0049",
        "c-hard2-s0075",
        "c-hard2-s0061",
        "c-hard2-s0068",
    ],
    "gate0-hard2-b": [
        "b-hard2-s0036",
        "b-hard2-s0006",
        "b-hard2-s0069",
        "b-hard2-s0005",
        "b-hard2-s0072",
        "b-hard2-s0049",
        "b-hard2-s0068",
        "b-hard2-s0043",
    ],
}
RESCUE = {
    "physics-resort",
    "count-mode",
    "grid-rescue",
    "grid-rescue-cover",
    "fallback",
}

_SCENES = {}


def scene_of(spec):
    key = (spec["seed"], spec["layout"], spec["task"])
    if key not in _SCENES:
        _SCENES[key] = make_scene(spec["seed"], spec["layout"], spec["task"])
    return _SCENES[key]


def load_record(rec, scene):
    return json.load(open(os.path.join(BENCH, rec, scene + ".json")))


def records(rec):
    return sorted(glob.glob(os.path.join(BENCH, rec, "[bc]-hard2-s*.json")))


def rung(step):
    return str(step.get("archetype")).split("/")[0]


def container_offsets(r):
    final = {it["index"]: it for it in r["final_items"]}
    off = collections.defaultdict(list)
    for s in r["steps"]:
        if (
            s.get("event") != "step"
            or not s.get("is_placed_safe")
            or "pos_local" not in s
        ):
            continue
        f = final.get(s["item_index"])
        if f is not None:
            off[s["container_idx"]].append(f["pos"][0] - s["pos_local"][0])
    return {k: statistics.median(v) for k, v in off.items()}


def placed_steps(r):
    return [
        s
        for s in r["steps"]
        if s.get("event") == "step" and s.get("is_placed_safe") and "size" in s
    ]


def packed_item(s, item, pos):
    return {
        "index": s["item_index"],
        "length": float(item["length"]),
        "width": float(item["width"]),
        "height": float(item["height"]),
        "mass": float(item.get("mass", 0.0)),
        "is_soft": bool(item["is_soft"]),
        "is_prioritized": bool(item["is_prioritized"]),
        "orientation": int(s.get("orientation", 0)),
        "dims": tuple(float(v) for v in s["size"]),
        "pos": tuple(float(v) for v in pos),
        "belongs_to": s["container_idx"],
        "layer": 1,
    }


def step_poses(r, use="final"):
    """(step, item, local pos) for every placed step; ``use`` 'final' (settled at the
    end) or 'local' (the agent's intended pose)."""
    sc = scene_of(r["scene_spec"])
    by = {i["index"]: i for i in sc.items}
    final = {it["index"]: it for it in r["final_items"]}
    off = container_offsets(r)
    out = []
    for s in placed_steps(r):
        it = by[s["item_index"]]
        f = final.get(s["item_index"])
        if use == "final" and f is not None:
            pos = (
                f["pos"][0] - off.get(s["container_idx"], 0.0),
                f["pos"][1],
                f["pos"][2],
            )
        else:
            pos = tuple(s["pos_local"])
        out.append((s, it, pos))
    return out


def containers_at(r, k, use="final", spacing=None):
    """Observation-shaped container dicts (the analytic frame, offset = position x
    scene spacing) with the items of the first ``k`` placed steps packed."""
    sc = scene_of(r["scene_spec"])
    cons = sc.rule_alpha_containers()
    for c in cons:
        c["packed_items"] = []
    for s, it, pos in step_poses(r, use)[:k]:
        ci = s["container_idx"]
        ox = float(cons[ci].get("center", (0.0, 0.0, 0.0))[0])
        cons[ci]["packed_items"].append(
            packed_item(s, it, (pos[0] + ox, pos[1], pos[2]))
        )
    return cons


class FloorTracker:
    """Per-container floor masks: soft / hard / priority footprints of boxes with
    their bottom under z_floor + FLOOR_BAND (the taxonomy's floor rule)."""

    def __init__(self, sc):
        self.cons = [dict(c, packed_items=[]) for c in sc.containers]
        self.models = [ContainerModel(c, DEFAULT_CONFIG) for c in self.cons]
        self.loads = [_Load(m, CELL) for m in self.models]
        self.floor = [ld.floor.copy() for ld in self.loads]
        self.area = sum(float(f.sum()) for f in self.floor) * CELL * CELL
        self.soft = [np.zeros_like(f) for f in self.floor]
        self.hard = [np.zeros_like(f) for f in self.floor]
        self.boxes = [[] for _ in self.cons]  # (aabb, soft, prio)

    def add(self, ci, size, pos, soft, prio):
        from rule_alpha._reuse import AABB

        box = AABB(tuple(pos), tuple(size), "x")
        zf = self.models[ci].z_floor
        bottom = float(box.minimum[2]) - zf
        under = self.support_of(ci, box)
        self.boxes[ci].append((box, soft, prio))
        if bottom < FLOOR_BAND:
            m = self.loads[ci].mask(box)
            (self.soft if soft else self.hard)[ci] |= m
        return bottom, under

    def support_of(self, ci, box, tol=0.04):
        """What the box rests on: 'floor', 'shelf', or the kinds of the packed boxes
        whose top is within tol of its bottom and overlap its footprint."""
        zf = self.models[ci].z_floor
        b = float(box.minimum[2])
        if b - zf < tol:
            return "floor"
        kinds = set()
        for o, s, p in self.boxes[ci]:
            if abs(float(o.maximum[2]) - b) <= tol:
                ox = min(float(o.maximum[0]), float(box.maximum[0])) - max(
                    float(o.minimum[0]), float(box.minimum[0])
                )
                oy = min(float(o.maximum[1]), float(box.maximum[1])) - max(
                    float(o.minimum[1]), float(box.minimum[1])
                )
                if ox > 0.02 and oy > 0.02:
                    kinds.add("soft" if s else ("prio" if p else "hard"))
        if not kinds:
            return "shelf/other"
        return "+".join(sorted(kinds))

    def soft_share(self):
        return sum(float(m.sum()) for m in self.soft) * CELL * CELL / self.area

    def hard_share(self):
        return sum(float(m.sum()) for m in self.hard) * CELL * CELL / self.area

    def free_share(self):
        return (
            sum(
                float((f & ~s & ~h).sum())
                for f, s, h in zip(self.floor, self.soft, self.hard)
            )
            * CELL
            * CELL
            / self.area
        )


def vol(i):
    return i["length"] * i["width"] * i["height"]


def need_of(r):
    """The taxonomy's need: volume of the first threshold items over the simulator's
    container volume."""
    sc = scene_of(r["scene_spec"])
    m = r["metrics"]
    thr = m["total_items"] // 2 + 1
    models = [
        ContainerModel(dict(c, packed_items=[]), DEFAULT_CONFIG) for c in sc.containers
    ]
    cvol = sum(md.usable_volume for md in models)
    return sum(vol(i) for i in sc.items[:thr]) / cvol
