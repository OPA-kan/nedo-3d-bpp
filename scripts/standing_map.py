"""standing_map.py <record_dir>...: where the standing poses stand, and what they waste.

The levelness instrument (``levelness.py``) charges a standing pose two
to ten times a flat one, wherever it occurs; the ground-handling
practice document says the standing poses belong at the back wall and
along the walls, with the front laid flat.  This maps every placement
by pose (flat / standing) and by place -- against the back wall, against
a side wall, beside a top of its own height (within 3 cm), or free --
with the count, the mean waste and the share of the suite's waste for
each cell, per archetype and in total.  The rule for standing poses,
if there is one, is read off the cells that waste the most.
"""
import collections
import glob
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from levelness import _scene, episode  # noqa: E402
from rule_alpha.config import DEFAULT_CONFIG  # noqa: E402
from rule_alpha.geometry import ContainerModel  # noqa: E402

WALL = 0.05   # within this of a wall counts as against it
MATCH = 0.03  # a neighbouring top within this of the pose's top
NEAR = 0.06   # a neighbour: its box within this of the pose's footprint


def places(record, scene):
    """Per step: the place of the pose, in the order of the record's steps."""
    models = [ContainerModel(c, DEFAULT_CONFIG) for c in scene.containers]
    placed = [[] for _ in scene.containers]  # (x0, x1, y0, y1, top)
    out = []
    steps = [s for s in record["steps"] if s.get("event") == "step" and "pos_local" in s]
    for s in steps:
        ci = s["container_idx"]
        x, y, z = s["pos_local"]
        sx, sy, sz = s["size"]
        x0, x1, y0, y1 = x - sx / 2, x + sx / 2, y - sy / 2, y + sy / 2
        top = z + sz / 2
        rect = models[ci].floor_rect
        back = y1 >= rect.y_max - WALL
        side = x1 >= rect.x_max - WALL or x0 <= float(models[ci].x_limit_at_height(z - sz / 2 + 1e-3)) + WALL
        match = False
        for (px0, px1, py0, py1, ptop) in placed[ci]:
            near = px0 < x1 + NEAR and px1 > x0 - NEAR and py0 < y1 + NEAR and py1 > y0 - NEAR
            if near and abs(ptop - top) <= MATCH:
                match = True
                break
        placed[ci].append((x0, x1, y0, y1, top))
        place = "back wall" if back else ("side wall" if side else ("beside a top" if match else "free"))
        out.append(place)
    return out


def main():
    for d in sys.argv[1:]:
        files = sorted(glob.glob(str(pathlib.Path(d) / "[abc]-*.json")))
        cells = collections.defaultdict(list)   # (archetype, pose, place) -> wastes
        totals = collections.defaultdict(list)  # (pose, place) -> wastes
        for f in files:
            record = json.load(open(f))
            ep = episode(record)
            pl = places(record, _scene(record["scene_spec"]))
            for step, place in zip(ep["steps"], pl):
                pose = "flat" if step["flat"] else "standing"
                cells[(step["archetype"], pose, place)].append(step["waste"])
                totals[(pose, place)].append(step["waste"])
        if not files:
            continue
        total = sum(sum(v) for v in totals.values()) or 1e-9
        print(f"### {pathlib.Path(d).name}: {len(files)} episodes, {sum(len(v) for v in totals.values())} placements")
        print("| pose | place | placements | mean waste m^2 | share of waste |")
        print("|---|---|---:|---:|---:|")
        for (pose, place), v in sorted(totals.items(), key=lambda kv: -sum(kv[1])):
            print(f"| {pose} | {place} | {len(v)} | {np.mean(v):.3f} | {sum(v) / total:.2f} |")
        print()
        print("| archetype | pose | place | placements | mean waste m^2 | share of waste |")
        print("|---|---|---|---:|---:|---:|")
        for (arch, pose, place), v in sorted(cells.items(), key=lambda kv: -sum(kv[1]))[:24]:
            print(f"| {arch} | {pose} | {place} | {len(v)} | {np.mean(v):.3f} | {sum(v) / total:.2f} |")
        print()


if __name__ == "__main__":
    main()
