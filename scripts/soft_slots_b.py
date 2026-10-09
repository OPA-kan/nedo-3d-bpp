"""soft_slots_b.py <record_dir>: Task B's soft cargo against the slots it had.

For every step of every episode the load is rebuilt on a 2 cm grid
(floor, the shelf plates, every placed box as a column), the visible
pool is reconstructed from the stream, and for each soft item of the
pool a *slot* is looked for: a level patch the item's flat footprint
fits with 3 cm for the clearances (tops within 2 cm, the floor, or a
shelf plate), with the item's height plus 3 cm free above it under the
local ceiling (a shelf plate is the ceiling of what stands under it).
Reachability and the stability rules are not applied: the slot is the
geometric necessary condition.

Per episode: how many steps had a soft item in the pool with a slot
while a hard item was placed (soft deferred), and at the decline how
many of the pool's soft items still have a slot and on what (floor,
shelf, a top).  If the pool's soft items have no slot at the end, the
stop is geometry; if they do, it is the rules or the order."""
import glob
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from bench.scenes import make_hard_scene, make_scene  # noqa: E402
from rule_alpha.config import DEFAULT_CONFIG  # noqa: E402
from rule_alpha.geometry import ContainerModel  # noqa: E402

CELL = 0.02
TOL = 0.02
CLEAR = 0.03


def _scene(spec):
    if spec.get("layout") == "hard" or "hard" in spec["name"]:
        return make_hard_scene(spec["seed"], spec["task"])
    return make_scene(spec["seed"], spec["layout"], spec["task"])


class Load:
    def __init__(self, container: dict):
        self.c = container
        self.model = ContainerModel(container, DEFAULT_CONFIG)
        L, W = container["length"], container["width"]
        self.nx, self.ny = int(round(L / CELL)), int(round(W / CELL))
        self.x0, self.y0 = -L / 2.0, -W / 2.0
        xs = self.x0 + (np.arange(self.nx) + 0.5) * CELL
        ys = self.y0 + (np.arange(self.ny) + 0.5) * CELL
        self.xx, self.yy = np.meshgrid(xs, ys, indexing="ij")
        fr = self.model.floor_rect
        self.usable = (self.xx >= fr.x_min) & (self.xx <= fr.x_max) & (self.yy >= fr.y_min) & (self.yy <= fr.y_max)
        self.z_floor = float(self.model.z_floor)
        self.z_ceiling = float(self.model.z_ceiling)
        # the shelf plates: (mask, top, bottom)
        self.shelves = []
        for s in self.model.shelves:
            m = ((self.xx >= float(s.minimum[0])) & (self.xx <= float(s.maximum[0]))
                 & (self.yy >= float(s.minimum[1])) & (self.yy <= float(s.maximum[1])))
            self.shelves.append((m, float(s.maximum[2]), float(s.minimum[2])))
        self.boxes = []  # (mask, bottom, top)

    def add(self, pos, size):
        x, y, z = pos
        sx, sy, sz = size
        m = ((self.xx >= x - sx / 2) & (self.xx <= x + sx / 2) & (self.yy >= y - sy / 2) & (self.yy <= y + sy / 2))
        self.boxes.append((m, z - sz / 2, z + sz / 2))

    def _local_ceiling(self, z: float) -> np.ndarray:
        ceil = np.full((self.nx, self.ny), self.z_ceiling)
        for m, top, bottom in self.shelves:
            under = m & (z < bottom - 1e-6)
            ceil[under] = np.minimum(ceil[under], bottom)
        return ceil

    def levels(self):
        out = {round(self.z_floor, 2): "floor"}
        for _m, top, _b in self.shelves:
            out.setdefault(round(top, 2), "shelf")
        for _m, _b, top in self.boxes:
            out.setdefault(round(top, 2), "top")
        return out

    def slot(self, dims, hard_tops_only: bool = False):
        """The kind of level the item has a slot on ('floor', 'shelf',
        'top') or None.  ``dims`` = (l, w, h) with l >= w."""
        found = self.slot_pose(dims)
        return found[0] if found else None

    def slot_pose(self, dims):
        """``(kind, (cx, cy, cz), (dx, dy, dz))`` of the deepest slot (the
        back-most, then left-most window) on the lowest level that has
        one, or None."""
        l, w, h = dims
        need = h + CLEAR
        nxw, nyw = int(round((l + CLEAR) / CELL)), int(round((w + CLEAR) / CELL))
        for z, kind in sorted(self.levels().items()):
            if z + need > self.z_ceiling + 1e-9:
                continue
            support = np.zeros((self.nx, self.ny), dtype=bool)
            if kind == "floor":
                support |= self.usable
            # the chamfer wall at the box's bottom: nothing may stand left
            # of the slope's limit at that height
            x_limit = float(self.model.x_limit_at_height(z + 1e-3))
            wall_ok = self.xx >= x_limit + CLEAR / 2.0
            for m, top, _b in self.shelves:
                if abs(top - z) <= TOL:
                    support |= m
            for m, _b, top in self.boxes:
                if abs(top - z) <= TOL:
                    support |= m
            free = self._local_ceiling(z) >= z + need - 1e-9
            for m, bottom, top in self.boxes:
                # anything occupying (z, z + need) blocks the column
                blocks = m & (top > z + 1e-3) & (bottom < z + need - 1e-3)
                free &= ~blocks
            ok = support & free & wall_ok
            if ok.sum() < nxw * nyw:
                continue
            s = np.zeros((self.nx + 1, self.ny + 1), dtype=np.int32)
            s[1:, 1:] = np.cumsum(np.cumsum(ok.astype(np.int32), axis=0), axis=1)
            for a, b in ((nxw, nyw), (nyw, nxw)):
                if a > self.nx or b > self.ny:
                    continue
                tot = s[a:, b:] - s[:-a, b:] - s[a:, :-b] + s[:-a, :-b]
                ok_win = tot == a * b
                if ok_win.any():
                    ii, jj = np.nonzero(ok_win)
                    # the back-most (largest y), then left-most window
                    k = int(np.lexsort((ii, -jj))[0])
                    i, j = int(ii[k]), int(jj[k])
                    cx = self.x0 + (i + a / 2.0) * CELL
                    cy = self.y0 + (j + b / 2.0) * CELL
                    dx, dy = (l, w) if a == nxw else (w, l)
                    return kind, (cx, cy, z + h / 2.0), (dx, dy, h)
        return None


def episode(record):
    spec = record["scene_spec"]
    scene = _scene(spec)
    items = scene.items
    look = int(spec.get("look_ahead", 10) or 10)
    steps = [s for s in record["steps"] if s.get("event") == "step" and "pos_local" in s]
    loads = [Load(c) for c in scene.containers]
    placed = []
    deferred = 0
    soft_in_pool_steps = 0
    slot_steps = 0
    for s in steps:
        pool = [i for i in range(len(items)) if i not in placed][:look]
        soft_pool = [i for i in pool if items[i].get("is_soft")]
        if soft_pool:
            soft_in_pool_steps += 1
            has = False
            for i in soft_pool:
                it = items[i]
                d = sorted((it["length"], it["width"], it["height"]), reverse=True)
                dims = (d[0], d[1], d[2])
                if any(ld.slot(dims) for ld in loads):
                    has = True
                    break
            if has:
                slot_steps += 1
                if not items[s["item_index"]].get("is_soft"):
                    deferred += 1
        loads[s["container_idx"]].add(s["pos_local"], s["size"])
        placed.append(s["item_index"])
    pool = [i for i in range(len(items)) if i not in placed][:look]
    soft_pool = [i for i in pool if items[i].get("is_soft")]
    end = {"floor": 0, "shelf": 0, "top": 0, "none": 0}
    for i in soft_pool:
        it = items[i]
        d = sorted((it["length"], it["width"], it["height"]), reverse=True)
        kinds = [ld.slot((d[0], d[1], d[2])) for ld in loads]
        kind = next((k for k in kinds if k), None)
        end[kind or "none"] += 1
    return {
        "scene": record["scene"], "placed": len(steps),
        "soft_placed": sum(1 for s in steps if items[s["item_index"]].get("is_soft")),
        "soft_total": sum(1 for it in items if it.get("is_soft")),
        "steps_soft_in_pool": soft_in_pool_steps, "steps_with_slot": slot_steps, "deferred": deferred,
        "end_pool_soft": len(soft_pool), **{"end_" + k: v for k, v in end.items()},
    }


def validate_end_slots(record) -> list:
    """At the end state, the analytic validator's verdict on a pose in
    each end-pool soft item's slot (the load rebuilt from the steps'
    settled poses, the record's own arm config).  Returns
    ``[(kind, verdict, dims)]``."""
    import collections

    import rule_alpha.layer1 as layer1
    from bench.arms import config_from_spec, resolve_alias

    spec = record["scene_spec"]
    scene = _scene(spec)
    items = scene.items
    look = int(spec.get("look_ahead", 10) or 10)
    steps = [s for s in record["steps"] if s.get("event") == "step" and "pos_local" in s]
    arm = record.get("arm", {}).get("arm", "ladder")
    body = arm.split("@", 1)
    base = resolve_alias("ladder-stable") if body[0].startswith(("stack", "wedge")) else body[0]
    config = config_from_spec(base + ("@" + body[1] if len(body) > 1 else ""))
    containers = []
    for c in scene.containers:
        d = dict(c)
        d["packed_items"] = []
        containers.append(d)
    for s in steps:
        it = items[s["item_index"]]
        containers[s["container_idx"]]["packed_items"].append({
            "index": s["item_index"], "pos": list(s["pos_local"]), "dims": list(s["size"]),
            "is_soft": bool(it.get("is_soft")), "is_prioritized": bool(it.get("is_prioritized")),
            "length": it["length"], "width": it["width"], "height": it["height"], "mass": it.get("mass", 1.0),
        })
    loads = [Load(c) for c in containers]
    for s in steps:
        loads[s["container_idx"]].add(s["pos_local"], s["size"])
    models = [ContainerModel(c, config) for c in containers]
    placed = {s["item_index"] for s in steps}
    pool = [i for i in range(len(items)) if i not in placed][:look]
    out = []
    for i in pool:
        it = items[i]
        if not it.get("is_soft"):
            continue
        d = sorted((it["length"], it["width"], it["height"]), reverse=True)
        verdict = None
        for ci, ld in enumerate(loads):
            found = ld.slot_pose((d[0], d[1], d[2]))
            if not found:
                continue
            kind, centre, dims = found
            from rule_alpha._reuse import AABB
            ok, why = layer1.validate(AABB(centre, dims, "probe"), models[ci], containers[ci], config)
            verdict = (kind, "ok" if ok else why, f"{d[0]:.2f}x{d[1]:.2f}x{d[2]:.2f}")
            break
        out.append(verdict or ("none", "no-slot", f"{d[0]:.2f}x{d[1]:.2f}x{d[2]:.2f}"))
    return out


def main():
    if len(sys.argv) > 2 and sys.argv[2] == "--validate":
        import collections

        counts = collections.Counter()
        by_dims = collections.Counter()
        for f in sorted(glob.glob(str(pathlib.Path(sys.argv[1]) / "[abc]-*.json"))):
            for kind, verdict, dims in validate_end_slots(json.load(open(f))):
                counts[(kind, verdict)] += 1
                by_dims[(dims, kind, verdict)] += 1
        print("end-pool soft items by slot kind and the validator's verdict on a pose in the slot:")
        for (kind, verdict), n in counts.most_common():
            print(f"  {n:4d}  {kind:6s} {verdict}")
        print("by dims:")
        for (dims, kind, verdict), n in by_dims.most_common(16):
            print(f"  {n:4d}  {dims} {kind} {verdict}")
        return
    rows = [episode(json.load(open(f))) for f in sorted(glob.glob(str(pathlib.Path(sys.argv[1]) / "[abc]-*.json")))]
    print("| scene | placed | soft placed / total | steps with soft in pool | with a slot | hard placed instead | pool soft at end | slot: floor / shelf / top / none |")
    print("|---|---:|---:|---:|---:|---:|---:|---|")
    for r in rows:
        print(f"| {r['scene']} | {r['placed']} | {r['soft_placed']} / {r['soft_total']} | {r['steps_soft_in_pool']} | {r['steps_with_slot']} | {r['deferred']} | {r['end_pool_soft']} | {r['end_floor']} / {r['end_shelf']} / {r['end_top']} / {r['end_none']} |")
    n = len(rows)
    print()
    print(f"episodes {n}: soft placed {sum(r['soft_placed'] for r in rows)} of {sum(r['soft_total'] for r in rows)}; "
          f"steps with soft in the pool {sum(r['steps_soft_in_pool'] for r in rows)}, of them with a slot {sum(r['steps_with_slot'] for r in rows)}, "
          f"a hard item placed instead {sum(r['deferred'] for r in rows)}; at the end {sum(r['end_pool_soft'] for r in rows)} soft in the pools, "
          f"with a slot on the floor {sum(r['end_floor'] for r in rows)}, a shelf {sum(r['end_shelf'] for r in rows)}, a top {sum(r['end_top'] for r in rows)}, none {sum(r['end_none'] for r in rows)}")


if __name__ == "__main__":
    main()
