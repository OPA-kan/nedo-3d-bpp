"""render.py <record> <scene> <t> [ci] -- ASCII top view of container ci after the
first t placements: top heights in decimetres (0-9, then a-h for 1.0-1.7 m),
'.' bare floor, the back wall at the top, the door at the bottom.  Placement t-1
(the newest) is upper-cased letters?  No: its cells are shown in brackets via a
second map underneath.  Sealed spot centres of the end board's visible items
(trace JSON) are marked '*' in the second map."""

from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sealkit as K  # noqa: E402

DIG = "0123456789abcdefghij"


def heightmap(ep, cs, ci, cell=0.04):
    m = ep.models[ci]
    r = m.floor_rect
    xs = np.arange(r.x_min + cell / 2, r.x_max, cell)
    ys = np.arange(r.y_min + cell / 2, r.y_max, cell)
    top = np.full((len(xs), len(ys)), np.nan)
    who = np.full((len(xs), len(ys)), -1)
    for k, it in enumerate(cs[ci]["packed_items"]):
        c = np.asarray(it["pos"])
        d = np.asarray(it["dims"])
        ix = (xs >= c[0] - d[0] / 2) & (xs <= c[0] + d[0] / 2)
        iy = (ys >= c[1] - d[1] / 2) & (ys <= c[1] + d[1] / 2)
        sub = top[np.ix_(ix, iy)]
        t = c[2] + d[2] / 2
        upd = np.isnan(sub) | (sub < t)
        sub[upd] = t
        top[np.ix_(ix, iy)] = sub
        w = who[np.ix_(ix, iy)]
        w[upd] = k
        who[np.ix_(ix, iy)] = w
    return xs, ys, top, who


def render(ep, t, ci, marks=(), newest=None, cell=0.04):
    cs = ep.containers_at(t)
    xs, ys, top, who = heightmap(ep, cs, ci, cell)
    zf = ep.models[ci].z_floor
    lines = []
    mk = set()
    for x, y in marks:
        mk.add((int(np.argmin(abs(xs - x))), int(np.argmin(abs(ys - y)))))
    for j in range(len(ys) - 1, -1, -1):
        row = ""
        for i in range(len(xs)):
            if (i, j) in mk:
                row += "*"
            elif np.isnan(top[i, j]):
                row += "."
            else:
                h = top[i, j] - zf
                ch = DIG[min(len(DIG) - 1, int(h * 10))]
                if newest is not None and who[i, j] == newest:
                    ch = ch.upper() if ch.isalpha() else "#"
                row += ch
        lines.append(f"{ys[j]:+.2f} |{row}|")
    lines.append("       " + "door (y min) " + f"x {xs[0]:+.2f}..{xs[-1]:+.2f}")
    return "\n".join(lines)


def main():
    rec, scene, t = sys.argv[1], sys.argv[2], int(sys.argv[3])
    ci = int(sys.argv[4]) if len(sys.argv) > 4 else None
    ep = K.Episode(K.load_record(rec, scene))
    tr = os.path.join(
        os.environ.get("SCRATCH", "/home/user/inv-G-scratch"),
        "trace",
        rec,
        scene + ".json",
    )
    marks = []
    if os.path.exists(tr):
        d = json.load(open(tr))
        for p in d["patches"]:
            if ci is None or p["ci"] == ci:
                marks += [(x[0], x[1]) for x in p.get("spots_xy", [])]
    if ci is None:
        ci = ep.placements[t - 1]["ci"] if t > 0 else 0
    newest = None
    if t > 0 and ep.placements[t - 1]["ci"] == ci:
        newest = sum(1 for p in ep.placements[:t] if p["ci"] == ci) - 1
    print(
        f"{scene} after {t} placements, container {ci}; newest = {'#' if newest is not None else '-'} "
        f"{ep.placements[t - 1]['step'].get('archetype') if t else ''}"
    )
    print(render(ep, t, ci, marks, newest))


if __name__ == "__main__":
    main()
