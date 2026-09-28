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
    cache_lookup,
    packed_aabbs_local,
    shelf_aabbs,
    transport_samples,
)

_CACHE: dict = {}
_CACHE_LIMIT = 16


def _compute_obstacles(container: dict) -> dict:
    shelves = list(shelf_aabbs(container))
    packed = [box for box, _soft, _prio in packed_aabbs_local(container)]
    shelf_min = np.array([s.minimum for s in shelves], dtype=np.float64).reshape(-1, 3)
    shelf_max = np.array([s.maximum for s in shelves], dtype=np.float64).reshape(-1, 3)
    packed_min = np.array([b.minimum for b in packed], dtype=np.float64).reshape(-1, 3)
    packed_max = np.array([b.maximum for b in packed], dtype=np.float64).reshape(-1, 3)
    return {
        "shelf_min": shelf_min,
        "shelf_max": shelf_max,
        "shelf_names": [s.name for s in shelves],
        "packed_min": packed_min,
        "packed_max": packed_max,
        # shelves then packed items in one pair of arrays, for one pass
        "all_min": np.concatenate([shelf_min, packed_min], axis=0),
        "all_max": np.concatenate([shelf_max, packed_max], axis=0),
        "n_shelves": int(shelf_min.shape[0]),
        "floor_top": float(container["thickness"]) + float(container.get("buffer", 0.0)),
    }


def obstacles(container: dict) -> dict:
    """Shelves and packed items of one container as arrays, cached on the
    identity of the container and its packed-item dicts (see
    ``_reuse.cache_lookup`` for why identity alone is not enough).

    Returns ``{"shelf_min", "shelf_max", "shelf_names", "packed_min",
    "packed_max"}``; the packed arrays are (N, 3), the shelf arrays (S, 3)."""
    return cache_lookup(_CACHE, _CACHE_LIMIT, container, _compute_obstacles)


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


def _validate_v1(box: AABB, model, container: dict, config, action_center_fn, stability_fn):
    """The first vectorised form: the reference's structure with cached
    obstacle arrays.  Kept as the oracle the faster form is tested against."""
    if not model.inside(box, config.settled_wall_clearance, floor_clearance=0.0):
        return False, "settled-pose-outside"

    commanded = AABB(
        center=tuple(action_center_fn(box, model, container, config)),
        size=box.size,
        name="action",
    )
    if not model.inside(commanded, config.inclusion_clearance):
        return False, "outside-container"

    if getattr(config, "conservative_transport", True):
        from .transport import transport_samples as conservative_samples

        samples = conservative_samples(box, container)
    else:
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
        sweep = getattr(config, "transport_clearance", None) or config.settled_clearance
        shelf_hits = _within_clearance(smin, smax, obs["shelf_min"], obs["shelf_max"], sweep)
        packed_hits = _within_clearance(smin, smax, obs["packed_min"], obs["packed_max"], sweep)
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


# --- the faster form ---------------------------------------------------------
#
# ``_validate_v1`` spends its time outside the geometry: three ``inside``
# calls of a few numpy operations each, the official ``transport_samples``
# building an AABB per sweep sample, ``simulator_action_center`` through the
# AABB properties (``minimum``/``maximum`` rebuild two arrays a call), and the
# AABB property calls of the box itself.  On a mid-episode board that was
# 0.47 ms a call and 70 % of a decision.  This form computes the same numbers
# from the box's centre and size as Python floats, the container's planes as
# cached arrays, and the sweep's sample centres as one array; the inequalities
# and the order of the reasons are the reference's.

_P = _reuse_module = None


def _constants():
    global _P
    if _P is None:
        from . import _reuse

        prod = _reuse._production
        _P = {
            "DROP": float(prod.SIMULATOR_DROP_HEIGHT),
            "START": float(prod.SIMULATOR_START_MARGIN),
            "CEIL_MARGIN": float(prod.SIMULATOR_CEILING_MARGIN),
            "CEIL_CLIP": float(prod.SIMULATOR_CEILING_CLIP_EPS),
            "SHELF_LIFT": float(prod.SHELF_ACTION_LIFT),
            "FLOOR_LIFT": float(prod.FLOOR_ACTION_LIFT),
            "STEP": float(prod.TRANSPORT_SAMPLE_STEP),
        }
    return _P


def _planes(model):
    """The container's planes as Python floats: a list of (n0, n1, n2, p0,
    p1, p2, |n0|, |n1|, |n2|) per plane, and the floor plane's index."""
    cached = getattr(model, "_fg_planes", None)
    if cached is None:
        normals = np.asarray(model.plane_normals, dtype=np.float64)
        points = np.asarray(model.plane_points, dtype=np.float64)
        rows = []
        for n, p in zip(normals, points):
            rows.append((float(n[0]), float(n[1]), float(n[2]), float(p[0]), float(p[1]), float(p[2]),
                         abs(float(n[0])), abs(float(n[1])), abs(float(n[2]))))
        cached = (rows, int(model.floor_plane_index))
        try:
            model._fg_planes = cached
        except AttributeError:
            pass
    return cached


def _inside(model, cx, cy, cz, hx, hy, hz, clearance, floor_clearance):
    """``model.inside`` in Python floats: every plane's signed distance of
    the box's farthest corner, ``n . (c - p) + |n| . h``, within the
    clearance (the floor plane's own when given).  The sums run in the
    reference's order, so the numbers are the same."""
    rows, floor_index = _planes(model)
    limit = -clearance + 1e-9
    floor_limit = limit if floor_clearance is None else -floor_clearance + 1e-9
    for i, (n0, n1, n2, p0, p1, p2, a0, a1, a2) in enumerate(rows):
        signed = (n0 * (cx - p0) + n1 * (cy - p1) + n2 * (cz - p2)) + (a0 * hx + a1 * hy + a2 * hz)
        if signed > (floor_limit if i == floor_index else limit):
            return False
    return True


def _sim_action_z(cx, cy, cz, hx, hy, hz, obs):
    """``simulator_action_center``'s z for a settled box (x and y are the
    box's own)."""
    k = _constants()
    zmin = cz - hz
    cmin_x, cmax_x, cmin_y, cmax_y = cx - hx, cx + hx, cy - hy, cy + hy
    smin, smax = obs["shelf_min"], obs["shelf_max"]
    for i in range(obs["n_shelves"]):
        if abs(zmin - float(smax[i, 2])) <= CONTACT_TOLERANCE:
            ox = max(0.0, min(cmax_x, float(smax[i, 0])) - max(cmin_x, float(smin[i, 0])))
            oy = max(0.0, min(cmax_y, float(smax[i, 1])) - max(cmin_y, float(smin[i, 1])))
            if ox * oy > EPS:
                return cz + k["SHELF_LIFT"]
    if abs(zmin - obs["floor_top"]) <= CONTACT_TOLERANCE:
        return cz + k["FLOOR_LIFT"]
    return cz


def action_center(box: AABB, model, container: dict, config):
    """``layer1.action_center`` without the AABB properties: the simulator's
    release height, plus rule-alpha's own floor lift when the simulator
    applied none."""
    obs = obstacles(container)
    cx, cy, cz = (float(v) for v in box.center)
    hx, hy, hz = (float(v) / 2.0 for v in box.size)
    z = _sim_action_z(cx, cy, cz, hx, hy, hz, obs)
    if abs(z - cz) <= 1e-9 and abs((cz - hz) - model.z_floor) <= config.contact_tolerance:
        z = z + config.floor_action_lift
    return np.array([cx, cy, z], dtype=np.float64)


def _transport(cx, cy, cz, hx, hz, container, obs, sim_z):
    """``transport_samples``' geometry without the AABBs: the sweep's z and
    its sample centres (the y sweep from the opening, then the x sweep)."""
    import math

    k = _constants()
    length = float(container["length"])
    width = float(container["width"])
    thickness = float(container["thickness"])
    cut_x = float(container.get("cut_x", 0.0))
    x_min = -length / 2.0 + thickness + cut_x + hx + k["START"]
    x_max = length / 2.0 - thickness - hx - k["START"]
    start_x = min(max(cx, x_min), x_max)
    entry_y = -width / 2.0
    height = float(container["height"])
    buffer = float(container.get("buffer", 0.0))
    effective_start_z = k["DROP"]
    bottom_z = sim_z - hz
    for resting_z in (thickness, height / 2.0 + thickness + buffer):
        if 0.0 <= bottom_z - resting_z <= 0.05:
            effective_start_z = 0.0
            break
    top_z = sim_z + hz
    if effective_start_z > 0.0:
        for ceiling_z in (height / 2.0 + buffer, height + buffer - thickness):
            clearance = ceiling_z - top_z
            if 0.0 <= clearance < effective_start_z + k["CEIL_MARGIN"]:
                effective_start_z = max(0.0, clearance - k["CEIL_MARGIN"] - k["CEIL_CLIP"])
                break
    maximum_start_z = height + buffer - thickness - hz - k["START"]
    transport_z = min(maximum_start_z, sim_z + effective_start_z)
    step = k["STEP"]
    dist_y = abs(cy - entry_y)
    steps_y = max(int(math.ceil(dist_y / step)), 1)
    dist_x = abs(cx - start_x)
    steps_x = max(int(math.ceil(dist_x / step)), 1)
    # the reference's ``entry + (target - entry) * (i / steps)`` per sample,
    # the same operations elementwise
    frac_y = np.arange(steps_y + 1, dtype=np.float64) / float(steps_y)
    frac_x = np.arange(steps_x + 1, dtype=np.float64) / float(steps_x)
    xs = np.concatenate([np.full(steps_y + 1, start_x), start_x + (cx - start_x) * frac_x])
    ys = np.concatenate([entry_y + (cy - entry_y) * frac_y, np.full(steps_x + 1, cy)])
    return transport_z, xs, ys


def validate(box: AABB, model, container: dict, config, action_center_fn, stability_fn):
    """Same verdicts as ``layer1.validate``; see that docstring for the rules."""
    if getattr(config, "conservative_transport", True):
        return _validate_v1(box, model, container, config, action_center_fn, stability_fn)
    obs = obstacles(container)
    cx, cy, cz = (float(v) for v in box.center)
    sx, sy, sz = (float(v) for v in box.size)
    hx, hy, hz = sx / 2.0, sy / 2.0, sz / 2.0
    # the commanded pose (rule-alpha's action centre) and the sweep's height
    sim_z = _sim_action_z(cx, cy, cz, hx, hy, hz, obs)
    cmd_z = sim_z
    if abs(sim_z - cz) <= 1e-9 and abs((cz - hz) - model.z_floor) <= config.contact_tolerance:
        cmd_z = sim_z + config.floor_action_lift
    wall = float(config.settled_wall_clearance)
    if not _inside(model, cx, cy, cz, hx, hy, hz, wall, 0.0):
        return False, "settled-pose-outside"
    if not _inside(model, cx, cy, cmd_z, hx, hy, hz, float(config.inclusion_clearance), None):
        return False, "outside-container"
    transport_z, xs, ys = _transport(cx, cy, cz, hx, hz, container, obs, sim_z)
    if not _inside(model, cx, cy, transport_z, hx, hy, hz, wall, 0.0):
        return False, "transport-pose-outside"

    cmin = np.array([cx - hx, cy - hy, cz - hz], dtype=np.float64)
    cmax = np.array([cx + hx, cy + hy, cz + hz], dtype=np.float64)
    hit = _penetrates_any(cmin, cmax, obs["all_min"], obs["all_max"], config.settled_clearance)
    if hit.any():
        first = int(np.argmax(hit))
        if first < obs["n_shelves"]:
            return False, f"overlaps-{obs['shelf_names'][first]}"
        return False, "overlaps-packed-item"

    stable, margin = stability_fn(box, container, config)
    if not stable:
        return False, (
            "no-support" if margin == -float("inf") else "centre-of-mass-outside-support"
        )

    sweep = float(getattr(config, "transport_clearance", None) or config.settled_clearance)
    omin, omax = obs["all_min"], obs["all_max"]
    if omin.shape[0] == 0:
        return True, "ok"
    # every sample rides at the sweep's height, so an obstacle whose gap in
    # z alone reaches the clearance cannot be within it on any sample (the
    # norm is at least the z gap): the sweep is tested against the rest
    z_gap = np.maximum(0.0, np.maximum(omin[:, 2] - (transport_z + hz), (transport_z - hz) - omax[:, 2]))
    near = np.nonzero(z_gap < sweep - EPS)[0]
    if near.shape[0] == 0:
        return True, "ok"
    n = xs.shape[0]
    smin = np.empty((n, 3), dtype=np.float64)
    smax = np.empty((n, 3), dtype=np.float64)
    smin[:, 0] = xs - hx
    smin[:, 1] = ys - hy
    smin[:, 2] = transport_z - hz
    smax[:, 0] = xs + hx
    smax[:, 1] = ys + hy
    smax[:, 2] = transport_z + hz
    hits = _within_clearance(smin, smax, omin[near], omax[near], sweep)
    rows = hits.any(axis=1)
    if rows.any():
        first = int(np.argmax(rows))
        n_shelves = obs["n_shelves"]
        row = hits[first]
        shelf_cols = near < n_shelves
        if shelf_cols.any() and row[shelf_cols].any():
            k = int(near[shelf_cols][int(np.argmax(row[shelf_cols]))])
            return False, f"transport-hits-{obs['shelf_names'][k]}"
        return False, "transport-hits-packed-item"
    return True, "ok"
