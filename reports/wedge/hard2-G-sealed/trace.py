"""trace.py <record> <scene> [<scene> ...]  (or --g for the taxonomy's G list)

For every scene: the end board's level spots for the visible items, the exact
transport check (sealkit.exact) against the taxonomy's cell check, and for every
level spot that is sealed at the end, when it became level (t_L) and which
placement first blocked its travel path (t_S).  Spots are grouped into patches
(container, support level).  A patch is *sealed after open* when some spot in it
was level and clear for at least one step (t_L < t_S); the sealing placement is
the one that closed the patch's last open spot.  Otherwise the patch was *born
sealed*: it became level only after its path was already blocked.

Writes one JSON per scene into $SCRATCH/trace/<record>/ and prints a line.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sealkit as K  # noqa: E402

SCRATCH = os.environ.get("SCRATCH", "/home/user/inv-G-scratch")

G_C = [
    "c-hard2-s0059",
    "c-hard2-s0027",
    "c-hard2-s0013",
    "c-hard2-s0060",
    "c-hard2-s0063",
    "c-hard2-s0055",
    "c-hard2-s0081",
    "c-hard2-s0087",
    "c-hard2-s0070",
]
G_B = [
    "b-hard2-s0007",
    "b-hard2-s0009",
    "b-hard2-s0077",
    "b-hard2-s0026",
    "b-hard2-s0064",
    "b-hard2-s0004",
    "b-hard2-s0081",
    "b-hard2-s0056",
    "b-hard2-s0030",
    "b-hard2-s0055",
    "b-hard2-s0073",
    "b-hard2-s0071",
    "b-hard2-s0075",
    "b-hard2-s0086",
]


def cells_reach(ep, cs, ci, item):
    """The taxonomy's reach count (extract.reach_fit), for comparison."""
    sys.path.insert(0, os.path.join(K.REPO, "reports", "wedge", "hard2-miss-taxonomy"))
    import extract  # noqa: E402  (modules already loaded from this worktree)

    load = ep.load(cs, ci)
    return extract.reach_fit(
        load, ep.models[ci], item, soft_support=bool(item["is_soft"])
    )


def pinfo(ep, t):
    p = ep.placements[t]
    s = p["step"]
    it = p["item"]
    return dict(
        t=t,
        step=s["step"],
        item=it["index"],
        arch=str(s.get("archetype")),
        pos=[round(v, 3) for v in p["pos"]],
        size=p["dims"],
        ci=p["ci"],
        soft=it["is_soft"],
        prio=it["is_prioritized"],
        considered=s.get("considered"),
        survivors=s.get("survivors"),
        policy_s=s.get("policy_seconds"),
        shadow=(s.get("shadow") or {}).get("outcome"),
        standing=p["dims"][2] > max(p["dims"][:2]) + 1e-6,
    )


def analyse(ep):
    T = len(ep.placements)
    cs_end = ep.containers_at(T)
    ci_orders = {
        ci: [t for t, p in enumerate(ep.placements) if p["ci"] == ci]
        for ci in range(len(cs_end))
    }
    out = dict(
        scene=ep.rec["scene"],
        task=ep.sp["task"],
        margin=ep.margin,
        placed=ep.placed,
        thr=ep.thr,
        T=T,
        order=ep.sp["order"],
        stratum=ep.sp["stratum"],
        shelves=[bool(c.get("require_shelf")) for c in ep.raw_containers],
        n_containers=len(cs_end),
        visible=[],
        patches=[],
    )
    patches = {}
    for v in ep.visible:
        vrec = dict(
            idx=v["index"],
            dims=[v["length"], v["width"], v["height"]],
            soft=v["is_soft"],
            prio=v["is_prioritized"],
            level=0,
            reach_exact=0,
            reach_cells=0,
        )
        for ci in range(len(cs_end)):
            spots, load = K.enumerate_spots(ep, cs_end, ci, v)
            res = K.reach_exact(ep, cs_end, ci, spots)
            vrec["reach_cells"] += cells_reach(ep, cs_end, ci, v)
            for sp, (clear, fb) in zip(spots, res):
                n_lvl = int(sp["origins"].sum())
                n_cl = int(clear.sum())
                vrec["level"] += n_lvl
                vrec["reach_exact"] += n_cl
                sealed = sp["origins"] & ~clear
                if not sealed.any():
                    continue
                key = (ci, round(sp["z"], 2))
                P = patches.setdefault(
                    key, dict(ci=ci, z=round(sp["z"], 2), spots=[], items=set())
                )
                P["items"].add(v["index"])
                I, J = np.nonzero(sealed)
                for i, j in zip(I, J):
                    packed_idx = int(fb[i, j])
                    npk = len(cs_end[ci]["packed_items"])
                    if packed_idx >= npk:  # the big shelf
                        tS = -1
                    else:
                        tS = ci_orders[ci][packed_idx]
                    P["spots"].append(
                        dict(
                            item=v["index"],
                            fx=sp["fx"],
                            fy=sp["fy"],
                            h=sp["h"],
                            i=int(i),
                            j=int(j),
                            cx=float(sp["cx"][i, j]),
                            cy=float(sp["cy"][i, j]),
                            tS=tS,
                            on_floor=sp["on_floor"],
                            on_shelf=sp["on_shelf"],
                        )
                    )
        out["visible"].append(vrec)
    # t_L: the first prefix at which each sealed spot is level
    for key, P in patches.items():
        ci, z = key
        combos = {}
        for s in P["spots"]:
            combos.setdefault((s["item"], s["fx"], s["fy"], s["h"]), []).append(s)
        for s in P["spots"]:
            s["tL"] = None
        for t in range(T + 1):
            pending = [
                (c, ss) for c, ss in combos.items() if any(x["tL"] is None for x in ss)
            ]
            if not pending:
                break
            cs = ep.containers_at(t)
            load = ep.load(cs, ci)
            for (vi, fx, fy, h), ss in pending:
                item = ep.byidx[vi]
                org = K.level_origins(load, fx, fy, h, z, bool(item["is_soft"]))
                if org is None:
                    continue
                for x in ss:
                    if (
                        x["tL"] is None
                        and x["i"] < org.shape[0]
                        and x["j"] < org.shape[1]
                        and org[x["i"], x["j"]]
                    ):
                        x["tL"] = t
        # summarise the patch
        sp = P["spots"]
        opened = [
            x for x in sp if x["tL"] is not None and x["tS"] >= 0 and x["tL"] <= x["tS"]
        ]
        # tL <= tS: the spot was level after t_L placements and the blocker is placement index tS
        # (prefix tS still clear), so it was open for prefixes tL..tS.
        rec = dict(
            ci=ci,
            z=z,
            n_spots=len(sp),
            items=sorted(P["items"]),
            y_range=[
                round(min(x["cy"] for x in sp), 3),
                round(max(x["cy"] for x in sp), 3),
            ],
            x_range=[
                round(min(x["cx"] for x in sp), 3),
                round(max(x["cx"] for x in sp), 3),
            ],
            on_floor=any(x["on_floor"] for x in sp),
            on_shelf=any(x["on_shelf"] for x in sp),
            shelf_blocked=sum(1 for x in sp if x["tS"] == -1),
        )
        if opened:
            seal_t = max(x["tS"] for x in opened)
            rec["kind"] = "sealed-after-open"
            rec["open_from"] = min(x["tL"] for x in opened)
            rec["seal_t"] = seal_t
            rec["open_steps"] = seal_t + 1 - rec["open_from"]
            rec["n_opened"] = len(opened)
            # which placements closed the opened spots, and how many each
            cl = {}
            for x in opened:
                cl[x["tS"]] = cl.get(x["tS"], 0) + 1
            rec["closers"] = sorted(([t, n] for t, n in cl.items()), key=lambda u: u[0])
            rec["sealer"] = pinfo(ep, seal_t)
        else:
            born = [x for x in sp if x["tL"] is not None]
            rec["kind"] = "born-sealed"
            rec["tL"] = min(x["tL"] for x in born) if born else None
            blk = [x["tS"] for x in sp if x["tS"] >= 0]
            rec["first_blocker_t"] = min(blk) if blk else None
            rec["last_blocker_t"] = max(blk) if blk else None
            rec["blockers"] = sorted({x["tS"] for x in sp})
            if blk:
                rec["sealer"] = pinfo(ep, max(blk))
            if rec["tL"] is not None and rec["tL"] > 0:
                rec["support_t"] = pinfo(ep, rec["tL"] - 1)
        # blocker set at the end (for the whole patch)
        rec["end_blockers"] = sorted({x["tS"] for x in sp})
        stride = max(1, len(sp) // 300)
        rec["spots_xy"] = [
            [
                round(x["cx"], 3),
                round(x["cy"], 3),
                x["tL"],
                x["tS"],
                x["item"],
                x["fx"],
                x["fy"],
                x["h"],
            ]
            for x in sp[::stride]
        ]
        out["patches"].append(rec)
    out["last"] = [pinfo(ep, t) for t in range(max(0, T - 10), T)]
    return out


def main():
    args = sys.argv[1:]
    record = args[0]
    scenes = args[1:]
    if scenes == ["--g"]:
        scenes = (
            G_C
            if record.startswith("gate0-hard2")
            and not record.endswith("-b")
            and "-b-" not in record
            else G_B
        )
        if record.startswith("gate0det"):
            scenes = G_C
    od = os.path.join(SCRATCH, "trace", record)
    os.makedirs(od, exist_ok=True)
    for sc in scenes:
        rec = K.load_record(record, sc)
        ep = K.Episode(rec)
        out = analyse(ep)
        json.dump(
            out, open(os.path.join(od, sc + ".json"), "w"), default=float, indent=1
        )
        vis = "; ".join(
            f"{v['idx']}:{v['level']}/{v['reach_exact']}/{v['reach_cells']}"
            for v in out["visible"]
        )
        pk = "; ".join(
            f"c{p['ci']} z{p['z']} {p['kind']} n{p['n_spots']} "
            + (
                f"open {p['open_from']}..{p['seal_t']} by t{p['seal_t']}:{p['sealer']['arch']}"
                if p["kind"] == "sealed-after-open"
                else f"tL {p.get('tL')} blk {p.get('first_blocker_t')}..{p.get('last_blocker_t')}"
            )
            for p in out["patches"]
        )
        print(
            f"{sc} m{out['margin']} T{out['T']} vis[lvl/exact/cells] {vis} | {pk}",
            flush=True,
        )


if __name__ == "__main__":
    main()
