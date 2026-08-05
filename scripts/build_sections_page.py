"""
Build the stowage-plan page from replay dumps.

Reads one or more packing-*.json dumps (produced by dump_packing.py from a
real replay) and emits a single self-contained HTML page of orthographic
sections. No external assets: the drawings are inline SVG computed from the
container's published half-spaces and the settled item AABBs.
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from render_sections import (  # noqa: E402
    View,
    axis_span,
    bounds,
    crosses,
    esc,
    item_class,
    poly_path,
    rect,
    section,
)

PAD = 34.0
VOID_CELL = 0.02
_UID = [0]


def uid():
    _UID[0] += 1
    return f"h{_UID[0]}"


def inside_poly(poly, u, v):
    """Even-odd test; the section polygons are convex so this is exact."""
    hit = False
    n = len(poly)
    for i in range(n):
        u0, v0 = poly[i]
        u1, v1 = poly[(i + 1) % n]
        if (v0 > v) != (v1 > v):
            cut = u0 + (v - v0) * (u1 - u0) / (v1 - v0)
            if u < cut:
                hit = not hit
    return hit


def sealed_cells(poly, boxes, u0, v0, u1, v1):
    """
    Cells inside the section that are free, but sit under something.

    This is a two-dimensional reading of dead space -- the void visible in
    THIS slice, not the 3-D covered_void the feature set computes. Called
    the same thing in a caption it would be a different number, so it is
    labelled as a slice quantity everywhere it appears.
    """
    nu = max(int((u1 - u0) / VOID_CELL), 1)
    nv = max(int((v1 - v0) / VOID_CELL), 1)
    cells = []
    for i in range(nu):
        u = u0 + (i + 0.5) * VOID_CELL
        column = []
        top = None
        for j in range(nv):
            v = v0 + (j + 0.5) * VOID_CELL
            if not inside_poly(poly, u, v):
                column.append(None)
                continue
            filled = any(
                a0 - 1e-9 <= u <= a1 + 1e-9 and b0 - 1e-9 <= v <= b1 + 1e-9
                for a0, b0, a1, b1 in boxes
            )
            column.append(filled)
            if filled:
                top = j
        if top is None:
            continue
        # merge each column's free cells into runs, so a slice emits tens of
        # rectangles rather than thousands
        run_start = None
        for j in range(top + 1):
            free = j < top and column[j] is False
            if free and run_start is None:
                run_start = j
            elif not free and run_start is not None:
                cells.append(
                    (
                        u0 + i * VOID_CELL,
                        v0 + run_start * VOID_CELL,
                        VOID_CELL,
                        (j - run_start) * VOID_CELL,
                        j - run_start,
                    )
                )
                run_start = None
    return cells, nu * nv


def ticks(view, step=0.25, label_every=None):
    # a 0.25 m label every tick is unreadable once the pane shrinks
    if label_every is None:
        label_every = 2 if view.s >= 150 else 4
    parts = []
    start = math.ceil(view.u0 / step) * step
    k = 0
    u = start
    while u <= view.u1 + 1e-9:
        x, _ = view.xy(u, view.v0)
        parts.append(
            f'<line class="tick" x1="{x:.1f}" y1="{view.h - PAD:.1f}" '
            f'x2="{x:.1f}" y2="{view.h - PAD + 5:.1f}"/>'
        )
        if k % label_every == 0:
            parts.append(
                f'<text class="dim" x="{x:.1f}" y="{view.h - PAD + 16:.1f}" '
                f'text-anchor="middle">{u:+.2f}</text>'
            )
        u += step
        k += 1
    start = math.ceil(view.v0 / step) * step
    k = 0
    v = start
    while v <= view.v1 + 1e-9:
        _, y = view.xy(view.u0, v)
        parts.append(
            f'<line class="tick" x1="{PAD - 5:.1f}" y1="{y:.1f}" '
            f'x2="{PAD:.1f}" y2="{y:.1f}"/>'
        )
        if k % label_every == 0:
            parts.append(
                f'<text class="dim" x="{PAD - 8:.1f}" y="{y + 3:.1f}" '
                f'text-anchor="end">{v:+.2f}</text>'
            )
        v += step
        k += 1
    return "".join(parts)


def pane(container, axis, value, scale, flip_u=False, mark=None, voids=True):
    keep = [i for i in (0, 1, 2) if i != axis]
    poly = section(container, axis, value)
    if not poly:
        return None
    u0, v0, u1, v1 = bounds([poly])
    view = View(u0, v0, u1, v1, scale, PAD, flip_u=flip_u)
    hatch = uid()
    out = [
        f'<svg viewBox="0 0 {view.w:.1f} {view.h:.1f}" '
        f'preserveAspectRatio="xMidYMid meet" role="img">',
        f'<defs><pattern id="{hatch}" width="6" height="6" '
        'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        f'<line class="hatchline" x1="0" y1="0" x2="0" y2="6"/></pattern></defs>',
    ]
    out.append(ticks(view))
    out.append(f'<polygon class="hull" points="{poly_path(view, poly)}"/>')

    cut_boxes = []
    for item in container["items"]:
        if not crosses(item, axis, value):
            continue
        lo0, hi0 = axis_span(item, keep[0])
        lo1, hi1 = axis_span(item, keep[1])
        cut_boxes.append((lo0, lo1, hi0, hi1))

    void_fraction = None
    if voids and cut_boxes:
        cells, total = sealed_cells(poly, cut_boxes, u0, v0, u1, v1)
        void_fraction = sum(run[4] for run in cells) / max(total, 1)
        for cu, cv, cw, ch, _n in cells:
            x, y = view.xy(cu, cv + ch)
            out.append(
                f'<rect fill="url(#{hatch})" x="{x:.2f}" y="{y:.2f}" '
                f'width="{cw * scale + .6:.2f}" height="{ch * scale + .6:.2f}" '
                'stroke="none"/>'
            )

    for shelf in container.get("shelves") or []:
        lo, hi = shelf["min"], shelf["max"]
        if not (lo[axis] - 1e-9 <= value <= hi[axis] + 1e-9):
            continue
        a0, b0 = lo[keep[0]], lo[keep[1]]
        a1, b1 = hi[keep[0]], hi[keep[1]]
        if (b1 - b0) * scale < 4:  # a 40 mm plate seen edge-on
            mid = (b0 + b1) / 2.0
            b0, b1 = mid - 2.0 / scale, mid + 2.0 / scale
        out.append(rect(view, a0, b0, a1, b1, "shelf"))

    ghosts, solids = [], []
    for index, item in enumerate(sorted(container["items"], key=lambda i: i["c"][2])):
        lo0, hi0 = axis_span(item, keep[0])
        lo1, hi1 = axis_span(item, keep[1])
        cut = crosses(item, axis, value)
        cls = f"box {item_class(item)}" + ("" if cut else " ghost")
        target = solids if cut else ghosts
        target.append(rect(view, lo0, lo1, hi0, hi1, cls))
        if cut:
            x, y = view.xy((lo0 + hi0) / 2.0, (lo1 + hi1) / 2.0)
            if abs(hi0 - lo0) * scale > 24 and abs(hi1 - lo1) * scale > 15:
                target.append(
                    f'<text class="tag" x="{x:.1f}" y="{y + 3.5:.1f}">{index + 1}</text>'
                )
    out.extend(ghosts)
    out.extend(solids)

    if mark is not None:
        out.append(mark(view))
    out.append("</svg>")
    return "".join(out), view, void_fraction


def station_marks(stations):
    def draw(view):
        parts = []
        for value in stations:
            x, _ = view.xy(value, view.v0)
            parts.append(
                f'<line class="trace" x1="{x:.1f}" y1="{PAD * 0.35:.1f}" '
                f'x2="{x:.1f}" y2="{view.h - PAD:.1f}"/>'
            )
        return "".join(parts)

    return draw


def wall_marks(container):
    """Label the two side walls, which are not at the same |y|."""

    def draw(view):
        ymin, ymax = view.u0, view.u1
        parts = []
        for value, text in ((ymin, f"{ymin:+.3f}"), (ymax, f"{ymax:+.3f}")):
            x, _ = view.xy(value, view.v1)
            anchor = "start" if value == ymin else "end"
            dx = 3 if value == ymin else -3
            parts.append(
                f'<text class="wall" x="{x + dx:.1f}" y="{PAD - 10:.1f}" '
                f'text-anchor="{anchor}">{text}</text>'
            )
        return "".join(parts)

    return draw


def deck_levels(container):
    bottoms = sorted({round(i["c"][2] - i["s"][2] / 2.0, 3) for i in container["items"]})
    levels = []
    for b in bottoms:
        mid = round(b + 0.06, 3)
        if all(abs(mid - z) > 0.15 for z in levels):
            levels.append(mid)
    return levels[:4] or [round(container["thickness"] + 0.06, 3)]


def stations(container):
    xs = sorted(i["c"][0] for i in container["items"])
    if not xs:
        return [0.0]
    lo, hi = xs[0], xs[-1]
    return [round(lo + (hi - lo) * f, 3) for f in (0.15, 0.5, 0.85)]


def readings(container):
    items = container["items"]
    if not items:
        return []
    width = container["width"]
    ymin = min(i["c"][1] - i["s"][1] / 2.0 for i in items)
    ymax = max(i["c"][1] + i["s"][1] / 2.0 for i in items)
    xmin = min(i["c"][0] - i["s"][0] / 2.0 for i in items)
    xmax = max(i["c"][0] + i["s"][0] / 2.0 for i in items)
    zmax = max(i["c"][2] + i["s"][2] / 2.0 for i in items)
    volume = sum(i["s"][0] * i["s"][1] * i["s"][2] for i in items)
    envelope = container["length"] * width * container["height"]

    cell = 0.05
    heights = {}
    for i in items:
        x0, x1 = i["c"][0] - i["s"][0] / 2.0, i["c"][0] + i["s"][0] / 2.0
        y0, y1 = i["c"][1] - i["s"][1] / 2.0, i["c"][1] + i["s"][1] / 2.0
        z0, z1 = i["c"][2] - i["s"][2] / 2.0, i["c"][2] + i["s"][2] / 2.0
        for a in range(int((x1 - x0) / cell) + 1):
            for b in range(int((y1 - y0) / cell) + 1):
                key = (round(x0 + a * cell, 2), round(y0 + b * cell, 2))
                heights.setdefault(key, []).append((z0, z1))
    void = 0.0
    for spans in heights.values():
        spans.sort()
        reach = container["thickness"]
        for z0, z1 in spans:
            if z0 > reach + 1e-6:
                void += (z0 - reach) * cell * cell
            reach = max(reach, z1)

    ywall_lo = min(p[1] for p, n in zip(container["points"], container["n_vecs"])
                   if n[1] < -0.5)
    ywall_hi = min(p[1] for p, n in zip(container["points"], container["n_vecs"])
                   if n[1] > 0.5)
    return [
        ("items stowed", f"{len(items)}"),
        ("soft / priority",
         f"{sum(1 for i in items if i['soft'])} / "
         f"{sum(1 for i in items if i['prio'])}"),
        ("occupied volume",
         f"{volume:.3f} m³ — {100 * volume / envelope:.1f}% of L·W·H"),
        ("side walls", f"y = {ywall_lo:+.3f} and {ywall_hi:+.3f} (not symmetric)"),
        ("y extent used", f"{ymin:+.3f} … {ymax:+.3f} m"),
        ("x extent used", f"{xmin:+.3f} … {xmax:+.3f} m"),
        ("stack height", f"{zmax:.3f} m of {container['height']:.3f}"),
        ("covered void (3-D)", f"{void:.3f} m³ sealed under stowed items"),
    ]


CSS = """
:root {
  color-scheme: light dark;
  --paper:#dde3e9; --sheet:#eef2f5; --ink:#101820; --ink-2:#38495b; --ink-3:#66788b;
  --rule:#93a6b8; --hull:#22364a; --cargo:#9fb2c4; --cargo-e:#5a7089;
  --soft:#d4762e; --soft-e:#8f4a15; --prio:#14958c; --prio-e:#0a5b55;
  --shelf:#57708a; --grid:rgba(47,71,95,.10); --hatch:rgba(34,54,74,.45);
}
@media (prefers-color-scheme: dark) {
  :root {
    --paper:#0b1016; --sheet:#141c25; --ink:#dce6ef; --ink-2:#9db0c2; --ink-3:#6c8093;
    --rule:#3d5063; --hull:#9ab8d4; --cargo:#465a70; --cargo-e:#93abc2;
    --soft:#9d5620; --soft-e:#e79c5c; --prio:#0d6b65; --prio-e:#52cdc3;
    --shelf:#5b7089; --grid:rgba(150,180,210,.08); --hatch:rgba(160,190,215,.40);
  }
}
:root[data-theme="dark"] {
  --paper:#0b1016; --sheet:#141c25; --ink:#dce6ef; --ink-2:#9db0c2; --ink-3:#6c8093;
  --rule:#3d5063; --hull:#9ab8d4; --cargo:#465a70; --cargo-e:#93abc2;
  --soft:#9d5620; --soft-e:#e79c5c; --prio:#0d6b65; --prio-e:#52cdc3;
  --shelf:#5b7089; --grid:rgba(150,180,210,.08); --hatch:rgba(160,190,215,.40);
}
:root[data-theme="light"] {
  --paper:#dde3e9; --sheet:#eef2f5; --ink:#101820; --ink-2:#38495b; --ink-3:#66788b;
  --rule:#93a6b8; --hull:#22364a; --cargo:#9fb2c4; --cargo-e:#5a7089;
  --soft:#d4762e; --soft-e:#8f4a15; --prio:#14958c; --prio-e:#0a5b55;
  --shelf:#57708a; --grid:rgba(47,71,95,.10); --hatch:rgba(34,54,74,.45);
}

* { box-sizing: border-box; }
body {
  margin:0; background:var(--paper); color:var(--ink);
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  font-size:15px; line-height:1.62;
}
.mono,.titleblock,.cap,table,.legend { font-family: ui-monospace, SFMono-Regular,
  "JetBrains Mono", Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; }
.wrap { max-width:1200px; margin:0 auto; padding:44px 22px 96px; }

h1 { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size:clamp(21px,3.3vw,33px); font-weight:700; letter-spacing:.11em;
  text-transform:uppercase; text-wrap:balance; margin:0 0 8px; }
.sub { color:var(--ink-2); max-width:66ch; margin:0 0 26px; }
h2 { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size:13px; letter-spacing:.2em; text-transform:uppercase; color:var(--ink-2);
  border-bottom:1px solid var(--rule); padding-bottom:8px; margin:56px 0 20px;
  font-weight:600; }
h3 { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:var(--ink-3);
  margin:30px 0 10px; font-weight:600; }
p { max-width:68ch; }

.titleblock { border:1px solid var(--rule); background:var(--sheet);
  display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); }
.titleblock > div { padding:11px 15px; border-right:1px solid var(--rule); }
.titleblock > div:last-child { border-right:0; }
.titleblock .k { font-size:10px; letter-spacing:.16em; text-transform:uppercase;
  color:var(--ink-3); display:block; margin-bottom:3px; }
.titleblock .v { font-size:16px; }

.row { display:flex; flex-wrap:wrap; gap:16px; align-items:flex-start; }
.fig { background:var(--sheet); border:1px solid var(--rule); padding:8px 8px 5px;
  background-image: linear-gradient(var(--grid) 1px, transparent 1px),
                    linear-gradient(90deg, var(--grid) 1px, transparent 1px);
  background-size:15px 15px; }
.fig svg { display:block; height:auto; max-width:100%; }
/* strips of small panes keep their drawn size and scroll, rather than
   shrinking until the dimension labels stop being readable */
.row.strip { flex-wrap:nowrap; }
.row.strip .fig { flex:0 0 auto; }
.row.strip .fig svg { max-width:none; }
.cap { font-size:10px; letter-spacing:.11em; text-transform:uppercase;
  color:var(--ink-3); padding-top:5px; border-top:1px solid var(--rule);
  margin-top:5px; }
.scroll { overflow-x:auto; padding-bottom:2px; }

.hull { fill:none; stroke:var(--hull); stroke-width:1.8; }
.shelf { fill:var(--shelf); opacity:.55; stroke:var(--shelf); stroke-width:1; }
.box { stroke-width:1.1; }
.box.reg { fill:var(--cargo); stroke:var(--cargo-e); }
.box.soft { fill:var(--soft); stroke:var(--soft-e); }
.box.prio { fill:var(--prio); stroke:var(--prio-e); stroke-width:2.2; }
.box.ghost { fill:none; stroke-dasharray:2 3; opacity:.34; stroke-width:.9; }
.trace { stroke:var(--hull); stroke-width:.9; stroke-dasharray:7 3 2 3; opacity:.6; }
.tick { stroke:var(--rule); stroke-width:1; }
.hatchline { stroke:var(--hatch); stroke-width:1.4; }
.tag { font-family: ui-monospace, Menlo, monospace; font-size:9px; fill:var(--ink);
  text-anchor:middle; opacity:.8; }
.dim { font-family: ui-monospace, Menlo, monospace; font-size:8.5px;
  fill:var(--ink-3); }
.wall { font-family: ui-monospace, Menlo, monospace; font-size:9.5px;
  fill:var(--hull); font-weight:700; }

.legend { display:flex; flex-wrap:wrap; gap:16px; font-size:11px; letter-spacing:.07em;
  text-transform:uppercase; color:var(--ink-2); margin:16px 0 0; }
.legend span { display:inline-flex; align-items:center; gap:7px; }
.sw { width:15px; height:11px; border:1px solid var(--cargo-e); background:var(--cargo);
  display:inline-block; flex:none; }
.sw.soft { background:var(--soft); border-color:var(--soft-e); }
.sw.prio { background:var(--prio); border-color:var(--prio-e); border-width:2px; }
.sw.ghost { background:none; border-style:dashed; }
.sw.shelf { background:var(--shelf); opacity:.6; }
.sw.void { background:repeating-linear-gradient(45deg, var(--hatch) 0 1.4px,
  transparent 1.4px 6px); border-color:var(--rule); }

table { border-collapse:collapse; font-size:13px; margin-top:14px; }
td, th { padding:5px 16px 5px 0; text-align:left; vertical-align:top; }
td.k { color:var(--ink-3); white-space:nowrap; }
.note { border-left:2px solid var(--rule); padding:2px 0 2px 16px; margin:22px 0;
  color:var(--ink-2); max-width:68ch; }
"""


def container_block(container, case_label):
    parts = [f"<h2>{esc(case_label)}</h2>"]
    levels = deck_levels(container)
    sts = stations(container)
    rows = readings(container)
    shelves = container.get("shelves") or []

    parts.append('<div class="titleblock">')
    parts.append(
        f'<div><span class="k">envelope L·W·H</span><span class="v mono">'
        f'{container["length"]:.2f} × {container["width"]:.2f} × '
        f'{container["height"]:.2f}</span></div>'
    )
    parts.append(
        f'<div><span class="k">shelves</span><span class="v mono">'
        f'{len(shelves)}'
        f'{" (incl. main)" if container["shelf"] else ""}</span></div>'
    )
    parts.append(
        f'<div><span class="k">priority container</span><span class="v mono">'
        f'{"yes" if container["prio"] else "no"}</span></div>'
    )
    for key, value in rows[:2]:
        parts.append(
            f'<div><span class="k">{esc(key)}</span>'
            f'<span class="v mono">{esc(value)}</span></div>'
        )
    parts.append("</div>")

    parts.append("<h3>Profile — section on the centreline, y = 0</h3>")
    built = pane(container, 1, 0.0, 168.0, mark=station_marks(sts))
    if built:
        svg, _view, void = built
        extra = "" if void is None else f" · dead space in slice {100 * void:.1f}%"
        parts.append(
            '<div class="scroll"><div class="fig">' + svg
            + '<div class="cap">x → · z ↑ · dash-dot = station '
            + esc(", ".join(f"x={s:+.2f}" for s in sts)) + esc(extra)
            + "</div></div></div>"
        )

    parts.append("<h3>Plan — deck by deck, looking down</h3>")
    parts.append('<div class="scroll"><div class="row strip">')
    for z in levels:
        built = pane(container, 2, z, 168.0)
        if not built:
            continue
        svg, _view, void = built
        extra = "" if void is None else f" · gaps {100 * void:.0f}%"
        parts.append(
            '<div class="fig">' + svg
            + f'<div class="cap">z = {z:+.3f} m · x → · y ↑{esc(extra)}'
            "</div></div>"
        )
    parts.append("</div></div>")

    parts.append("<h3>Stations — transverse sections, looking along +x</h3>")
    parts.append('<div class="scroll"><div class="row strip">')
    for x in sts:
        built = pane(container, 0, x, 155.0, mark=wall_marks(container))
        if not built:
            continue
        svg, _view, void = built
        extra = "" if void is None else f" · dead {100 * void:.0f}%"
        parts.append(
            '<div class="fig">' + svg
            + f'<div class="cap">x = {x:+.3f} m · y → · z ↑{esc(extra)}'
            "</div></div>"
        )
    parts.append("</div></div>")

    parts.append("<table><tbody>")
    for key, value in rows:
        parts.append(f'<tr><td class="k">{esc(key)}</td><td>{esc(value)}</td></tr>')
    parts.append("</tbody></table>")
    return "".join(parts)


def build(dumps, out_path, title, intro, notes_html=""):
    body = [
        '<div class="wrap">',
        f"<h1>{esc(title)}</h1>",
        f'<p class="sub">{intro}</p>',
        '<div class="legend">'
        '<span><i class="sw"></i>regular</span>'
        '<span><i class="sw soft"></i>soft</span>'
        '<span><i class="sw prio"></i>priority</span>'
        '<span><i class="sw ghost"></i>not cut by this plane</span>'
        '<span><i class="sw shelf"></i>shelf</span>'
        '<span><i class="sw void"></i>free but built over</span>'
        "</div>",
        notes_html,
    ]
    for path in dumps:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        for container in data["containers"]:
            label = (
                f'{data["case"]} · container {container["index"]} '
                f'· {data["steps"]} steps replayed'
            )
            body.append(container_block(container, label))
    body.append("</div>")
    html = f"<title>{esc(title)}</title>\n<style>{CSS}</style>\n" + "".join(body)
    pathlib.Path(out_path).write_text(html, encoding="utf-8")
    print(f"wrote {out_path} ({len(html):,} bytes)")


if __name__ == "__main__":
    build(
        sys.argv[2:],
        sys.argv[1],
        "Stowage sections",
        "Orthographic sections through containers packed by the shipped agent.",
    )
