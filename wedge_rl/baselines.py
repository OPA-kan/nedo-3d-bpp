"""Reference policies for a region environment."""

from __future__ import annotations

import random

from .env import PASS


def greedy_gain(env, rng=None) -> int:
    """The first candidate (regions sort their best-paying pose first); pass
    if nothing pays.  On the shelf every pose pays, so this places whenever
    it can, lowest and furthest back first."""
    cands = env.candidates()
    if not cands:
        return PASS
    best = max(range(len(cands)), key=lambda i: cands[i].gain)
    if cands[best].gain <= 0:
        return PASS
    return best


def greedy_any(env, rng=None) -> int:
    """Place whenever anything is legal, in the region's own order."""
    return 0 if env.candidates() else PASS


def staircase(env, rng=None) -> int:
    """Hand rule for the wedge: take wedge volume when offered; otherwise lay
    the box as flat as possible, as far back and as far left as it goes, so
    that the next box has a low base to step up from.  On the shelf this is
    the same as greedy_any."""
    cands = env.candidates()
    if not cands:
        return PASS
    best = max(range(len(cands)), key=lambda i: cands[i].gain)
    if cands[best].gain > 0 and env.region == "wedge":
        return best
    return min(range(len(cands)), key=lambda i: (
        round(float(cands[i].box.maximum[2]), 3),      # lowest top
        -round(float(cands[i].box.center[1]), 3),      # back first
        round(float(cands[i].box.minimum[0]), 3),      # left first
    ))


def random_policy(env, rng: random.Random) -> int:
    cands = env.candidates()
    if not cands:
        return PASS
    return rng.randrange(len(cands))


# kept under its old name for the wedge scripts and reports
greedy_strip = greedy_gain


def run_episode(env, policy, seed: int, rng=None) -> dict:
    env.reset(seed)
    rng = rng or random.Random(seed)
    total = 0.0
    passes = 0
    while not env.done:
        a = policy(env, rng)
        _obs, r, _done, info = env.step(a)
        total += r
        passes += int(info["passed"])
    return {"gain": total, "strip_volume": total, "placed_volume": env.placed_volume(),
            "placed": len(env.placed), "passes": passes, "items": env.n_items}
