"""gap_kpi.py <dir>...: the gaps between neighbouring boxes in a run's end states.

For every placed box, the nearest box (or wall) on each of its four sides
at the same height (the two boxes overlap by at least 5 cm vertically and
by at least 5 cm along the other axis); the gap is the distance between
the facing sides.  Reported per directory: the mean gap, the bands the
gaps fall in, the share of a row's length lost to gaps (sum of gaps over
sum of box widths plus gaps, along x and y), and the vertical gap under a
box that rests on another.  The agent plans with settled_clearance 0.026
+ anchor_slack 0.0005 between boxes; the validator asks 0.015 at
transport."""
import glob, json, sys
import numpy as np


def gaps_of(record):
    steps = [s for s in record["steps"] if s["event"] == "step"]
    boxes = {}
    for s in steps:
        x, y, z = s["pos_local"]; dx, dy, dz = s["size"]
        boxes.setdefault(s["container_idx"], []).append((x - dx / 2, x + dx / 2, y - dy / 2, y + dy / 2, z - dz / 2, z + dz / 2))
    out = []; row_loss = []; vgaps = []
    for ci, bs in boxes.items():
        arr = np.array(bs)
        for i, (x0, x1, y0, y1, z0, z1) in enumerate(bs):
            vo = (np.minimum(arr[:, 5], z1) - np.maximum(arr[:, 4], z0)) >= 0.05
            yo = (np.minimum(arr[:, 3], y1) - np.maximum(arr[:, 2], y0)) >= 0.05
            xo = (np.minimum(arr[:, 1], x1) - np.maximum(arr[:, 0], x0)) >= 0.05
            right = arr[vo & yo & (arr[:, 0] >= x1 - 1e-6), 0]
            left = arr[vo & yo & (arr[:, 1] <= x0 + 1e-6), 1]
            front = arr[vo & xo & (arr[:, 2] >= y1 - 1e-6), 2]
            back = arr[vo & xo & (arr[:, 3] <= y0 + 1e-6), 3]
            for side in (right - x1 if right.size else [], x0 - left if left.size else [], front - y1 if front.size else [], y0 - back if back.size else []):
                if len(side):
                    out.append(float(np.min(side)))
            # the box under it
            below = arr[(np.minimum(arr[:, 1], x1) - np.maximum(arr[:, 0], x0) >= 0.05) & yo & (arr[:, 5] <= z0 + 0.05) & (arr[:, 5] > z0 - 0.2), 5]
            if below.size and z0 > 0.1:
                vgaps.append(float(z0 - np.max(below)))
    return out, vgaps


def report(d):
    gaps = []; vg = []
    files = sorted(glob.glob(d + "/[abc]-*.json"))
    for f in files:
        g, v = gaps_of(json.load(open(f))); gaps += g; vg += v
    g = np.array(gaps); v = np.array(vg)
    bands = [(0, 0.02), (0.02, 0.03), (0.03, 0.05), (0.05, 0.10), (0.10, 0.20), (0.20, 9)]
    bd = ", ".join(f"{lo*100:.0f}-{hi*100:.0f}cm {np.mean((g >= lo) & (g < hi))*100:.0f}%" for lo, hi in bands)
    print(f"{d}: {len(files)} scenes, {len(g)} neighbour gaps: mean {g.mean()*100:.1f} cm, median {np.median(g)*100:.1f} cm; bands {bd}; "
          f"gaps over 5 cm hold {g[g >= 0.05].sum()/max(g.sum(),1e-9)*100:.0f}% of the gap length; "
          f"vertical gap under a stacked box: mean {v.mean()*100:.1f} cm, over 1 cm {np.mean(v > 0.01)*100:.0f}%")


for d in sys.argv[1:]:
    report(d)
