"""Branching harness for the H-strip investigation (read-only on the agent).

An episode is replayed from a bench record: the recorded actions are forced
for steps < k (the agent is not asked; only its pocket guard's stream
statistics are fed, the one piece of cross-call state that changes later
decisions), then at step k the agent decides and a probe may dump the
decision and/or replace the action, then the shipped agent continues to the
end.  Two simulators:

* ``physics``: the official GroundHandlingEnv, the control flow of
  ``bench.episode.run_episode`` (needs pybullet; the agent's shadow check
  and physics resort are on, as shipped).
* ``analytic``: rule-alpha's analytic model (``bench.analytic``); the shadow
  check and the physics resort are off (no pybullet), so the continuation is
  the v18-like ladder + stack option + last resort only.

Nothing in rule_alpha is modified.  Alternatives are built from the
decision's survivors with ``layer1.build_placement`` and the agent's own
``_action`` (band lift and action centre included).
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import sys
import time

import numpy as np

REPO = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../..")
)
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from bench.arms import make_arm  # noqa: E402
from bench.scenes import make_scene  # noqa: E402
from rule_alpha import layer1  # noqa: E402

REC = {
    "C": "gate0-hard2",
    "B": "gate0-hard2-b",
    "Cdet": "gate0det-hard2",
    "Br2": "gate0-hard2-b-r2",
}


def have_pybullet() -> bool:
    try:
        import pybullet  # noqa: F401

        return True
    except Exception:
        return False


def load(scene_name: str, record: str | None = None):
    task = scene_name[0].upper()
    record = record or REC[task]
    path = f"{REPO}/reports/bench/{record}/{scene_name}.json"
    rec = json.load(open(path))
    sp = rec["scene_spec"]
    scene = make_scene(int(sp["seed"]), sp["layout"], sp["task"])
    os.chdir(REPO)  # the arm spec names the stack policy by a repo-relative path
    arm = make_arm(rec["arm"]["arm"])
    return scene, rec, arm


def recorded_actions(rec) -> list[dict]:
    out = []
    for s in rec["steps"]:
        if s.get("event") != "step":
            break
        out.append(
            {
                "item_idx": s["pool_index"],
                "container_idx": s["container_idx"],
                "orientation": s["orientation"],
                "place_pos": list(s["place_pos"]),
                "_pos_local": s.get("pos_local"),
                "_size": s.get("size"),
                "_item_index": s.get("item_index"),
                "_arch": s.get("archetype"),
            }
        )
    return out


# ---------------------------------------------------------------- simulators
class PhysicsEpisode:
    def __init__(self, scene, arm, policy_budget=8.0):
        from bench.episode import load_env_class

        Env = load_env_class()
        self.scene = scene
        self._sink = io.StringIO()
        with contextlib.redirect_stdout(self._sink):
            self.env = Env(
                config=scene.sim_config(policy_timeout=policy_budget),
                verbose=False,
                render_mode=None,
            )
            self.env.reset_settings()
            self.agent = arm(scene)
            self.agent.get_init_states(self.env.get_init_states())
            if scene.optimize:
                order = self.agent.optimize(self.env.get_info_for_optimization())
                self.env.set_item_order(order)
            self.env.reset_item_stream()
            self.obs, _ = self.env.reset(seed=42)
        self.done = False
        self.end = None

    def observation(self):
        return self.obs

    def step(self, action) -> dict:
        from bench.episode import _end_reason

        a = {k: v for k, v in action.items() if not k.startswith("_")}
        with contextlib.redirect_stdout(self._sink):
            item = self.env.stream_manager.get_item(int(a["item_idx"]))
            self.obs, _r, term, trunc, info = self.env.step(a)
        status = (info or {}).get("status", {})
        reason = _end_reason(status, term, trunc, self.env.stream_manager.is_empty())
        ok = bool(
            status.get("is_included")
            and status.get("is_valid")
            and status.get("is_placed_safe")
        )
        if reason is not None or term or trunc:
            self.done = True
            self.end = reason or "format"
        return {
            "item_index": None if item is None else int(item.index),
            "ok": ok,
            "end": reason,
            "status": {
                k: bool(status.get(k))
                for k in ("is_included", "is_valid", "is_placed_safe")
            },
        }

    def placed_count(self) -> int:
        return sum(len(c.packed_items) for c in self.env.container_manager.containers)

    def settled(self) -> list[dict]:
        out = []
        for c in self.env.container_manager.containers:
            for it in c.packed_items:
                if it.pybullet_id is not None:
                    out.append(
                        {
                            "index": int(it.index),
                            "container": int(c.index),
                            "pos": [
                                round(float(v), 4)
                                for v in it.get_pose(self.env.client)[0]
                            ],
                        }
                    )
        return out

    def close(self):
        with contextlib.suppress(Exception):
            self.env.close()


class AnalyticEpisode:
    def __init__(self, scene, arm, policy_budget=8.0):
        self.scene = scene
        self.containers = scene.rule_alpha_containers()
        self.agent = arm(scene)
        self.agent.get_init_states(
            {
                "optimize": scene.optimize,
                "lookahead_k": scene.look_ahead,
                "container_list": self.containers,
            }
        )
        self.board = layer1.Board(self.containers, arm.config)
        self.queue = [dict(i) for i in scene.items]
        self.pool = []
        self._refill()
        self.done = False
        self.end = None
        self._pending_placement = None

    def _refill(self):
        while len(self.pool) < self.scene.look_ahead and self.queue:
            self.pool.append(self.queue.pop(0))

    def observation(self):
        return {
            "optimize": self.scene.optimize,
            "lookahead_k": self.scene.look_ahead,
            "container_list": self.board.containers,
            "pool_list": [dict(i) for i in self.pool],
        }

    def step(self, action) -> dict:
        """Apply an action.  When ``action['_placement']`` is given (the
        agent's own placement), it is applied as the analytic runner does;
        otherwise the recorded box (``_pos_local``/``_size``) is appended."""
        pi = int(action["item_idx"])
        item = self.pool.pop(pi)
        ci = int(action["container_idx"])
        pl = action.get("_placement")
        if pl is not None:
            self.board.apply(pl)
        else:
            c = self.board.containers[ci]
            off = float(c.get("center", (0.0, 0.0, 0.0))[0])
            pos = action["_pos_local"]
            size = action["_size"]
            c["packed_items"].append(
                {
                    "index": int(item["index"]),
                    "length": float(item["length"]),
                    "width": float(item["width"]),
                    "height": float(item["height"]),
                    "mass": float(item.get("mass", 0.0)),
                    "is_prioritized": bool(item["is_prioritized"]),
                    "is_soft": bool(item["is_soft"]),
                    "orientation": int(action["orientation"]),
                    "dims": tuple(float(v) for v in size),
                    "pos": (float(pos[0]) + off, float(pos[1]), float(pos[2])),
                    "belongs_to": ci,
                    "layer": 1,
                }
            )
            self.board = layer1.Board(self.board.containers, self.agent.config)
        self._refill()
        if not self.pool:
            self.done = True
            self.end = "stream-exhausted"
        return {"item_index": int(item["index"]), "ok": True, "end": self.end}

    def placed_count(self) -> int:
        return sum(len(c["packed_items"]) for c in self.board.containers)

    def settled(self):
        out = []
        for ci, c in enumerate(self.board.containers):
            off = float(c.get("center", (0.0, 0.0, 0.0))[0])
            for p in c["packed_items"]:
                out.append(
                    {
                        "index": int(p["index"]),
                        "container": ci,
                        "pos": [p["pos"][0], p["pos"][1], p["pos"][2]],
                    }
                )
        return out

    def close(self):
        pass


def make_episode(scene, arm, sim):
    return (
        PhysicsEpisode(scene, arm) if sim == "physics" else AnalyticEpisode(scene, arm)
    )


# ---------------------------------------------------------------- the run
def run(scene, arm, rec, sim='physics', k=None, probe=None, max_steps=400, quiet=True, log=None,
        follow_record=False, probe_steps=None, on_agent=None, forced_actions=None):
    """Force the record's actions for steps < k (k=None: never), let the agent
    decide from k on.  ``probe(step, agent, obs, action) -> action|None`` is
    called right after the agent's own call at step k (or at every step in
    ``probe_steps``); a returned action replaces the agent's.  With
    ``follow_record`` the record's action is applied after the probe at
    every step the record has (archaeology: the agent is asked, the record's
    course is kept).  Returns a summary dict."""
    ep = make_episode(scene, arm, sim)
    agent = ep.agent
    if on_agent is not None:
        on_agent(agent)
    if forced_actions is not None:
        # full-precision actions of an earlier run (the record's are rounded
        # to 0.1 mm, which moves the settled poses by millimetres)
        forced = forced_actions
    else:
        forced = recorded_actions(rec) if (k or follow_record) else []
    if probe_steps is None:
        probe_steps = {k} if k is not None else set()
    steps = []
    end = 'max-steps'
    sink = io.StringIO()
    t_start = time.perf_counter()
    try:
        for i in range(max_steps):
            obs = ep.observation()
            if not obs.get('pool_list'):
                end = 'stream-exhausted'
                break
            if k is not None and i < k and i < len(forced) and i not in probe_steps:
                if agent.pocket is not None:
                    with contextlib.suppress(Exception):
                        agent.pocket.observe(obs['pool_list'], len(obs['container_list']))
                action = forced[i]
                info = ep.step(action)
                steps.append({'step': i, 'forced': True, 'item_index': info['item_index'], 'ok': info['ok'],
                              'arch': action.get('_arch')})
                if ep.done:
                    end = ep.end
                    break
                continue
            t0 = time.perf_counter()
            with (contextlib.redirect_stdout(sink) if quiet else contextlib.nullcontext()):
                action = agent.policy(obs)
            dt = time.perf_counter() - t0
            dec = agent.last_decision
            shadow = (agent.last_shadow or {}).get('outcome')
            replaced = False
            if probe is not None and i in probe_steps:
                alt = probe(i, agent, obs, action)
                if alt is not None:
                    action = alt
                    replaced = True
            if follow_record and i < len(forced):
                action = forced[i]
                replaced = True
            elif follow_record:
                steps.append({'step': i, 'event': 'beyond-record', 'agent_declined': action is None})
                end = 'record-end'
                break
            if action is None:
                steps.append({'step': i, 'event': 'declined', 'policy_seconds': round(dt, 3)})
                end = 'declined'
                break
            if sim == 'analytic' and '_placement' not in action and not replaced and dec is not None:
                action = dict(action, _placement=dec.placement)
            info = ep.step(action)
            rec_step = {'step': i, 'forced': False, 'item_index': info['item_index'], 'ok': info['ok'],
                        'policy_seconds': round(dt, 3), 'replaced': replaced,
                        'arch': (action.get('_arch') if replaced else (dec.placement.archetype if dec is not None else None)),
                        'shadow': shadow if not replaced else None, 'end': info.get('end')}
            if dec is not None and not replaced:
                rec_step['pos_local'] = [round(float(v), 4) for v in dec.placement.box.center]
                rec_step['size'] = [round(float(v), 4) for v in dec.placement.box.size]
                rec_step['ci'] = int(dec.placement.container_idx)
            elif replaced:
                rec_step['pos_local'] = action.get('_pos_local'); rec_step['size'] = action.get('_size')
                rec_step['ci'] = int(action['container_idx'])
            steps.append(rec_step)
            if log:
                log(f"  step {i} {rec_step['arch']} ok={info['ok']} {dt:.2f}s")
            if ep.done:
                end = ep.end
                break
        placed = ep.placed_count()
        final = ep.settled()
    finally:
        ep.close()
    N = len(scene.items)
    return {'scene': scene.name, 'sim': sim, 'k': k, 'placed': placed, 'thr': N // 2 + 1,
            'margin': placed - (N // 2 + 1), 'end': end, 'steps': steps, 'final': final,
            'seconds': round(time.perf_counter() - t_start, 1)}


def det_arm(arm):
    """The same arm with deterministic budgets (the clock-free continuation)."""
    if 'deterministic_budgets=true' in arm.spec:
        return arm
    os.chdir(REPO)
    return make_arm(arm.spec + ',deterministic_budgets=true')


# ---------------------------------------------------------------- alternatives
def alt_action(agent, decision, cand, archetype=None, pool_index=0):
    """The action for survivor ``cand`` of ``decision`` as the agent would emit it."""
    profile = getattr(cand, "profile", None) or decision.placement.profile
    ci = int(cand.container_idx)
    pl = layer1.build_placement(
        cand,
        archetype or (decision.placement.archetype if decision is not None else "max-footprint"),
        agent.board,
        ci,
        profile,
        agent.config,
    )
    a = agent._action(pool_index, pl)
    a = dict(a)
    a["_placement"] = pl
    a["_pos_local"] = [round(float(v), 4) for v in pl.box.center]
    a["_size"] = [round(float(v), 4) for v in pl.box.size]
    a["_arch"] = "alt:" + (archetype or "?")
    return a
