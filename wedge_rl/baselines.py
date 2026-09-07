"""Reference policies for the chamfer strip."""

from __future__ import annotations

import random

from .env import PASS, WedgeEnv


def greedy_strip(env: WedgeEnv, rng=None) -> int:
    """The candidate with the largest immediate strip volume; pass if none gains."""
    cands = env.candidates()
    if not cands:
        return PASS
    if cands[0].strip_gain <= 0:
        return PASS
    return 0


def greedy_any(env: WedgeEnv, rng=None) -> int:
    """Place whenever anything is legal, preferring strip volume, then low."""
    return 0 if env.candidates() else PASS


def staircase(env: WedgeEnv, rng=None) -> int:
    """Hand rule for the wedge: take wedge volume when offered; otherwise lay
    the box as flat as possible, as far back and as far left as it goes, so
    that the next box has a low base to step up from."""
    cands = env.candidates()
    if not cands:
        return PASS
    if cands[0].strip_gain > 0:
        return 0
    best = min(range(len(cands)), key=lambda i: (
        round(float(cands[i].box.maximum[2]), 3),      # lowest top
        -round(float(cands[i].box.center[1]), 3),      # back first
        round(float(cands[i].box.minimum[0]), 3),      # left first
    ))
    return best


def random_policy(env: WedgeEnv, rng: random.Random) -> int:
    cands = env.candidates()
    if not cands:
        return PASS
    return rng.randrange(len(cands))


def run_episode(env: WedgeEnv, policy, seed: int, rng=None) -> dict:
    env.reset(seed)
    rng = rng or random.Random(seed)
    total = 0.0
    passes = 0
    while not env.done:
        a = policy(env, rng)
        _obs, r, _done, info = env.step(a)
        total += r
        passes += int(info["passed"])
    return {"strip_volume": total, "placed_volume": env.placed_volume(),
            "placed": len(env.placed), "passes": passes, "items": env.n_items}
