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


def _swept_box(box: AABB, commanded: AABB, container: dict, config) -> AABB:
    """The box the production sample rules read: the box itself, or, when
    the commanded pose is the band lift (``band_lift_z``), the box raised
    to it -- the simulator's band and ceiling rules read the commanded
    height.  The floor and shelf lifts are the production's own and its
    rules already apply them."""
    if float(getattr(config, "band_lift", 0.0) or 0.0) <= 0.0:
        return box
    cz = float(box.center[2])
    band_z = band_lift_z(cz, float(box.size[2]) / 2.0, container, config)
    if abs(band_z - cz) <= 1e-9 or abs(float(commanded.center[2]) - band_z) > 1e-9:
        return box
    return AABB(center=(float(box.center[0]), float(box.center[1]), band_z), size=box.size, name=box.name)


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

    # the sweep of a band-lifted pose starts from the lifted box: the
    # production's sample rules read the box's own height
    swept = _swept_box(box, commanded, container, config)
    if getattr(config, "conservative_transport", True):
        from .transport import transport_samples as conservative_samples

        samples = conservative_samples(swept, container)
    else:
        samples = transport_samples(swept, container)
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


BAND_EDGE = 0.003
"""Slack at the edges of the simulator's zero-lift band (``band_lift_z``):
the band test runs in float32 on the platform, and a bottom within this
of an edge can fall on either side there."""


def band_lift_z(cz: float, hz: float, container: dict, config) -> float:
    """``config.band_lift``: the commanded centre z of a box whose bottom
    lies in the simulator's zero-lift band above the shelf level (within
    ``BAND_EDGE`` of its edges), raised so the bottom sits ``band_lift``
    above the band's top; the box's own z otherwise.  The caller applies
    it only when the simulator lifts nothing itself (floor and shelf
    contacts have their own lifts)."""
    lift = float(getattr(config, "band_lift", 0.0) or 0.0)
    if lift <= 0.0:
        return cz
    height = float(container["height"])
    buffer = float(container.get("buffer", 0.0))
    level = height / 2.0 + float(container["thickness"]) + buffer
    above = (cz - hz) - level
    if -BAND_EDGE <= above <= 0.05 + BAND_EDGE:
        return level + 0.05 + lift + hz
    # the mid-height ceiling rule: under the shelf level (a ceiling surface
    # in every container) the lift is clipped to the clearance less the
    # ceiling margin, so a top within the margin plus the sweep clearance
    # of the level rides in touching its support; and a top exactly at the
    # level is "under" it in float32.  Without a shelf there is nothing
    # above the level: the box is commanded with its top just over it, so
    # the rule does not fire and the usual lift applies.
    if bool(getattr(config, "band_lift_top", True)) and not bool(
            container.get("require_shelf", container.get("shelf", False))):
        k = _constants()
        mid = height / 2.0 + buffer
        below = mid - (cz + hz)
        dead = k["CEIL_MARGIN"] + k["CEIL_CLIP"] + max(0.016, float(getattr(config, "transport_clearance", 0.0) or 0.0))
        if -BAND_EDGE <= below <= dead + BAND_EDGE:
            return mid + lift - hz
    return cz


def action_center(box: AABB, model, container: dict, config):
    """``layer1.action_center`` without the AABB properties: the simulator's
    release height, plus rule-alpha's own floor lift when the simulator
    applied none, plus the band lift (``band_lift_z``) when neither did."""
    obs = obstacles(container)
    cx, cy, cz = (float(v) for v in box.center)
    hx, hy, hz = (float(v) / 2.0 for v in box.size)
    z = _sim_action_z(cx, cy, cz, hx, hy, hz, obs)
    if abs(z - cz) <= 1e-9:
        if abs((cz - hz) - model.z_floor) <= config.contact_tolerance:
            z = z + config.floor_action_lift
        else:
            z = band_lift_z(cz, hz, container, config)
    return np.array([cx, cy, z], dtype=np.float64)


def _transport(cx, cy, cz, hx, hz, container, obs, sim_z):
    """``transport_samples``' geometry without the AABBs: the sweep's z, its
    start x, and the entry y; the sample centres come from ``_samples``
    when an obstacle is at the sweep's height."""
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
    return transport_z, start_x, entry_y


def _samples(cx, cy, start_x, entry_y):
    """The sweep's sample centres: the y sweep from the opening at the start
    x, then the x sweep at the target y; the reference's ``entry +
    (target - entry) * (i / steps)`` per sample, the same operations."""
    import math

    step = _constants()["STEP"]
    dist_y = abs(cy - entry_y)
    steps_y = max(int(math.ceil(dist_y / step)), 1)
    dist_x = abs(cx - start_x)
    steps_x = max(int(math.ceil(dist_x / step)), 1)
    frac_y = np.arange(steps_y + 1, dtype=np.float64) / float(steps_y)
    frac_x = np.arange(steps_x + 1, dtype=np.float64) / float(steps_x)
    xs = np.concatenate([np.full(steps_y + 1, start_x), start_x + (cx - start_x) * frac_x])
    ys = np.concatenate([entry_y + (cy - entry_y) * frac_y, np.full(steps_x + 1, cy)])
    return xs, ys


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
    if abs(sim_z - cz) <= 1e-9:
        if abs((cz - hz) - model.z_floor) <= config.contact_tolerance:
            cmd_z = sim_z + config.floor_action_lift
        else:
            # the band lift is the commanded height, and the simulator's
            # own rules (the band, the ceiling clip) read that height
            sim_z = cmd_z = band_lift_z(cz, hz, container, config)
    wall = float(config.settled_wall_clearance)
    if not _inside(model, cx, cy, cz, hx, hy, hz, wall, 0.0):
        return False, "settled-pose-outside"
    if not _inside(model, cx, cy, cmd_z, hx, hy, hz, float(config.inclusion_clearance), None):
        return False, "outside-container"
    transport_z, start_x, entry_y = _transport(cx, cy, cz, hx, hz, container, obs, sim_z)
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
    return _sweep_verdict(cx, cy, hx, hy, hz, transport_z, start_x, entry_y, obs, sweep)


def _sweep_verdict(cx, cy, hx, hy, hz, transport_z, start_x, entry_y, obs, sweep):
    """The transport sweep's verdict for one box: ``(ok, reason)``."""
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
    xs, ys = _samples(cx, cy, start_x, entry_y)
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


# --- many boxes at once ---------------------------------------------------------
#
# The candidate generators (``layer1.generate_candidates``, the stack
# option's ``stack_candidates``) validate a grid of anchors at one height
# and one size, and read only the verdict.  On the sample's Task A dry-run
# that is 190 000 distinct calls of ``validate`` at 0.13 ms each, three
# quarters of the dry-run.  ``validate_points`` gives the same verdicts for
# a whole grid: the geometry of every check in one numpy pass over the
# points (the same expressions, so the same floating-point numbers), the
# stability rule and the transport sweep only for the points the geometry
# accepts, one at a time as before.


def _inside_many(model, cx, cy, cz, hx, hy, hz, clearance, floor_clearance):
    """``_inside`` for arrays ``cx``, ``cy`` and a scalar or array ``cz``."""
    rows, floor_index = _planes(model)
    limit = -clearance + 1e-9
    floor_limit = limit if floor_clearance is None else -floor_clearance + 1e-9
    ok = np.ones(cx.shape[0], dtype=bool)
    for i, (n0, n1, n2, p0, p1, p2, a0, a1, a2) in enumerate(rows):
        signed = (n0 * (cx - p0) + n1 * (cy - p1) + n2 * (cz - p2)) + (a0 * hx + a1 * hy + a2 * hz)
        ok &= ~(signed > (floor_limit if i == floor_index else limit))
    return ok


def validate_points(points, z: float, size, model, container: dict, config, stability_fn) -> list:
    """``validate(AABB((x, y, z), size))[0]`` for every ``(x, y)`` of
    ``points``, in order.  The same verdicts as ``validate``, from the same
    expressions; the reasons are not computed.  With
    ``conservative_transport`` the boxes go through ``validate`` one by one."""
    points = list(points)
    if not points:
        return []
    if getattr(config, "conservative_transport", True):
        return [validate(AABB((float(x), float(y), float(z)), size, "candidate"), model, container, config,
                         action_center, stability_fn)[0] for x, y in points]
    obs = obstacles(container)
    k = _constants()
    cz = float(z)
    sx, sy, sz = (float(v) for v in size)
    hx, hy, hz = sx / 2.0, sy / 2.0, sz / 2.0
    cx = np.array([float(x) for x, _y in points], dtype=np.float64)
    cy = np.array([float(y) for _x, y in points], dtype=np.float64)
    n = cx.shape[0]

    # the commanded pose (rule-alpha's action centre) and the sweep's height
    zmin = cz - hz
    cmin_x, cmax_x, cmin_y, cmax_y = cx - hx, cx + hx, cy - hy, cy + hy
    sim_z = np.full(n, cz, dtype=np.float64)
    lifted = np.zeros(n, dtype=bool)
    smin, smax = obs["shelf_min"], obs["shelf_max"]
    for i in range(obs["n_shelves"]):
        if abs(zmin - float(smax[i, 2])) <= CONTACT_TOLERANCE:
            ox = np.maximum(0.0, np.minimum(cmax_x, float(smax[i, 0])) - np.maximum(cmin_x, float(smin[i, 0])))
            oy = np.maximum(0.0, np.minimum(cmax_y, float(smax[i, 1])) - np.maximum(cmin_y, float(smin[i, 1])))
            lifted |= ox * oy > EPS
    if lifted.any():
        sim_z[lifted] = cz + k["SHELF_LIFT"]
    if abs(zmin - obs["floor_top"]) <= CONTACT_TOLERANCE:
        sim_z[~lifted] = cz + k["FLOOR_LIFT"]
        lifted[:] = True
    cmd_z = sim_z.copy()
    if not lifted.all():
        # the points the simulator lifts nothing for: the floor lift of
        # rule-alpha's own, else the band lift (a function of z alone)
        if abs((cz - hz) - model.z_floor) <= config.contact_tolerance:
            cmd_z[~lifted] = cz + config.floor_action_lift
        else:
            band = band_lift_z(cz, hz, container, config)
            sim_z[~lifted] = band
            cmd_z[~lifted] = band
    wall = float(config.settled_wall_clearance)
    ok = _inside_many(model, cx, cy, cz, hx, hy, hz, wall, 0.0)
    ok &= _inside_many(model, cx, cy, cmd_z, hx, hy, hz, float(config.inclusion_clearance), None)

    # ``_transport``
    length = float(container["length"])
    width = float(container["width"])
    thickness = float(container["thickness"])
    cut_x = float(container.get("cut_x", 0.0))
    x_min = -length / 2.0 + thickness + cut_x + hx + k["START"]
    x_max = length / 2.0 - thickness - hx - k["START"]
    start_x = np.minimum(np.maximum(cx, x_min), x_max)
    entry_y = -width / 2.0
    height = float(container["height"])
    buffer = float(container.get("buffer", 0.0))
    bottom_z = sim_z - hz
    eff = np.full(n, k["DROP"], dtype=np.float64)
    for resting_z in (thickness, height / 2.0 + thickness + buffer):
        rest = bottom_z - resting_z
        eff[(0.0 <= rest) & (rest <= 0.05)] = 0.0
    top_z = sim_z + hz
    open_ = eff > 0.0
    for ceiling_z in (height / 2.0 + buffer, height + buffer - thickness):
        clearance = ceiling_z - top_z
        hit = open_ & (0.0 <= clearance) & (clearance < eff + k["CEIL_MARGIN"])
        if hit.any():
            eff[hit] = np.maximum(0.0, clearance[hit] - k["CEIL_MARGIN"] - k["CEIL_CLIP"])
            open_ &= ~hit
    maximum_start_z = height + buffer - thickness - hz - k["START"]
    transport_z = np.minimum(maximum_start_z, sim_z + eff)
    ok &= _inside_many(model, cx, cy, transport_z, hx, hy, hz, wall, 0.0)

    # the settled box against every shelf and packed item
    omin, omax = obs["all_min"], obs["all_max"]
    if omin.shape[0] and ok.any():
        clearance = config.settled_clearance
        cmin_z, cmax_z = cz - hz, cz + hz
        vertical_gap = np.maximum(omin[None, :, 2] - cmax_z, cmin_z - omax[None, :, 2])
        x_gap = np.maximum(omin[None, :, 0] - cmax_x[:, None], cmin_x[:, None] - omax[None, :, 0])
        y_gap = np.maximum(omin[None, :, 1] - cmax_y[:, None], cmin_y[:, None] - omax[None, :, 1])
        hit = (vertical_gap < -CONTACT_TOLERANCE) & (x_gap < clearance - EPS) & (y_gap < clearance - EPS)
        ok &= ~hit.any(axis=1)

    sweep = float(getattr(config, "transport_clearance", None) or config.settled_clearance)
    out = ok.tolist()
    survivors = np.nonzero(ok)[0].tolist()
    if not survivors:
        return out
    # the stability rule for every survivor in one pass over the structure
    # (stability.evaluate_points), unless the caller's rule is another
    from . import stability as _stability

    if stability_fn is _stability.is_stable:
        states = _stability.evaluate_points(cx[survivors], cy[survivors], cz, (sx, sy, sz), container, config)
        stable = [s.margin >= config.com_margin for s in states]
    else:
        stable = [stability_fn(AABB((float(cx[i]), float(cy[i]), cz), (sx, sy, sz), "candidate"), container, config)[0]
                  for i in survivors]
    swept = []
    for i, ok_i in zip(survivors, stable):
        if not ok_i:
            out[i] = False
        else:
            swept.append(i)
    if not swept or omin.shape[0] == 0:
        return out
    # the transport sweep of every stable survivor at once: each sweep's
    # samples (``_samples``, the same centres) stacked, every obstacle's
    # clearance to every sample in one pass, an obstacle counted for a
    # sample only when its gap in z alone is under the clearance (the
    # ``near`` rule of ``_sweep_verdict``, so the same comparisons)
    tz = transport_z[swept]
    z_gap = np.maximum(0.0, np.maximum(omin[None, :, 2] - (tz + hz)[:, None], (tz - hz)[:, None] - omax[None, :, 2]))
    near = z_gap < sweep - EPS
    xs_all, ys_all, owner = [], [], []
    for j, i in enumerate(swept):
        if not near[j].any():
            continue
        xs, ys = _samples(float(cx[i]), float(cy[i]), float(start_x[i]), entry_y)
        xs_all.append(xs)
        ys_all.append(ys)
        owner.append(np.full(xs.shape[0], j, dtype=np.int64))
    if not xs_all:
        return out
    xs = np.concatenate(xs_all)
    ys = np.concatenate(ys_all)
    owner = np.concatenate(owner)
    m = xs.shape[0]
    smin = np.empty((m, 3), dtype=np.float64)
    smax = np.empty((m, 3), dtype=np.float64)
    smin[:, 0] = xs - hx
    smin[:, 1] = ys - hy
    smin[:, 2] = tz[owner] - hz
    smax[:, 0] = xs + hx
    smax[:, 1] = ys + hy
    smax[:, 2] = tz[owner] + hz
    hits = _within_clearance(smin, smax, omin, omax, sweep) & near[owner]
    for j in np.unique(owner[hits.any(axis=1)]).tolist():
        out[swept[j]] = False
    return out


def lift_to_tops(box: AABB, container: dict, config) -> AABB:
    """The box raised to rest on the highest packed top under its footprint.

    The generators anchor a box at one support's top; when its footprint
    spans a neighbour a few centimetres taller the validator refuses the
    pose as ``overlaps-packed-item`` and the place is lost, although a box
    set down there would simply rest on the taller neighbour (c-hard-s0048
    declined at 20 of 40 with a 0.6 x 0.8 m plateau at 0.85 m under 0.7 m
    of headroom: every anchor on it sat 2.5 cm inside the taller column).
    Packed items that overlap the footprint laterally (within the settled
    clearance) and cross the plane of the box's bottom lift it to their
    top, repeatedly; a lift beyond ``config.lift_to_tops`` metres (or none
    needed) returns the box as it was.  Overhangs above the lifted pose are
    the validator's to refuse."""
    limit = float(getattr(config, "lift_to_tops", 0.0) or 0.0)
    if limit <= 0.0:
        return box
    obs = obstacles(container)
    n = obs["n_shelves"]
    omin, omax = obs["all_min"][n:], obs["all_max"][n:]
    if omin.shape[0] == 0:
        return box
    cx, cy, cz = (float(v) for v in box.center)
    sx, sy, sz = (float(v) for v in box.size)
    hx, hy, hz = sx / 2.0, sy / 2.0, sz / 2.0
    clearance = float(config.settled_clearance)
    x_gap = np.maximum(omin[:, 0] - (cx + hx), (cx - hx) - omax[:, 0])
    y_gap = np.maximum(omin[:, 1] - (cy + hy), (cy - hy) - omax[:, 1])
    lateral = (x_gap < clearance - EPS) & (y_gap < clearance - EPS)
    if not lateral.any():
        return box
    tops = omax[lateral, 2]
    bottoms = omin[lateral, 2]
    bottom = cz - hz
    start = bottom
    for _ in range(8):
        crossing = (tops > bottom + CONTACT_TOLERANCE) & (bottoms < bottom + CONTACT_TOLERANCE)
        if not crossing.any():
            break
        bottom = float(tops[crossing].max())
        if bottom - start > limit + EPS:
            return box
    if bottom - start <= EPS:
        return box
    return AABB((cx, cy, bottom + hz), (sx, sy, sz), box.name)
