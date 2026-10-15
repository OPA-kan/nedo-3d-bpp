"""branch.py -- decision probes and counterfactual rollouts from a recorded board.

The board after the first t placements of a bench record (settled poses, as in
sealkit.Episode) is loaded into bench.rollouts.EpisodeState with the record's own
arm (``deterministic_budgets=true`` added: the ladder's pool loop, the pocket
guard and the pool item search stop reading the clock; the physics resort and
the shadow keep theirs).  The shadow check runs in its private pybullet world
when pybullet imports, so the rungs, the shade veto and the rescue stages are
the shipped ones; the board then evolves on the analytic model.

Instrumentation is a monkeypatch for the duration of one probe: every
``layer1.choose_for_item`` call (per pool item), every ``_emit`` (with the
shadow verdict and the shade), and the stage that produced the action.  The
shipped code is untouched.

    probe(rec, scene, t)            -> dict (what the agent does at step t, and why)
    rollout(rec, scene, t, alt=...) -> dict (placed count at the end, per branch)
"""

from __future__ import annotations

import contextlib
import copy
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sealkit as K  # noqa: E402

from bench.arms import make_arm  # noqa: E402
from bench.rollouts import EpisodeState  # noqa: E402
from rule_alpha import layer1  # noqa: E402
from rule_alpha.agent import RuleAlphaAgent  # noqa: E402

_ARMS = {}


def arm_for(rec):
    spec = rec["arm"]["arm"]
    if "deterministic_budgets" not in spec:
        spec += ",deterministic_budgets=true"
    if spec not in _ARMS:
        _ARMS[spec] = make_arm(spec)
    return _ARMS[spec]


def pool_sequence(ep):
    """The pool before each placement (list of item dicts), replaying the record's picks."""
    items = [dict(i) for i in ep.items]
    look = ep.scene.look_ahead
    queue = list(items)
    pool = []
    while len(pool) < look and queue:
        pool.append(queue.pop(0))
    seq = []
    for p in ep.placements:
        seq.append(([dict(i) for i in pool], [dict(i) for i in queue]))
        idx = p["item"]["index"]
        k = next(n for n, it in enumerate(pool) if it["index"] == idx)
        pool.pop(k)
        while len(pool) < look and queue:
            pool.append(queue.pop(0))
    seq.append(([dict(i) for i in pool], [dict(i) for i in queue]))
    return seq


def containers_for(ep, t):
    """rule_alpha observation containers with the first t placements (world x)."""
    cs = ep.scene.rule_alpha_containers()
    for p in ep.placements[:t]:
        c = cs[p["ci"]]
        it = p["item"]
        ox = float(c.get("center", (0.0, 0.0, 0.0))[0])
        c["packed_items"].append(
            {
                "index": it["index"],
                "length": float(it["length"]),
                "width": float(it["width"]),
                "height": float(it["height"]),
                "mass": float(it.get("mass", 0.0)),
                "is_prioritized": bool(it["is_prioritized"]),
                "is_soft": bool(it["is_soft"]),
                "orientation": int(p["step"].get("orientation", 0)),
                "dims": tuple(float(v) for v in p["dims"]),
                "pos": (p["pos"][0] + ox, p["pos"][1], p["pos"][2]),
                "belongs_to": p["ci"],
                "layer": int(p["step"].get("layer", 1) or 1),
            }
        )
    return cs


def state_at(ep, t, rec):
    seq = pool_sequence(ep)
    pool, queue = seq[t]
    st = EpisodeState(
        ep.scene, arm_for(rec), containers=containers_for(ep, t), queue=queue, pool=pool
    )
    st.steps = t
    return st


# --- instrumentation -------------------------------------------------------


def _cand(c, rank=None, key=None):
    b = c.box
    f = c.features
    return dict(
        rank=rank,
        ci=int(c.container_idx),
        surface=c.surface,
        role=c.role,
        orient=int(c.orientation.index),
        centre=[round(float(v), 3) for v in b.center],
        size=[round(float(v), 3) for v in b.size],
        y_back=round(float(f.get("y_back", b.maximum[1])), 3),
        top=round(float(b.maximum[2]), 3),
        footprint=round(float(f.get("footprint", 0.0)), 3),
        sealed_added=round(float(f.get("sealed_added", 0.0)), 3),
        stranded_added=round(float(f.get("stranded_added", 0.0)), 3),
        terrain_behind=round(float(f.get("terrain_behind", 0.0)), 3),
        vetoes=list(getattr(c, "vetoes", []) or []),
        archetypes=sorted(c.archetypes),
        key=[
            (
                round(float(v), 4)
                if isinstance(v, (float, int, np.floating, np.integer))
                and not isinstance(v, bool)
                else v
            )
            for v in key
        ]
        if key is not None
        else None,
    )


def decision_dump(decision, config, top=12):
    if decision is None:
        return None
    out = dict(
        archetype=decision.placement.archetype,
        considered=decision.considered,
        veto_counts=dict(decision.veto_counts or {}),
        ladder=list(decision.ladder or []),
        n_survivors=len(decision.survivors or []),
        rungs=[],
    )
    surv = list(decision.survivors or [])
    for name in decision.ladder or []:
        pool = [c for c in surv if name in c.archetypes]
        if not pool:
            continue
        ordered = layer1.rung_order(name, pool, config)
        keyfn = layer1.ARCHETYPE_KEYS.get(name)
        cands = []
        for r, c in enumerate(ordered[:top]):
            try:
                key = keyfn(c) if keyfn else None
            except Exception:
                key = None
            cands.append(_cand(c, r, key))
        out["rungs"].append(
            dict(
                name=name,
                n=len(pool),
                top=cands,
                chosen_here=decision.chosen is not None and decision.chosen in pool,
            )
        )
        if len(out["rungs"]) >= 4:
            break
    if decision.chosen is not None:
        out["chosen"] = _cand(decision.chosen)
    out["placement"] = dict(
        centre=[round(float(v), 3) for v in decision.placement.box.center],
        size=[round(float(v), 3) for v in decision.placement.box.size],
        ci=int(decision.placement.container_idx),
    )
    return out


@contextlib.contextmanager
def instrument(agent, log):
    orig_choose = layer1.choose_for_item
    orig_emit = RuleAlphaAgent._emit
    stages = ["_physics_resort", "_grid_rescue", "_last_resort", "_pool_item_search"]
    orig_stage = {s: getattr(RuleAlphaAgent, s) for s in stages}
    so = agent.stack_option
    orig_propose = so.propose if so is not None else None
    cfg = agent.config

    def choose(board, profile, config, *a, **kw):
        d = orig_choose(board, profile, config, *a, **kw)
        log.append(
            dict(
                ev="ladder", item=int(profile.index), decision=decision_dump(d, config)
            )
        )
        return d

    def emit(self, pool_index, placement):
        act = orig_emit(self, pool_index, placement)
        log.append(
            dict(
                ev="emit",
                pool_index=int(pool_index),
                arch=placement.archetype,
                centre=[round(float(v), 3) for v in placement.box.center],
                size=[round(float(v), 3) for v in placement.box.size],
                ci=int(placement.container_idx),
                accepted=act is not None,
                shadow=copy.deepcopy(self.last_shadow),
            )
        )
        return act

    def wrap_stage(name):
        f = orig_stage[name]

        def g(self, *a, **kw):
            log.append(dict(ev="stage-in", stage=name))
            r = f(self, *a, **kw)
            log.append(dict(ev="stage-out", stage=name, action=r is not None))
            return r

        return g

    def propose(board, profile, *a, **kw):
        d = orig_propose(board, profile, *a, **kw)
        log.append(
            dict(
                ev="stack-rl",
                item=int(profile.index),
                placement=None
                if d is None
                else dict(
                    centre=[round(float(v), 3) for v in d.placement.box.center],
                    size=[round(float(v), 3) for v in d.placement.box.size],
                ),
            )
        )
        return d

    layer1.choose_for_item = choose
    RuleAlphaAgent._emit = emit
    for s in stages:
        setattr(RuleAlphaAgent, s, wrap_stage(s))
    if so is not None:
        so.propose = propose
    try:
        yield
    finally:
        layer1.choose_for_item = orig_choose
        RuleAlphaAgent._emit = orig_emit
        for s in stages:
            setattr(RuleAlphaAgent, s, orig_stage[s])
        if so is not None:
            so.propose = orig_propose


def probe_state(st):
    log = []
    t0 = time.perf_counter()
    with instrument(st.agent, log):
        action, decision = st.decide()
    secs = time.perf_counter() - t0
    out = dict(seconds=round(secs, 2), log=log, declined=action is None)
    if action is not None:
        pl = decision.placement
        out["action"] = dict(
            item=int(st.pool[int(action["item_idx"])]["index"]),
            pool_index=int(action["item_idx"]),
            arch=pl.archetype,
            ci=int(pl.container_idx),
            centre=[round(float(v), 3) for v in pl.box.center],
            size=[round(float(v), 3) for v in pl.box.size],
            shadow=copy.deepcopy(st.agent.last_shadow),
        )
    return out, action, decision


def run_to_end(st, max_steps=400):
    """Continue with the agent until it declines; returns the placements made."""
    made = []
    for _ in range(max_steps):
        if not st.pool:
            break
        action, decision = st.decide()
        if action is None:
            break
        pl = decision.placement
        made.append(
            dict(
                item=int(st.pool[int(action["item_idx"])]["index"]),
                arch=pl.archetype,
                ci=int(pl.container_idx),
                centre=[round(float(v), 3) for v in pl.box.center],
                size=[round(float(v), 3) for v in pl.box.size],
            )
        )
        st.apply_placement(pl, int(action["item_idx"]))
    return made



# --- counterfactual decisions -------------------------------------------------

class Protected:
    """Spots (from a trace patch) to keep reachable: a box 'seals' a spot when it
    blocks the spot's exact transport sweep without occupying the spot itself; it
    'fills' the patch when it rests at the patch level over a spot's footprint."""

    def __init__(self, ep, patch):
        self.ci = int(patch['ci'])
        self.z = float(patch['z'])
        self.cont = ep.raw_containers[self.ci]
        self.spots = [x for x in patch['spots_xy']]
        self.on_floor = bool(patch['on_floor'])
        self.on_shelf = bool(patch['on_shelf'])

    def _local(self, box, ci, st):
        c = np.asarray(box.center, float).copy()
        return c, np.asarray(box.size, float)

    def seals(self, box, ci):
        if int(ci) != self.ci:
            return 0
        c = np.asarray(box.center, float); d = np.asarray(box.size, float)
        lo = (c - d / 2)[None]; hi = (c + d / 2)[None]
        n = 0
        for (cx, cy, _tl, _ts, _it, fx, fy, h) in self.spots:
            slo = np.array([cx - fx / 2, cy - fy / 2, self.z]); shi = np.array([cx + fx / 2, cy + fy / 2, self.z + h])
            if np.all(lo[0] < shi - 1e-6) and np.all(hi[0] > slo + 1e-6):
                continue  # occupies the spot: not a seal
            zt = K.transport_z(self.cont, self.z, h, self.on_floor, self.on_shelf)
            if K.exact_blockers(self.cont, lo, hi, [cx], [cy], fx, fy, h, zt).any():
                n += 1
        return n

    def left_open(self, box, ci, t):
        """(open before, open after): spots open at prefix t (level, path clear) and
        how many of them this box leaves open (neither blocked nor occupied)."""
        opened = [x for x in self.spots if x[2] is not None and x[3] is not None and x[3] >= 0 and x[2] <= t <= x[3]]
        if int(ci) != self.ci:
            return len(opened), len(opened)
        c = np.asarray(box.center, float); d = np.asarray(box.size, float)
        lo = (c - d / 2)[None]; hi = (c + d / 2)[None]
        n = 0
        for (cx, cy, _tl, _ts, _it, fx, fy, h) in opened:
            slo = np.array([cx - fx / 2, cy - fy / 2, self.z]); shi = np.array([cx + fx / 2, cy + fy / 2, self.z + h])
            if np.all(lo[0] < shi - 1e-6) and np.all(hi[0] > slo + 1e-6):
                continue
            zt = K.transport_z(self.cont, self.z, h, self.on_floor, self.on_shelf)
            if not K.exact_blockers(self.cont, lo, hi, [cx], [cy], fx, fy, h, zt).any():
                n += 1
        return len(opened), n

    def fills(self, box, ci):
        if int(ci) != self.ci:
            return False
        c = np.asarray(box.center, float); d = np.asarray(box.size, float)
        if abs((c[2] - d[2] / 2) - self.z) > 0.03:
            return False
        for (cx, cy, _tl, _ts, _it, fx, fy, h) in self.spots:
            ox = min(c[0] + d[0] / 2, cx + fx / 2) - max(c[0] - d[0] / 2, cx - fx / 2)
            oy = min(c[1] + d[1] / 2, cy + fy / 2) - max(c[1] - d[1] / 2, cy - fy / 2)
            if ox > 0.05 and oy > 0.05:
                return True
        return False


def ladder_ranked(survivors, ladder, config):
    """All survivors in the ladder's order: rung by rung, each rung in its order;
    returns [(candidate, rung name)] without repeats."""
    out, seen = [], set()
    for name in ladder:
        pool = [c for c in survivors if name in c.archetypes]
        if not pool:
            continue
        for c in layer1.rung_order(name, pool, config):
            if id(c) not in seen:
                seen.add(id(c)); out.append((c, name))
    for c in survivors:
        if id(c) not in seen:
            seen.add(id(c)); out.append((c, 'fallback'))
    return out


def decide_cf(st, mode='agent', k=1, protect=None, defer_item=None):
    """One decision under a counterfactual.
    mode 'agent'   : the agent's own pick;
         'kth'     : the k-th candidate (k=1 is the ladder's pick) in the ladder's
                     order over the survivors of every ladder decision this call
                     (installed as the selector);
         'noseal'  : the first candidate in the ladder's order that seals none of
                     ``protect``'s spots (selector), and every other stage's pose
                     refused at _emit when it seals; when the call then declines,
                     the agent's own pick is played (reported);
         'fill'    : the first candidate in ladder order that fills the patch;
         'defer'   : the decision with ``defer_item`` taken out of the pool (B).
    Returns (action, decision, note)."""
    agent = st.agent
    cfg = st.config
    note = {}
    if mode == 'agent':
        a, d = st.decide()
        return a, d, note
    if mode in ('alt', 'alt-noseal'):
        # the k-th distinct pose the agent would emit: the first k-1 refused at
        # _emit, so the agent moves on (next survivor on a shadow veto, next pool
        # item, next stage) exactly as after a shadow refusal; 'alt-noseal' keeps
        # refusing until a pose seals none of the protected spots (at most k tries)
        refused = []
        orig_emit2 = RuleAlphaAgent._emit

        def emit2(self, pool_index, placement):
            c = np.asarray(placement.box.center, float)
            for (ci, cc, it) in refused:
                if ci == int(placement.container_idx) and it == int(self._pool[pool_index]['index']) and np.abs(c - cc).max() < 0.01:
                    return None
            return orig_emit2(self, pool_index, placement)
        tries = []
        a = d = None
        for n in range(k):
            RuleAlphaAgent._emit = emit2
            try:
                a, d = st.decide()
            finally:
                RuleAlphaAgent._emit = orig_emit2
            if a is None:
                break
            pl = d.placement
            seal = protect.seals(pl.box, pl.container_idx) if protect is not None else None
            tries.append(dict(arch=pl.archetype, centre=[round(float(v), 3) for v in pl.box.center], seals=seal))
            if mode == 'alt' and n == k - 1:
                break
            if mode == 'alt-noseal' and seal == 0:
                break
            refused.append((int(pl.container_idx), np.asarray(pl.box.center, float), int(st.pool[int(a['item_idx'])]['index'])))
        note['tries'] = tries
        if a is None:
            note['declined_at'] = len(tries) + 1
        return a, d, note
    if mode == 'defer':
        keep = st.pool
        idx = [n for n, it in enumerate(keep) if int(it['index']) != int(defer_item)]
        st.pool = [keep[n] for n in idx]
        try:
            a, d = st.decide()
        finally:
            st.pool = keep
        if a is not None:
            a = dict(a); a['item_idx'] = idx[int(a['item_idx'])]
        return a, d, note
    orig_sel = agent.selector
    orig_emit = RuleAlphaAgent._emit

    def selector(survivors, chosen, chosen_archetype, board, container_idx, profile):
        ranked = ladder_ranked(survivors, archetype_ladder_for(board, profile, container_idx, cfg), cfg)
        if mode == 'kth':
            if len(ranked) >= k:
                note.setdefault('picked', []).append(dict(rank=k, n=len(ranked), rung=ranked[k - 1][1]))
                return ranked[k - 1][0], ranked[k - 1][1]
            return None
        for r, (c, name) in enumerate(ranked):
            if mode == 'noseal' and protect.seals(c.box, c.container_idx) == 0:
                note.setdefault('picked', []).append(dict(rank=r + 1, n=len(ranked), rung=name))
                return c, name
            if mode == 'fill' and protect.fills(c.box, c.container_idx):
                note.setdefault('picked', []).append(dict(rank=r + 1, n=len(ranked), rung=name))
                return c, name
        note.setdefault('none_in', []).append(len(ranked))
        return None

    def emit(self, pool_index, placement):
        if mode == 'noseal' and protect.seals(placement.box, placement.container_idx) > 0:
            note['refused'] = note.get('refused', 0) + 1
            return None
        if mode == 'fill' and not protect.fills(placement.box, placement.container_idx):
            note['refused'] = note.get('refused', 0) + 1
            return None
        return orig_emit(self, pool_index, placement)

    agent.selector = selector
    if mode in ('noseal', 'fill'):
        RuleAlphaAgent._emit = emit
    try:
        a, d = st.decide()
    finally:
        agent.selector = orig_sel
        RuleAlphaAgent._emit = orig_emit
    if a is None and mode in ('noseal', 'fill'):
        note['fell_back'] = True
        a, d = st.decide()
    return a, d, note


def archetype_ladder_for(board, profile, container_idx, cfg):
    return layer1.archetype_ladder(profile, board, container_idx, cfg)


def branch_rollout(ep, rec, t, mode='agent', k=1, protect=None, defer_item=None, persistent=False, max_steps=400):
    """Board after t placements; one counterfactual decision (or, with persistent,
    the protection kept on every later decision until the patch is filled), then the
    shipped agent to the end.  Returns dict with the total placed count."""
    t0 = time.perf_counter()
    st = state_at(ep, t, rec)
    a, d, note = decide_cf(st, mode, k, protect, defer_item)
    first = None
    made = 0
    if a is not None:
        pl = d.placement
        first = dict(item=int(st.pool[int(a['item_idx'])]['index']), arch=pl.archetype, ci=int(pl.container_idx),
                     centre=[round(float(v), 3) for v in pl.box.center], size=[round(float(v), 3) for v in pl.box.size],
                     seals=protect.seals(pl.box, pl.container_idx) if protect else None,
                     fills=protect.fills(pl.box, pl.container_idx) if protect else None)
        st.apply_placement(pl, int(a['item_idx']))
        made = 1
        filled = first['fills'] if protect else False
        rest = []
        for _ in range(max_steps):
            if not st.pool:
                break
            if persistent and protect is not None and not filled:
                a2, d2, n2 = decide_cf(st, 'noseal', protect=protect)
            else:
                a2, d2 = st.decide()
            if a2 is None:
                break
            pl2 = d2.placement
            if protect is not None and protect.fills(pl2.box, pl2.container_idx):
                filled = True
            rest.append(dict(item=int(st.pool[int(a2['item_idx'])]['index']), arch=pl2.archetype))
            st.apply_placement(pl2, int(a2['item_idx']))
        made += len(rest)
    total = t + made
    return dict(t=t, mode=mode, k=k, persistent=persistent, defer_item=defer_item, first=first, note=note,
                placed=total, thr=ep.thr, margin=total - ep.thr, record_placed=ep.placed,
                seconds=round(time.perf_counter() - t0, 1))


def placement_from_box(st, item_pool_index, ci, centre, size, archetype="hand"):
    """A hand-made placement: the item at pool index, a box (local centre, size) in
    container ci, validated by the agent's own analytic validator (returns None
    when invalid)."""
    from rule_alpha import classify as cls
    from rule_alpha._reuse import AABB

    item = st.pool[item_pool_index]
    profile = cls.classify_item(int(item["index"]), item, st.config)
    board = layer1.Board(st.board.containers, st.config)
    want = tuple(round(float(v), 4) for v in size)
    orient = None
    for o in profile.orientations:
        if tuple(round(v, 4) for v in (o.dx, o.dy, o.dz)) == want:
            orient = o
            break
    if orient is None:
        return None, "no-orientation"
    box = AABB(tuple(centre), tuple(size), "hand")
    cand = (
        layer1.Candidate(
            profile=profile,
            orientation=orient,
            box=box,
            container_idx=ci,
            surface="floor"
            if abs(box.minimum[2] - board.model(ci).z_floor) < 0.01
            else "item",
            role="none",
            family="hand",
        )
        if hasattr(layer1, "Candidate")
        else None
    )
    if cand is None:
        return None, "no-candidate-class"
    return layer1.build_placement(cand, archetype, board, ci, profile, st.config), "ok"
