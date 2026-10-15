"""instrument.py: what the shipped agent saw and why it chose, at one decision.

``probe_decision(agent, observation)`` runs the agent's own ``policy`` on the
observation with opt-in wrappers around the module functions it calls (nothing in
rule_alpha is edited; the wrappers are removed on exit) and returns:

* ``action`` and the final placement (rung, surface, pose);
* ``ladder``: per item tried, the ladder's shortlist with every candidate's surface,
  bottom, centre, size, archetypes, the soft-edge key and its vetoes, the survivors
  and the rung order;
* ``pocket``: the pocket guard's view: the hard classes it expects (with their
  arrival probabilities), the slots the ladder's pose keeps, and the ranking of its
  own candidates (floor / on soft / on hard / shelf, bottom, slots), so whether the
  guard overrode and by how much is visible;
* ``stack``: the stack option's proposal when it was asked;
* ``stages``: the order of the stages that ran (ladder, stack, last resort, physics
  resort, grid rescue) and what each returned;
* ``soft_tops``: for a soft item, a census of the stack generator's legal poses by
  support kind under the shipped rules (soft carries load up to the 0.7 m cap) and
  with the cap lifted, so "no soft top existed" and "the cap removed it" can be told
  apart.
"""

import contextlib
import dataclasses
import time

import numpy as np

from rule_alpha import layer1
from rule_alpha import stability as _stability
from rule_alpha._reuse import packed_aabbs_local


def _support_kind(box, container, model, tol=0.03):
    b = float(box.minimum[2])
    if b - model.z_floor < tol:
        return "floor"
    for sh in getattr(model, "shelves", []) or []:
        try:
            if abs(float(sh.maximum[2]) - b) < tol:
                return "shelf"
        except Exception:
            pass
    kinds = set()
    for o, s, p in packed_aabbs_local(container):
        if abs(float(o.maximum[2]) - b) <= tol:
            ox = min(float(o.maximum[0]), float(box.maximum[0])) - max(
                float(o.minimum[0]), float(box.minimum[0])
            )
            oy = min(float(o.maximum[1]), float(box.maximum[1])) - max(
                float(o.minimum[1]), float(box.minimum[1])
            )
            if ox > 0.02 and oy > 0.02:
                kinds.add("soft" if s else ("prio" if p else "hard"))
    return "+".join(sorted(kinds)) if kinds else "shelf/other"


def _r(v, n=3):
    return [round(float(x), n) for x in v]


def cand_row(c, board):
    model = board.model(c.container_idx)
    f = c.features
    return {
        "ci": int(c.container_idx),
        "surface": c.surface,
        "role": c.role,
        "bottom": round(float(c.box.minimum[2]) - model.z_floor, 3),
        "center": _r(c.box.center),
        "size": _r(c.box.size),
        "archetypes": sorted(c.archetypes or []),
        "vetoes": list(c.vetoes or []),
        "on": _support_kind(c.box, board.container(c.container_idx), model),
        "soft_zone_fit": round(float(f.get("soft_zone_fit", 0.0)), 3),
        "soft_cluster": round(float(f.get("soft_cluster", 0.0)), 3),
        "front_right_cost": round(float(f.get("front_right_cost", 0.0)), 3),
    }


def pocket_ranking(guard, board, profile, mass, container_idx, chosen_box, top=12):
    """The pocket guard's alternative() with the whole ranking kept (same scorer,
    same candidates, same filters, no deadline)."""
    from rule_alpha.pocket import SOFT_ALT
    from wedge_rl.stack import stack_candidates

    classes = guard.classes()
    out = {
        "classes": [
            [round(l, 2), round(w, 2), round(h, 2), round(p, 3)]
            for l, w, h, p in classes
        ],
        "remaining": round(guard.frequencies.remaining, 1)
        if guard.frequencies
        else None,
        "seen": guard.frequencies.seen_count if guard.frequencies else None,
    }
    if not classes:
        out["stood_down"] = True
        return out
    guard.scorer.classes = classes
    alt_name = SOFT_ALT if profile.is_soft else "pocket-hard"
    out["chosen_slots"] = round(
        guard.scorer.slots(
            board, container_idx, extra=dataclasses.replace(chosen_box, name=alt_name)
        ),
        3,
    )
    out["now_slots"] = [
        round(guard.scorer.slots(board, ci), 3) for ci in range(len(board.containers))
    ]
    cfg = dataclasses.replace(
        guard.config, stack_soft_min_support=0.0, stack_soft_standing=False
    )
    rows = []
    for ci in range(len(board.containers)):
        cands = stack_candidates(
            board.model(ci),
            board.container(ci),
            cfg,
            profile,
            max_candidates=guard.max_candidates,
            mass=float(mass),
            tower_min=None,
            extra_clearance=0.0,
            z_top=None,
            dense=guard.anchor_step,
        )
        n_all = len(cands)
        cands = [c for c in cands if c.on_floor or c.support_ratio >= guard.min_support]
        for c in cands:
            s = guard.scorer.slots(
                board, ci, extra=dataclasses.replace(c.box, name=alt_name)
            )
            rows.append(
                {
                    "ci": ci,
                    "slots": round(s, 3),
                    "bottom": round(c.bottom - board.model(ci).z_floor, 3),
                    "on": _support_kind(c.box, board.container(ci), board.model(ci)),
                    "support": round(c.support_ratio, 2),
                    "center": _r(c.box.center),
                    "size": _r(c.dims),
                }
            )
        out.setdefault("n_cands", []).append([n_all, len(cands)])
    rows.sort(
        key=lambda x: (-x["slots"], x["bottom"], 0 if x["ci"] == container_idx else 1)
    )
    out["best"] = rows[:top]
    for kind in ("floor", "soft", "hard", "shelf"):
        sub = [x for x in rows if x["on"] == kind]
        out[f"best_{kind}"] = sub[0] if sub else None
        out[f"n_{kind}"] = len(sub)
    out["margin"] = guard.margin
    out["would_override"] = (
        bool(rows) and rows[0]["slots"] > out["chosen_slots"] + guard.margin
    )
    return out


def soft_top_census(board, profile, config, mass=0.0):
    """Legal stack-generator poses by support kind, with the shipped cap and without."""
    from wedge_rl.stack import stack_candidates

    res = {}
    saved = _stability.SOFT_STRUCTURE_MAX_TOP
    try:
        for label, cap in (("capped", saved), ("uncapped", None)):
            _stability.SOFT_STRUCTURE_MAX_TOP = cap
            counts = {}
            best_soft = None
            for ci in range(len(board.containers)):
                model = board.model(ci)
                cands = stack_candidates(
                    model,
                    board.container(ci),
                    config,
                    profile,
                    max_candidates=10**6,
                    mass=float(mass),
                    tower_min=None,
                    extra_clearance=0.0,
                    z_top=None,
                )
                for c in cands:
                    k = _support_kind(c.box, board.container(ci), model)
                    if not c.on_floor and k != "shelf":
                        k = k + ("/full" if c.support_ratio >= 0.6 else "/part")
                    counts[k] = counts.get(k, 0) + 1
                    if k.startswith("soft") and (
                        best_soft is None or c.bottom < best_soft[0]
                    ):
                        best_soft = (
                            round(c.bottom - model.z_floor, 3),
                            ci,
                            _r(c.box.center),
                            _r(c.dims),
                            round(c.support_ratio, 2),
                        )
            res[label] = {"counts": counts, "lowest_soft_top": best_soft}
    finally:
        _stability.SOFT_STRUCTURE_MAX_TOP = saved
    # the soft tops on the board and their heights against the cap
    tops = []
    for ci in range(len(board.containers)):
        model = board.model(ci)
        for o, s, p in packed_aabbs_local(board.container(ci)):
            if s:
                tops.append(round(float(o.maximum[2]), 3))
    res["soft_tops_frame"] = sorted(tops)
    res["cap_value"] = saved
    return res


@contextlib.contextmanager
def _patched(obj, name, wrapper):
    orig = getattr(obj, name)
    setattr(obj, name, wrapper(orig))
    try:
        yield orig
    finally:
        setattr(obj, name, orig)


def probe_decision(agent, observation, census=True):
    log = {"ladder": [], "stack": [], "stages": [], "pocket": None}
    board_ref = {}

    def wrap_vetoes(orig):
        def f(candidates, board, container_idx, config):
            surv, counts = orig(candidates, board, container_idx, config)
            board_ref["board"] = board
            log["_short"] = [c for c in candidates]
            log["_counts"] = dict(counts)
            log["_surv_ids"] = {id(c) for c in surv}
            return surv, counts

        return f

    def wrap_choose(orig):
        def f(board, profile, config, **kw):
            log["_short"] = []
            t0 = time.perf_counter()
            d = orig(board, profile, config, **kw)
            entry = {
                "item": int(profile.index),
                "soft": bool(profile.is_soft),
                "sec": round(time.perf_counter() - t0, 3),
                "decision": None,
            }
            short = log.get("_short") or []
            entry["shortlist"] = [cand_row(c, board) for c in short]
            entry["veto_counts"] = log.get("_counts", {})
            if d is not None:
                entry["decision"] = {
                    "rung": d.placement.archetype,
                    "surface": d.placement.surface,
                    "ci": int(d.placement.container_idx),
                    "bottom": round(
                        float(d.placement.box.minimum[2])
                        - board.model(d.placement.container_idx).z_floor,
                        3,
                    ),
                    "center": _r(d.placement.box.center),
                    "size": _r(d.placement.box.size),
                    "ladder": list(d.ladder or []),
                    "considered": int(d.considered),
                    "n_survivors": len(d.survivors or []),
                }
                if d.survivors:
                    rung = d.placement.archetype
                    try:
                        order = layer1.rung_order(
                            rung,
                            [c for c in d.survivors if rung in c.archetypes],
                            config,
                        )
                    except Exception:
                        order = list(d.survivors)
                    entry["rung_order"] = [cand_row(c, board) for c in order[:15]]
                    entry["survivors"] = [cand_row(c, board) for c in d.survivors[:40]]
            log["ladder"].append(entry)
            log["stages"].append(("ladder", int(profile.index), d is not None))
            return d

        return f

    pocket = getattr(agent, "pocket", None)

    def wrap_alt(orig):
        def f(board, profile, mass, container_idx, chosen_box, deadline, soft=True):
            t0 = time.perf_counter()
            res = orig(
                board, profile, mass, container_idx, chosen_box, deadline, soft=soft
            )
            sec = time.perf_counter() - t0
            try:
                rank = pocket_ranking(
                    pocket, board, profile, mass, container_idx, chosen_box
                )
            except Exception as exc:  # the probe must never change the decision
                rank = {"error": repr(exc)}
            rank["real_override"] = res is not None
            rank["real_sec"] = round(sec, 3)
            if res is not None:
                cand, ci, cs, bs = res
                rank["real_pick"] = {
                    "ci": int(ci),
                    "bottom": round(cand.bottom - board.model(ci).z_floor, 3),
                    "on": _support_kind(cand.box, board.container(ci), board.model(ci)),
                    "chosen_slots": round(cs, 3),
                    "best_slots": round(bs, 3),
                }
            log["pocket"] = rank
            log["stages"].append(("pocket", int(profile.index), res is not None))
            return res

        return f

    stack_opt = getattr(agent, "stack_option", None)

    def wrap_stack(orig):
        def f(board, profile, **kw):
            d = orig(board, profile, **kw)
            log["stack"].append(
                {
                    "item": int(profile.index),
                    "placed": d is not None,
                    "pose": None
                    if d is None
                    else {
                        "bottom": round(
                            float(d.placement.box.minimum[2])
                            - board.model(d.placement.container_idx).z_floor,
                            3,
                        ),
                        "ci": int(d.placement.container_idx),
                        "center": _r(d.placement.box.center),
                        "size": _r(d.placement.box.size),
                        "on": _support_kind(
                            d.placement.box,
                            board.container(d.placement.container_idx),
                            board.model(d.placement.container_idx),
                        ),
                    },
                }
            )
            log["stages"].append(("stack", int(profile.index), d is not None))
            return d

        return f

    def wrap_stage(name):
        def w(orig):
            def f(*a, **kw):
                t0 = time.perf_counter()
                res = orig(*a, **kw)
                log["stages"].append(
                    (name, None, res is not None, round(time.perf_counter() - t0, 2))
                )
                return res

            return f

        return w

    with contextlib.ExitStack() as st:
        st.enter_context(_patched(layer1, "apply_vetoes", wrap_vetoes))
        st.enter_context(_patched(layer1, "choose_for_item", wrap_choose))
        if pocket is not None:
            st.enter_context(_patched(pocket, "alternative", wrap_alt))
        if stack_opt is not None:
            st.enter_context(_patched(stack_opt, "propose", wrap_stack))
        for nm in ("_last_resort", "_physics_resort", "_grid_rescue"):
            st.enter_context(_patched(agent, nm, wrap_stage(nm)))
        t0 = time.perf_counter()
        action = agent.policy(observation)
        log["sec"] = round(time.perf_counter() - t0, 3)
    for k in ("_short", "_counts", "_surv_ids"):
        log.pop(k, None)
    log["action"] = (
        None
        if action is None
        else {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in action.items()}
    )
    d = agent.last_decision
    if action is not None and d is not None:
        b = agent.board
        log["final"] = {
            "rung": d.placement.archetype,
            "surface": d.placement.surface,
            "ci": int(d.placement.container_idx),
            "bottom": round(
                float(d.placement.box.minimum[2])
                - b.model(d.placement.container_idx).z_floor,
                3,
            ),
            "center": _r(d.placement.box.center),
            "size": _r(d.placement.box.size),
            "on": _support_kind(
                d.placement.box,
                b.container(d.placement.container_idx),
                b.model(d.placement.container_idx),
            ),
            "shadow": (agent.last_shadow or {}).get("outcome"),
        }
    if census:
        pool = observation.get("pool_list") or []
        from rule_alpha import classify as cls

        out = []
        for item in pool:
            if item.get("is_soft"):
                prof = cls.classify_item(int(item["index"]), item, agent.config)
                out.append(
                    {
                        "item": int(item["index"]),
                        **soft_top_census(
                            agent.board,
                            prof,
                            agent.config,
                            float(item.get("mass", 0.0)),
                        ),
                    }
                )
        log["soft_tops"] = out
    return log
