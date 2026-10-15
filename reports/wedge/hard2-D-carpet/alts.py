"""alts.py: alternative placements at one decision, as official actions.

Every generator rebuilds the agent's board from the observation (as ``policy``
does), so it can be called from a ``physbranch.run_branch`` override.

Spec strings (``action_for(spec, agent, obs)``):
  agent            the agent's own choice (``policy``)
  ladder:N         the N-th candidate of the ladder's chosen rung (0 = the ladder's own
                   pose, before the pocket guard); a soft item barred from a priority
                   container is asked under the last resort's relaxed margins, which is
                   where its ladder pose comes from on those boards
  guard:N          the N-th best pose of the pocket guard's ranking (slots kept for the
                   expected hard classes; floor or tops, half the footprint supported)
  soft:N           the N-th lowest legal pose on soft tops under the shipped rules
                   (the 0.7 m cap), support >= 0.6, best guard slots first within a level
  softnocap:N      the same with the cap lifted for this one box
  shelf:N          the N-th pose on the shelf (lowest, back first)
  floor:N          the N-th floor pose ranked by the guard's slots
  ctr:C            the best guard pose in container C
  pool:P           (B) the agent's pick restricted to pool item P
Each returns (action, info) or (None, info) when the generator has nothing.
"""

import dataclasses

from rule_alpha import classify as cls
from rule_alpha import layer1
from rule_alpha import stability as _stability
from rule_alpha.planner import _placement

from instrument import _support_kind


def fresh_board(agent, obs):
    agent.board = layer1.Board(obs["container_list"], agent.config)
    agent._reapply_zone_scales()
    agent._resize_zones_for_what_is_left()
    agent._pool = obs.get("pool_list") or []
    return agent.board


def profile_of(agent, obs, pi):
    item = obs["pool_list"][pi]
    return cls.classify_item(int(item["index"]), item, agent.config), float(
        item.get("mass", 0.0)
    )


def _act(agent, pi, placement):
    return agent._action(pi, placement)


def _info(placement, board, label):
    ci = int(placement.container_idx)
    m = board.model(ci)
    return {
        "label": label,
        "ci": ci,
        "bottom": round(float(placement.box.minimum[2]) - m.z_floor, 3),
        "center": [round(float(v), 3) for v in placement.box.center],
        "size": [round(float(v), 3) for v in placement.box.size],
        "on": _support_kind(placement.box, board.container(ci), m),
    }


def ladder_decision(agent, obs, pi):
    board = fresh_board(agent, obs)
    prof, _mass = profile_of(agent, obs, pi)
    cfg = agent.config
    d = layer1.choose_for_item(board, prof, cfg)
    stage = "strict"
    if d is None:
        strict = agent.config
        relaxed = dataclasses.replace(
            strict,
            settled_clearance=min(
                strict.settled_clearance, strict.last_resort_settled_clearance
            ),
            com_margin=min(strict.com_margin, strict.last_resort_com_margin),
            routing_any_container=strict.last_resort_any_container,
        )
        b2 = layer1.Board(obs["container_list"], relaxed)
        agent.board = b2
        agent._reapply_zone_scales()
        d = layer1.choose_for_item(b2, prof, relaxed)
        cfg, board, stage = relaxed, b2, "relaxed"
    return d, cfg, board, prof, stage


def ladder_alt(agent, obs, pi, n):
    d, cfg, board, prof, stage = ladder_decision(agent, obs, pi)
    if d is None or not d.survivors:
        return None, {"label": f"ladder:{n}", "none": "no ladder decision"}
    rung = d.placement.archetype
    pool = [c for c in d.survivors if rung in c.archetypes] or list(d.survivors)
    order = (
        layer1.rung_order(rung, pool, cfg) if rung in layer1.ALL_ARCHETYPES else pool
    )
    if n >= len(order):
        return None, {
            "label": f"ladder:{n}",
            "none": f"only {len(order)} in rung {rung}",
        }
    c = order[n]
    pl = layer1.build_placement(c, rung, board, c.container_idx, prof, cfg)
    info = _info(pl, board, f"ladder:{n}")
    info.update(stage=stage, rung=rung, n_rung=len(order))
    return _act(agent, pi, pl), info


def _stack_cands(agent, obs, pi, cap="shipped", dense=None, min_support=0.6):
    from wedge_rl.stack import stack_candidates

    board = fresh_board(agent, obs)
    prof, mass = profile_of(agent, obs, pi)
    g = agent.pocket
    cfg = dataclasses.replace(
        agent.config, stack_soft_min_support=0.0, stack_soft_standing=False
    )
    saved = _stability.SOFT_STRUCTURE_MAX_TOP
    out = []
    try:
        if cap == "none":
            _stability.SOFT_STRUCTURE_MAX_TOP = None
        for ci in range(len(board.containers)):
            cands = stack_candidates(
                board.model(ci),
                board.container(ci),
                cfg,
                prof,
                max_candidates=(g.max_candidates if g else 120)
                * (4 if cap == "none" else 1),
                mass=mass,
                tower_min=None,
                extra_clearance=0.0,
                z_top=None,
                dense=(g.anchor_step if g else 0.06) if dense is None else dense,
            )
            for c in cands:
                if c.on_floor or c.support_ratio >= min_support:
                    out.append(
                        (
                            ci,
                            c,
                            _support_kind(c.box, board.container(ci), board.model(ci)),
                        )
                    )
    finally:
        _stability.SOFT_STRUCTURE_MAX_TOP = saved
    return board, prof, mass, out


def _slots(agent, board, prof, ci, c):
    from rule_alpha.pocket import SOFT_ALT

    g = agent.pocket
    if g is None:
        return 0.0
    classes = g.classes()
    if not classes:
        return 0.0
    g.scorer.classes = classes
    return g.scorer.slots(
        board,
        ci,
        extra=dataclasses.replace(
            c.box, name=SOFT_ALT if prof.is_soft else "pocket-hard"
        ),
    )


def stack_alt(agent, obs, pi, kind, n, cap="shipped", ctr=None):
    board, prof, mass, cands = _stack_cands(agent, obs, pi, cap=cap)
    if kind == "soft":
        cands = [x for x in cands if x[2] == "soft"]
    elif kind == "shelf":
        cands = [x for x in cands if x[2] == "shelf"]
    elif kind == "floor":
        cands = [x for x in cands if x[2] == "floor"]
    if ctr is not None:
        cands = [x for x in cands if x[0] == ctr]
    scored = [
        (round(_slots(agent, board, prof, ci, c), 3), ci, c, k) for ci, c, k in cands
    ]
    if kind in ("soft", "shelf"):
        scored.sort(
            key=lambda t: (
                round(t[2].bottom, 2),
                -t[0],
                -round(float(t[2].box.center[1]), 3),
            )
        )
    else:
        scored.sort(key=lambda t: (-t[0], round(t[2].bottom, 3)))
    label = f"{kind}{'nocap' if cap == 'none' else ''}:{n}" + (
        f"@c{ctr}" if ctr is not None else ""
    )
    if n >= len(scored):
        return None, {"label": label, "none": f"only {len(scored)}"}
    s, ci, c, k = scored[n]
    pl = _placement(c, 1, prof, ci, board.model(ci))
    pl.archetype = "cf-" + kind
    info = _info(pl, board, label)
    info.update(slots=s, n_alts=len(scored), support=round(c.support_ratio, 2))
    return _act(agent, pi, pl), info


def action_for(spec, agent, obs, pi=0):
    kind, _, arg = spec.partition(":")
    if kind == "agent":
        a = agent.policy(obs)
        d = agent.last_decision
        info = {"label": "agent"}
        if a is not None and d is not None:
            info.update(_info(d.placement, agent.board, "agent"))
            info["rung"] = d.placement.archetype
        return a, info
    if kind == "ladder":
        return ladder_alt(agent, obs, pi, int(arg or 0))
    if kind == "guard":
        return stack_alt(agent, obs, pi, "any", int(arg or 0))
    if kind in ("soft", "shelf", "floor"):
        return stack_alt(agent, obs, pi, kind, int(arg or 0))
    if kind == "softnocap":
        return stack_alt(agent, obs, pi, "soft", int(arg or 0), cap="none")
    if kind == "ctr":
        return stack_alt(agent, obs, pi, "any", 0, ctr=int(arg))
    raise KeyError(spec)


def _touches(box, container, model, gap=0.035):
    """The footprint is flush (within ``gap``) with a wall or with a soft box on the
    floor, on some side."""
    from rule_alpha._reuse import packed_aabbs_local
    rect = model.floor_rect
    x0, x1 = float(box.minimum[0]), float(box.maximum[0])
    y0, y1 = float(box.minimum[1]), float(box.maximum[1])
    if y1 >= rect.y_max - gap or x1 >= rect.x_max - gap or x0 <= model.x_limit_at_height(model.z_floor) + gap or y0 <= rect.y_min + gap:
        return True
    for o, s, _p in packed_aabbs_local(container):
        if not s or float(o.minimum[2]) > model.z_floor + 0.06:
            continue
        ox = min(x1, float(o.maximum[0])) - max(x0, float(o.minimum[0]))
        oy = min(y1, float(o.maximum[1])) - max(y0, float(o.minimum[1]))
        if (ox > 0.05 and -gap <= oy <= 0.01) or (oy > 0.05 and -gap <= ox <= 0.01):
            return True
    return False


def compact_placement(agent, obs, pi, ctr=None):
    """The realisable compaction pose for a soft box headed for the floor: a floor
    pose (the guard's generator, full support) in the deepest 5 cm band still open
    (back wall first, so the soft block grows from the back and never seals the door
    side), flush with a wall or with a soft box already on the floor, then from the
    chamfer side (low x).  Lexicographic, no weights."""
    board, prof, mass, cands = _stack_cands(agent, obs, pi)
    rows = []
    for ci, c, k in cands:
        if k != 'floor' or (ctr is not None and ci != ctr):
            continue
        m = board.model(ci)
        rows.append(((-round(float(c.box.maximum[1]) / 0.05), 0 if _touches(c.box, board.container(ci), m) else 1,
                      round(float(c.box.minimum[0]), 3), ci), ci, c))
    if not rows:
        return None, board, prof
    rows.sort(key=lambda t: t[0])
    _key, ci, c = rows[0]
    pl = _placement(c, 1, prof, ci, board.model(ci))
    pl.archetype = 'cf-compact'
    return pl, board, prof


def wrap_compact(agent, max_soft_floor=None):
    """Replace the agent's soft floor poses by compact_placement (through the agent's
    own shadow check; the agent's pose stands when the check vetoes it)."""
    orig = agent.policy
    state = {'n': 0, 'replaced': 0, 'vetoed': 0}
    agent._compact_state = state

    def policy(obs):
        a = orig(obs)
        if a is None:
            return a
        d = agent.last_decision
        pool = obs.get('pool_list') or []
        pi = int(a['item_idx'])
        if not pool[pi].get('is_soft') or d is None:
            return a
        m = agent.board.model(d.placement.container_idx)
        if float(d.placement.box.minimum[2]) - m.z_floor > 0.06:
            return a
        if max_soft_floor is not None and state['n'] >= max_soft_floor:
            return a
        state['n'] += 1
        saved_board = agent.board
        pl, board, _prof = compact_placement(agent, obs, pi)
        if pl is None:
            agent.board = saved_board
            return a
        alt = agent._emit(pi, pl)
        if alt is None:
            state['vetoed'] += 1
            agent.board = saved_board
            return a
        state['replaced'] += 1
        agent.last_decision = dataclasses.replace(d, placement=pl, survivors=[], chosen=None)
        return alt

    agent.policy = policy
    return agent
