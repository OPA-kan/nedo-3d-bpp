"""orient.py <scene> [...]: was a standing pose available at the floor placements?

Replays a reference run exactly (its full-precision actions, the record's
course kept) and, at every step where the agent put a hard box on the floor,
asks the ladder (on the agent's board, after the agent's own call) what it had
per orientation class:

* legal: every floor pose of that class the ladder's generator and validator
  produce (all orientations of the item, no vetoes);
* shortlisted / surviving: in the ladder's own pipeline (its orientation
  policy, shortlist and vetoes), with the veto counts of that class;
* the best surviving standing pose: its rank in the chosen rung's order, the
  key terms it lost on, its shade and a shadow verdict (private ShadowSim:
  drift and angle, i.e. whether it would tip), and how much usable floor it
  would leave against the agent's pose.

"standing" = the height is not the box's smallest dimension and is > 0.3 m
(as strips.py).
Output: /home/user/inv-H-scratch/orient/orient-<scene>.json
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H  # noqa: E402
import strips as S  # noqa: E402
from cf import candidates  # noqa: E402
from ref import own_verdict  # noqa: E402
from rule_alpha import classify as cls  # noqa: E402
from rule_alpha import layer1  # noqa: E402
from rule_alpha._reuse import packed_aabbs_local  # noqa: E402

OUT = "/home/user/inv-H-scratch/orient"


def standing(size):
    return size[2] > min(size[0], size[1]) + 1e-6 and size[2] > 0.3


def usable_floor_after(agent, obs, ci, box):
    st = S.CState(agent.board.model(ci))
    for b, soft, _p in packed_aabbs_local(obs["container_list"][ci]):
        st.boxes.append((b, bool(soft)))
    if box is not None:
        st.boxes.append((box, False))
    _L, _occ, free, usable = st.floor()
    return float(usable.sum()) * S.CELL**2


def main(scene_name):
    ref = json.load(open(f"/home/user/inv-H-scratch/ref/ref-{scene_name}.json"))
    scene, rec, arm = H.load(
        scene_name, "gate0det-hard2" if scene_name[0] == "c" else None
    )
    arm = H.det_arm(arm)
    acts = ref["actions"]
    dumps = ref["dumps"]
    floor_steps = set()
    for i, x in enumerate(dumps):
        a = x["agent"]
        if a is None or a["pos_local"] is None:
            continue
        it = x["pool"][a["pool_index"]]
        bottom = a["pos_local"][2] - a["size"][2] / 2.0
        if bottom < 0.04 + 0.10 and not it["is_soft"]:
            floor_steps.add(i)
    out = []

    def probe(i, agent, obs, action):
        x = dumps[i]
        a = x["agent"]
        pi = a["pool_index"]
        item = obs["pool_list"][pi]
        profile = cls.classify_item(int(item["index"]), item, agent.config)
        ci = a["ci"]
        rec_ = {
            "step": i,
            "item": S.cls_of(item),
            "agent_arch": a["arch"],
            "agent_size": a["size"],
            "agent_standing": standing(a["size"]),
            "reason": a.get("reason", "")[:60],
        }
        # legal floor poses by class
        legal = {"lying": [], "standing": []}
        for orient in profile.orientations:
            try:
                cands = layer1.generate_candidates(
                    agent.board, profile, ci, orient, ("floor",), agent.config
                )
            except Exception:  # noqa: BLE001
                cands = []
            for c in cands:
                legal["standing" if standing(list(c.box.size)) else "lying"].append(c)
        rec_["legal"] = {k: len(v) for k, v in legal.items()}
        # the ladder's pipeline
        dec, rung_lists, vetoed = candidates(agent, obs, pi)
        surv = dec.survivors if dec is not None else []
        rec_["survivors"] = {
            "lying": sum(
                1
                for c in surv
                if c.surface == "floor" and not standing(list(c.box.size))
            ),
            "standing": sum(
                1 for c in surv if c.surface == "floor" and standing(list(c.box.size))
            ),
        }
        vs = {}
        for c in vetoed:
            if c.surface != "floor" or not standing(list(c.box.size)):
                continue
            _s, counts = layer1.apply_vetoes(
                [c], agent.board, int(c.container_idx), agent.config
            )
            for k in counts:
                vs[k] = vs.get(k, 0) + 1
        rec_["standing_vetoed_by"] = vs
        rec_["standing_shortlisted"] = (
            sum(
                1 for c in vetoed if c.surface == "floor" and standing(list(c.box.size))
            )
            + rec_["survivors"]["standing"]
        )
        from rule_alpha.geometry import AABB

        rec_["usable_floor_before"] = round(usable_floor_after(agent, obs, ci, None), 3)
        rec_["agent_floor_after"] = round(
            usable_floor_after(
                agent,
                obs,
                ci,
                AABB(center=tuple(a["pos_local"]), size=tuple(a["size"])),
            ),
            3,
        )
        # best standing survivor in the chosen rung
        if dec is not None:
            chosen = dec.placement.archetype
            for name, ordered in rung_lists:
                if name != chosen:
                    continue
                for rank, c in enumerate(ordered):
                    if c.surface == "floor" and standing(list(c.box.size)):
                        f = c.features
                        try:
                            act = H.alt_action(
                                agent, dec, c, archetype=name, pool_index=pi
                            )
                            v = own_verdict(agent, obs, act, item)
                            shade = round(
                                float(
                                    agent.__class__._shade_of(agent, act["_placement"])
                                ),
                                3,
                            )
                        except Exception as exc:  # noqa: BLE001
                            v, shade = repr(exc), None
                        rec_["best_standing"] = {
                            "rank": rank + 1,
                            "of": len(ordered),
                            "size": [round(float(s), 3) for s in c.box.size],
                            "center": [round(float(s), 3) for s in c.box.center],
                            "footprint": round(float(f.get("footprint", 0)), 3),
                            "row_waste": round(float(f.get("row_waste", 0)), 3),
                            "y_back": round(float(f.get("y_back", 0)), 3),
                            "tipping": round(float(c.orientation.tipping_ratio), 2),
                            "shade": shade,
                            "verdict": v,
                            "floor_after": round(
                                usable_floor_after(agent, obs, ci, c.box), 3
                            ),
                        }
                        break
                top = ordered[0]
                rec_["rung_top"] = {
                    "rung": name,
                    "size": [round(float(s), 3) for s in top.box.size],
                    "footprint": round(float(top.features.get("footprint", 0)), 3),
                    "row_waste": round(float(top.features.get("row_waste", 0)), 3),
                }
        # best legal standing pose by usable floor left (no vetoes)
        best = None
        for c in legal["standing"]:
            u = usable_floor_after(agent, obs, ci, c.box)
            if best is None or u > best[0]:
                best = (u, c)
        if best is not None:
            rec_["best_legal_standing_floor_after"] = round(best[0], 3)
            rec_["best_legal_standing"] = [
                round(float(s), 3) for s in best[1].box.center
            ]
        out.append(rec_)
        print(
            f"[{scene_name}] {i} {rec_['item']} agent {'STAND' if rec_['agent_standing'] else 'lie'} {a['arch']} legal {rec_['legal']} surv {rec_['survivors']} "
            f"vetoes {vs} best {rec_.get('best_standing', {}).get('rank')} floor {rec_['usable_floor_before']}->{rec_['agent_floor_after']} "
            f"(stand best {rec_.get('best_standing', {}).get('floor_after')}, legal-best {rec_.get('best_legal_standing_floor_after')})",
            flush=True,
        )
        return None

    H.run(
        scene,
        arm,
        rec,
        sim="physics",
        k=len(acts),
        probe=probe,
        follow_record=True,
        probe_steps=floor_steps,
        forced_actions=acts,
    )
    os.makedirs(OUT, exist_ok=True)
    json.dump(
        {"scene": scene_name, "margin": ref["margin"], "steps": out},
        open(f"{OUT}/orient-{scene_name}.json", "w"),
        default=str,
    )


if __name__ == "__main__":
    for n in sys.argv[1:]:
        if not os.path.exists(f"{OUT}/orient-{n}.json"):
            main(n)
