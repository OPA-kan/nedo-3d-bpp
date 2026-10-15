"""compact_slots.py: slots for the big hard class at the first big hard item, on the
whole-episode branches (k = 0) of cf.py: the baseline and the compaction wrappers.

Boards are rebuilt from the branch's own steps (the agent's intended poses,
``pos_local`` and ``size``; not settled), with the same greedy packer and class as
shape.py.  Output: a table on stdout and data/compact_slots.json.
"""

import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import CELL, FloorTracker, load_record, scene_of  # noqa: E402
from shape import CLEAR, big_class, greedy_slots, compact  # noqa: E402


def main():
    out = []
    for line in open("/home/user/inv-D-scratch/cf/results.jsonl"):
        j = json.loads(line)
        if j["k"] != 0 or j["spec"] != "agent" or j.get("arm", "record") != "record":
            continue
        r = load_record(j["rec"], j["scene"])
        sc = scene_of(r["scene_spec"])
        items = sc.items
        fs = next((p for p, i in enumerate(items) if i["is_soft"]), 0)
        big = next(
            (
                p
                for p, i in enumerate(items)
                if p > fs and not i["is_soft"] and i["length"] * i["width"] >= 0.2
            ),
            None,
        )
        cls_ = big_class(sc, big or 0)
        a = int(round((cls_[0] + 2 * CLEAR) / CELL))
        b = int(round((cls_[1] + 2 * CLEAR) / CELL))
        ft = FloorTracker(sc)
        by = {i["index"]: i for i in items}
        snap = None
        for s in j["steps"]:
            if s.get("event") == "declined" or not s.get("ok") or s.get("size") is None:
                continue
            if big is not None and s["item"] >= big and snap is None:
                snap = True
                break
            it = by[s["item"]]
            ft.add(
                s["ci"],
                s["size"],
                s["pos_local"],
                bool(it["is_soft"]),
                bool(it["is_prioritized"]),
            )
        real = comp = 0
        for ci in range(len(ft.floor)):
            free = ft.floor[ci] & ~ft.soft[ci] & ~ft.hard[ci]
            real += greedy_slots(free, a, b)
            cs = compact(ft.floor[ci], ft.soft[ci], ft.hard[ci])
            comp += greedy_slots(ft.floor[ci] & ~cs & ~ft.hard[ci], a, b)
        m = j.get("metrics") or {}
        row = dict(
            scene=j["scene"],
            wrap=j.get("wrap") or "",
            placed=j["placed"],
            mg=j["mg"],
            reached_big=bool(snap),
            soft_share=round(ft.soft_share(), 3),
            slots_real=real,
            slots_compact=comp,
            soft_count=m.get("soft_count"),
            soft_covered=m.get("soft_covered"),
        )
        out.append(row)
    out.sort(key=lambda x: (x["scene"], x["wrap"]))
    print(
        "| scene | branch | placed / margin | soft floor share at the first big hard item | slots real / compact bound | soft placed / covered |"
    )
    print("|---|---|---|---:|---|---|")
    for x in out:
        print(
            f"| {x['scene']} | {x['wrap'] or 'baseline'} | {x['placed']} / {x['mg']:+d} | {x['soft_share']:.2f}{'' if x['reached_big'] else ' (end, no big hard item)'} | {x['slots_real']} / {x['slots_compact']} | {x['soft_count']} / {x['soft_covered']} |"
        )
    json.dump(
        out, open(os.path.join(HERE, "data", "compact_slots.json"), "w"), indent=0
    )


if __name__ == "__main__":
    main()
