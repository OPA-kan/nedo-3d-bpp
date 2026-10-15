"""shape.py: is the carpet's cost its area or its shape?  (records only)

For every hard2 episode with an order in (soft-first, small-first) and every carpet
(soft floor share >= 0.40 at the end), at two moments -- when the first hard item of
the main hard run arrives (the first hard item after the stream's leading soft run,
or after the threshold's first half for streams that start with small hard boxes)
and at the end -- the floor of every container is rasterised (2 cm) from the settled
poses into soft / hard / free cells, and:

* ``slots_real``: how many footprints of the stream's commonest large hard class
  (0.65 x 0.45 when present, else 0.55 x 0.40; each side + 2 x 0.026 m clearance)
  a greedy back-to-front packer fits into the free floor;
* ``slots_compact``: the same with the soft floor cells moved into one compact block
  (the same cell count, filled column by column from the left wall, i.e. against the
  chamfer side) and the hard floor cells kept where they are;
* ``slots_empty``: the same on the floor with only the hard cells.

``slots_real`` < ``slots_compact`` means the carpet's spread (shape) costs slots that
its area alone would not.  Output: data/shape.json and a table on stdout.
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (
    CELL,
    FLOOR_BAND,
    FloorTracker,
    REACH,
    load_record,
    records,
    scene_of,
    step_poses,
)  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CLEAR = 0.026


def greedy_slots(free, a, b):
    """Greedy count of a x b (cells) windows, either orientation, back (high y index)
    to front, left to right; placed windows are removed."""
    free = free.copy()
    nx, ny = free.shape
    n = 0
    for p, q in ((a, b), (b, a)):
        pass

    # prefix sums recomputed lazily: simple scan
    def fits(i, j, p, q):
        return i + p <= nx and j + q <= ny and free[i : i + p, j : j + q].all()

    for j in range(ny - 1, -1, -1):
        for i in range(nx):
            if not free[i, j]:
                continue
            for p, q in ((a, b), (b, a)):
                j0 = j - q + 1
                if j0 >= 0 and fits(i, j0, p, q):
                    free[i : i + p, j0 : j0 + q] = False
                    n += 1
                    break
    return n


def compact(floor, soft, hard):
    """Soft cells moved into a block filled column by column (x first index) from
    the low-x side, skipping hard cells and non-floor."""
    k = int(soft.sum())
    out = np.zeros_like(soft)
    nx, ny = soft.shape
    for i in range(nx):
        for j in range(ny):
            if k <= 0:
                return out
            if floor[i, j] and not hard[i, j]:
                out[i, j] = True
                k -= 1
    return out


def big_class(sc, start):
    rest = [i for i in sc.items[start:] if not i["is_soft"]]
    dims = [tuple(sorted((i["length"], i["width"]), reverse=True)) for i in rest]
    if (0.65, 0.45) in dims:
        return (0.65, 0.45)
    if (0.55, 0.40) in dims:
        return (0.55, 0.40)
    return max(dims, key=lambda d: d[0] * d[1]) if dims else (0.55, 0.40)


def analyse(rec, path):
    r = json.load(open(path))
    sp = r["scene_spec"]
    sc = scene_of(sp)
    m = r["metrics"]
    thr = m["total_items"] // 2 + 1
    items = sc.items
    # the main hard run's first item: first hard item after the first soft item
    first_soft = next((p for p, i in enumerate(items) if i["is_soft"]), None)
    if first_soft is None:
        return None
    first_hard = next(
        (
            p
            for p, i in enumerate(items)
            if p > first_soft and not i["is_soft"] and i["length"] * i["width"] >= 0.2
        ),
        None,
    )
    poses = step_poses(r, "final")
    placed_idx = [s["item_index"] for s, _i, _p in poses]
    k_hard = None
    if first_hard is not None:
        k_hard = next(
            (k for k, idx in enumerate(placed_idx) if idx >= first_hard), None
        )
    ft = FloorTracker(sc)
    snaps = {}
    for k, (s, it, pos) in enumerate(poses):
        if k_hard is not None and k == k_hard:
            snaps["at_hard"] = (
                [x.copy() for x in ft.soft],
                [x.copy() for x in ft.hard],
                k,
            )
        ft.add(
            s["container_idx"],
            s["size"],
            pos,
            bool(it["is_soft"]),
            bool(it["is_prioritized"]),
        )
    snaps["end"] = (
        [x.copy() for x in ft.soft],
        [x.copy() for x in ft.hard],
        len(poses),
    )
    cls_ = big_class(sc, first_hard or 0)
    a = int(round((cls_[0] + 2 * CLEAR) / CELL))
    b = int(round((cls_[1] + 2 * CLEAR) / CELL))
    out = dict(
        scene=r["scene"],
        rec=rec,
        order=sp["order"],
        mg=m["placed_count"] - thr,
        n=sp["containers_n"],
        first_hard=first_hard,
        k_hard=k_hard,
        hard_class=cls_,
    )
    for name, (soft, hard, k) in snaps.items():
        real = comp = empty = 0
        sa = fa = 0.0
        for ci in range(len(ft.floor)):
            floor = ft.floor[ci]
            free = floor & ~soft[ci] & ~hard[ci]
            real += greedy_slots(free, a, b)
            cs = compact(floor, soft[ci], hard[ci])
            comp += greedy_slots(floor & ~cs & ~hard[ci], a, b)
            empty += greedy_slots(floor & ~hard[ci], a, b)
            sa += float(soft[ci].sum()) * CELL * CELL
            fa += float(free.sum()) * CELL * CELL
        out[name] = dict(
            k=k,
            soft_share=round(sa / ft.area, 3),
            free_share=round(fa / ft.area, 3),
            slots_real=real,
            slots_compact=comp,
            slots_empty=empty,
        )
    # hard items the stream still held after the snapshot that were never placed
    return out


def main():
    res = []
    for rec in ("gate0-hard2", "gate0-hard2-b", "gate0det-hard2"):
        for p in records(rec):
            r = json.load(open(p))
            if r["scene_spec"]["order"] not in ("soft-first", "small-first"):
                continue
            x = analyse(rec, p)
            if x:
                res.append(x)
                e = x["end"]
                h = x.get("at_hard") or {}
                print(
                    f"{rec[:14]:14s} {x['scene']} {x['order']:10s} mg {x['mg']:+4d} n {x['n']} cls {x['hard_class']} "
                    f"at-hard k={h.get('k')} soft {h.get('soft_share')} free {h.get('free_share')} slots real/compact/empty "
                    f"{h.get('slots_real')}/{h.get('slots_compact')}/{h.get('slots_empty')} | end soft {e['soft_share']} "
                    f"free {e['free_share']} slots {e['slots_real']}/{e['slots_compact']}/{e['slots_empty']}",
                    flush=True,
                )
    json.dump(res, open(os.path.join(HERE, "data", "shape.json"), "w"), indent=0)


if __name__ == "__main__":
    main()
