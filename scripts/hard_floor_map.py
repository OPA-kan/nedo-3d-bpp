"""hard_floor_map.py <dir>: for every scene, the floor's occupancy at the end -- share covered by soft
and by hard cargo, free share, the largest free rectangle against the declined item's footprint,
and how many soft boxes rest on the floor rather than on cargo."""
import json, glob, sys
import numpy as np
import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from bench.scenes import make_hard_scene
d = sys.argv[1]
CELL = 0.02
def largest_rect(free):
    # maximal all-true rectangle in a boolean grid (histogram method); returns (h, w, x0) in metres/cells
    best = 0; bw = bh = 0; bx = 0
    h = np.zeros(free.shape[1], dtype=int)
    for i, row in enumerate(free):
        h = np.where(row, h + 1, 0)
        stack = []
        for j in range(len(h) + 1):
            cur = h[j] if j < len(h) else 0
            start = j
            while stack and stack[-1][1] >= cur:
                s, hh = stack.pop()
                area = hh * (j - s)
                if area > best: best, bh, bw, bx = area, hh, j - s, i - hh + 1
                start = s
            stack.append((start, cur))
    return bh * CELL, bw * CELL, bx * CELL
out = []
for f in sorted(glob.glob(d + "/[abc]-hard-*.json")):
    r = json.load(open(f)); m = r["metrics"]; sp = r["scene_spec"]
    sc = make_hard_scene(sp["seed"], sp["task"]); items = sc.items; n = len(items); thr = n // 2 + 1
    cap = sum(c["length"] * c["width"] * c["height"] for c in sc.containers)
    vols = [i["length"] * i["width"] * i["height"] for i in items]
    need = sum(sorted(vols[:thr + sc.look_ahead - 1])[:thr]) / cap
    if need > 0.65 or m["placed_count"] >= thr: continue
    steps = [s for s in r["steps"] if s["event"] == "step"]
    placed = set(s["item_index"] for s in steps)
    pool = [i for i in range(n) if i not in placed][:sc.look_ahead]
    nxt = items[pool[0]]
    grids = {}; soft_floor = hard_floor = soft_up = hard_up = 0
    for s in steps:
        c = sc.containers[s["container_idx"]]
        g = grids.setdefault(s["container_idx"], np.zeros((int(c["length"] / CELL), int(c["width"] / CELL)), dtype=np.int8))
        x, y, z = s["pos_local"]; sx, sy, sz = s["size"]
        it = items[s["item_index"]]
        on_floor = z - sz / 2 < 0.06
        if it["is_soft"]:
            if on_floor: soft_floor += 1
            else: soft_up += 1
        else:
            if on_floor: hard_floor += 1
            else: hard_up += 1
        if on_floor:
            i0 = int((x - sx / 2 + c["length"] / 2) / CELL); i1 = int((x + sx / 2 + c["length"] / 2) / CELL)
            j0 = int((y - sy / 2 + c["width"] / 2) / CELL); j1 = int((y + sy / 2 + c["width"] / 2) / CELL)
            g[max(i0, 0):i1, max(j0, 0):j1] = 2 if it["is_soft"] else 1
    free_share = []; rects = []; soft_share = []
    for ci, c in enumerate(sc.containers):
        g = grids.get(ci, np.zeros((int(c["length"] / CELL), int(c["width"] / CELL)), dtype=np.int8))
        g = g.copy(); t = c["thickness"]
        g[:int((c["cut_x"] + t) / CELL), :] = 3; g[-int(t / CELL):, :] = 3; g[:, :int(t / CELL)] = 3; g[:, -int(t / CELL):] = 3
        real = g != 3
        free_share.append(((g == 0).sum()) / real.sum()); soft_share.append((g == 2).sum() / real.sum())
        rects.append(largest_rect(g == 0))
    fp = sorted((nxt["length"], nxt["width"], nxt["height"]))
    fits = any(min(rc[:2]) >= fp[0] + 0.03 and max(rc[:2]) >= fp[1] + 0.03 for rc in rects)
    out.append((r["scene"], f"{m['placed_count']}/{thr}", f"need {need:.2f} fill {m['fill_volume']/100:.2f}", sp["mix"], sp["order"],
                f"floor free {['%.2f' % v for v in free_share]} soft-covered {['%.2f' % v for v in soft_share]}",
                f"largest free {[('%.2fx%.2f@x%.2f' % (rc[0], rc[1], rc[2] - sc.containers[k]['length'] / 2)) for k, rc in enumerate(rects)]}", f"next {'S' if nxt['is_soft'] else 'H'}{fp[0]:.2f}x{fp[1]:.2f}x{fp[2]:.2f} {'FITS-FLOOR' if fits else 'no-floor'}",
                f"soft floor/up {soft_floor}/{soft_up} hard floor/up {hard_floor}/{hard_up}"))
for row in out: print(*row)
print("scenes", len(out), "next fits floor", sum('FITS-FLOOR' in row[7] for row in out))
