"""phase_volume.py <record_dir>...: the free volume at the phase change and at the end.

``phase_map.py`` found the rules change where the usable surface over
the floor area falls through about 0.2: above it the ladder's rungs
place, below it the rescue mechanisms place most of the items.  This
asks where the end state's empty volume (0.44 of the container) comes
from: at the step where the usable surface first falls under the
boundary, how much volume is free and how much of it is already in
pieces no footprint fits (``end_states.floor_and_volume``), against the
same reading at the decline; and how many items are placed before and
after the boundary.  If the free volume at the boundary is mostly still
usable, the low phase turns it into pieces and the low phase's rules
are the lever; if it is already in pieces, the high phase made them.
"""
import glob
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from end_states import floor_and_volume  # noqa: E402
from levelness import _scene  # noqa: E402
from soft_slots_b import CELL, Load  # noqa: E402

BOUNDARIES = (0.4, 0.2)


def episode(record):
    scene = _scene(record["scene_spec"])
    items = scene.items
    loads = [Load(c) for c in scene.containers]
    floor_area = sum(float(ld.usable.sum()) * CELL * CELL for ld in loads)
    usable = [ld.usable_mask() for ld in loads]
    steps = [s for s in record["steps"] if s.get("event") == "step" and "pos_local" in s]
    series = []
    for s in steps:
        series.append(sum(float(u.sum()) for u in usable) * CELL * CELL / floor_area)
        ci = s["container_idx"]
        loads[ci].add(s["pos_local"], s["size"], soft=bool(items[s["item_index"]].get("is_soft")))
        usable[ci] = loads[ci].usable_mask()
    out = {"placed": len(steps)}
    for b in BOUNDARIES:
        k = next((i for i, r in enumerate(series) if r < b), len(steps))
        rows = floor_and_volume(scene, steps[:k])
        exact = floor_and_volume(scene, steps[:k], window=(0.40, 0.55))
        out[b] = {
            "pieces_exact": float(np.mean([r["vol_pieces_share"] for r in exact])),
            "usable_exact": float(np.mean([r["vol_usable_share"] for r in exact])),
            "step": k, "share_of_episode": k / max(1, len(steps)),
            "free": float(np.mean([r["free_volume_share"] for r in rows])),
            "pieces": float(np.mean([r["vol_pieces_share"] for r in rows])),
            "usable": float(np.mean([r["vol_usable_share"] for r in rows])),
            "low": float(np.mean([r["vol_low_share"] for r in rows])),
            "floor_free": float(np.mean([r["floor_free"] for r in rows])),
        }
    rows = floor_and_volume(scene, steps)
    exact = floor_and_volume(scene, steps, window=(0.40, 0.55))
    out["end"] = {
        "pieces_exact": float(np.mean([r["vol_pieces_share"] for r in exact])),
        "usable_exact": float(np.mean([r["vol_usable_share"] for r in exact])),
        "free": float(np.mean([r["free_volume_share"] for r in rows])),
        "pieces": float(np.mean([r["vol_pieces_share"] for r in rows])),
        "usable": float(np.mean([r["vol_usable_share"] for r in rows])),
        "low": float(np.mean([r["vol_low_share"] for r in rows])),
        "floor_free": float(np.mean([r["floor_free"] for r in rows])),
    }
    return out


def main():
    for d in sys.argv[1:]:
        files = sorted(glob.glob(str(pathlib.Path(d) / "[abc]-*.json")))
        if not files:
            continue
        eps = [episode(json.load(open(f))) for f in files]
        print(f"### {pathlib.Path(d).name}: {len(eps)} episodes, {np.mean([e['placed'] for e in eps]):.1f} placed")
        print("| point | step (share of episode) | items after | free volume | of the container: in pieces | usable | (exact-stack window: pieces | usable) | under low headroom | floor free |")
        print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for b in BOUNDARIES:
            v = [e[b] for e in eps]
            after = [e["placed"] - e[b]["step"] for e in eps]
            print(f"| usable surface < {b:.1f} | {np.mean([x['step'] for x in v]):.1f} ({np.mean([x['share_of_episode'] for x in v]):.2f}) | {np.mean(after):.1f} | "
                  f"{np.mean([x['free'] for x in v]):.3f} | {np.mean([x['pieces'] for x in v]):.3f} | {np.mean([x['usable'] for x in v]):.3f} | {np.mean([x['pieces_exact'] for x in v]):.3f} | {np.mean([x['usable_exact'] for x in v]):.3f} | {np.mean([x['low'] for x in v]):.3f} | {np.mean([x['floor_free'] for x in v]):.2f} |")
        v = [e["end"] for e in eps]
        print(f"| decline | {np.mean([e['placed'] for e in eps]):.1f} (1.00) | 0 | {np.mean([x['free'] for x in v]):.3f} | {np.mean([x['pieces'] for x in v]):.3f} | {np.mean([x['usable'] for x in v]):.3f} | {np.mean([x['pieces_exact'] for x in v]):.3f} | {np.mean([x['usable_exact'] for x in v]):.3f} | {np.mean([x['low'] for x in v]):.3f} | {np.mean([x['floor_free'] for x in v]):.2f} |")
        print()


if __name__ == "__main__":
    main()
