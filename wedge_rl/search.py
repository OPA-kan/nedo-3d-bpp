"""Ceiling of a region: beam search over the same candidates the policy sees.

A learned policy that plateaus may be at the limit of what its action space
allows, or at the limit of the learner.  This tells the two apart on a few
streams: an offline search with no time limit over exactly the same
candidate generator, PASS included, gives a lower bound on the optimum for
this action space.  If the search finds much more than the policy, the
learner is the limit; if it finds about the same, the candidate set is.

The search is a beam over item steps.  Each beam state is a partial
arrangement (the container's packed list, the gain so far); expanding a
state generates the candidates for the next item, keeps the best ``k`` by
gain plus PASS, and the beam keeps the best ``width`` states by gain after
removing duplicate arrangements.  No look-ahead heuristic is used, so the
bound is honest but loose on regions where early greed blocks later steps
(the shelf); a wider beam narrows that.
"""

from __future__ import annotations

import copy
import time

import numpy as np

from .env import PASS


def _signature(packed) -> tuple:
    return tuple(sorted((round(p["pos"][0], 3), round(p["pos"][1], 3), round(p["pos"][2], 3),
                         tuple(round(d, 3) for d in p["dims"])) for p in packed))


def _packed_entry(item, c) -> dict:
    return {"index": int(item["index"]), "length": item["length"], "width": item["width"],
            "height": item["height"], "mass": item["mass"], "is_soft": bool(item["is_soft"]),
            "is_prioritized": False, "orientation": c.orientation, "dims": tuple(c.dims),
            "pos": tuple(float(v) for v in c.box.center), "layer": 1}


def _load(env, template, packed, t):
    env.container = dict(template)
    env.container["packed_items"] = list(packed)
    env.cursor = t
    env.placed = []
    env._cands = None


def _rollout_gain(env, template, packed, t, policy) -> float:
    """Finish the stream from (packed, t) with ``policy``; the gain it adds."""
    _load(env, template, packed, t)
    total = 0.0
    while not env.done:
        a = policy(env, None)
        _obs, r, _d, _i = env.step(a)
        total += r
    return total


def _children_of(cands, k: int, spread: int) -> list[int]:
    """The best ``k`` by gain plus ``spread`` more taken evenly along the
    region's own candidate order, so a state with no paying pose yet (an
    empty strip) still branches over different bases."""
    by_gain = sorted(range(len(cands)), key=lambda i: -cands[i].gain)[:k]
    chosen = list(by_gain)
    rest = [i for i in range(len(cands)) if i not in set(by_gain)]
    if spread and rest:
        step = max(1, len(rest) // spread)
        chosen.extend(rest[::step][:spread])
    return chosen


def beam_search(env, seed: int, width: int = 100, k: int = 8, spread: int = 0, rollout=None,
                log=None) -> dict:
    """Best arrangement found for the stream ``seed``; the env is reused for
    candidate generation by swapping its container state in and out.

    ``rollout``: a baseline policy used to finish the stream from every child;
    the beam is then ranked by gain so far plus the rollout's gain, which
    sees past the one-step greed (a base with no gain of its own but a step
    to come).  Reported gains are always the arrangement's own."""
    env.reset(seed)
    template = dict(env.container)
    stream = list(env.stream)
    n = len(stream)
    # a region that starts from a pre-filled board (the stack) has boxes in
    # the container before the first item; the search starts from them
    base = list(env.container["packed_items"])
    beam = [{"packed": base, "gain": 0.0, "placed": 0, "actions": [], "rank": 0.0}]
    t0 = time.perf_counter()
    expansions = 0
    for t in range(n):
        children = {}
        for state in beam:
            _load(env, template, state["packed"], t)
            env.stream = stream
            cands = env.candidates()
            expansions += 1
            item = stream[t]
            options = [(PASS, list(state["packed"]), state["gain"], state["placed"])]
            for i in _children_of(cands, k, spread):
                c = cands[i]
                options.append((i, list(state["packed"]) + [_packed_entry(item, c)], state["gain"] + c.gain,
                                state["placed"] + 1))
            for action, packed, gain, placed in options:
                sig = _signature(packed)
                if sig in children and children[sig]["gain"] >= gain:
                    continue
                rank = gain
                if rollout is not None and t + 1 < n:
                    rank = gain + _rollout_gain(env, template, packed, t + 1, rollout)
                    env.stream = stream
                children[sig] = {"packed": packed, "gain": gain, "placed": placed,
                                 "actions": state["actions"] + [action], "rank": rank}
        beam = sorted(children.values(), key=lambda s: (-s["rank"], -s["gain"], -s["placed"]))[:width]
        if log:
            log(f"  seed {seed} step {t + 1}/{n}: beam {len(beam)} best gain {max(s['gain'] for s in beam):.4f} "
                f"rank {beam[0]['rank']:.4f} ({time.perf_counter() - t0:.0f}s, {expansions} expansions)")
    best = max(beam, key=lambda s: (s["gain"], s["placed"]))
    _load(env, template, base, 0)
    env.stream = stream
    return {"seed": seed, "gain": best["gain"], "placed": best["placed"], "actions": best["actions"],
            "expansions": expansions, "seconds": round(time.perf_counter() - t0, 1),
            "width": width, "k": k, "spread": spread, "rollout": rollout is not None}


def teacher_trajectory(env, seed: int, actions) -> list[dict]:
    """Replay a searched action sequence and record what the policy would
    have seen at each step: observation, candidate features, the chosen
    index (len(feats) means PASS) and the reward.  This is the imitation
    target for ``ppo.pretrain``."""
    obs = env.reset(seed)
    out = []
    for a in actions:
        cands = env.candidates()
        feats = np.stack([c.features(env) for c in cands]) if cands else np.zeros((0, 12), dtype=np.float32)
        target = len(feats) if a == PASS else int(a)
        _obs2, r, _d, _i = env.step(a)
        out.append({"obs": {k: (v.copy() if hasattr(v, "copy") else v) for k, v in obs.items()},
                    "feats": feats, "a": target, "r": float(r)})
        obs = _obs2
    return out


def value_teacher_trajectory(env, policy, seed: int, k: int = 4, by_gain: int = 1, explore_eps: float = 0.2,
                             rng=None) -> list[dict]:
    """Soft targets at the policy's own states (expert iteration, DAgger-style).

    The stream is played by the policy with a little exploration (with
    probability ``explore_eps`` one of its top three candidates is taken
    instead of the decoded one, so the recorded states are the ones the
    policy visits and some it nearly visits).  Every state is expanded with
    ``Lookahead.expand``: the decoded choice, PASS, the policy's next
    preferences and the best by gain, each finished with the policy.  The
    recorded target is the dictionary of child values; the training loss
    turns it into a distribution with a temperature, so equally good
    children share the mass instead of one arbitrary member getting it all.
    """
    import random as _random

    import torch

    from .lookahead import Lookahead
    from .ppo import _features, decode

    rng = rng or _random.Random(seed)
    la = Lookahead(policy, k=k, by_gain=by_gain, threshold=2.0, horizon=None)
    obs = env.reset(seed)
    out = []
    while not env.done:
        cands = env.candidates()
        feats = _features(env)
        with torch.no_grad():
            logits = policy.logits(policy.embed(obs), feats)
        a = decode(logits, len(feats))
        if not cands:
            obs, _r, _d, _i = env.step(PASS)
            continue
        p = torch.softmax(logits, dim=0).numpy()
        values = la.expand(env, cands, p, a)
        targets = {(len(feats) if key == PASS else int(key)): float(v) for key, v in values.items()}
        out.append({"obs": {kk: (vv.copy() if hasattr(vv, "copy") else vv) for kk, vv in obs.items()},
                    "feats": feats, "targets": targets, "decoded": (len(feats) if a == PASS else a)})
        # continue along the policy's path, with exploration
        step_action = a
        if rng.random() < explore_eps:
            top = np.argsort(-p[:-1])[:3].tolist()
            step_action = rng.choice(top) if top else PASS
        obs, _r, _d, _i = env.step(step_action)
    return out


def _teach_one(args):
    region, layout, n_items, seed, width, k, spread, rollout_name, out_dir, policy_dir, mode, explore_eps = args
    import pathlib
    import pickle

    from .regions import make_env

    path = pathlib.Path(out_dir) / f"s{seed}.pkl"
    if path.exists():
        return {"seed": seed, "skipped": True}
    env = make_env(region, layout, n_items)
    t0 = time.perf_counter()
    if mode == "values":
        import torch

        from .ppo import Policy

        policy = Policy(env.nx, env.ny)
        policy.load_state_dict(torch.load(pathlib.Path(policy_dir) / "policy.pt"))
        policy.eval()
        traj = value_teacher_trajectory(env, policy, seed, k=k, by_gain=spread, explore_eps=explore_eps)
        best = sum(max(s["targets"].values()) - s["targets"].get(s["decoded"], 0.0) for s in traj)
        record = {"seed": seed, "region": region, "layout": layout, "mode": "values", "k": k, "by_gain": spread,
                  "explore_eps": explore_eps, "policy": str(policy_dir), "gain": float("nan"),
                  "regret": best, "placed": 0, "seconds": round(time.perf_counter() - t0, 1), "steps": traj}
        summary = {"seed": seed, "gain": best, "placed": len(traj), "seconds": record["seconds"]}
    else:
        rollout = _rollout_policy(rollout_name, policy_dir, env)
        result = beam_search(env, seed, width=width, k=k, spread=spread, rollout=rollout)
        traj = teacher_trajectory(env, seed, result["actions"])
        record = {"seed": seed, "region": region, "layout": layout, "mode": "beam", "gain": result["gain"],
                  "placed": result["placed"], "seconds": result["seconds"], "width": width, "k": k,
                  "spread": spread, "rollout": rollout_name, "steps": traj}
        summary = {"seed": seed, "gain": result["gain"], "placed": result["placed"], "seconds": result["seconds"]}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        pickle.dump(record, fh)
    return summary


def teach(region: str, layout: str, n_items: int, seeds, width: int, k: int, spread: int, rollout: str,
          out_dir, workers: int = 1, policy_dir: str = "", mode: str = "beam", explore_eps: float = 0.2,
          log=print) -> list[dict]:
    """Teacher data for many streams, one pickle per stream (resumable).

    ``mode="beam"``: the searched trajectory (hard targets).  ``mode="values"``:
    child values at the policy's own states (soft targets); ``k`` children by
    policy preference, ``spread`` by gain."""
    jobs = [(region, layout, n_items, s, width, k, spread, rollout, str(out_dir), policy_dir, mode, explore_eps)
            for s in seeds]
    out = []
    if workers <= 1:
        for job in jobs:
            r = _teach_one(job)
            out.append(r)
            if log and not r.get("skipped"):
                log(f"[teach {region} s{r['seed']}] gain {r['gain']:.4f} placed {r['placed']} in {r['seconds']}s")
        return out
    import multiprocessing as mp

    with mp.get_context("spawn").Pool(workers) as pool:
        for r in pool.imap_unordered(_teach_one, jobs):
            out.append(r)
            if log and not r.get("skipped"):
                log(f"[teach {region} s{r['seed']}] gain {r['gain']:.4f} placed {r['placed']} in {r['seconds']}s")
    return sorted(out, key=lambda r: r["seed"])


def load_teacher(paths, env=None, policy=None, log=None) -> list[dict]:
    """All steps of all teacher pickles, flattened.  With ``env`` and a
    ``policy(env, rng) -> action`` the streams the policy already matches or
    beats are dropped: imitating a weaker teacher would pull the policy
    down, and the search is only a lower bound on the optimum."""
    import pickle

    steps = []
    kept = dropped = 0
    for p in paths:
        with open(p, "rb") as fh:
            d = pickle.load(fh)
        if env is not None and policy is not None and d.get("mode", "beam") == "beam":
            from .baselines import run_episode

            own = run_episode(env, policy, d["seed"])["gain"]
            if own >= d["gain"] - 1e-9:
                dropped += 1
                continue
        kept += 1
        steps.extend(d["steps"])
    if log:
        log(f"teacher: kept {kept} streams, dropped {dropped} the policy already matches")
    return steps


def _rollout_policy(name: str, policy_dir: str, env):
    from .baselines import greedy_any, staircase

    if name in ("", "none"):
        return None
    if name == "staircase":
        return staircase
    if name == "greedy_any":
        return greedy_any
    if name == "ppo":
        from .__main__ import load_ppo_policy

        return load_ppo_policy(policy_dir, env)
    raise KeyError(f"unknown rollout {name!r}")


def _one(args):
    region, layout, n_items, seed, width, k, spread, rollout_name, policy_dir = args
    from .regions import make_env

    env = make_env(region, layout, n_items)
    rollout = _rollout_policy(rollout_name, policy_dir, env)
    return beam_search(env, seed, width=width, k=k, spread=spread, rollout=rollout)


def ceilings(region: str, layout: str, n_items: int, seeds, width: int, k: int, workers: int = 1,
             spread: int = 0, rollout: str = "", policy_dir: str = "", log=print) -> list[dict]:
    jobs = [(region, layout, n_items, s, width, k, spread, rollout, policy_dir) for s in seeds]
    if workers <= 1:
        out = []
        for job in jobs:
            r = _one(job)
            out.append(r)
            if log:
                log(f"[{region} s{r['seed']}] beam {r['gain']:.4f} placed {r['placed']} in {r['seconds']}s")
        return out
    import multiprocessing as mp

    with mp.get_context("spawn").Pool(workers) as pool:
        out = []
        for r in pool.imap_unordered(_one, jobs):
            out.append(r)
            if log:
                log(f"[{region} s{r['seed']}] beam {r['gain']:.4f} placed {r['placed']} in {r['seconds']}s")
    return sorted(out, key=lambda r: r["seed"])
