"""physbranch.py: counterfactual branches in the official simulator (PyBullet).

``run_branch(rec, scene, k, override=None)``:
  * steps 0..k-1 replay the record's own actions (pool index, container, orientation,
    place_pos) in the official environment, so the board at step k is the record's
    board (checked: ``replay_check``);
  * the agent (the record's arm, optionally with extra overrides) is warmed with the
    pools it would have seen (the pocket guard's class frequencies are its only state
    that depends on the past calls);
  * at step k ``override`` (an action dict, or a callable(agent, observation, env) ->
    action) replaces the agent's choice; None lets the agent choose;
  * the agent then plays to the end (declined / failed / stream exhausted).

Returns a compact record (placed count, threshold, end reason, the steps after k with
their rung, item, pose and shadow outcome).  Nothing in the shipped logic is touched.
"""

import contextlib
import io
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import REPO, load_record, scene_of  # noqa: E402

os.chdir(REPO)  # the arms name their policy directories relative to the repository

from bench.arms import make_arm  # noqa: E402
from bench.episode import _decision_digest, _end_reason, load_env_class  # noqa: E402


def arm_for(r, extra=""):
    spec = r["arm"]["arm"]
    if extra:
        spec = spec + "," + extra
    return make_arm(spec)


def recorded_actions(r):
    out = []
    for s in r["steps"]:
        if s.get("event") != "step":
            continue
        out.append(
            {
                "item_idx": int(s["pool_index"]),
                "container_idx": int(s["container_idx"]),
                "orientation": int(s["orientation"]),
                "place_pos": np.asarray(s["place_pos"], dtype=float),
            }
        )
    return out


def run_branch(
    rec,
    scene,
    k,
    override=None,
    extra="",
    budget=4.5,
    max_steps=400,
    arm=None,
    r=None,
    until=None,
    verbose=False,
    wrap=None,
    metrics=True,
):
    r = r or load_record(rec, scene)
    sc = scene_of(r["scene_spec"])
    arm = arm or arm_for(r, extra)
    acts = recorded_actions(r)
    GroundHandlingEnv = load_env_class()
    sink = io.StringIO()
    stream = contextlib.nullcontext() if verbose else contextlib.redirect_stdout(sink)
    steps = []
    end = "max-steps"
    t_start = time.perf_counter()
    with stream:
        env = GroundHandlingEnv(
            config=sc.sim_config(policy_timeout=budget), verbose=False, render_mode=None
        )
        try:
            env.reset_settings()
            agent = arm(sc)
            agent.get_init_states(env.get_init_states())
            if wrap is not None:
                # an opt-in policy wrapper (e.g. the compaction branch of cf.py)
                wrap(agent)
            env.reset_item_stream()
            obs, _ = env.reset(seed=42)
            for t in range(max_steps):
                pool = obs.get("pool_list") or []
                if t < k:
                    # replay: warm the agent's per-call state without a decision
                    if getattr(agent, "pocket", None) is not None:
                        agent.pocket.observe(pool, len(obs.get("container_list") or []))
                    action = acts[t]
                    src = "replay"
                    digest = {}
                    sec = 0.0
                elif t == k and override is not None:
                    if getattr(agent, "pocket", None) is not None:
                        agent.pocket.observe(pool, len(obs.get("container_list") or []))
                    action = (
                        override(agent, obs, env) if callable(override) else override
                    )
                    src = "override"
                    digest = {}
                    sec = 0.0
                    if action is None:
                        end = "override-none"
                        break
                else:
                    t0 = time.perf_counter()
                    action = agent.policy(obs)
                    sec = time.perf_counter() - t0
                    src = "agent"
                    if action is None:
                        steps.append(
                            {"step": t, "event": "declined", "sec": round(sec, 3)}
                        )
                        end = "declined"
                        break
                    digest = _decision_digest(agent)
                item = env.stream_manager.get_item(int(action["item_idx"]))
                obs, _rw, term, trunc, info = env.step(action)
                status = (info or {}).get("status", {})
                steps.append(
                    {
                        "step": t,
                        "src": src,
                        "item": None if item is None else int(item.index),
                        "soft": None
                        if item is None
                        else bool(getattr(item, "is_soft", False)),
                        "ci": int(action["container_idx"]),
                        "ori": int(action["orientation"]),
                        "pos": [
                            round(float(v), 4) for v in np.asarray(action["place_pos"])
                        ],
                        "ok": bool(status.get("is_included"))
                        and bool(status.get("is_valid"))
                        and bool(status.get("is_placed_safe")),
                        "sec": round(sec, 3),
                        "rung": digest.get("archetype"),
                        "surface": digest.get("surface"),
                        "size": digest.get("size"),
                        "pos_local": digest.get("pos_local"),
                        "shadow": (digest.get("shadow") or {}).get("outcome"),
                    }
                )
                reason = _end_reason(status, term, trunc, env.stream_manager.is_empty())
                if reason is not None:
                    end = reason
                    break
                if term or trunc:
                    end = "format"
                    break
                if until is not None and t + 1 >= until:
                    end = "until"
                    break
            placed = sum(len(c.packed_items) for c in env.container_manager.containers)
            tm = {}
            if metrics:
                try:
                    from bench.metrics import terminal_metrics

                    m = terminal_metrics(env, with_shake=False)
                    tm = {k2: m.get(k2) for k2 in ("soft_count", "soft_covered", "priority_count", "priority_covered", "fill_volume")}
                except Exception as exc:  # metrics are a convenience
                    tm = {"error": repr(exc)}
            final = [
                {
                    "index": int(it.index),
                    "container": int(c.index),
                    "pos": [round(float(v), 4) for v in it.get_pose(env.client)[0]],
                }
                for c in env.container_manager.containers
                for it in c.packed_items
                if it.pybullet_id is not None
            ]
        finally:
            with contextlib.suppress(Exception):
                env.close()
    total = len(sc.items)
    thr = total // 2 + 1
    return {
        "scene": scene,
        "rec": rec,
        "k": k,
        "extra": extra,
        "placed": placed,
        "thr": thr,
        "mg": placed - thr,
        "end": end,
        "seconds": round(time.perf_counter() - t_start, 1),
        "steps": steps,
        "final": final,
        "metrics": tm,
    }


def replay_check(rec, scene):
    """Replay every recorded action; compare the settled poses with final_items."""
    r = load_record(rec, scene)
    n = sum(1 for s in r["steps"] if s.get("event") == "step")
    out = run_branch(rec, scene, k=n, r=r, until=n)
    rf = {it["index"]: it["pos"] for it in r["final_items"]}
    d = [
        float(np.linalg.norm(np.asarray(f["pos"]) - np.asarray(rf[f["index"]])))
        for f in out["final"]
        if f["index"] in rf
    ]
    return {
        "scene": scene,
        "placed": out["placed"],
        "record_placed": r["metrics"]["placed_count"],
        "max_pose_diff": round(max(d), 4) if d else None,
        "mean_pose_diff": round(float(np.mean(d)), 4) if d else None,
        "end": out["end"],
    }


if __name__ == "__main__":
    print(json.dumps(replay_check(sys.argv[1], sys.argv[2])))


def state_at(rec, scene, k, extra='deterministic_budgets=true', r=None):
    """(agent, observation) after replaying the record's first k actions; the agent
    is warmed with the pools it would have seen.  The env is closed: the observation
    is a plain dict of the settled board."""
    holder = {}

    def grab(agent, obs, env):
        holder['agent'], holder['obs'] = agent, obs
        return None

    run_branch(rec, scene, k, override=grab, extra=extra, r=r)
    return holder['agent'], holder['obs']
