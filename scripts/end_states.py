"""end_states.py <out_dir> <record_dir>...: the end state of every episode as data.

One row per episode (CSV) and a summary (Markdown): where the episode
stopped against the count threshold (the margin), what stopped it (the
first item with no pose: class and dimensions, and on Task B the whole
pool), what the floor looked like (free share, the share of the free
floor in runs narrower than 0.30 m, the largest free rectangle), how
much of the container's volume stood free above the height map, how the
typed cargo fared (placed against seen), and the gap KPI.  Built to
hold the v39 arm's end states as the starting point for whatever comes
next: a change is read against these rows, not against a mean.
"""
import csv
import glob
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from bench.gaps import gap_metrics  # noqa: E402
from bench.scenes import make_hard_scene, make_scene  # noqa: E402

CELL = 0.02
MIN_WIDTH = 0.30


def _scene(spec):
    if spec.get("layout") == "hard" or "hard" in spec["name"]:
        return make_hard_scene(spec["seed"], spec["task"])
    kwargs = {k: spec[k] for k in ("look_ahead", "items_per_container") if k in spec}
    try:
        return make_scene(spec["seed"], spec["layout"], spec["task"], **kwargs)
    except TypeError:
        return make_scene(spec["seed"], spec["layout"], spec["task"])


def _largest_rect(free):
    best = 0
    bh = bw = 0
    h = np.zeros(free.shape[1], dtype=int)
    for row in free:
        h = np.where(row, h + 1, 0)
        stack = []
        for j in range(len(h) + 1):
            cur = h[j] if j < len(h) else 0
            start = j
            while stack and stack[-1][1] >= cur:
                s, hh = stack.pop()
                area = hh * (j - s)
                if area > best:
                    best, bh, bw = area, hh, j - s
                start = s
            stack.append((start, cur))
    return bh * CELL, bw * CELL


def _narrow(free, need):
    out = np.zeros_like(free)
    for axis in (0, 1):
        arr = free if axis == 0 else free.T
        mark = np.zeros_like(arr)
        for j in range(arr.shape[1]):
            col = arr[:, j]
            i = 0
            while i < len(col):
                if not col[i]:
                    i += 1
                    continue
                i2 = i
                while i2 < len(col) and col[i2]:
                    i2 += 1
                if i2 - i < need:
                    mark[i:i2, j] = True
                i = i2
        out |= mark if axis == 0 else mark.T
    return out


def floor_and_volume(scene, steps):
    """Per container: floor free share, strip share of the free floor,
    largest free rectangle, free volume share above the height map, the
    highest top."""
    rows = []
    for ci, c in enumerate(scene.containers):
        L, W, H, t = c["length"], c["width"], c["height"], c["thickness"]
        nx, ny = int(round(L / CELL)), int(round(W / CELL))
        occupied = np.zeros((nx, ny), dtype=bool)
        height = np.zeros((nx, ny), dtype=float)
        wall = np.zeros((nx, ny), dtype=bool)
        tc = max(1, int(round(t / CELL)))
        cut = int(round((c.get("cut_x", 0.0) + t) / CELL))
        wall[:cut, :] = True
        wall[-tc:, :] = True
        wall[:, :tc] = True
        wall[:, -tc:] = True
        for s in steps:
            if s["container_idx"] != ci:
                continue
            x, y, z = s["pos_local"]
            sx, sy, sz = s["size"]
            i0 = max(0, int((x - sx / 2 + L / 2) / CELL))
            i1 = min(nx, int(round((x + sx / 2 + L / 2) / CELL)))
            j0 = max(0, int((y - sy / 2 + W / 2) / CELL))
            j1 = min(ny, int(round((y + sy / 2 + W / 2) / CELL)))
            height[i0:i1, j0:j1] = np.maximum(height[i0:i1, j0:j1], z + sz / 2)
            if z - sz / 2 < 0.06:
                occupied[i0:i1, j0:j1] = True
        real = ~wall
        free = real & ~occupied
        need = int(MIN_WIDTH / CELL)
        strip = _narrow(free, need) & free
        rect = _largest_rect(free)
        inner_h = H - t
        free_vol = float(np.clip(inner_h - height[real], 0.0, None).sum()) * CELL * CELL
        cap = float(real.sum()) * CELL * CELL * inner_h
        rows.append({
            "floor_free": float(free.sum()) / max(float(real.sum()), 1.0),
            "strip_share": float(strip.sum()) / max(float(free.sum()), 1.0),
            "largest_rect": f"{max(rect):.2f}x{min(rect):.2f}",
            "largest_rect_area": rect[0] * rect[1],
            "free_volume_share": free_vol / max(cap, 1e-9),
            "top_max": float(height[real].max()) if real.any() else 0.0,
            "height_inner": inner_h,
        })
    return rows


def fits(item, rect_dims, flat: bool = True):
    """Does the item fit the rectangle with 3 cm for the clearances: flat
    (its two largest dimensions as the footprint) or on any face?"""
    a, b = rect_dims
    dims = sorted((item["length"], item["width"], item["height"]))
    faces = [(dims[2], dims[1])] if flat else [(dims[2], dims[1]), (dims[2], dims[0]), (dims[1], dims[0])]
    return any(max(a, b) >= f[0] + 0.03 and min(a, b) >= f[1] + 0.03 for f in faces)


def episode_row(record):
    spec = record["scene_spec"]
    scene = _scene(spec)
    items = scene.items
    n = len(items)
    thr = n // 2 + 1
    m = record["metrics"]
    steps = [s for s in record["steps"] if s.get("event") == "step" and "pos_local" in s]
    placed = {s["item_index"] for s in steps}
    look = int(spec.get("look_ahead", scene.look_ahead if hasattr(scene, "look_ahead") else 1) or 1)
    order = record.get("order") or list(range(n))
    stream = [i for i in order if i not in placed]
    pool = stream[:look]
    nxt = items[pool[0]] if pool else None
    seen = set(placed) | set(pool)
    soft_seen = sum(1 for i in seen if items[i].get("is_soft"))
    prio_seen = sum(1 for i in seen if items[i].get("is_prioritized"))
    floors = floor_and_volume(scene, steps)
    biggest = max(floors, key=lambda r: r["largest_rect_area"]) if floors else None
    gaps = gap_metrics(record["steps"])
    row = {
        "scene": record["scene"], "task": spec["task"], "layout": spec.get("layout", ""),
        "containers": len(scene.containers),
        "placed": m["placed_count"], "total": n, "threshold": thr, "margin": m["placed_count"] - thr,
        "fill": round(m["fill_volume"], 2), "end": m.get("end_reason", ""),
        "policy_max": round(m.get("policy_time_max", 0.0), 2),
        "next_class": ("soft" if nxt and nxt.get("is_soft") else "hard") + ("+prio" if nxt and nxt.get("is_prioritized") else "") if nxt else "",
        "next_dims": "x".join(f"{v:.2f}" for v in sorted((nxt["length"], nxt["width"], nxt["height"]), reverse=True)) if nxt else "",
        "next_fits_floor": bool(biggest and nxt and fits(nxt, tuple(float(v) for v in biggest["largest_rect"].split("x")))),
        "next_fits_any_face": bool(biggest and nxt and fits(nxt, tuple(float(v) for v in biggest["largest_rect"].split("x")), flat=False)),
        "pool_size": len(pool),
        "pool_hard": sum(1 for i in pool if not items[i].get("is_soft")),
        "pool_any_fits_floor": bool(biggest and any(fits(items[i], tuple(float(v) for v in biggest["largest_rect"].split("x"))) for i in pool)),
        "pool_any_fits_any_face": bool(biggest and any(fits(items[i], tuple(float(v) for v in biggest["largest_rect"].split("x")), flat=False) for i in pool)),
        "soft_placed": m.get("soft_count", 0), "soft_seen": soft_seen,
        "prio_placed": m.get("priority_count", 0), "prio_seen": prio_seen,
        "soft_covered": m.get("soft_covered", 0), "prio_covered": m.get("priority_covered", 0),
        "topples": m.get("shake_topples", 0),
        "floor_free": round(float(np.mean([f["floor_free"] for f in floors])), 3) if floors else 0.0,
        "strip_share": round(float(np.mean([f["strip_share"] for f in floors])), 3) if floors else 0.0,
        "largest_rect": biggest["largest_rect"] if biggest else "",
        "free_volume_share": round(float(np.mean([f["free_volume_share"] for f in floors])), 3) if floors else 0.0,
        "top_max_share": round(float(max(f["top_max"] / f["height_inner"] for f in floors)), 3) if floors else 0.0,
        "gap_median_cm": gaps.get("gap_median_cm", 0.0), "gap_strip_share": gaps.get("gap_strip_share", 0.0),
        "archetypes": " ".join(f"{k}:{v}" for k, v in sorted(
            __import__("collections").Counter(s.get("archetype", "?") for s in steps).items(), key=lambda kv: -kv[1])[:6]),
    }
    return row


def summarise(name, rows):
    margins = [r["margin"] for r in rows]
    lines = [f"### {name}: {len(rows)} episodes", ""]
    lines.append(f"- placed {np.mean([r['placed'] for r in rows]):.2f} of {np.mean([r['total'] for r in rows]):.1f} a scene, fill {np.mean([r['fill'] for r in rows]):.2f}")
    over = sum(1 for v in margins if v >= 0)
    lines.append(f"- over the threshold {over} / {len(rows)}; margin median {np.median(margins):.0f}, within +-2 of it {sum(1 for v in margins if -2 <= v <= 2)}, under by 1-3 {sum(1 for v in margins if -3 <= v <= -1)}, over by 0-2 {sum(1 for v in margins if 0 <= v <= 2)}")
    lines.append(f"- margin histogram: " + ", ".join(f"{k}:{v}" for k, v in sorted(__import__('collections').Counter(max(-6, min(10, m)) for m in margins).items())))
    ends = __import__("collections").Counter(r["end"] for r in rows)
    lines.append(f"- end reasons: {dict(ends)}")
    nxt = __import__("collections").Counter(r["next_class"] for r in rows)
    lines.append(f"- the item that stopped it: {dict(nxt)}; its dims: {dict(__import__('collections').Counter(r['next_dims'] for r in rows).most_common(6))}")
    lines.append(f"- it fits the largest free floor rectangle flat in {sum(1 for r in rows if r['next_fits_floor'])} episodes (on some face {sum(1 for r in rows if r['next_fits_any_face'])}); some pool item does flat in {sum(1 for r in rows if r['pool_any_fits_floor'])} (some face {sum(1 for r in rows if r['pool_any_fits_any_face'])})")
    lines.append(f"- floor free {np.mean([r['floor_free'] for r in rows]):.3f} (strips {np.mean([r['strip_share'] for r in rows]):.3f} of it), free volume above the height map {np.mean([r['free_volume_share'] for r in rows]):.3f}, highest top {np.mean([r['top_max_share'] for r in rows]):.3f} of the inner height")
    lines.append(f"- soft placed / seen {sum(r['soft_placed'] for r in rows)} / {sum(r['soft_seen'] for r in rows)}, priority {sum(r['prio_placed'] for r in rows)} / {sum(r['prio_seen'] for r in rows)}; covered soft {sum(r['soft_covered'] for r in rows)}, priority {sum(r['prio_covered'] for r in rows)}; topples {sum(r['topples'] for r in rows)}")
    lines.append(f"- gap median {np.mean([r['gap_median_cm'] for r in rows]):.2f} cm, strip share {np.mean([r['gap_strip_share'] for r in rows]):.3f}")
    close = sorted((r for r in rows if -3 <= r["margin"] <= 2), key=lambda r: r["margin"])
    if close:
        lines.append("")
        lines.append("| scene | placed/thr | margin | end | next | fits floor | floor free | largest rect | free vol |")
        lines.append("|---|---:|---:|---|---|---|---:|---|---:|")
        for r in close:
            fit = "flat" if r["next_fits_floor"] else ("face" if r["next_fits_any_face"] else "no")
            lines.append(f"| {r['scene']} | {r['placed']}/{r['threshold']} | {r['margin']:+d} | {r['end']} | {r['next_class']} {r['next_dims']} | {fit} | {r['floor_free']:.2f} | {r['largest_rect']} | {r['free_volume_share']:.2f} |")
    lines.append("")
    return "\n".join(lines)


def main():
    out = pathlib.Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    summary = ["# End states", "", "One row per episode in the CSVs; the margin is placed minus the count threshold (strictly more than half).", ""]
    for d in sys.argv[2:]:
        name = pathlib.Path(d).name
        rows = []
        for f in sorted(glob.glob(str(pathlib.Path(d) / "[abc]-*.json"))):
            rows.append(episode_row(json.load(open(f))))
        if not rows:
            continue
        with (out / f"{name}.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        summary.append(summarise(name, rows))
        print(f"{name}: {len(rows)} rows", flush=True)
    (out / "summary.md").write_text("\n".join(summary))


if __name__ == "__main__":
    main()
