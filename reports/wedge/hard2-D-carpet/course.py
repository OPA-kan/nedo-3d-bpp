"""course.py [record ...] -> /home/user/inv-D-scratch/course/<record>.json and a compact
summary data/course_summary.json (records only, nothing rerun).

Per placed step of every hard2 episode: the item (soft / priority / dims and its
stream position), the rung (``archetype``), the surface, the container, the bottom
above the floor, what it rests on (floor / shelf / soft / hard / priority tops), and
the floor shares after the step (soft / hard footprints of boxes with their bottom
under 0.10 m, free) from the settled poses.  Per episode: when the carpet formed
(soft floor share crossing 0.2 / 0.3 / 0.4), how many soft boxes went to the floor,
on soft, on hard, on the shelf, by which rung, and the hard items after the carpet.
"""

import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (
    FloorTracker,
    REACH,
    SOFT_CARPET,
    load_record,
    need_of,
    records,
    rung,  # noqa: E402
    scene_of,
    step_poses,
)

SCRATCH = "/home/user/inv-D-scratch/course"
HERE = os.path.dirname(os.path.abspath(__file__))
SETS = [
    "gate0-hard2",
    "gate0-hard2-b",
    "gate0-hard2-b-r2",
    "gate0det-hard2",
    "bandntdet-hard2",
    "bandnt-hard2",
    "bandnt-hard2-b",
]


def episode(path):
    import json as _j

    r = _j.load(open(path))
    sp = r["scene_spec"]
    sc = scene_of(sp)
    m = r["metrics"]
    thr = m["total_items"] // 2 + 1
    ft = FloorTracker(sc)
    rows = []
    for s, it, pos in step_poses(r, "final"):
        bottom, under = ft.add(
            s["container_idx"],
            s["size"],
            pos,
            bool(it["is_soft"]),
            bool(it["is_prioritized"]),
        )
        rows.append(
            dict(
                k=len(rows),
                idx=s["item_index"],
                soft=bool(it["is_soft"]),
                prio=bool(it["is_prioritized"]),
                dims=[it["length"], it["width"], it["height"]],
                size=s["size"],
                rung=rung(s),
                surface=s.get("surface"),
                ci=s["container_idx"],
                bottom=round(bottom, 3),
                on=under,
                soft_share=round(ft.soft_share(), 4),
                hard_share=round(ft.hard_share(), 4),
                free_share=round(ft.free_share(), 4),
                sec=s.get("policy_seconds"),
                considered=s.get("considered"),
                survivors=s.get("survivors"),
                shadow=(s.get("shadow") or {}).get("outcome"),
            )
        )
    stream = [
        dict(
            idx=i["index"],
            soft=bool(i["is_soft"]),
            prio=bool(i["is_prioritized"]),
            dims=[i["length"], i["width"], i["height"]],
        )
        for i in sc.items
    ]
    decl = [s for s in r["steps"] if s.get("event") == "declined"]
    return dict(
        scene=r["scene"],
        task=sp["task"],
        order=sp["order"],
        stratum=sp["stratum"],
        mix=sp["mix"],
        n=sp["containers_n"],
        shelves=sp["shelves"],
        soft_share_spec=sp["soft_share"],
        total=m["total_items"],
        thr=thr,
        placed=m["placed_count"],
        mg=m["placed_count"] - thr,
        end=m["end_reason"],
        need=round(need_of(r), 4),
        over_budget=m.get("over_budget_steps"),
        steps=rows,
        stream=stream,
        last_call=decl[-1]["policy_seconds"] if decl else None,
    )


def summarise(e):
    st = e["steps"]
    out = {
        k: e[k]
        for k in (
            "scene",
            "task",
            "order",
            "stratum",
            "mix",
            "n",
            "shelves",
            "total",
            "thr",
            "placed",
            "mg",
            "end",
            "need",
            "over_budget",
            "last_call",
        )
    }
    out["soft_share_end"] = st[-1]["soft_share"] if st else 0.0
    out["carpet"] = out["soft_share_end"] >= SOFT_CARPET
    out["in_reach"] = e["need"] <= REACH
    for lvl in (0.2, 0.3, 0.4):
        k = next((x["k"] for x in st if x["soft_share"] >= lvl), None)
        out[f"k_soft{int(lvl * 100)}"] = k
    soft = [x for x in st if x["soft"]]
    out["n_soft"] = len(soft)
    out["n_hard"] = len(st) - len(soft)
    where = collections.Counter()
    by_rung_floor = collections.Counter()
    for x in soft:
        if x["on"] == "floor":
            w = "floor"
            by_rung_floor[x["rung"]] += 1
        elif x["surface"] == "shelf" or x["on"] == "shelf/other":
            w = "shelf"
        elif "soft" in x["on"] and "hard" not in x["on"] and "prio" not in x["on"]:
            w = "soft"
        else:
            w = "hard/mixed"
        where[w] += 1
    out["soft_where"] = dict(where)
    out["soft_floor_by_rung"] = dict(by_rung_floor)
    # the stream: soft items among the first half, position of the first hard item
    stream = e["stream"]
    out["stream_soft_first_thr"] = sum(1 for i in stream[: e["thr"]] if i["soft"])
    out["first_hard_pos"] = next(
        (p for p, i in enumerate(stream) if not i["soft"]), None
    )
    # the first soft-on-soft placement, the last one, and soft floor placements after the first soft-on-soft
    sos = [x["k"] for x in soft if x["on"] == "soft"]
    out["k_first_soft_on_soft"] = sos[0] if sos else None
    out["k_last_soft_on_soft"] = sos[-1] if sos else None
    out["soft_floor_after_first_sos"] = sum(
        1 for x in soft if x["on"] == "floor" and sos and x["k"] > sos[0]
    )
    # hard placed after the soft share passed 0.4
    k40 = out["k_soft40"]
    out["hard_after_k40"] = sum(
        1 for x in st if not x["soft"] and k40 is not None and x["k"] > k40
    )
    # hard items' floor share at the end and the free floor
    out["hard_share_end"] = st[-1]["hard_share"] if st else 0.0
    out["free_share_end"] = st[-1]["free_share"] if st else 1.0
    out["rescue_share"] = sum(
        1
        for x in st
        if x["rung"]
        in (
            "physics-resort",
            "count-mode",
            "grid-rescue",
            "grid-rescue-cover",
            "fallback",
        )
    ) / max(1, len(st))
    return out


def main():
    os.makedirs(SCRATCH, exist_ok=True)
    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    sets = sys.argv[1:] or SETS
    summ = {}
    for rec in sets:
        eps = [episode(p) for p in records(rec)]
        json.dump(eps, open(os.path.join(SCRATCH, rec + ".json"), "w"))
        summ[rec] = [summarise(e) for e in eps]
        print(
            rec,
            len(eps),
            "carpets",
            sum(1 for s in summ[rec] if s["carpet"]),
            flush=True,
        )
    path = os.path.join(HERE, "data", "course_summary.json")
    old = json.load(open(path)) if os.path.exists(path) else {}
    old.update(summ)
    json.dump(old, open(path, "w"), indent=0)


if __name__ == "__main__":
    main()
