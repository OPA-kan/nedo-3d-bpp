"""
Of the free space that is still open from above, how much could take an item?

The voxel audit says 44% of the envelope is free with nothing above it, but
"nothing above it" includes a 5 cm sliver over a stack, which no baggage
will ever occupy. This erodes the free region by each published type's
footprint and reports how many independent drops still fit -- the honest
version of "there is space left".

A slot is counted where the item's whole box fits inside the free region AND
its bottom rests on solid material or the floor, which is what a release can
actually produce. Slots are deduplicated on a 25 cm lattice so one pocket
that admits many nearby drops counts once.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

CELL = 0.05
LATTICE = 0.25

TYPES = [
    ("suitcase_large", 0.75, 0.56, 0.27),
    ("suitcase_medium", 0.65, 0.45, 0.25),
    ("suitcase_small", 0.55, 0.40, 0.24),
    ("duffel", 0.60, 0.30, 0.25),
    ("cardboard", 0.50, 0.40, 0.40),
    ("backpack_large", 0.65, 0.35, 0.23),
    ("daypack_small", 0.45, 0.30, 0.20),
]


def grids(container):
    offset = float(container.get("offset_x") or 0.0)
    points = np.asarray(container["points"], dtype=np.float64).copy()
    points[:, 0] -= offset
    normals = np.asarray(container["n_vecs"], dtype=np.float64)

    half_l = container["length"] / 2.0
    half_w = container["width"] / 2.0
    height = container["height"]
    xs = np.arange(-half_l + CELL / 2, half_l, CELL)
    ys = np.arange(-half_w + CELL / 2, half_w, CELL)
    zs = np.arange(CELL / 2, height, CELL)
    gx, gy, gz = np.meshgrid(xs, ys, zs, indexing="ij")
    pts = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=1)

    inside = np.ones(len(pts), dtype=bool)
    for point, normal in zip(points, normals):
        inside &= (pts - point) @ normal <= 0.0

    solid = np.zeros(len(pts), dtype=bool)
    for item in container["items"]:
        c = np.asarray(item["c"])
        s = np.asarray(item["s"]) / 2.0
        solid |= np.all(np.abs(pts - c) <= s, axis=1)
    for plate in container.get("shelves") or []:
        lo = np.asarray(plate["min"])
        hi = np.asarray(plate["max"])
        solid |= np.all((pts >= lo) & (pts <= hi), axis=1)

    shape = gx.shape
    return xs, ys, zs, inside.reshape(shape), solid.reshape(shape)


def slots(container, dims):
    xs, ys, zs, inside, solid = grids(container)
    free = inside & ~solid
    nx = max(int(round(dims[0] / CELL)), 1)
    ny = max(int(round(dims[1] / CELL)), 1)
    nz = max(int(round(dims[2] / CELL)), 1)
    if nx > len(xs) or ny > len(ys) or nz > len(zs):
        return 0

    # 3-D erosion by the item box, via cumulative sums
    pad = np.pad(free.astype(np.int32), ((1, 0), (1, 0), (1, 0)))
    c = pad.cumsum(0).cumsum(1).cumsum(2)

    def block(i, j, k):
        return (
            c[i + nx, j + ny, k + nz]
            - c[i, j + ny, k + nz]
            - c[i + nx, j, k + nz]
            - c[i + nx, j + ny, k]
            + c[i, j, k + nz]
            + c[i, j + ny, k]
            + c[i + nx, j, k]
            - c[i, j, k]
        )

    found = set()
    target = nx * ny * nz
    for i in range(len(xs) - nx + 1):
        for j in range(len(ys) - ny + 1):
            for k in range(len(zs) - nz + 1):
                if block(i, j, k) != target:
                    continue
                # must rest on something: floor cell, or solid directly below
                if k > 0 and not solid[i : i + nx, j : j + ny, k - 1].any():
                    continue
                found.add(
                    (
                        int(round(xs[i] / LATTICE)),
                        int(round(ys[j] / LATTICE)),
                        int(round(zs[k] / 0.10)),
                    )
                )
    return len(found)


def main():
    print(f'{"case / container":30s} ' + " ".join(f"{n[:9]:>9s}" for n, *_ in TYPES))
    for path in sys.argv[1:]:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        for container in data["containers"]:
            counts = [slots(container, d) for _n, *d in TYPES]
            label = f'{data["case"]}/c{container["index"]}'
            print(f"{label:30s} " + " ".join(f"{v:9d}" for v in counts))


if __name__ == "__main__":
    main()
