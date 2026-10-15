"""ref.py <scene> [<scene> ...]: the reference run and its decision archaeology.

The shipped v50 arm of the scene's record, with deterministic budgets
(``deterministic_budgets=true``: the clock-dependent budgets inside a call
lifted; the shadow check and the physics resort keep their own clocks), plays
the scene in the official simulator from the start.  With full-precision
actions the simulator is deterministic (``round_test`` in the report: a
forced replay of the same actions reproduces every settled pose to 0.0 m,
while the bench records' actions, rounded to 0.1 mm, move them by 2-50 mm),
so this run is the trunk every counterfactual branch (``cf.py``) forces.

At every step it dumps (``arch.py`` helpers):
* the agent's answer (stage/rung, pose, shadow outcome, the reason string);
* the call's trace: every shadow verdict and shade reading in order;
* the ladder for the item the agent placed (or, at a decline, the first
  pool item), recomputed with ``layer1.choose_for_item`` on the agent's
  board: considered, veto counts, rung order, per rung the eligible
  survivors; the chosen rung's best 6 with their key terms; for its best 3
  and every other rung's best the shade area and a shadow verdict from a
  private ShadowSim (not the agent's, so its clocks are untouched);
* the floor before the step and a 4 cm ASCII map.

Output: /home/user/inv-H-scratch/ref/ref-<scene>.json (actions at full
precision, steps, dumps).
"""

from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H  # noqa: E402
from arch import cand_digest, floor_of, install_trace, ladder_dump, rnd  # noqa: E402

OUT = "/home/user/inv-H-scratch/ref"
_SIM = {}


def own_verdict(agent, obs, action, item):
    from rule_alpha import shadow

    if "sim" not in _SIM:
        _SIM["sim"] = shadow.ShadowSim()
    sim = _SIM["sim"]
    sim.sync(obs["container_list"])
    v = sim.check(
        int(action["container_idx"]),
        item,
        tuple(float(x) for x in action["place_pos"]),
        int(action["orientation"]),
    )
    cfg = agent.config
    ok = bool(
        v["transport_ok"]
        and v["settle_ok"]
        and v["drift_xy"] <= cfg.shadow_max_drift_xy
        and v["angle_deg"] <= cfg.shadow_max_angle_deg
    )
    hard = bool(
        not v["transport_ok"]
        or not v["settle_ok"]
        or v["drift_xy"] > cfg.shadow_hard_drift_xy
        or v["angle_deg"] > cfg.shadow_hard_angle_deg
    )
    return {
        "transport_ok": bool(v["transport_ok"]),
        "settle_ok": bool(v["settle_ok"]),
        "drift_xy": round(float(v["drift_xy"]), 3),
        "angle_deg": round(float(v["angle_deg"]), 1),
        "ok": ok,
        "hard": hard,
    }


def reference(name, record=None):
    scene, rec, arm = H.load(name, record)
    arm = H.det_arm(arm)
    log = {"events": [], "on": False}
    actions = []
    dumps = []

    def on_agent(agent):
        install_trace(agent, log)
        orig_policy = agent.policy

        def pol(obs):
            log["events"] = []
            log["on"] = True
            try:
                a = orig_policy(obs)
            finally:
                log["on"] = False
            if a is not None:
                actions.append(
                    {
                        "item_idx": int(a["item_idx"]),
                        "container_idx": int(a["container_idx"]),
                        "orientation": int(a["orientation"]),
                        "place_pos": [float(v) for v in np.asarray(a["place_pos"])],
                    }
                )
            return a

        agent.policy = pol

    def probe(i, agent, obs, action):
        t0 = time.perf_counter()
        dec = agent.last_decision
        d = {
            "step": i,
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
                "tried": (agent.last_shadow or {}).get("tried"),
                "pos_local": rnd(dec.placement.box.center) if dec is not None else None,
                "size": rnd(dec.placement.box.size) if dec is not None else None,
                "surface": getattr(dec.placement, "surface", None)
                if dec is not None
                else None,
                "ci": int(action["container_idx"]),
                "pool_index": int(action["item_idx"]),
                "item": int(obs["pool_list"][int(action["item_idx"])]["index"]),
                "reason": getattr(dec.placement, "reason", "")
                if dec is not None
                else "",
            },
            "trace": list(log["events"]),
            "floor_before": floor_of(agent, obs),
        }
        pi = int(action["item_idx"]) if action is not None else 0
        lad, extra, _profile = ladder_dump(agent, obs, pi)
        item = obs["pool_list"][pi]
        if extra is not None:
            ldec, rungs = extra
            chosen_name = ldec.placement.archetype
            out_rungs = []
            for name_r, ordered in rungs:
                entry = {"rung": name_r, "n": len(ordered), "top": []}
                top_n = 6 if name_r == chosen_name else 1
                for r, c in enumerate(ordered[:top_n]):
                    cd = cand_digest(c)
                    if (name_r == chosen_name and r < 3) or name_r != chosen_name:
                        try:
                            a = H.alt_action(
                                agent, ldec, c, archetype=name_r, pool_index=pi
                            )
                            cd["shade"] = round(
                                float(
                                    agent.__class__._shade_of(agent, a["_placement"])
                                ),
                                3,
                            )
                            cd["verdict"] = own_verdict(agent, obs, a, item)
                            cd["built_center"] = a["_pos_local"]
                        except Exception as exc:  # noqa: BLE001
                            cd["err"] = repr(exc)
                    entry["top"].append(cd)
                out_rungs.append(entry)
            lad["rung_detail"] = out_rungs
        d["ladder"] = lad
        d["probe_seconds"] = round(time.perf_counter() - t0, 1)
        dumps.append(d)
        return None

    res = H.run(
        scene,
        arm,
        rec,
        sim="physics",
        k=None,
        probe=probe,
        probe_steps=set(range(0, 400)),
        on_agent=on_agent,
    )
    os.makedirs(OUT, exist_ok=True)
    out = {
        "scene": name,
        "record": record or H.REC[name[0].upper()],
        "arm": arm.spec,
        "record_placed": rec["metrics"]["placed_count"],
        "thr": len(scene.items) // 2 + 1,
        "placed": res["placed"],
        "margin": res["margin"],
        "end": res["end"],
        "seconds": res["seconds"],
        "actions": actions,
        "steps": res["steps"],
        "final": res["final"],
        "dumps": dumps,
    }
    json.dump(out, open(f"{OUT}/ref-{name}.json", "w"), default=str)
    print(
        f"[{name}] ref placed {res['placed']} margin {res['margin']} end {res['end']} "
        f"(record {rec['metrics']['placed_count']}) in {res['seconds']}s",
        flush=True,
    )
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    rec = None
    if args and args[0].startswith("--record="):
        rec = args[0].split("=", 1)[1]
        args = args[1:]
    for n in args:
        if os.path.exists(f"{OUT}/ref-{n}.json") and "--force" not in sys.argv:
            continue
        if n.startswith("--"):
            continue
        reference(n, rec)
