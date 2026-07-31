"""
S1 plumbing: canonical-frame local heightmap patches for the slide line.

Extracts, for every release row with settle labels, a local heightmap
patch around the commanded (x, y) expressed in the S0 canonical frame
(row axis = downhill direction u, column axis = transverse v), plus the
S0 scalar features and targets, and stores everything as one .npz for
the future S1 encoder. No model is trained here.

In the canonical frame, mirror augmentation is a single flip along the
transverse axis (with d_trans negated) -- the ingredient L_inv needs.
Heights are relative to the predicted rest height z_rest, clipped to
[-PATCH_DEPTH, PATCH_DEPTH].
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.evaluate_release_risk as err  # noqa: E402
import scripts.evaluate_mechanics_features as emf  # noqa: E402
import scripts.evaluate_slide_equivariant as ese  # noqa: E402

DEFAULT_DATASET_ROOT = ROOT / "reports" / "replay-dataset"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "slide-patches"
PATCH_CELLS = 16
PATCH_METERS = 0.64
PATCH_DEPTH = 0.5


def surface_universe(agent, container: dict[str, Any]):
    """(x0, x1, y0, y1, top) surfaces: floor, shelves, packed AABBs."""
    floor_top = float(container["thickness"]) + float(
        container.get("buffer", 0.0)
    )
    length = float(container["length"])
    width = float(container["width"])
    surfaces = [
        (-length / 2.0, length / 2.0, -width / 2.0, width / 2.0, floor_top)
    ]
    for box in agent.shelf_aabbs(container):
        surfaces.append(
            (
                float(box.minimum[0]),
                float(box.maximum[0]),
                float(box.minimum[1]),
                float(box.maximum[1]),
                float(box.top),
            )
        )
    for box, _soft, _prio in agent.packed_aabbs_local(container):
        surfaces.append(
            (
                float(box.minimum[0]),
                float(box.maximum[0]),
                float(box.minimum[1]),
                float(box.maximum[1]),
                float(box.top),
            )
        )
    return surfaces


def height_at(surfaces, x: float, y: float) -> float:
    best = -math.inf
    for x0, x1, y0, y1, top in surfaces:
        if x0 <= x <= x1 and y0 <= y <= y1 and top > best:
            best = top
    return best if math.isfinite(best) else 0.0


def canonical_patch(
    surfaces,
    x: float,
    y: float,
    u: tuple[float, float],
    z_rest: float,
    cells: int = PATCH_CELLS,
    meters: float = PATCH_METERS,
) -> np.ndarray:
    """
    Heightmap in the canonical frame: rows advance along +u (downhill),
    columns along +v (transverse, v = rotate90(u)). Heights relative to
    z_rest, clipped to +-PATCH_DEPTH.
    """
    ux, uy = u
    vx, vy = -uy, ux
    half = meters / 2.0
    step = meters / cells
    patch = np.zeros((cells, cells), dtype=np.float32)
    for i in range(cells):
        a = -half + step * (i + 0.5)
        for j in range(cells):
            b = -half + step * (j + 0.5)
            gx = x + a * ux + b * vx
            gy = y + a * uy + b * vy
            patch[i, j] = height_at(surfaces, gx, gy) - z_rest
    return np.clip(patch, -PATCH_DEPTH, PATCH_DEPTH)


def build(dataset_dirs: list[pathlib.Path]) -> dict[str, Any]:
    agent = emf.load_agent_module()
    rows = ese.prepare(dataset_dirs)
    containers = emf.load_containers(dataset_dirs)

    patches = []
    scalars = []
    d_long = []
    d_trans = []
    d_mag = []
    snapshot_ids = []
    splits = []
    surface_cache: dict[tuple[str, str], Any] = {}
    for row in rows:
        source = row["_source"]
        key = (source["_dataset_dir"], source["snapshot_path"])
        container = containers.get(key)
        if container is None:
            continue
        if key not in surface_cache:
            surface_cache[key] = surface_universe(agent, container)
        x, y, z_command = (float(v) for v in source["center"])
        dims = tuple(float(v) for v in source["size"])
        z_rest = float(agent.release_rest_height(x, y, dims, container))
        contact = emf.contact_patches(agent, container, x, y, dims, z_rest)
        centroid = ese.support_centroid(contact)
        if centroid is None:
            continue
        ex, ey = x - centroid[0], y - centroid[1]
        norm = math.hypot(ex, ey)
        u = (ex / norm, ey / norm) if norm >= 1e-9 else (1.0, 0.0)
        patches.append(
            canonical_patch(surface_cache[key], x, y, u, z_rest)
        )
        scalars.append(
            [row["features"][k] for k in ese.EQUIVARIANT_FEATURES]
        )
        d_long.append(row["d_long"])
        d_trans.append(row["d_trans"])
        d_mag.append(row["d_mag"])
        snapshot_ids.append(row["snapshot_id"])
        splits.append(source["_split"])

    return {
        "patches": np.stack(patches) if patches else np.zeros((0,)),
        "scalars": np.array(scalars, dtype=np.float32),
        "d_long": np.array(d_long, dtype=np.float32),
        "d_trans": np.array(d_trans, dtype=np.float32),
        "d_mag": np.array(d_mag, dtype=np.float32),
        "snapshot_ids": np.array(snapshot_ids),
        "splits": np.array(splits),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset-root", type=pathlib.Path, default=DEFAULT_DATASET_ROOT
    )
    parser.add_argument(
        "--output-dir", type=pathlib.Path, default=DEFAULT_OUTPUT_DIR
    )
    args = parser.parse_args()
    dataset_dirs = sorted(
        path for path in args.dataset_root.iterdir() if path.is_dir()
    )
    data = build(dataset_dirs)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    npz_path = args.output_dir / "slide-patches.npz"
    np.savez_compressed(npz_path, **data)
    meta = {
        "rows": int(len(data["d_mag"])),
        "snapshots": int(len(set(data["snapshot_ids"].tolist()))),
        "patch_cells": PATCH_CELLS,
        "patch_meters": PATCH_METERS,
        "patch_depth_clip": PATCH_DEPTH,
        "scalar_order": list(ese.EQUIVARIANT_FEATURES),
        "frame": (
            "rows advance along +u (downhill), columns along +v; mirror "
            "augmentation = flip axis 1 and negate d_trans"
        ),
        "splits": {
            split: int((data["splits"] == split).sum())
            for split in sorted(set(data["splits"].tolist()))
        },
    }
    (args.output_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(npz_path, meta["rows"], "rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
