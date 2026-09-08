"""Selective one-step look-ahead over the trained policy.

The diagnosis (`diagnose.py`) showed that the executors' regret sits in
the states where the policy is unsure (chosen probability at most 0.9):
80 % of it on the shelf, 97 % on the wedge.  So at play time the policy is
kept as it is on confident states, and on unsure ones a few children (the
policy's own top choices, the best by gain, and PASS) are each finished
with the policy for ``horizon`` steps, the value head filling in what lies
beyond the horizon; the child with the best total is taken.  This is a
policy improvement that needs no training and is bounded in time by
``k`` and ``horizon``.
"""

from __future__ import annotations

import time

import numpy as np
import torch

from .env import PASS
from .ppo import REWARD_SCALE, _features, decode


def _entry(item, c):
    return {"index": int(item["index"]), "length": item["length"], "width": item["width"],
            "height": item["height"], "mass": item["mass"], "is_soft": bool(item["is_soft"]),
            "is_prioritized": False, "orientation": c.orientation, "dims": tuple(c.dims),
            "pos": tuple(float(v) for v in c.box.center), "layer": 1}


class Lookahead:
    def __init__(self, policy, k: int = 4, by_gain: int = 1, threshold: float = 0.9,
                 horizon: int | None = None, use_value: bool = True):
        self.policy = policy
        self.k = k
        self.by_gain = by_gain
        self.threshold = threshold
        self.horizon = horizon
        self.use_value = use_value
        self.expansions = 0
        self.decisions = 0
        self.seconds = []

    # -- the base policy ---------------------------------------------------
    def _logits(self, env):
        feats = _features(env)
        with torch.no_grad():
            emb = self.policy.embed(env.observation())
            logits = self.policy.logits(emb, feats)
            v = float(self.policy.value(emb)) / REWARD_SCALE
        return feats, logits, v

    def _base_act(self, env) -> int:
        feats, logits, _v = self._logits(env)
        return decode(logits, len(feats))

    # -- rollouts on a scratch copy of the state ---------------------------
    def _load(self, env, packed, cursor):
        env.container = dict(env.template)
        env.container["packed_items"] = list(packed)
        env.cursor = cursor
        env._cands = None

    def _finish(self, env, packed, cursor) -> float:
        self._load(env, packed, cursor)
        total = 0.0
        steps = 0
        while not env.done:
            if self.horizon is not None and steps >= self.horizon:
                if self.use_value:
                    _f, _l, v = self._logits(env)
                    total += max(0.0, v)
                break
            _o, r, _d, _i = env.step(self._base_act(env))
            total += r
            steps += 1
        return total

    # -- the improved action ------------------------------------------------
    def act(self, env, _rng=None) -> int:
        self.decisions += 1
        cands = env.candidates()
        feats, logits, _v = self._logits(env)
        a = decode(logits, len(feats))
        if not cands:
            return PASS
        p = torch.softmax(logits, dim=0).numpy()
        chosen_idx = len(feats) if a == PASS else a
        if p[chosen_idx] > self.threshold:
            return a
        t0 = time.perf_counter()
        self.expansions += 1
        # children: policy's top-k, best by gain, the decoded choice, PASS
        order = np.argsort(-p[:-1])[: self.k].tolist()
        children = set(order)
        children.update(sorted(range(len(cands)), key=lambda i: -cands[i].gain)[: self.by_gain])
        if a != PASS:
            children.add(a)
        packed0 = list(env.container["packed_items"])
        cursor0 = env.cursor
        placed0 = list(env.placed)
        item = env.stream[cursor0]
        values = {PASS: self._finish(env, packed0, cursor0 + 1)}
        for i in children:
            values[i] = cands[i].gain + self._finish(env, packed0 + [_entry(item, cands[i])], cursor0 + 1)
        # restore the live state exactly
        self._load(env, packed0, cursor0)
        env.placed = placed0
        best = max(values, key=lambda key: (values[key], key == a))
        self.seconds.append(time.perf_counter() - t0)
        return best

    def stats(self) -> dict:
        return {"decisions": self.decisions, "expansions": self.expansions,
                "expansion_rate": self.expansions / max(self.decisions, 1),
                "seconds_mean": float(np.mean(self.seconds)) if self.seconds else 0.0,
                "seconds_max": float(np.max(self.seconds)) if self.seconds else 0.0}
