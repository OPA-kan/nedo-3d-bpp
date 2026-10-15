"""archaeology.py <record> <scene> [steps] [--out FILE]

Walk the record's own trajectory in the official simulator (each step replays the
recorded action) and, at the listed steps (default: every step), ask the shipped
agent (the record's arm with deterministic budgets, so the answer does not depend on
the machine's clock) what it would do on that board, with the probe of
``instrument.py``.  The record's action is then played, so later probes see the
record's boards.  Output: one JSON line per probed step in
/home/user/inv-D-scratch/arch/<scene>.<record>.jsonl (heavy), and a compact digest
on stdout.
"""

import contextlib
import io
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_record, scene_of  # noqa: E402
from instrument import probe_decision  # noqa: E402
from physbranch import arm_for, recorded_actions  # noqa: E402

from bench.episode import load_env_class  # noqa: E402

OUT = "/home/user/inv-D-scratch/arch"


def walk(
    rec,
    scene,
    probe_steps=None,
    extra="deterministic_budgets=true",
    census=True,
    verbose=False,
    subs=None,
    probe_from=0,
):
    r = load_record(rec, scene)
    sc = scene_of(r["scene_spec"])
    arm = arm_for(r, extra)
    acts = recorded_actions(r)
    rs = [s for s in r["steps"] if s.get("event") == "step"]
    GroundHandlingEnv = load_env_class()
    sink = io.StringIO()
    out = []
    with contextlib.nullcontext() if verbose else contextlib.redirect_stdout(sink):
        env = GroundHandlingEnv(
            config=sc.sim_config(policy_timeout=4.5), verbose=False, render_mode=None
        )
        try:
            env.reset_settings()
            agent = arm(sc)
            agent.get_init_states(env.get_init_states())
            env.reset_item_stream()
            obs, _ = env.reset(seed=42)
            last = max(probe_steps) if probe_steps else len(acts)
            n_decl = 1 if r["steps"][-1].get("event") == "declined" else 0
            for t in range(min(last + 1, len(acts) + n_decl)):
                pool = obs.get("pool_list") or []
                if (probe_steps is None or t in probe_steps) and t >= probe_from:
                    t0 = time.perf_counter()
                    log = probe_decision(agent, obs, census=census)
                    log["step"] = t
                    log["pool"] = [
                        {
                            "index": int(i["index"]),
                            "soft": bool(i.get("is_soft")),
                            "prio": bool(i.get("is_prioritized")),
                            "dims": [i["length"], i["width"], i["height"]],
                        }
                        for i in pool
                    ]
                    log["record"] = (
                        None
                        if t >= len(rs)
                        else {
                            k: rs[t].get(k)
                            for k in (
                                "item_index",
                                "archetype",
                                "surface",
                                "pos_local",
                                "size",
                                "policy_seconds",
                                "container_idx",
                            )
                        }
                    )
                    log["probe_sec"] = round(time.perf_counter() - t0, 2)
                    out.append(log)
                elif getattr(agent, "pocket", None) is not None:
                    agent.pocket.observe(pool, len(obs.get("container_list") or []))
                if t >= len(acts):
                    break
                action = acts[t]
                if subs and t in subs:
                    # the record's pose fails on this machine's board: the agent's own
                    # (deterministic) pose for the record's item instead, so the walk
                    # can go on along a record-like trajectory
                    pi = int(acts[t]["item_idx"])
                    one = dict(obs, pool_list=[obs["pool_list"][pi]])
                    a = agent.policy(one)
                    if a is None:
                        out.append({"step": t, "replay_failed": True, "substitute": None})
                        break
                    action = dict(a, item_idx=pi)
                    out.append({"step": t, "substituted": True, "rung": getattr(agent.last_decision.placement, "archetype", None)})
                obs, _rw, term, trunc, info = env.step(action)
                st = (info or {}).get("status", {})
                if not (
                    st.get("is_included")
                    and st.get("is_valid")
                    and st.get("is_placed_safe")
                ):
                    out.append(
                        {
                            "step": t,
                            "replay_failed": True,
                            "status": {
                                k: bool(v)
                                for k, v in st.items()
                                if isinstance(v, (bool, np.bool_))
                            },
                        }
                    )
                    break
                if term or trunc:
                    break
        finally:
            with contextlib.suppress(Exception):
                env.close()
    return out


def digest(log):
    if log.get("substituted"):
        return f"step {log['step']}: record pose failed here; the agent's own pose ({log.get('rung')}) was played"
    if log.get("replay_failed"):
        return f"step {log['step']}: replay failed {log.get('status')}"
    rec = log.get("record") or {}
    fin = log.get("final") or {}
    p = log.get("pocket") or {}
    lad = log["ladder"][0] if log["ladder"] else {}
    d = lad.get("decision") or {}
    st = log.get("soft_tops") or []
    cen = ""
    if st:
        c = st[0]
        cap = c["capped"]["counts"]
        nocap = c["uncapped"]["counts"]
        cen = (
            f" soft-tops cap:{sum(v for k, v in cap.items() if k.startswith('soft'))}"
            f" nocap:{sum(v for k, v in nocap.items() if k.startswith('soft'))} floor:{cap.get('floor', 0)}"
        )
    pk = ""
    if p:
        if p.get("stood_down"):
            pk = f" guard: stood down (seen {p.get('seen')}, remaining {p.get('remaining')})"
        elif "chosen_slots" in p:
            b = p.get("best") or [{}]
            bs = p.get("best_soft") or {}
            pk = (
                f" guard: chosen {p['chosen_slots']} best {b[0].get('slots')} ({b[0].get('on')}@{b[0].get('bottom')})"
                f" best-on-soft {bs.get('slots')} override {p.get('real_override')}"
            )
    return (
        f"step {log['step']} item {rec.get('item_index')} rec[{rec.get('archetype')}/{rec.get('surface')}] "
        f"agent[{fin.get('rung')}/{fin.get('on')}@{fin.get('bottom')}] ladder[{d.get('rung')}/{d.get('surface')}@{d.get('bottom')} "
        f"surv {d.get('n_survivors')} vetoes {lad.get('veto_counts')}]{pk}{cen} stages {[s[0] + ('+' if s[2] else '-') for s in log['stages']]}"
    )


def main():
    rec, scene = sys.argv[1], sys.argv[2]
    steps = None
    if len(sys.argv) > 3 and sys.argv[3] != "all":
        steps = set()
        for part in sys.argv[3].split(","):
            if "-" in part:
                a, b = part.split("-")
                steps.update(range(int(a), int(b) + 1))
            else:
                steps.add(int(part))
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f'{scene}.{rec}.jsonl')
    if '--digest' in sys.argv:
        for line in open(path):
            print(digest(json.loads(line)))
        return
    if "--resume" in sys.argv:
        prev = [json.loads(line) for line in open(path)]
        subs = {l["step"] for l in prev if l.get("substituted")}
        fail = next((l["step"] for l in prev if l.get("replay_failed")), None)
        if fail is None or any(l.get("replay_failed") and l.get("substitute", 1) is None for l in prev):
            print("nothing to resume")
            return
        subs.add(fail)
        keep = [l for l in prev if not l.get("replay_failed") and not l.get("substituted")]
        new = walk(rec, scene, steps, subs=subs, probe_from=fail)
        logs = keep + new
        logs.sort(key=lambda l: (l["step"], 0 if l.get("substituted") else 1))
    else:
        logs = walk(rec, scene, steps)
    with open(os.path.join(OUT, f"{scene}.{rec}.jsonl"), "w") as fh:
        for log in logs:
            fh.write(json.dumps(log, default=float) + "\n")
    for log in logs:
        print(digest(log))


if __name__ == "__main__":
    main()
