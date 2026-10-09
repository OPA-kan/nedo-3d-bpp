"""levelness.py <record_dir>...: the levelness of the load as it is built.

The end states leave 44 % of the container empty, 0.41 of it over
level patches too small for a footprint ("The end states as data").
This instrument watches that surface step by step: after every
placement the load is rebuilt on a 2 cm grid and the *usable surface*
measured -- the cells of the top surface (floor, shelf plates, box
tops) that lie in a level patch (tops within 2 cm) holding a 0.40 x
0.55 window with 3 cm of clearance and 0.27 m free above it, i.e. the
surface the smallest hard class could still stand on.  A placement's
*waste* is the usable surface it removes beyond what it would remove
by standing on a usable patch and leaving a usable top:

    waste = (usable before - usable after) - footprint,
                               when the box stands on a usable patch;
    waste = (usable before - usable after),           otherwise;

so a box that lands on a level patch, keeps the remainder usable and
offers its own top as a new patch wastes nothing, and a box that
breaks a patch into pieces or stands where nothing level remains is
charged the surface it closed.  Per archetype: how many placements,
the mean waste, the share of the suite's waste.  Per episode: the
usable share of the floor area at the start, at a quarter, half, three
quarters and the end.  Per suite: the archetypes that lose the most.
"""
import collections
import glob
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from bench.scenes import make_hard_scene, make_scene  # noqa: E402
from soft_slots_b import CELL, Load  # noqa: E402


def _scene(spec):
    if spec.get("layout") == "hard" or "hard" in spec["name"]:
        return make_hard_scene(spec["seed"], spec["task"])
    return make_scene(spec["seed"], spec["layout"], spec["task"])


def episode(record):
    spec = record["scene_spec"]
    scene = _scene(spec)
    steps = [s for s in record["steps"] if s.get("event") == "step" and "pos_local" in s]
    items = scene.items
    loads = [Load(c) for c in scene.containers]
    floor_area = sum(float(ld.usable.sum()) * CELL * CELL for ld in loads)
    usable = [ld.usable_mask() for ld in loads]
    series = [sum(float(u.sum()) for u in usable) * CELL * CELL / floor_area]
    per_step = []
    for s in steps:
        ci = s["container_idx"]
        before = usable[ci]
        x, y, z = s["pos_local"]
        sx, sy, sz = s["size"]
        foot = ((loads[ci].xx >= x - sx / 2) & (loads[ci].xx <= x + sx / 2)
                & (loads[ci].yy >= y - sy / 2) & (loads[ci].yy <= y + sy / 2))
        on_usable = bool((foot & before).sum() >= 0.5 * foot.sum())
        loads[ci].add(s["pos_local"], s["size"], soft=bool(items[s["item_index"]].get("is_soft")))
        after = loads[ci].usable_mask()
        usable[ci] = after
        removed = float((before & ~after).sum()) * CELL * CELL
        footprint = float(foot.sum()) * CELL * CELL
        waste = removed - footprint if on_usable else removed
        # the top it offers back
        added = float((after & ~before).sum()) * CELL * CELL
        per_step.append({
            "step": s["step"], "archetype": s.get("archetype", "?"), "surface": s.get("surface", "?"),
            "on_usable": on_usable, "removed": removed, "added": added, "footprint": footprint,
            "waste": max(0.0, waste - added), "net": removed - added,
            "flat": abs(sz - min(sx, sy, sz)) < 1e-6,
        })
        series.append(sum(float(u.sum()) for u in usable) * CELL * CELL / floor_area)
    n = len(series) - 1
    marks = [series[0]] + [series[int(round(q * n))] for q in (0.25, 0.5, 0.75, 1.0)] if n else [series[0]] * 5
    return {"scene": record["scene"], "steps": per_step, "marks": marks, "placed": len(steps)}


def main():
    for d in sys.argv[1:]:
        rows = [episode(json.load(open(f))) for f in sorted(glob.glob(str(pathlib.Path(d) / "[abc]-*.json")))]
        if not rows:
            continue
        by = collections.defaultdict(list)
        for r in rows:
            for s in r["steps"]:
                by[s["archetype"]].append(s)
        total_waste = sum(s["waste"] for r in rows for s in r["steps"]) or 1e-9
        marks = np.mean([r["marks"] for r in rows], axis=0)
        print(f"### {pathlib.Path(d).name}: {len(rows)} episodes; usable surface / floor area at start, 1/4, 1/2, 3/4, end: "
              + " / ".join(f"{m:.2f}" for m in marks))
        print("| archetype | placements | flat | on a usable patch | mean waste m^2 (flat / standing) | mean net loss m^2 | share of waste |")
        print("|---|---:|---:|---:|---:|---:|---:|")
        for name, ss in sorted(by.items(), key=lambda kv: -sum(s["waste"] for s in kv[1])):
            w = sum(s["waste"] for s in ss)
            flat = [s for s in ss if s["flat"]]
            stand = [s for s in ss if not s["flat"]]
            wf = np.mean([s["waste"] for s in flat]) if flat else float("nan")
            ws = np.mean([s["waste"] for s in stand]) if stand else float("nan")
            print(f"| {name} | {len(ss)} | {len(flat) / len(ss):.2f} | {np.mean([s['on_usable'] for s in ss]):.2f} | {np.mean([s['waste'] for s in ss]):.3f} ({wf:.3f} / {ws:.3f}) | {np.mean([s['net'] for s in ss]):.3f} | {w / total_waste:.2f} |")
        print()


if __name__ == "__main__":
    main()
