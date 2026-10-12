"""phase_map.py <record_dir>...: is there a phase change in the episode, and can the state show it?

For every step of every episode the usable surface (the levelness
instrument's measure, over the floor area) is read *before* the
placement, and the placement is classed by the mechanism that made it:
``floor`` (the floor rungs: max-footprint, back-corner, wall and wedge
roles, the typed edges), ``raised`` (terraces, plateau merges, stacks,
pocket soft), ``rescue`` (the physics resort, the count pass, the last
resort, the fallback).  If the mechanisms live in different bands of
the usable surface -- the floor rungs while the surface is wide, the
rescue once it is gone -- the surface is a phase variable the agent can
read online (1 ms a step), and the band edge is where the rules change.
Per suite: the median and quartiles of the usable surface at which each
class placed, the share of placements per class per band of the
surface, and per episode the surface at the first rescue placement and
at the decline.
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

FLOOR = {"max-footprint", "back-corner", "minimum-hole", "largest-residual-rectangle", "elongated-wall",
         "slope-infill", "wall-front", "tall-perimeter", "wedge-step", "wedge-soft-cap", "front-wedge",
         "soft-edge", "priority-edge", "sp-cluster", "hole-fill", "shelf-space-saving", "typed-cap"}
RAISED = {"terrace-extension", "plateau-merge", "wedge-bridge", "stack-rl", "pocket-soft", "residual"}
RESCUE = {"physics-resort", "count-mode", "last-resort", "fallback"}
BANDS = [(0.6, 9.0), (0.4, 0.6), (0.25, 0.4), (0.15, 0.25), (0.08, 0.15), (0.0, 0.08)]


def klass(arch: str) -> str:
    a = str(arch).split("/")[-1]
    if a in RESCUE:
        return "rescue"
    if a in RAISED:
        return "raised"
    if a in FLOOR or a == "plan":
        return "floor"
    return "other"


def episode(record):
    scene = _scene(record["scene_spec"])
    items = scene.items
    loads = [Load(c) for c in scene.containers]
    floor_area = sum(float(ld.usable.sum()) * CELL * CELL for ld in loads)
    usable = [ld.usable_mask() for ld in loads]
    rows = []
    for s in record["steps"]:
        if s.get("event") != "step" or "pos_local" not in s:
            continue
        ratio = sum(float(u.sum()) for u in usable) * CELL * CELL / floor_area
        rows.append((ratio, klass(s.get("archetype", "?")), s.get("archetype", "?")))
        ci = s["container_idx"]
        loads[ci].add(s["pos_local"], s["size"], soft=bool(items[s["item_index"]].get("is_soft")))
        usable[ci] = loads[ci].usable_mask()
    end = sum(float(u.sum()) for u in usable) * CELL * CELL / floor_area
    return rows, end, record["metrics"]["placed_count"], record["metrics"].get("placed_fraction", 0.0)


def main():
    for d in sys.argv[1:]:
        files = sorted(glob.glob(str(pathlib.Path(d) / "[abc]-*.json")))
        if not files:
            continue
        by = collections.defaultdict(list)
        band_counts = collections.defaultdict(lambda: collections.Counter())
        first_rescue = []
        ends = []
        margins = []
        for f in files:
            rows, end, placed, frac = episode(json.load(open(f)))
            ends.append(end)
            margins.append(frac)
            seen_rescue = False
            for i, (ratio, k, arch) in enumerate(rows):
                by[k].append(ratio)
                for lo, hi in BANDS:
                    if lo <= ratio < hi:
                        band_counts[(lo, hi)][k] += 1
                        break
                if k == "rescue" and not seen_rescue:
                    first_rescue.append((ratio, i / max(1, len(rows))))
                    seen_rescue = True
        print(f"### {pathlib.Path(d).name}: {len(files)} episodes")
        print("| class | placements | usable surface at placement: q25 / median / q75 |")
        print("|---|---:|---:|")
        for k in ("floor", "raised", "rescue", "other"):
            v = by.get(k, [])
            if v:
                print(f"| {k} | {len(v)} | {np.percentile(v, 25):.2f} / {np.median(v):.2f} / {np.percentile(v, 75):.2f} |")
        print()
        print("| usable surface band | placements | floor | raised | rescue |")
        print("|---|---:|---:|---:|---:|")
        for lo, hi in BANDS:
            c = band_counts[(lo, hi)]
            n = sum(c.values())
            if n:
                print(f"| {lo:.2f}-{min(hi, 1.2):.2f} | {n} | {c['floor'] / n:.2f} | {c['raised'] / n:.2f} | {c['rescue'] / n:.2f} |")
        if first_rescue:
            r = np.array(first_rescue)
            print(f"\nfirst rescue placement: usable surface median {np.median(r[:, 0]):.2f} (q25 {np.percentile(r[:, 0], 25):.2f}, q75 {np.percentile(r[:, 0], 75):.2f}), "
                  f"at {np.median(r[:, 1]):.2f} of the episode; {len(first_rescue)} of {len(files)} episodes had one")
        print(f"usable surface at the decline: median {np.median(ends):.2f}, q75 {np.percentile(ends, 75):.2f}, max {np.max(ends):.2f}")
        print()


if __name__ == "__main__":
    main()
