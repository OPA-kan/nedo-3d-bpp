"""census.py <record> [<record> ...] -- sealing events in every episode of a record.

For every placement t (board rebuilt from settled poses, sealkit.Episode) and three
reference classes (0.55x0.40x0.24, 0.65x0.45x0.25, 0.75x0.56x0.27, all hard), the
level spots of the board before and after, with the exact transport check.  A spot
the placement *seals* was level and reachable before, is still level after (the
box does not occupy it), and is no longer reachable.  The sealed area is the union
of the sealed windows (m^2, cells of 2 cm).  Per sealing placement the agent's own
readings are recorded too:
  shade   wedge_rl.stack.shade_area (the shade veto / resort order's measure)
  sealed  rule_alpha.layer1 sealed_added (reach_at over reach_probe_heights; the
          ladder computes it for floor candidates only)
Writes $SCRATCH/census/<record>.json.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sealkit as K  # noqa: E402
from rule_alpha.config import DEFAULT_CONFIG  # noqa: E402
from rule_alpha import layer1  # noqa: E402

SCRATCH = os.environ.get("SCRATCH", "/home/user/inv-G-scratch")
REF = [(0.55, 0.40, 0.24), (0.65, 0.45, 0.25), (0.75, 0.56, 0.27)]


def cover(org, a, b, nx, ny):
    """Cells covered by the windows (a x b cells) at the True origins."""
    out = np.zeros((nx, ny), dtype=bool)
    I, J = np.nonzero(org)
    for i, j in zip(I, J):
        out[i : i + a, j : j + b] = True
    return out


def spot_sets(ep, cs, ci, item):
    """{key: (level, reachable)} per spot key (fx, fy, h, z, i, j) for the item in ci."""
    spots, load = K.enumerate_spots(ep, cs, ci, item, soft_support=False)
    res = K.reach_exact(ep, cs, ci, spots)
    lvl, rch = {}, {}
    for sp, (clear, _fb) in zip(spots, res):
        k = (
            round(sp["fx"], 3),
            round(sp["fy"], 3),
            round(sp["h"], 3),
            round(sp["z"], 2),
        )
        lvl[k] = sp["origins"]
        rch[k] = clear
    return lvl, rch, load


def area_of(keyed, load):
    tot = np.zeros((load.nx, load.ny), dtype=bool)
    for (fx, fy, h, z), org in keyed.items():
        a = int(round((fx + K.CLEAR) / K.CELL))
        b = int(round((fy + K.CLEAR) / K.CELL))
        tot |= cover(org, a, b, load.nx, load.ny)
    return float(tot.sum()) * K.CELL * K.CELL


def agent_readings(ep, cs_before, p):
    """shade_area and sealed_added (reach_at at the probe heights) for placement p on
    the board before it, as the agent computes them."""
    from wedge_rl.stack import shade_area, skyline
    from rule_alpha._reuse import AABB

    ci = p["ci"]
    import branch as B

    board = layer1.Board(cs_before, DEFAULT_CONFIG)
    model = board.model(ci)
    box = AABB(tuple(p["pos"]), tuple(p["dims"]), "p")
    shade = float(
        shade_area(box, skyline(board.container(ci), model), float(model.z_ceiling))
    )
    grid = board.grid(ci)
    rect = layer1.box_rect(box)
    mask = grid.rect_mask(rect)
    top_rel = float(box.maximum[2]) - model.z_floor
    worst = 0.0
    for probe in DEFAULT_CONFIG.reach_probe_heights:
        if probe >= top_rel - 1e-9:
            continue
        _rb, sb = board.reach_at_height(ci, probe)
        _ra, sa = layer1.reach_at(grid, model.z_floor, probe, mask, top_rel)
        worst = max(worst, sa - sb)
    return shade, worst


def analyse(ep, with_agent=True):
    import branch as B

    T = len(ep.placements)
    nci = len(ep.raw_containers)
    items = [
        dict(
            length=a,
            width=b,
            height=c,
            is_soft=False,
            is_prioritized=False,
            index=-1 - n,
        )
        for n, (a, b, c) in enumerate(REF)
    ]
    prev = None
    events = []
    traj = []
    for t in range(T + 1):
        cs = ep.containers_at(t)
        cur = {}
        for ci in range(nci):
            for n, it in enumerate(items):
                cur[(ci, n)] = spot_sets(ep, cs, ci, it)
        # trajectory: level and reachable area (class 0 and 1), summed over containers
        row = []
        for n in range(len(items)):
            al = sum(area_of(cur[(ci, n)][0], cur[(ci, n)][2]) for ci in range(nci))
            ar = sum(
                area_of({k: v for k, v in cur[(ci, n)][1].items()}, cur[(ci, n)][2])
                for ci in range(nci)
            )
            row.append((round(al, 3), round(ar, 3)))
        traj.append(row)
        if prev is not None:
            p = ep.placements[t - 1]
            ci = p["ci"]
            sealed = []
            for n in range(len(items)):
                lv0, rc0, load = prev[(ci, n)]
                lv1, rc1, _ = cur[(ci, n)]
                keyed = {}
                for k, r0 in rc0.items():
                    if k not in lv1:
                        continue
                    l1 = lv1[k]
                    r1 = rc1[k]
                    if l1.shape != r0.shape:
                        continue
                    s = r0 & l1 & ~r1
                    if s.any():
                        keyed[k] = s
                sealed.append(round(area_of(keyed, load), 3) if keyed else 0.0)
            s = p["step"]
            ev = dict(
                t=t - 1,
                step=s["step"],
                arch=str(s.get("archetype")).split("/")[0],
                ci=ci,
                pos=[round(v, 3) for v in p["pos"]],
                size=p["dims"],
                soft=p["item"]["is_soft"],
                prio=p["item"]["is_prioritized"],
                standing=p["dims"][2] > max(p["dims"][:2]) + 1e-6,
                sealed=sealed,
                lead=T - t,
            )
            if with_agent and max(sealed) > 0.0:
                try:
                    ev["shade"], ev["sealed_added"] = [
                        round(v, 3)
                        for v in agent_readings(
                            ep,
                            ep.containers_at(t - 1)
                            if False
                            else B.containers_for(ep, t - 1),
                            p,
                        )
                    ]
                except Exception as exc:  # report, do not stop
                    ev["agent_err"] = repr(exc)
            events.append(ev)
        prev = cur
    return dict(
        scene=ep.rec["scene"],
        task=ep.sp["task"],
        margin=ep.margin,
        T=T,
        order=ep.sp["order"],
        stratum=ep.sp["stratum"],
        events=events,
        traj=traj,
    )


def main():
    for record in sys.argv[1:]:
        only = None
        if "=" in record:
            record, only = record.split("=")
            only = only.split(",")
        d = os.path.join(K.RECORDS, record)
        out = []
        path = os.path.join(SCRATCH, "census", record + ".json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        done = {}
        if os.path.exists(path):
            done = {x["scene"]: x for x in json.load(open(path))}
        for f in sorted(os.listdir(d)):
            if not (
                f.startswith("c-hard2-s") or f.startswith("b-hard2-s")
            ) or not f.endswith(".json"):
                continue
            sc = f[:-5]
            if only and sc not in only:
                continue
            if sc in done:
                out.append(done[sc])
                continue
            ep = K.Episode(K.load_record(record, sc))
            out.append(analyse(ep))
            json.dump(out, open(path, "w"), default=float)
            ev = out[-1]["events"]
            big = [e for e in ev if max(e["sealed"]) >= 0.1]
            print(
                f"{record} {sc} m{ep.margin} T{len(ep.placements)} seal events >=0.1: {len(big)} "
                f"total sealed {sum(max(e['sealed']) for e in ev):.2f}",
                flush=True,
            )


if __name__ == "__main__":
    main()
