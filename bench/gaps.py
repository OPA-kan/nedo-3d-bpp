"""The gaps between neighbouring boxes in an end state, as metrics.

For every placed box, the nearest box on each of its four sides at the
same height (the two overlap by at least 5 cm vertically and by at
least 5 cm along the other axis); the gap is the distance between the
facing sides.  Walls do not count.  The agent plans with
``settled_clearance`` 0.026 + ``anchor_slack`` 0.0005 between boxes
where the validator asks 0.015 at transport, so a tight load shows a
2-3 cm band; the strips the floor map shows (findings, "The hard
suites") are the gaps of 10 cm and more.  Measured from the planned
poses in the step records (the settled drift is under a millimetre on
the suites)."""

from __future__ import annotations

import numpy as np


def gap_metrics(steps: list[dict]) -> dict:
    boxes: dict[int, list[tuple]] = {}
    for s in steps:
        if s.get("event") != "step" or "pos_local" not in s or "size" not in s:
            continue
        x, y, z = s["pos_local"]
        dx, dy, dz = s["size"]
        boxes.setdefault(int(s["container_idx"]), []).append(
            (x - dx / 2, x + dx / 2, y - dy / 2, y + dy / 2, z - dz / 2, z + dz / 2))
    gaps: list[float] = []
    vgaps: list[float] = []
    for bs in boxes.values():
        arr = np.array(bs, dtype=np.float64)
        for x0, x1, y0, y1, z0, z1 in bs:
            vo = (np.minimum(arr[:, 5], z1) - np.maximum(arr[:, 4], z0)) >= 0.05
            yo = (np.minimum(arr[:, 3], y1) - np.maximum(arr[:, 2], y0)) >= 0.05
            xo = (np.minimum(arr[:, 1], x1) - np.maximum(arr[:, 0], x0)) >= 0.05
            right = arr[vo & yo & (arr[:, 0] >= x1 - 1e-6), 0]
            left = arr[vo & yo & (arr[:, 1] <= x0 + 1e-6), 1]
            front = arr[vo & xo & (arr[:, 2] >= y1 - 1e-6), 2]
            back = arr[vo & xo & (arr[:, 3] <= y0 + 1e-6), 3]
            for side in ((right - x1) if right.size else None, (x0 - left) if left.size else None,
                         (front - y1) if front.size else None, (y0 - back) if back.size else None):
                if side is not None and side.size:
                    gaps.append(float(np.min(side)))
            below = arr[xo & yo & (arr[:, 5] <= z0 + 0.05) & (arr[:, 5] > z0 - 0.2), 5]
            if below.size and z0 > 0.1:
                vgaps.append(float(z0 - np.max(below)))
    g = np.array(gaps) if gaps else np.zeros(0)
    v = np.array(vgaps) if vgaps else np.zeros(0)
    return {
        "gap_count": int(g.size),
        "gap_mean_cm": round(float(g.mean()) * 100, 2) if g.size else 0.0,
        "gap_median_cm": round(float(np.median(g)) * 100, 2) if g.size else 0.0,
        # the planned clearance band, and the strips
        "gap_tight_share": round(float(np.mean(g < 0.03)), 3) if g.size else 0.0,
        "gap_strip_share": round(float(np.mean(g >= 0.10)), 3) if g.size else 0.0,
        "vertical_gap_mean_cm": round(float(v.mean()) * 100, 2) if v.size else 0.0,
    }
