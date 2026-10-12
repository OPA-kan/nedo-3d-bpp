"""piece_makers.py <record_dir>...: which placements turn the container's volume into pieces.

``phase_volume.py`` found that at the phase boundary (usable surface
under 0.2 of the floor area) half the container's volume is already in
*pieces* -- volume over level patches too small for the smallest hard
footprint (0.43 x 0.58 with the clearances, tops within 2 cm) -- and
that the end state's 0.40 is what is left of them.  This follows the
pieces step by step: for every placement the pieces volume before and
after, so that each placement is charged what it made (or credited what
it consumed), and the piece it made is split into the column over its
own top (its top too narrow for the window, or a soft top) and the rest
(the surface beside it that lost the window).  Per archetype, per pose,
per phase of the usable surface: how much of the pieces each made, and
whether the piece is its own top or the surface it broke.
"""
import collections
import glob
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from levelness import _scene  # noqa: E402
from soft_slots_b import CELL, Load  # noqa: E402

WINDOW = (0.43, 0.58)
LOW = 0.23 + 0.03
BRIDGE = "--bridge" in sys.argv
from rule_alpha.surface import _close_gaps  # noqa: E402


class Volume:
    """One container's heightmap on the 2 cm grid with the pieces reading
    of ``end_states.floor_and_volume``, updated a box at a time."""

    def __init__(self, c):
        L, W, H, t = c["length"], c["width"], c["height"], c["thickness"]
        self.L, self.W = L, W
        self.nx, self.ny = int(round(L / CELL)), int(round(W / CELL))
        wall = np.zeros((self.nx, self.ny), dtype=bool)
        tc = max(1, int(round(t / CELL)))
        cut = int(round((c.get("cut_x", 0.0) + t) / CELL))
        wall[:cut, :] = True
        wall[-tc:, :] = True
        wall[:, :tc] = True
        wall[:, -tc:] = True
        self.real = ~wall
        self.height = np.zeros((self.nx, self.ny), dtype=float)
        self.soft_top = np.zeros((self.nx, self.ny), dtype=bool)
        self.inner_h = H - t
        self.cap = float(self.real.sum()) * CELL * CELL * self.inner_h

    def cells(self, s):
        x, y, _z = s["pos_local"]
        sx, sy, _sz = s["size"]
        i0 = max(0, int((x - sx / 2 + self.L / 2) / CELL))
        i1 = min(self.nx, int(round((x + sx / 2 + self.L / 2) / CELL)))
        j0 = max(0, int((y - sy / 2 + self.W / 2) / CELL))
        j1 = min(self.ny, int(round((y + sy / 2 + self.W / 2) / CELL)))
        return i0, i1, j0, j1

    def add(self, s, soft):
        i0, i1, j0, j1 = self.cells(s)
        top = s["pos_local"][2] + s["size"][2] / 2
        sub = self.height[i0:i1, j0:j1]
        raised = top > sub
        sub[raised] = top
        self.soft_top[i0:i1, j0:j1][raised] = bool(soft)

    def masks(self):
        head = np.clip(self.inner_h - self.height, 0.0, None)
        low = self.real & (head < LOW)
        usable = np.zeros_like(self.real)
        levels = np.round(self.height / 0.02).astype(int)
        base = self.real & ~low & ~self.soft_top
        nxw, nyw = int(round(WINDOW[0] / CELL)), int(round(WINDOW[1] / CELL))
        for level in np.unique(levels[base]):
            on = base & (np.abs(levels - level) <= 1)
            if BRIDGE and level > 0:
                on = _close_gaps(on, 1) & base
            if on.sum() < nxw * nyw:
                continue
            s = np.zeros((on.shape[0] + 1, on.shape[1] + 1), dtype=np.int32)
            s[1:, 1:] = np.cumsum(np.cumsum(on.astype(np.int32), axis=0), axis=1)
            for a, b in ((nxw, nyw), (nyw, nxw)):
                if a > on.shape[0] or b > on.shape[1]:
                    continue
                tot = s[a:, b:] - s[:-a, b:] - s[a:, :-b] + s[:-a, :-b]
                origins = tot == a * b
                if not origins.any():
                    continue
                o = np.zeros((on.shape[0] + 1, on.shape[1] + 1), dtype=np.int32)
                o[1:on.shape[0] - a + 2, 1:on.shape[1] - b + 2] = np.cumsum(np.cumsum(origins.astype(np.int32), 0), 1)
                i = np.arange(on.shape[0]); j = np.arange(on.shape[1])
                hi_i = np.minimum(i, on.shape[0] - a) + 1; lo_i = np.maximum(i - a + 1, 0)
                hi_j = np.minimum(j, on.shape[1] - b) + 1; lo_j = np.maximum(j - b + 1, 0)
                cover = o[np.ix_(hi_i, hi_j)] - o[np.ix_(lo_i, hi_j)] - o[np.ix_(hi_i, lo_j)] + o[np.ix_(lo_i, lo_j)]
                usable |= cover > 0
        pieces = self.real & ~low & ~usable
        return head, usable, low, pieces

    def pieces_volume(self, head, pieces):
        return float(head[pieces].sum()) * CELL * CELL / self.cap


def episode(record):
    scene = _scene(record["scene_spec"])
    items = scene.items
    vols = [Volume(c) for c in scene.containers]
    loads = [Load(c) for c in scene.containers]
    floor_area = sum(float(ld.usable.sum()) * CELL * CELL for ld in loads)
    usable_surface = [ld.usable_mask() for ld in loads]
    state = [v.masks() for v in vols]
    rows = []
    for s in record["steps"]:
        if s.get("event") != "step" or "pos_local" not in s:
            continue
        ci = s["container_idx"]
        v = vols[ci]
        head0, _u0, _l0, p0 = state[ci]
        before = v.pieces_volume(head0, p0)
        surface = sum(float(u.sum()) for u in usable_surface) * CELL * CELL / floor_area
        soft = bool(items[s["item_index"]].get("is_soft"))
        v.add(s, soft)
        head1, u1, l1, p1 = v.masks()
        state[ci] = (head1, u1, l1, p1)
        after = v.pieces_volume(head1, p1)
        i0, i1, j0, j1 = v.cells(s)
        own_mask = np.zeros_like(v.real)
        own_mask[i0:i1, j0:j1] = True
        own = float(head1[own_mask & p1].sum()) * CELL * CELL / v.cap
        # what stood under the box's footprint before it (usable or pieces) is gone either way
        delta = after - before
        sz = s["size"]
        it = items[s["item_index"]]
        dims = sorted((float(it["length"]), float(it["width"]), float(it["height"])), reverse=True)
        rows.append({
            "cls": f"{dims[0]:.2f}x{dims[1]:.2f}x{dims[2]:.2f}" + (" soft" if soft else ""),
            "archetype": str(s.get("archetype", "?")).split("/")[-1],
            "flat": abs(sz[2] - min(sz)) < 1e-6,
            "soft": soft,
            "surface": surface,
            "delta": delta,
            "own": own,
            "rest": delta - own,
        })
        ld = loads[ci]
        ld.add(s["pos_local"], s["size"], soft=soft)
        usable_surface[ci] = ld.usable_mask()
    return rows


def phase(surface):
    return "high (>=0.4)" if surface >= 0.4 else ("mid (0.2-0.4)" if surface >= 0.2 else "low (<0.2)")


def main():
    for d in [a for a in sys.argv[1:] if not a.startswith("--")]:
        files = sorted(glob.glob(str(pathlib.Path(d) / "[abc]-*.json")))
        if not files:
            continue
        rows = [r for f in files for r in episode(json.load(open(f)))]
        made = sum(max(0.0, r["delta"]) for r in rows) or 1e-9
        print(f"### {pathlib.Path(d).name}{' (gaps bridged)' if BRIDGE else ''}: {len(files)} episodes, {len(rows)} placements; pieces made {made / len(files):.3f} of the container an episode, consumed {-sum(min(0.0, r['delta']) for r in rows) / len(files):.3f}")
        print("| phase | placements | pieces made (share) | consumed | made by the box's own top | by the surface beside it |")
        print("|---|---:|---:|---:|---:|---:|")
        for ph in ("high (>=0.4)", "mid (0.2-0.4)", "low (<0.2)"):
            v = [r for r in rows if phase(r["surface"]) == ph]
            if not v:
                continue
            pos = [r for r in v if r["delta"] > 0]
            print(f"| {ph} | {len(v)} | {sum(r['delta'] for r in pos) / made:.2f} | {-sum(min(0.0, r['delta']) for r in v) / made:.2f} | "
                  f"{sum(min(r['own'], r['delta']) for r in pos) / made:.2f} | {sum(max(0.0, r['delta'] - r['own']) for r in pos) / made:.2f} |")
        print()
        print("| archetype | pose | placements | mean delta pieces (of the container) | share of pieces made | own top share of what it made |")
        print("|---|---|---:|---:|---:|---:|")
        by = collections.defaultdict(list)
        for r in rows:
            by[(r["archetype"], "flat" if r["flat"] else "standing")].append(r)
        for (arch, pose), v in sorted(by.items(), key=lambda kv: -sum(max(0.0, r["delta"]) for r in kv[1]))[:18]:
            pos = [r for r in v if r["delta"] > 0]
            m = sum(r["delta"] for r in pos)
            own = sum(min(r["own"], r["delta"]) for r in pos)
            print(f"| {arch} | {pose} | {len(v)} | {np.mean([r['delta'] for r in v]):+.4f} | {m / made:.2f} | {own / max(m, 1e-9):.2f} |")
        print()
        print("| item class | pose | placements (max-footprint, flat) | mean delta pieces | share of pieces made | own top share |")
        print("|---|---|---:|---:|---:|---:|")
        byc = collections.defaultdict(list)
        for r in rows:
            if r["archetype"] == "max-footprint":
                byc[(r["cls"], "flat" if r["flat"] else "standing")].append(r)
        for (c, pose), v in sorted(byc.items(), key=lambda kv: -sum(max(0.0, r["delta"]) for r in kv[1])):
            pos = [r for r in v if r["delta"] > 0]
            m = sum(r["delta"] for r in pos)
            own = sum(min(r["own"], r["delta"]) for r in pos)
            print(f"| {c} | {pose} | {len(v)} | {np.mean([r['delta'] for r in v]):+.4f} | {m / made:.2f} | {own / max(m, 1e-9):.2f} |")
        print()


if __name__ == "__main__":
    main()
