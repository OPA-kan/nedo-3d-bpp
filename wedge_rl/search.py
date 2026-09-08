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
    beam = [{"packed": [], "gain": 0.0, "placed": 0, "actions": [], "rank": 0.0}]
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
    env.container = dict(template)
    env.container["packed_items"] = []
    env.cursor = 0
    env._cands = None
    return {"seed": seed, "gain": best["gain"], "placed": best["placed"], "actions": best["actions"],
            "expansions": expansions, "seconds": round(time.perf_counter() - t0, 1),
            "width": width, "k": k, "spread": spread, "rollout": rollout is not None}


def _one(args):
    region, layout, n_items, seed, width, k, spread, rollout_name = args
    from .baselines import greedy_any, staircase
    from .regions import make_env

    env = make_env(region, layout, n_items)
    rollout = {"": None, "none": None, "staircase": staircase, "greedy_any": greedy_any}[rollout_name]
    return beam_search(env, seed, width=width, k=k, spread=spread, rollout=rollout)


def ceilings(region: str, layout: str, n_items: int, seeds, width: int, k: int, workers: int = 1,
             spread: int = 0, rollout: str = "", log=print) -> list[dict]:
    jobs = [(region, layout, n_items, s, width, k, spread, rollout) for s in seeds]
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
