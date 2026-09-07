"""PPO over a variable set of candidate placements.

The policy scores each candidate from (state embedding, candidate features)
and adds one PASS logit from the state alone; a softmax over that set is the
action distribution, as in candidate-based packing policies (PCT, GOPT).
The value head reads the state embedding.  Episodes are short (one per item
stream), the environment is deterministic given the stream, and rewards are
the wedge volume each placement recovers.
"""

from __future__ import annotations

import json
import pathlib
import random
import time

import numpy as np
import torch
from torch import nn

from .env import FEATURE_SIZE, PASS, WedgeEnv


class Policy(nn.Module):
    def __init__(self, nx: int, ny: int, width: int = 16, emb: int = 64):
        super().__init__()
        self.conv1 = nn.Conv2d(2, width, 3, padding=1)
        self.conv2 = nn.Conv2d(width, width, 3, padding=1)
        self.state_fc = nn.Linear(2 * width + 5 + 1, emb)
        self.cand_fc = nn.Sequential(nn.Linear(emb + FEATURE_SIZE, 64), nn.ReLU(), nn.Linear(64, 1))
        self.pass_fc = nn.Linear(emb, 1)
        self.value_fc = nn.Sequential(nn.Linear(emb, 64), nn.ReLU(), nn.Linear(64, 1))

    def embed(self, obs: dict) -> torch.Tensor:
        h = torch.tensor(obs["heightmap"])[None]
        ch = torch.tensor(obs["chamfer"])[None, :, None].expand(1, h.shape[1], h.shape[2])
        x = torch.stack([h[0], ch[0]])[None]          # (1, 2, nx, ny)
        z = torch.relu(self.conv1(x)); z = torch.relu(self.conv2(z))
        pooled = torch.cat([z.mean(dim=(2, 3)), z.amax(dim=(2, 3))], dim=1)[0]
        vec = torch.cat([pooled, torch.tensor(obs["item"]), torch.tensor([obs["remaining"]], dtype=torch.float32)])
        return torch.relu(self.state_fc(vec))

    def logits(self, emb: torch.Tensor, feats: np.ndarray) -> torch.Tensor:
        pass_logit = self.pass_fc(emb)
        if feats.shape[0] == 0:
            return pass_logit
        f = torch.tensor(feats)
        cand = self.cand_fc(torch.cat([emb[None].expand(f.shape[0], -1), f], dim=1))[:, 0]
        return torch.cat([cand, pass_logit])       # last index = PASS

    def value(self, emb: torch.Tensor) -> torch.Tensor:
        return self.value_fc(emb)[0]


def _features(env: WedgeEnv) -> np.ndarray:
    cands = env.candidates()
    if not cands:
        return np.zeros((0, FEATURE_SIZE), dtype=np.float32)
    return np.stack([c.features(env) for c in cands])


def collect(env: WedgeEnv, policy: Policy, episodes: int, seed_base: int, rng: random.Random):
    """Run episodes; keep everything PPO needs, including the candidate features."""
    steps = []
    returns = []
    for e in range(episodes):
        seed = seed_base + e
        obs = env.reset(seed)
        traj = []
        while not env.done:
            feats = _features(env)
            with torch.no_grad():
                emb = policy.embed(obs)
                logits = policy.logits(emb, feats)
                dist = torch.distributions.Categorical(logits=logits)
                a = int(dist.sample())
                logp = float(dist.log_prob(torch.tensor(a)))
                v = float(policy.value(emb))
            action = PASS if a == len(feats) else a
            next_obs, r, done, _info = env.step(action)
            traj.append({"obs": obs, "feats": feats, "a": a, "logp": logp, "v": v, "r": r})
            obs = next_obs
        # GAE with gamma 1 (episodes are short and the objective is total volume)
        adv = 0.0
        ret = 0.0
        for t in reversed(range(len(traj))):
            next_v = traj[t + 1]["v"] if t + 1 < len(traj) else 0.0
            delta = traj[t]["r"] + next_v - traj[t]["v"]
            adv = delta + 0.95 * adv
            ret = traj[t]["r"] + ret
            traj[t]["adv"] = adv
            traj[t]["ret"] = ret
        steps.extend(traj)
        returns.append(sum(s["r"] for s in traj))
    return steps, returns


def ppo_update(policy: Policy, opt, steps, epochs: int = 4, clip: float = 0.2, ent: float = 0.01):
    advs = np.array([s["adv"] for s in steps], dtype=np.float32)
    advs = (advs - advs.mean()) / (advs.std() + 1e-6)
    for _ in range(epochs):
        order = np.random.permutation(len(steps))
        for start in range(0, len(order), 64):
            idx = order[start:start + 64]
            loss = 0.0
            for i in idx:
                s = steps[i]
                emb = policy.embed(s["obs"])
                logits = policy.logits(emb, s["feats"])
                dist = torch.distributions.Categorical(logits=logits)
                logp = dist.log_prob(torch.tensor(s["a"]))
                ratio = torch.exp(logp - s["logp"])
                a = torch.tensor(advs[i])
                pg = -torch.min(ratio * a, torch.clamp(ratio, 1 - clip, 1 + clip) * a)
                v = policy.value(emb)
                vl = (v - torch.tensor(s["ret"], dtype=torch.float32)) ** 2
                loss = loss + pg + 0.5 * vl - ent * dist.entropy()
            loss = loss / len(idx)
            opt.zero_grad(); loss.backward()
            nn.utils.clip_grad_norm_(policy.parameters(), 1.0)
            opt.step()


def evaluate(env: WedgeEnv, policy: Policy, seeds) -> dict:
    """Greedy (argmax) evaluation on fixed seeds."""
    totals, placed, volumes = [], [], []
    for seed in seeds:
        obs = env.reset(seed)
        total = 0.0
        while not env.done:
            feats = _features(env)
            with torch.no_grad():
                logits = policy.logits(policy.embed(obs), feats)
            a = int(torch.argmax(logits))
            obs, r, _d, _i = env.step(PASS if a == len(feats) else a)
            total += r
        totals.append(total); placed.append(len(env.placed)); volumes.append(env.placed_volume())
    return {"strip_volume": float(np.mean(totals)), "strip_max": float(np.max(totals)),
            "placed": float(np.mean(placed)), "placed_volume": float(np.mean(volumes)), "n": len(seeds)}


def train(out_dir: pathlib.Path, layout: str = "c1", n_items: int = 14, iterations: int = 100,
          episodes_per_iter: int = 16, lr: float = 3e-4, seed: int = 0, eval_seeds=range(10000, 10020),
          log=print) -> dict:
    torch.manual_seed(seed); np.random.seed(seed)
    rng = random.Random(seed)
    env = WedgeEnv(layout, n_items=n_items, seed=seed)
    policy = Policy(env.nx, env.ny)
    opt = torch.optim.Adam(policy.parameters(), lr=lr)
    out_dir.mkdir(parents=True, exist_ok=True)
    history = []
    best = (-1.0, None)
    for it in range(iterations):
        t0 = time.perf_counter()
        steps, returns = collect(env, policy, episodes_per_iter, seed_base=1_000_000 + it * episodes_per_iter, rng=rng)
        ppo_update(policy, opt, steps)
        row = {"iter": it, "train_return": float(np.mean(returns)), "steps": len(steps),
               "seconds": round(time.perf_counter() - t0, 1)}
        if it % 5 == 0 or it == iterations - 1:
            ev = evaluate(env, policy, list(eval_seeds))
            row.update({"eval_" + k: v for k, v in ev.items()})
            if ev["strip_volume"] > best[0]:
                best = (ev["strip_volume"], {k: v.detach().clone() for k, v in policy.state_dict().items()})
                torch.save(policy.state_dict(), out_dir / "policy.pt")
        history.append(row)
        if log:
            log(row)
        (out_dir / "history.json").write_text(json.dumps(history, indent=1), encoding="utf-8")
    return {"best_eval_strip_volume": best[0], "history": history}
