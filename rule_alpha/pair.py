"""The same-class pair reservation on Task B (``config.pair_reserve``).

The piece instrument (findings, "Where the empty volume is made") charged
the lone 0.55 x 0.40 x 0.24 floor box 0.14 of the container a placement,
59 % of it the column over its own top: 0.40 is 3 cm short of the window
of the smallest hard class, so a lone one of these carries nothing until
a second top of its height sits within about 4 cm of it, and two side by
side are 0.80 x 0.55, a window and more.  ``pair_key`` (a tie-break
towards a top of the same height within 6 cm) was inert: the lone box is
laid when nothing of its height is near it yet, and the pair needs the
*next* box, which Task C cannot see.  Task B can: its pool holds ten
items with their sizes.

So on Task B the pair is made in two calls.  When the ladder's pick for a
pool item is a floor pose of a box whose flat top alone cannot hold the
window (``narrow_top``: derived from ``pair_key_window`` plus the
instrument's clearance, not from a class) and the pool holds another item
of the same class, footprint and height, the pick is taken from the
first ``pair_reserve_k`` survivors of its rung, in the rung's order, that
leave room beside themselves for the partner: a pose of the same
dimensions flush along the side whose pair holds the window
(``pair_holds_window``; the short side of the 0.55 x 0.40 box, since
1.10 x 0.40 holds nothing), the settled clearance plus
``pair_reserve_slack`` between them, inside the floor and clear of the
packed boxes (``layer1.validate``).  The spot is reserved for one call.
On the next, the partner still in the pool and the spot still free
beside the box as it settled, the partner goes there first, through the
validator, the cover rule and the shadow gate like any pose; otherwise
the call falls through to the normal flow and the reservation is lost.
"""

from __future__ import annotations

from ._reuse import AABB, packed_dimensions, packed_position_world, world_to_local

# the instrument's clearance around the window (surface.CLEAR)
CLEAR = 0.03


def window_dims(config) -> tuple[float, float]:
    """The window of the smallest hard class, short side first."""
    spec = str(getattr(config, "pair_key_window", "0.40x0.55"))
    a, b = sorted(float(v) for v in spec.lower().split("x")[:2])
    return a, b


def narrow_top(dx: float, dy: float, config) -> bool:
    """A top ``dx x dy`` alone cannot hold the window with the clearance."""
    a, b = window_dims(config)
    lo, hi = sorted((float(dx), float(dy)))
    return lo + 1e-6 < a + CLEAR or hi + 1e-6 < b + CLEAR


def pair_holds_window(dx: float, dy: float, gap: float, axis: int, config) -> bool:
    """Two tops ``dx x dy`` side by side along ``axis`` (0: x, 1: y), the
    gap between them bridged as the surface instrument bridges it, hold
    the window with the clearance."""
    if axis == 0:
        w, l = 2.0 * float(dx) + float(gap), float(dy)
    else:
        w, l = float(dx), 2.0 * float(dy) + float(gap)
    lo, hi = sorted((w, l))
    a, b = window_dims(config)
    return lo + 1e-6 >= a + CLEAR and hi + 1e-6 >= b + CLEAR


def is_flat(dims) -> bool:
    """The pose lies on its largest face: the height is the smallest dimension."""
    dx, dy, dz = (float(v) for v in dims)
    return dz <= min(dx, dy) + 1e-6


def spot_box(first: AABB, axis: int, sign: int, gap: float, z_floor: float) -> AABB:
    """The partner's box: the first box's dimensions, flush beside it along
    ``axis`` in the direction ``sign``, on the floor."""
    size = tuple(float(v) for v in first.size)
    centre = [float(v) for v in first.center]
    centre[axis] += float(sign) * (size[axis] + float(gap))
    centre[2] = float(z_floor) + size[2] / 2.0
    return AABB(tuple(centre), size, "pair")


def directions(first: AABB, gap: float, config, preferred=None) -> list[tuple[int, int]]:
    """The (axis, sign) pairs whose pair holds the window, the preferred one
    first, then the deeper spot (towards the back wall, +y) before the
    shallower and the one nearer the slope wall (-x) before the other."""
    size = first.size
    out = []
    for axis in (0, 1):
        if not pair_holds_window(size[0], size[1], gap, axis, config):
            continue
        for sign in (1, -1):
            out.append((axis, sign))

    def key(d):
        axis, sign = d
        if preferred is not None and (axis, sign) == tuple(preferred):
            return (0, 0.0, 0.0)
        centre = spot_box(first, axis, sign, gap, 0.0).center
        return (1, -float(centre[1]), float(centre[0]))

    return sorted(out, key=key)


def find_spot(first: AABB, model, container: dict, config, gap: float, preferred=None,
              validate=None, covers=None):
    """The first direction whose spot the validator (and the cover rule,
    when given) accepts: ``(axis, sign, box)`` or None."""
    if validate is None:
        from . import layer1

        validate = lambda box: layer1.validate(box, model, container, config)  # noqa: E731
    for axis, sign in directions(first, gap, config, preferred):
        box = spot_box(first, axis, sign, gap, float(model.z_floor))
        ok, _reason = validate(box)
        if not ok:
            continue
        if covers is not None and covers(box):
            continue
        return axis, sign, box
    return None


def packed_box(container: dict, index: int) -> AABB | None:
    """The packed item with manifest index ``index`` as a local box, as it
    settled, or None."""
    for packed in container.get("packed_items", []) or []:
        try:
            if int(packed.get("index", -1)) != int(index):
                continue
            centre = world_to_local(packed_position_world(packed), container)
            dims = packed_dimensions(packed)
        except (KeyError, TypeError, ValueError):
            continue
        return AABB(tuple(float(v) for v in centre), tuple(float(v) for v in dims), "packed_item")
    return None


def same_class_partner(pool: list, pool_index: int, item: dict):
    """The first other pool item of the same class with the same
    dimensions (to the millimetre, whichever way round): ``(pool index,
    manifest index)`` or None."""
    try:
        dims = sorted(round(float(item[k]), 3) for k in ("length", "width", "height"))
    except (KeyError, TypeError, ValueError):
        return None
    soft, prio = bool(item.get("is_soft", False)), bool(item.get("is_prioritized", False))
    for j, other in enumerate(pool):
        if j == pool_index:
            continue
        if bool(other.get("is_soft", False)) != soft or bool(other.get("is_prioritized", False)) != prio:
            continue
        try:
            if sorted(round(float(other[k]), 3) for k in ("length", "width", "height")) != dims:
                continue
            return j, int(other["index"])
        except (KeyError, TypeError, ValueError):
            continue
    return None
