"""Vectorised twin of ``layer1.validate``.

The shipped ``validate`` re-parses every packed item's dict and tests every
(sample, obstacle) pair in Python; on a mid-episode board that is 3 000 calls
and two seconds per decision, ninety per cent of the planner's time.  This
module computes the same answer from cached obstacle arrays.  Same
inequalities, same constants, same order of reasons; ``tests/test_fastgeom.py``
checks the two agree on random boxes and the bench's negative control checks
they agree on whole episodes.
"""

from __future__ import annotations

import numpy as np

from ._reuse import (
    AABB,
    CONTACT_TOLERANCE,
    EPS,
    packed_aabbs_local,
    shelf_aabbs,
    transport_samples,
)

_CACHE: dict = {}
_CACHE_LIMIT = 16


def _key(container: dict) -> tuple:
    packed = container.get("packed_items", [])
    return (id(container), len(packed), tuple(id(p) for p in packed),
            bool(container.get("require_shelf", container.get("shelf", False))))


def obstacles(container: dict) -> dict:
    """Shelves and packed items of one container as arrays, cached.

    Returns ``{"shelf_min", "shelf_max", "shelf_names", "packed_min",
    "packed_max"}``; the packed arrays are (N, 3), the shelf arrays (S, 3)."""
    key = _key(container)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    shelves = list(shelf_aabbs(container))
    packed = [box for box, _soft, _prio in packed_aabbs_local(container)]
    out = {
        "shelf_min": np.array([s.minimum for s in shelves], dtype=np.float64).reshape(-1, 3),
        "shelf_max": np.array([s.maximum for s in shelves], dtype=np.float64).reshape(-1, 3),
        "shelf_names": [s.name for s in shelves],
        "packed_min": np.array([b.minimum for b in packed], dtype=np.float64).reshape(-1, 3),
        "packed_max": np.array([b.maximum for b in packed], dtype=np.float64).reshape(-1, 3),
    }
    if len(_CACHE) >= _CACHE_LIMIT:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = out
    return out


def _penetrates_any(cmin, cmax, omin, omax, clearance) -> np.ndarray:
    """Row-wise ``penetrates_with_lateral_clearance`` against (N, 3) arrays."""
    if omin.shape[0] == 0:
        return np.zeros(0, dtype=bool)
    vertical_gap = np.maximum(omin[:, 2] - cmax[2], cmin[2] - omax[:, 2])
    x_gap = np.maximum(omin[:, 0] - cmax[0], cmin[0] - omax[:, 0])
    y_gap = np.maximum(omin[:, 1] - cmax[1], cmin[1] - omax[:, 1])
    return (vertical_gap < -CONTACT_TOLERANCE) & (x_gap < clearance - EPS) & (y_gap < clearance - EPS)


def _within_clearance(smin, smax, omin, omax, clearance) -> np.ndarray:
    """(S, N) matrix of ``within_euclidean_clearance`` for S samples, N obstacles."""
    if omin.shape[0] == 0 or smin.shape[0] == 0:
        return np.zeros((smin.shape[0], omin.shape[0]), dtype=bool)
    gaps = np.maximum(
        0.0,
        np.maximum(omin[None, :, :] - smax[:, None, :], smin[:, None, :] - omax[None, :, :]),
    )
    return np.linalg.norm(gaps, axis=2) < float(clearance) - EPS


def validate(box: AABB, model, container: dict, config, action_center_fn, stability_fn):
    """Same verdicts as ``layer1.validate``; see that docstring for the rules."""
    if not model.inside(box, config.settled_wall_clearance, floor_clearance=0.0):
        return False, "settled-pose-outside"

    commanded = AABB(
        center=tuple(action_center_fn(box, model, container, config)),
        size=box.size,
        name="action",
    )
    if not model.inside(commanded, config.inclusion_clearance):
        return False, "outside-container"

    samples = transport_samples(box, container)
    if samples:
        transport_z = float(samples[0].center[2])
        transported = AABB(
            center=(float(box.center[0]), float(box.center[1]), transport_z),
            size=box.size,
            name="transported",
        )
        if not model.inside(transported, config.settled_wall_clearance, floor_clearance=0.0):
            return False, "transport-pose-outside"

    obs = obstacles(container)
    cmin = np.asarray(box.minimum, dtype=np.float64)
    cmax = np.asarray(box.maximum, dtype=np.float64)
    hit = _penetrates_any(cmin, cmax, obs["shelf_min"], obs["shelf_max"], config.settled_clearance)
    if hit.any():
        return False, f"overlaps-{obs['shelf_names'][int(np.argmax(hit))]}"
    hit = _penetrates_any(cmin, cmax, obs["packed_min"], obs["packed_max"], config.settled_clearance)
    if hit.any():
        return False, "overlaps-packed-item"

    stable, margin = stability_fn(box, container, config)
    if not stable:
        return False, (
            "no-support" if margin == -float("inf") else "centre-of-mass-outside-support"
        )

    if samples:
        half = np.asarray(box.size, dtype=np.float64) / 2.0
        centres = np.array([s.center for s in samples], dtype=np.float64)
        smin = centres - half
        smax = centres + half
        shelf_hits = _within_clearance(smin, smax, obs["shelf_min"], obs["shelf_max"], config.settled_clearance)
        packed_hits = _within_clearance(smin, smax, obs["packed_min"], obs["packed_max"], config.settled_clearance)
        shelf_rows = shelf_hits.any(axis=1) if shelf_hits.size else np.zeros(len(samples), dtype=bool)
        packed_rows = packed_hits.any(axis=1) if packed_hits.size else np.zeros(len(samples), dtype=bool)
        any_rows = shelf_rows | packed_rows
        if any_rows.any():
            first = int(np.argmax(any_rows))
            if shelf_rows[first]:
                name = obs["shelf_names"][int(np.argmax(shelf_hits[first]))]
                return False, f"transport-hits-{name}"
            return False, "transport-hits-packed-item"
    return True, "ok"
