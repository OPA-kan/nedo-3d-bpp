"""arch.py <scene> [--record R] [--from K] [--out DIR]: decision archaeology.

Replays a recorded episode in the official simulator, forcing the record's
actions, and from step K on asks the shipped agent at every step before
applying the record's action anyway (the record's course is kept).  For each
probed step it dumps:

* the agent's own answer in the replay (stage/rung, pose) and whether it
  matches the record's action;
* the call's trace: every shadow verdict (pose, ok / hard veto) and every
  shade reading, in the order the agent made them (wrapping the agent's
  ``_shadow_verdict`` and ``_shade_of``; behaviour unchanged);
* the ladder for the item, recomputed with ``layer1.choose_for_item`` on the
  agent's board: the candidates considered, the veto counts, the rung order,
  each rung's eligible survivors, the chosen rung's best 6 with their key
  terms, and for the best 4 of the chosen rung and the best of every other
  rung the shade area and a fresh shadow verdict;
* the floor before the step (from the observation's settled poses): free,
  usable (a 0.55 x 0.40 + 3 cm window), dead, largest empty rectangle,
  usable surface for the 0.40 x 0.55 x 0.24 window over every level.

Output: <out>/arch-<scene>.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H  # noqa: E402
import strips as S  # noqa: E402
from rule_alpha import classify as cls  # noqa: E402
from rule_alpha import layer1  # noqa: E402
from rule_alpha._reuse import packed_aabbs_local  # noqa: E402

SCRATCH = "/home/user/inv-H-scratch"


def rnd(v, n=3):
    return [round(float(x), n) for x in v]


def floor_of(agent, obs):
    out = []
    for ci, c in enumerate(obs["container_list"]):
        model = agent.board.model(ci)
        st = S.CState(model)
        for box, soft, _p in packed_aabbs_local(c):
            st.boxes.append((box, bool(soft)))
        L, occ, free, usable = st.floor()
        a, hx, hy = S.max_rect(free)
        top = float(st.load().usable(*S.WIN, None, 1).sum()) * S.CELL * S.CELL
        out.append(
            {
                "free": round(float(free.sum()) * S.CELL**2, 3),
                "usable": round(float(usable.sum()) * S.CELL**2, 3),
                "dead": round(float((free & ~usable).sum()) * S.CELL**2, 3),
                "ler": [round(hx * S.CELL, 2), round(hy * S.CELL, 2)],
                "usable_top": round(top, 3),
                "map": ascii_map(st, L, occ, free, usable),
            }
        )
    return out


def ascii_map(st, L, occ, free, usable, step=2):
    """Floor map, door at the bottom, x to the right, 4 cm a character:
    '#' hard box on the floor, 's' soft, '.' usable free floor, '-' dead free floor."""
    soft = np.zeros_like(occ)
    for b, sf in st.boxes:
        if sf and float(b.minimum[2]) < st.model.z_floor + S.FLOOR_BAND:
            soft |= L.mask(b)
    rows = []
    for j in range(L.ny - 1, -1, -step):
        row = ""
        for i in range(0, L.nx, step):
            if occ[i, j]:
                row += "s" if soft[i, j] else "#"
            elif usable[i, j]:
                row += "."
            elif free[i, j]:
                row += "-"
            else:
                row += " "
        rows.append(row)
    return rows


def cand_digest(c, key=None):
    f = c.features
    d = {
        "center": rnd(c.box.center),
        "size": rnd(c.box.size),
        "surface": c.surface,
        "role": c.role,
        "family": c.family,
        "orient": int(c.orientation.index),
        "top_z": round(float(f.get("top_z", 0.0)), 3),
        "footprint": round(float(f.get("footprint", 0.0)), 3),
        "y_back": round(float(f.get("y_back", 0.0)), 3),
        "row_waste": round(float(f.get("row_waste", 0.0)), 3),
        "stranded_added": round(float(f.get("stranded_added", 0.0)), 3),
        "frontier_contact": round(float(f.get("frontier_contact", 0.0)), 3),
        "plateau": round(float(f.get("hard_plateau_largest", 0.0)), 3),
        "level_residual": round(float(f.get("level_residual", 0.0)), 3),
        "sealed_added": round(float(f.get("sealed_added", 0.0)), 3),
        "neighbour_step": round(float(f.get("neighbour_height_step", 0.0)), 3),
        "archetypes": sorted(c.archetypes),
    }
    if key is not None:
        d["key"] = [
            round(float(x), 4)
            if isinstance(x, (int, float, np.floating, np.integer, bool))
            else str(x)
            for x in key
        ]
    return d


def ladder_dump(agent, obs, pool_index):
    item = obs["pool_list"][pool_index]
    profile = cls.classify_item(int(item["index"]), item, agent.config)
    t0 = time.perf_counter()
    dec = layer1.choose_for_item(agent.board, profile, agent.config)
    out = {"seconds": round(time.perf_counter() - t0, 2), "class": profile.cargo_class}
    if dec is None:
        out["none"] = True
        return out, None, profile
    surv = dec.survivors
    out.update(
        {
            "considered": dec.considered,
            "survivors": len(surv),
            "veto_counts": dec.veto_counts,
            "ladder": dec.ladder,
            "chosen_rung": dec.placement.archetype,
            "container": int(dec.placement.container_idx),
        }
    )
    rungs = []
    for name in dec.ladder:
        pool = [c for c in surv if name in c.archetypes]
        if pool:
            rungs.append((name, layer1.rung_order(name, pool, agent.config)))
    out["rungs"] = [(n, len(p)) for n, p in rungs]
    return out, (dec, rungs), profile


def verdict(agent, obs, action, item):
    sim = agent._shadow_sim()
    if sim is None:
        return None
    sim.sync(obs["container_list"])
    v = agent._shadow_verdict(sim, action, item)
    return {
        k: (round(float(v[k]), 3) if isinstance(v[k], float) else v[k])
        for k in ("transport_ok", "settle_ok", "drift_xy", "angle_deg", "ok")
        if k in v
    } | {"hard": agent._shadow_hard(v)}


def install_trace(agent, log):
    orig_v = agent._shadow_verdict
    orig_s = agent._shade_of

    def v_wrap(sim, action, item):
        v = orig_v(sim, action, item)
        if log.get("on"):
            log["events"].append(
                {
                    "ev": "verdict",
                    "pos": rnd(action["place_pos"]),
                    "orient": int(action["orientation"]),
                    "ci": int(action["container_idx"]),
                    "ok": bool(v.get("ok")),
                    "hard": bool(agent._shadow_hard(v)),
                    "drift_xy": round(float(v.get("drift_xy", 0.0)), 3),
                    "angle": round(float(v.get("angle_deg", 0.0)), 1),
                    "transport": bool(v.get("transport_ok")),
                    "settle": bool(v.get("settle_ok")),
                }
            )
        return v

    def s_wrap(placement):
        a = orig_s(placement)
        if log.get("on"):
            log["events"].append(
                {
                    "ev": "shade",
                    "center": rnd(placement.box.center),
                    "size": rnd(placement.box.size),
                    "arch": placement.archetype,
                    "area": round(float(a), 3),
                }
            )
        return a

    agent._shadow_verdict = v_wrap
    agent._shade_of = s_wrap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene")
    ap.add_argument("--record", default=None)
    ap.add_argument("--from", dest="k0", type=int, default=None)
    ap.add_argument("--back", type=int, default=12)
    ap.add_argument("--out", default=f"{SCRATCH}/arch")
    ap.add_argument(
        "--det", action="store_true", help="ask the deterministic-budget arm"
    )
    args = ap.parse_args()
    scene, rec, arm = H.load(args.scene, args.record)
    if args.det:
        arm = H.det_arm(arm)
    acts = H.recorded_actions(rec)
    n = len(acts)
    k0 = args.k0 if args.k0 is not None else max(0, n - args.back)
    log = {"events": [], "on": False}
    dumps = []

    def on_agent(agent):
        install_trace(agent, log)
        orig_policy = agent.policy

        def pol(obs):
            log["events"] = []
            log["on"] = True
            try:
                return orig_policy(obs)
            finally:
                log["on"] = False

        agent.policy = pol

    def probe(i, agent, obs, action):
        t0 = time.perf_counter()
        events = list(log["events"])
        dec = agent.last_decision
        rec_a = acts[i] if i < n else None
        d = {
            "step": i,
            "n_steps": n,
            "item": obs["pool_list"][int(action["item_idx"])]["index"]
            if action
            else None,
            "pool": [
                {
                    k: it[k]
                    for k in (
                        "index",
                        "length",
                        "width",
                        "height",
                        "is_soft",
                        "is_prioritized",
                    )
                }
                for it in obs["pool_list"]
            ],
            "agent": None
            if action is None
            else {
                "arch": dec.placement.archetype if dec is not None else None,
                "shadow": (agent.last_shadow or {}).get("outcome"),
                "pos_local": rnd(dec.placement.box.center) if dec is not None else None,
                "size": rnd(dec.placement.box.size) if dec is not None else None,
                "ci": int(action["container_idx"]),
                "pool_index": int(action["item_idx"]),
                "reason": getattr(dec.placement, "reason", "")
                if dec is not None
                else "",
            },
            "record": None
            if rec_a is None
            else {
                "arch": rec_a["_arch"],
                "pos_local": rec_a["_pos_local"],
                "size": rec_a["_size"],
                "pool_index": rec_a["item_idx"],
                "ci": rec_a["container_idx"],
            },
            "trace": events,
            "floor_before": floor_of(agent, obs),
        }
        if action is not None and rec_a is not None and dec is not None:
            d["match"] = bool(
                int(action["item_idx"]) == int(rec_a["item_idx"])
                and np.allclose(
                    dec.placement.box.center, rec_a["_pos_local"], atol=2e-3
                )
            )
        # the ladder for the item the record placed (or the agent's)
        pi = (
            rec_a["item_idx"]
            if rec_a is not None
            else (int(action["item_idx"]) if action else 0)
        )
        lad, extra, profile = ladder_dump(agent, obs, pi)
        item = obs["pool_list"][pi]
        if extra is not None:
            ldec, rungs = extra
            chosen_name = ldec.placement.archetype
            out_rungs = []
            for name, ordered in rungs:
                key_fn = None
                entry = {"rung": name, "n": len(ordered), "top": []}
                top_n = 6 if name == chosen_name else 1
                for r, c in enumerate(ordered[:top_n]):
                    cd = cand_digest(c)
                    if (name == chosen_name and r < 4) or name != chosen_name:
                        try:
                            a = H.alt_action(
                                agent, ldec, c, archetype=name, pool_index=pi
                            )
                            cd["shade"] = round(
                                float(agent._shade_of(a["_placement"])), 3
                            )
                            cd["verdict"] = verdict(agent, obs, a, item)
                            cd["built_center"] = a["_pos_local"]
                        except Exception as exc:  # noqa: BLE001
                            cd["err"] = repr(exc)
                    entry["top"].append(cd)
                out_rungs.append(entry)
            lad["rung_detail"] = out_rungs
        d["ladder"] = lad
        d["probe_seconds"] = round(time.perf_counter() - t0, 1)
        dumps.append(d)
        print(
            f"[{args.scene}] step {i}/{n} rec {d['record'] and d['record']['arch']} agent {d['agent'] and d['agent']['arch']} "
            f"match {d.get('match')} ladder {lad.get('chosen_rung')} surv {lad.get('survivors')} "
            f"usable {[f['usable'] for f in d['floor_before']]} top {[f['usable_top'] for f in d['floor_before']]} "
            f"({d['probe_seconds']}s)",
            flush=True,
        )
        return None

    res = H.run(
        scene,
        arm,
        rec,
        sim="physics",
        k=k0,
        probe=probe,
        follow_record=True,
        probe_steps=set(range(k0, n + 1)),
        on_agent=on_agent,
    )
    os.makedirs(args.out, exist_ok=True)
    json.dump(
        {
            "scene": args.scene,
            "record": args.record or H.REC[args.scene[0].upper()],
            "k0": k0,
            "n_steps": n,
            "replay": {k: res[k] for k in ("placed", "margin", "end", "seconds")},
            "replay_steps": res["steps"],
            "dumps": dumps,
        },
        open(f"{args.out}/arch-{args.scene}.json", "w"),
        default=str,
    )
    print(
        f"[{args.scene}] replay placed {res['placed']} margin {res['margin']} end {res['end']} in {res['seconds']}s",
        flush=True,
    )


if __name__ == "__main__":
    main()
