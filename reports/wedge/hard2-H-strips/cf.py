"""cf.py <scene> --ks K1,K2,... : counterfactual branches in the official simulator.

At each branch step k the record's actions are forced for steps < k, then
one placement is changed and the shipped agent (deterministic budgets,
i.e. the v50 arm with its clock-dependent budgets lifted; the physics resort
and the shadow keep their own clocks) plays to the end.  Branch kinds:

* ``null``   -- the agent's own answer at k (the reference: what the replay
                gives without a change; compare with the record);
* ``veto<j>`` -- the agent's (j+1)-th acceptable answer: the first j poses
                its shadow check would have accepted at step k are refused
                (their verdict turned into a hard veto), so the agent goes
                on exactly as it would on a real veto -- the shadow
                alternatives, the stack option, the last resort, the
                physics resort, the grid rescue.  Agent-consistent "next
                best" whatever stage placed the box;
* ``rung<r>`` -- the r-th distinct pose of the ladder's chosen rung order;
* ``other:<rung>`` -- the best distinct pose of another rung;
* ``vetoed:<reason>`` -- a shortlisted candidate the ladder's vetoes removed
                (legal by the analytic validator, refused by policy).

Every alternative is built with ``layer1.build_placement`` (compaction
included) and the agent's ``_action``.  Output: <out>/cf-<scene>.json.
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
from rule_alpha import classify as cls  # noqa: E402
from rule_alpha import layer1  # noqa: E402

SCRATCH = "/home/user/inv-H-scratch"


def rnd(v, n=3):
    return [round(float(x), n) for x in v]


def candidates(agent, obs, pool_index):
    """The ladder's decision for the item, its rung orders and the shortlist
    candidates its vetoes removed."""
    item = obs["pool_list"][pool_index]
    profile = cls.classify_item(int(item["index"]), item, agent.config)
    captured = []
    orig = layer1.apply_vetoes

    def cap(cands, board, ci, config):
        captured.append(list(cands))
        return orig(cands, board, ci, config)

    layer1.apply_vetoes = cap
    try:
        dec = layer1.choose_for_item(agent.board, profile, agent.config)
    finally:
        layer1.apply_vetoes = orig
    if dec is None:
        return None, [], []
    surv = dec.survivors
    rung_lists = []
    for name in dec.ladder:
        pool = [c for c in surv if name in c.archetypes]
        if pool:
            rung_lists.append((name, layer1.rung_order(name, pool, agent.config)))
    vetoed = []
    if captured:
        short = max(captured, key=len)
        ids = {id(c) for c in surv}
        vetoed = [c for c in short if id(c) not in ids]
        vetoed.sort(key=lambda c: (-float(c.features.get("footprint", 0.0)), -float(c.features.get("y_back", 0.0))))
    return dec, rung_lists, vetoed


def pose_key(c):
    return (round(float(c.box.center[0]) / 0.02), round(float(c.box.center[1]) / 0.02),
            round(float(c.box.center[2]) / 0.02), tuple(round(float(v), 2) for v in c.box.size))


def ladder_alternatives(agent, obs, pool_index, own_center=None, n_rung=2, n_other=2, n_vetoed=3):
    """The distinct alternative poses for the item at ``pool_index``:
    [(label, rung, candidate)].  'rung1' (the ladder's own pick) appears when
    the agent's answer was not it (a veto downstream replaced it)."""
    dec, rung_lists, vetoed = candidates(agent, obs, pool_index)
    if dec is None:
        return [], None
    seen = []

    def distinct(c):
        if own_center is not None and np.allclose(c.box.center, own_center, atol=0.02):
            return False
        k = pose_key(c)
        if k in seen:
            return False
        seen.append(k)
        return True

    out = []
    chosen = dec.placement.archetype
    for name, ordered in rung_lists:
        if name != chosen:
            continue
        r = 0
        for pos, c in enumerate(ordered):
            if r >= n_rung + 1:
                break
            if distinct(c):
                out.append((f"rung{pos + 1}", name, c))
                r += 1
    o = 0
    for name, ordered in rung_lists:
        if name == chosen or o >= n_other:
            continue
        for c in ordered:
            if distinct(c):
                out.append((f"other:{name}", name, c))
                o += 1
                break
    v = 0
    for c in vetoed:
        if v >= n_vetoed:
            break
        if not distinct(c):
            continue
        _s, counts = layer1.apply_vetoes([c], agent.board, int(c.container_idx), agent.config)
        reason = ",".join(sorted(counts)) or "none"
        out.append((f"vetoed:{reason}", "max-footprint", c))
        v += 1
    return out, dec


def find_candidate(agent, obs, pool_index, center, size):
    dec, rung_lists, vetoed = candidates(agent, obs, pool_index)
    if dec is None:
        return None, None
    for name, ordered in rung_lists:
        for c in ordered:
            if np.allclose(c.box.center, center, atol=0.006) and np.allclose(c.box.size, size, atol=0.006):
                return dec, (name, c)
    for c in vetoed:
        if np.allclose(c.box.center, center, atol=0.006) and np.allclose(c.box.size, size, atol=0.006):
            if not c.archetypes:
                c.archetypes = layer1.eligible_archetypes(c, agent.config)
            return dec, ("max-footprint", c)
    return dec, None


def install_veto(agent, j, state):
    """Refuse the first j acceptable shadow verdicts of the first policy call."""
    orig_v = agent._shadow_verdict
    orig_p = agent.policy
    state.update({"calls": 0, "refused": []})

    def v_wrap(sim, action, item):
        v = orig_v(sim, action, item)
        if (
            state["calls"] == 1
            and len(state["refused"]) < j
            and not agent._shadow_hard(v)
        ):
            state["refused"].append(rnd(action["place_pos"]))
            v = dict(v, settle_ok=False, ok=False)
        return v

    def p_wrap(obs):
        state["calls"] += 1
        return orig_p(obs)

    agent._shadow_verdict = v_wrap
    agent.policy = p_wrap


def summarise(res, k):
    st = [s for s in res["steps"] if not s.get("forced")]
    first = st[0] if st else {}
    return {
        "placed": res["placed"],
        "margin": res["margin"],
        "end": res["end"],
        "seconds": res["seconds"],
        "at_k": {
            x: first.get(x)
            for x in ("arch", "pos_local", "size", "ci", "ok", "shadow", "item_index")
        },
        "after": [
            (s.get("arch"), s.get("ok")) if "event" not in s else (s["event"],)
            for s in st[1:]
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene")
    ap.add_argument("--ks", required=True)
    ap.add_argument("--record", default=None)
    ap.add_argument("--veto", type=int, default=3)
    ap.add_argument("--rung", type=int, default=2)
    ap.add_argument("--other", type=int, default=2)
    ap.add_argument("--vetoed", type=int, default=3)
    ap.add_argument(
        "--tf", action="store_true", help="continue with the time-faithful arm instead"
    )
    ap.add_argument("--out", default=f"{SCRATCH}/cf")
    args = ap.parse_args()
    scene, rec, arm = H.load(args.scene, args.record or ("gate0det-hard2" if args.scene[0] == "c" else None))
    if not args.tf:
        arm = H.det_arm(arm)
    os.makedirs(args.out, exist_ok=True)
    path = f"{args.out}/cf-{args.scene}.json"
    data = (
        json.load(open(path))
        if os.path.exists(path)
        else {"scene": args.scene, "branches": {}}
    )
    ref = json.load(open(f"{SCRATCH}/ref/ref-{args.scene}.json"))
    acts = ref["actions"]
    n = len(acts)
    data["ref_placed"] = ref["placed"]
    data["n_steps"] = n
    data["record_placed"] = rec["metrics"]["placed_count"]
    data["thr"] = len(scene.items) // 2 + 1

    def save():
        json.dump(data, open(path, "w"), default=str)

    for k in [int(x) for x in args.ks.split(",")]:
        if k < 0 or k > n:
            continue
        key = str(k)
        B = data["branches"].setdefault(key, {})
        t_k = time.perf_counter()
        # null, which also lists the ladder's alternatives
        listing = {}

        def probe_list(i, agent, obs, action):
            pi = (
                int(action["item_idx"])
                if action is not None
                else (acts[k]["item_idx"] if k < n else 0)
            )
            own = (
                agent.last_decision.placement.box.center
                if (action is not None and agent.last_decision is not None)
                else None
            )
            alts, dec = ladder_alternatives(
                agent, obs, pi, own, args.rung, args.other, args.vetoed
            )
            listing["alts"] = [
                (lab, rung, rnd(c.box.center), rnd(c.box.size)) for lab, rung, c in alts
            ]
            listing["pi"] = pi
            listing["agent"] = (
                None
                if action is None
                else {
                    "arch": agent.last_decision.placement.archetype
                    if agent.last_decision
                    else None
                }
            )
            return None

        if "null" not in B:
            res = H.run(scene, arm, rec, sim="physics", k=k, probe=probe_list, forced_actions=acts)
            B["null"] = summarise(res, k)
            B["_alts"] = listing.get("alts", [])
            B["_pi"] = listing.get("pi")
            save()
            print(
                f"[{args.scene}] k={k} null placed {res['placed']} margin {res['margin']} ({res['seconds']}s) alts {len(B['_alts'])}",
                flush=True,
            )
        for j in range(1, args.veto + 1):
            lab = f"veto{j}"
            if lab in B:
                continue
            state = {}
            res = H.run(
                scene,
                arm,
                rec,
                sim="physics",
                k=k,
                on_agent=lambda a, j=j: install_veto(a, j, state),
                forced_actions=acts,
            )
            B[lab] = summarise(res, k)
            B[lab]["refused"] = state.get("refused")
            save()
            print(
                f"[{args.scene}] k={k} {lab} placed {res['placed']} margin {res['margin']} at_k {B[lab]['at_k'].get('arch')} ({res['seconds']}s)",
                flush=True,
            )
        for idx, (lab, rung, center, size) in enumerate(B.get("_alts", [])):
            if lab in B:
                continue

            def probe_alt(i, agent, obs, action, center=center, size=size, lab=lab):
                pi = listing.get("pi", B.get("_pi", int(action["item_idx"]) if action is not None else 0))
                dec, hit = find_candidate(agent, obs, pi, center, size)
                if hit is None:
                    print(f"[{args.scene}] k={k} {lab}: candidate not found", flush=True)
                    return None
                rname, c = hit
                a = H.alt_action(agent, dec, c, archetype=rname, pool_index=pi)
                a["_arch"] = "alt:" + lab
                return a

            res = H.run(scene, arm, rec, sim="physics", k=k, probe=probe_alt, forced_actions=acts)
            B[lab] = summarise(res, k)
            B[lab]["planned"] = {"rung": rung, "center": center, "size": size}
            save()
            print(
                f"[{args.scene}] k={k} {lab} placed {res['placed']} margin {res['margin']} ok {B[lab]['at_k'].get('ok')} ({res['seconds']}s)",
                flush=True,
            )
        print(
            f"[{args.scene}] k={k} done in {time.perf_counter() - t_k:.0f}s", flush=True
        )
    save()


if __name__ == "__main__":
    main()
