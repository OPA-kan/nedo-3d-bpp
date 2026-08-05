"""
Orthographic cross-sections of a real packed container.

Every number in the output comes from a replay dump (dump_packing.py): the
container half-spaces exactly as the simulator publishes them, and the item
AABBs exactly as `packed_aabbs_local` reports them after settling. Nothing
here is idealised -- the envelope is the intersection of the published
planes, not the box formula, which is the whole reason the drawing is worth
looking at.

Sections are taken the way a loading plan takes them:
  PLAN          x-y at chosen z levels (deck by deck)
  PROFILE       x-z at y = 0 (centreline, looking to port)
  STATIONS      y-z at chosen x (body plan)
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

BIG = 100.0


def clip(poly, a, b, c):
    """Sutherland-Hodgman clip of `poly` by the half-plane a*u + b*v <= c."""
    if not poly:
        return poly
    out = []
    n = len(poly)
    for i in range(n):
        u0, v0 = poly[i]
        u1, v1 = poly[(i + 1) % n]
        d0 = a * u0 + b * v0 - c
        d1 = a * u1 + b * v1 - c
        if d0 <= 0:
            out.append((u0, v0))
        if (d0 < 0 < d1) or (d1 < 0 < d0):
            t = d0 / (d0 - d1)
            out.append((u0 + t * (u1 - u0), v0 + t * (v1 - v0)))
    return out


def section(container, axis, value):
    """
    Polygon of the container interior on a plane normal to `axis`.

    axis 2 (z=value) returns (x, y); axis 1 (y=value) returns (x, z);
    axis 0 (x=value) returns (y, z). Coordinates are LOCAL -- the planes are
    published in a frame offset in x, so the offset is removed here rather
    than added to every item.
    """
    keep = [i for i in (0, 1, 2) if i != axis]
    offset = float(container.get("offset_x") or 0.0)
    poly = [(-BIG, -BIG), (BIG, -BIG), (BIG, BIG), (-BIG, BIG)]
    for point, normal in zip(container["points"], container["n_vecs"]):
        p = list(point)
        p[0] -= offset
        # n . (q - p) <= 0, with q pinned on the section plane
        rhs = sum(normal[i] * p[i] for i in range(3)) - normal[axis] * value
        a, b = normal[keep[0]], normal[keep[1]]
        if abs(a) < 1e-12 and abs(b) < 1e-12:
            if rhs < -1e-9:
                return []
            continue
        poly = clip(poly, a, b, rhs)
        if not poly:
            return []
    return poly


def bounds(polys):
    us = [u for poly in polys for u, _ in poly]
    vs = [v for poly in polys for _, v in poly]
    return min(us), min(vs), max(us), max(vs)


class View:
    """One orthographic pane: world (u, v) -> SVG (x, y), v pointing up."""

    def __init__(self, u0, v0, u1, v1, scale, pad, flip_u=False):
        self.u0, self.v0, self.u1, self.v1 = u0, v0, u1, v1
        self.s = scale
        self.pad = pad
        self.flip_u = flip_u
        self.w = (u1 - u0) * scale + 2 * pad
        self.h = (v1 - v0) * scale + 2 * pad

    def xy(self, u, v):
        x = (self.u1 - u) * self.s if self.flip_u else (u - self.u0) * self.s
        return x + self.pad, (self.v1 - v) * self.s + self.pad


def esc(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def poly_path(view, poly):
    if not poly:
        return ""
    pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in (view.xy(u, v) for u, v in poly))
    return pts


def item_class(item):
    if item["prio"]:
        return "prio"
    if item["soft"]:
        return "soft"
    return "reg"


def rect(view, umin, vmin, umax, vmax, cls, extra=""):
    x0, y0 = view.xy(umin, vmax)
    x1, y1 = view.xy(umax, vmin)
    x, w = min(x0, x1), abs(x1 - x0)
    y, h = min(y0, y1), abs(y1 - y0)
    return (
        f'<rect class="{cls}" x="{x:.2f}" y="{y:.2f}" '
        f'width="{w:.2f}" height="{h:.2f}"{extra}/>'
    )


def axis_span(item, axis):
    c = item["c"][axis]
    s = item["s"][axis] / 2.0
    return c - s, c + s


def crosses(item, axis, value):
    lo, hi = axis_span(item, axis)
    return lo - 1e-9 <= value <= hi + 1e-9


def draw_pane(container, axis, value, title, subtitle, scale, flip_u=False):
    """A single sectioned pane, returned as (svg, height)."""
    keep = [i for i in (0, 1, 2) if i != axis]
    poly = section(container, axis, value)
    if not poly:
        return "", 0.0
    u0, v0, u1, v1 = bounds([poly])
    pad = 30.0
    view = View(u0, v0, u1, v1, scale, pad, flip_u=flip_u)

    parts = [
        f'<svg class="pane" viewBox="0 0 {view.w:.1f} {view.h:.1f}" '
        f'width="{view.w:.1f}" height="{view.h:.1f}" role="img" '
        f'aria-label="{esc(title)} {esc(subtitle)}">'
    ]
    # envelope
    parts.append(f'<polygon class="hull" points="{poly_path(view, poly)}"/>')

    # shelves, where the plane meets them
    for shelf in container.get("shelves") or []:
        lo, hi = shelf["min"], shelf["max"]
        if not (lo[axis] - 1e-9 <= value <= hi[axis] + 1e-9):
            continue
        parts.append(
            rect(view, lo[keep[0]], lo[keep[1]], hi[keep[0]], hi[keep[1]], "shelf")
        )

    # items: solid where the plane cuts them, ghosted where it does not
    for item in sorted(container["items"], key=lambda i: i["c"][2]):
        lo0, hi0 = axis_span(item, keep[0])
        lo1, hi1 = axis_span(item, keep[1])
        cut = crosses(item, axis, value)
        cls = f"box {item_class(item)}" + ("" if cut else " ghost")
        parts.append(rect(view, lo0, lo1, hi0, hi1, cls))

    parts.append("</svg>")
    return "".join(parts), view.h


def deck_levels(container):
    """z levels worth drawing: just above the floor, then each item top."""
    tops = sorted({round(i["c"][2] + i["s"][2] / 2.0, 3) for i in container["items"]})
    bottoms = sorted({round(i["c"][2] - i["s"][2] / 2.0, 3) for i in container["items"]})
    levels = []
    for b in bottoms:
        mid = b + 0.05
        if all(abs(mid - z) > 0.12 for z in levels):
            levels.append(round(mid, 3))
    return levels[:4] or [container["thickness"] + 0.05]


def load(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    data = load(sys.argv[1])
    for c in data["containers"]:
        print(
            f"container {c['index']}: {len(c['items'])} items, "
            f"decks {deck_levels(c)}"
        )
        poly = section(c, 2, c["thickness"] + 0.05)
        print("  plan polygon:", [(round(u, 3), round(v, 3)) for u, v in poly])
