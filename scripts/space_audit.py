"""
Where does the empty space in a finished container actually go?

The sections make it obvious that a lot is left over; this puts a number on
each cause, because they are not the same kind of problem:

  outside envelope   the chamfer wedge and the wall clearances. Not
                     recoverable by any policy -- it is the container.
  shelf              the plates themselves.
  occupied           stowed items.
  open from above    free, with nothing above it. A drop can still reach
                     here, so this is space the agent declined.
  built over         free, with something above it. Unreachable by a
                     vertical release: lost when it was covered.

Voxels, not analysis: a 25 mm grid over the container's bounding box, tested
against the published half-spaces and the settled AABBs. Coarse enough to run
instantly, fine enough that the categories do not blur.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

CELL = 0.025


def audit(container):
    offset = float(container.get("offset_x") or 0.0)
    points = np.asarray(container["points"], dtype=np.float64)
    normals = np.asarray(container["n_vecs"], dtype=np.float64)
    points = points.copy()
    points[:, 0] -= offset

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

    occupied = np.zeros(len(pts), dtype=bool)
    for item in container["items"]:
        c = np.asarray(item["c"])
        s = np.asarray(item["s"]) / 2.0
        occupied |= np.all(np.abs(pts - c) <= s, axis=1)

    shelf = np.zeros(len(pts), dtype=bool)
    for plate in container.get("shelves") or []:
        lo = np.asarray(plate["min"])
        hi = np.asarray(plate["max"])
        shelf |= np.all((pts >= lo) & (pts <= hi), axis=1)

    shape = gx.shape
    solid = (occupied | shelf).reshape(shape)
    covered = np.zeros(shape, dtype=bool)
    # anything with solid material above it in the same column
    above = np.cumsum(solid[:, :, ::-1], axis=2)[:, :, ::-1] > 0
    covered = above & ~solid

    inside3 = inside.reshape(shape)
    occ3 = occupied.reshape(shape)
    shelf3 = shelf.reshape(shape)
    free3 = inside3 & ~solid
    built_over = free3 & covered
    open_above = free3 & ~covered

    voxel = CELL ** 3
    box = container["length"] * container["width"] * height
    return {
        "box_volume": box,
        "envelope": float(inside3.sum()) * voxel,
        "outside_envelope": box - float(inside3.sum()) * voxel,
        "occupied": float((occ3 & inside3).sum()) * voxel,
        "shelf": float((shelf3 & inside3).sum()) * voxel,
        "built_over": float(built_over.sum()) * voxel,
        "open_above": float(open_above.sum()) * voxel,
    }


def main():
    print(
        f'{"case / container":34s} {"envelope":>9s} {"stowed":>8s} '
        f'{"open":>8s} {"built over":>11s} {"chamfer+walls":>14s}'
    )
    totals = {}
    for path in sys.argv[1:]:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        for container in data["containers"]:
            r = audit(container)
            label = f'{data["case"]}/c{container["index"]}'
            env = r["envelope"]
            print(
                f'{label:34s} {env:9.3f} '
                f'{r["occupied"]:8.3f} {r["open_above"]:8.3f} '
                f'{r["built_over"]:11.3f} {r["outside_envelope"]:14.3f}'
            )
            print(
                f'{"":34s} {"":9s} '
                f'{100 * r["occupied"] / env:7.1f}% '
                f'{100 * r["open_above"] / env:7.1f}% '
                f'{100 * r["built_over"] / env:10.1f}% '
                f'{100 * r["outside_envelope"] / r["box_volume"]:13.1f}%'
            )
            for key, value in r.items():
                totals[key] = totals.get(key, 0.0) + value
    env = totals["envelope"]
    print(
        f'\nacross {len(sys.argv) - 1} dumps, of the space inside the envelope:'
        f'\n  stowed items      {100 * totals["occupied"] / env:5.1f}%'
        f'\n  shelf plates      {100 * totals["shelf"] / env:5.1f}%'
        f'\n  free, reachable   {100 * totals["open_above"] / env:5.1f}%'
        f'  <- a drop can still land here'
        f'\n  free, built over  {100 * totals["built_over"] / env:5.1f}%'
        f'  <- lost when it was covered'
    )
    print(
        f'\nand {100 * totals["outside_envelope"] / totals["box_volume"]:.1f}% of '
        f'length x width x height is outside the envelope entirely '
        f'(chamfer + wall clearance), which no policy can use.'
    )


if __name__ == "__main__":
    main()
