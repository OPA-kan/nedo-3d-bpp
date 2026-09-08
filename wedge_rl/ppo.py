"""PPO over a variable set of candidate placements.

The policy scores each candidate from (state embedding, candidate features)
and adds one PASS logit from the state alone; a softmax over that set is the
action distribution, as in candidate-based packing policies (PCT, GOPT).
The value head reads the state embedding.  Episodes are short (one per item
stream), the environment is deterministic given the stream, and rewards are
whatever the region pays for a placement (wedge volume, shelf volume).

Collection runs in forked worker processes: each holds one environment and
one copy of the policy, plays its share of the episodes and returns the
finished trajectories.  The update runs in the parent.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import pathlib
import random
import time

import numpy as np
import torch
from torch import nn

from .env import FEATURE_SIZE, PASS

REWARD_SCALE = 10.0
TEACHER_TAU = 0.005   # m^3: children within about 5 ml of the best share the target mass


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
        ch = torch.tensor(obs["profile"])[None, :, None].expand(1, h.shape[1], h.shape[2])
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


def _features(env) -> np.ndarray:
    cands = env.candidates()
    if not cands:
        return np.zeros((0, FEATURE_SIZE), dtype=np.float32)
    return np.stack([c.features(env) for c in cands])


def play_episode(env, policy: Policy, seed: int) -> tuple[list, float]:
    """One sampled episode; the trajectory with GAE advantages and returns.

    The action sampler is seeded per episode so a trajectory depends only on
    (policy weights, seed), in this process or in a worker."""
    torch.manual_seed(seed)
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
        next_obs, r, _done, _info = env.step(action)
        # rewards are cubic metres (0.01-0.1 per step); scale so the value
        # regression and advantages work in units near one
        traj.append({"obs": obs, "feats": feats, "a": a, "logp": logp, "v": v, "r": r * REWARD_SCALE})
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
    return traj, sum(s["r"] for s in traj) / REWARD_SCALE


# --- worker processes --------------------------------------------------------
_WORKER: dict = {}


def _worker_init(env_factory, nx: int, ny: int):
    torch.set_num_threads(1)
    _WORKER["env"] = env_factory()
    _WORKER["policy"] = Policy(nx, ny)
    _WORKER["policy"].eval()


def _worker_play(args):
    state_dict, seeds = args
    policy = _WORKER["policy"]
    policy.load_state_dict(state_dict)
    out = []
    for seed in seeds:
        out.append(play_episode(_WORKER["env"], policy, seed))
    return out


class Collector:
    """Plays episodes, in this process or in ``workers`` forked ones."""

    def __init__(self, env_factory, nx: int, ny: int, workers: int = 1):
        self.env_factory = env_factory
        self.workers = max(1, int(workers))
        self.env = env_factory() if self.workers == 1 else None
        self.pool = None
        if self.workers > 1:
            # spawn, not fork: the parent already runs torch's thread pool and
            # forking a multi-threaded process is unsafe; the factory and the
            # policy weights are picklable so a fresh interpreter is fine
            ctx = mp.get_context("spawn")
            self.pool = ctx.Pool(self.workers, initializer=_worker_init, initargs=(env_factory, nx, ny))

    def collect(self, policy: Policy, episodes: int, seed_base: int):
        seeds = [seed_base + e for e in range(episodes)]
        if self.pool is None:
            results = [play_episode(self.env, policy, s) for s in seeds]
        else:
            state = {k: v.detach().cpu() for k, v in policy.state_dict().items()}
            chunks = [seeds[i::self.workers] for i in range(self.workers)]
            results = [r for part in self.pool.map(_worker_play, [(state, c) for c in chunks if c]) for r in part]
        steps = [s for traj, _ret in results for s in traj]
        returns = [ret for _traj, ret in results]
        return steps, returns

    def close(self):
        if self.pool is not None:
            self.pool.close()
            self.pool.join()
            self.pool = None


def collect(env, policy: Policy, episodes: int, seed_base: int, rng=None):
    """Single-process collection (kept for callers that hold an env)."""
    results = [play_episode(env, policy, seed_base + e) for e in range(episodes)]
    return [s for traj, _r in results for s in traj], [r for _t, r in results]


def ppo_update(policy: Policy, opt, steps, epochs: int = 4, clip: float = 0.2, ent: float = 0.01,
               teacher=None, teacher_weight: float = 0.0, teacher_batch: int = 32, tau: float = TEACHER_TAU):
    """One PPO update; with ``teacher`` steps, every minibatch also carries an
    imitation term (expert iteration's policy target) so the search's
    knowledge is not washed out by the policy gradient."""
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
            if teacher and teacher_weight > 0:
                tidx = np.random.randint(0, len(teacher), size=min(teacher_batch, len(teacher)))
                loss = loss + teacher_weight * imitation_loss(policy, teacher, tidx, tau)
            opt.zero_grad(); loss.backward()
            nn.utils.clip_grad_norm_(policy.parameters(), 1.0)
            opt.step()


def soft_target(step: dict, n: int, tau: float = TEACHER_TAU) -> torch.Tensor:
    """Distribution over the n logits from a step's child values: mass
    proportional to exp((v - v_max) / tau) on the expanded children, zero
    elsewhere.  A step recorded with a single action gets a one-hot."""
    q = torch.zeros(n)
    if "targets" in step:
        items = list(step["targets"].items())
        vals = torch.tensor([v for _i, v in items], dtype=torch.float32)
        w = torch.exp((vals - vals.max()) / tau)
        w = w / w.sum()
        for (i, _v), wi in zip(items, w):
            q[int(i)] += wi
    else:
        q[int(step["a"])] = 1.0
    return q


def imitation_loss(policy: Policy, steps, idx, tau: float = TEACHER_TAU) -> torch.Tensor:
    """Cross-entropy between the teacher's (soft or hard) target and the
    policy's distribution, averaged over the given teacher steps (PASS is
    the last logit)."""
    loss = 0.0
    for i in idx:
        s = steps[i]
        logits = policy.logits(policy.embed(s["obs"]), s["feats"])
        q = soft_target(s, logits.shape[0], tau)
        loss = loss - (q * torch.log_softmax(logits, dim=0)).sum()
    return loss / max(len(idx), 1)


def pretrain(policy: Policy, teacher, epochs: int = 10, lr: float = 1e-3, batch: int = 64, log=print,
             tau: float = TEACHER_TAU) -> dict:
    """Behaviour cloning on teacher steps; returns the accuracy per epoch."""
    opt = torch.optim.Adam(policy.parameters(), lr=lr)
    history = []
    for ep in range(epochs):
        order = np.random.permutation(len(teacher))
        total = 0.0
        for start in range(0, len(order), batch):
            idx = order[start:start + batch]
            loss = imitation_loss(policy, teacher, idx, tau)
            opt.zero_grad(); loss.backward()
            nn.utils.clip_grad_norm_(policy.parameters(), 1.0)
            opt.step()
            total += float(loss) * len(idx)
        acc = teacher_accuracy(policy, teacher)
        row = {"epoch": ep, "loss": total / max(len(teacher), 1), "accuracy": acc}
        history.append(row)
        if log:
            log(row)
    return {"history": history}


def teacher_accuracy(policy: Policy, teacher, limit: int = 2000, tol: float = 1e-3) -> float:
    """Share of teacher steps where the deterministic decode agrees with
    the teacher: the recorded action for hard targets, any expanded child
    within ``tol`` of the best value for soft ones."""
    hits = 0
    n = min(len(teacher), limit)
    with torch.no_grad():
        for s in teacher[:n]:
            logits = policy.logits(policy.embed(s["obs"]), s["feats"])
            a = decode(logits, len(s["feats"]))
            idx = len(s["feats"]) if a == PASS else a
            if "targets" in s:
                best = max(s["targets"].values())
                hits += int(idx in s["targets"] and s["targets"][idx] >= best - tol)
            else:
                hits += int(idx == s["a"])
    return hits / max(n, 1)


def decode(logits: torch.Tensor, n_cands: int) -> int:
    """Deterministic action: PASS only when it carries more than half the
    probability mass; otherwise the best candidate.  A plain argmax would pass
    whenever fifty similar candidates split the mass among themselves."""
    if n_cands == 0:
        return PASS
    p = torch.softmax(logits, dim=0)
    if float(p[-1]) > 0.5:
        return PASS
    return int(torch.argmax(p[:-1]))


def evaluate(env, policy: Policy, seeds) -> dict:
    """Deterministic evaluation on fixed seeds."""
    totals, placed, volumes = [], [], []
    for seed in seeds:
        obs = env.reset(seed)
        total = 0.0
        while not env.done:
            feats = _features(env)
            with torch.no_grad():
                logits = policy.logits(policy.embed(obs), feats)
            obs, r, _d, _i = env.step(decode(logits, len(feats)))
            total += r
        totals.append(total); placed.append(len(env.placed)); volumes.append(env.placed_volume())
    return {"gain": float(np.mean(totals)), "gain_max": float(np.max(totals)),
            "placed": float(np.mean(placed)), "placed_volume": float(np.mean(volumes)), "n": len(seeds)}


class _StopFlag:
    """SIGINT/SIGTERM set a flag instead of raising: a KeyboardInterrupt in the
    middle of a pool.map can leave the pool hanging, and a job runner that
    sends the signal at its time limit then never reaches the evaluation and
    upload steps.  The training loop checks the flag between iterations."""

    def __init__(self):
        self.stop = False
        self._previous = {}

    def __enter__(self):
        import signal

        for sig in (signal.SIGINT, signal.SIGTERM):
            self._previous[sig] = signal.signal(sig, self._handle)
        return self

    def __exit__(self, *exc):
        import signal

        for sig, prev in self._previous.items():
            signal.signal(sig, prev)

    def _handle(self, _signum, _frame):
        self.stop = True


def train(out_dir: pathlib.Path, env_factory, iterations: int = 100, episodes_per_iter: int = 16,
          lr: float = 3e-4, seed: int = 0, eval_seeds=range(10000, 10020), log=print,
          init: pathlib.Path | None = None, workers: int = 1, max_minutes: float | None = None,
          teacher=None, teacher_weight: float = 0.0, pretrain_epochs: int = 0,
          teacher_tau: float = TEACHER_TAU) -> dict:
    torch.manual_seed(seed); np.random.seed(seed)
    env = env_factory()
    policy = Policy(env.nx, env.ny)
    if init is not None and pathlib.Path(init).exists():
        policy.load_state_dict(torch.load(init))
    out_dir.mkdir(parents=True, exist_ok=True)
    if teacher and pretrain_epochs > 0:
        bc = pretrain(policy, teacher, epochs=pretrain_epochs, log=log, tau=teacher_tau)
        (out_dir / "pretrain.json").write_text(json.dumps(bc["history"], indent=1), encoding="utf-8")
        torch.save(policy.state_dict(), out_dir / "policy-bc.pt")
    opt = torch.optim.Adam(policy.parameters(), lr=lr)
    collector = Collector(env_factory, env.nx, env.ny, workers=workers)
    history = []
    best = (-1.0, None)
    started = time.perf_counter()
    try:
      with _StopFlag() as flag:
        for it in range(iterations):
            if flag.stop:
                if log:
                    log({"stopped": "signal", "iter": it})
                break
            if max_minutes is not None and (time.perf_counter() - started) / 60.0 > max_minutes:
                if log:
                    log({"stopped": "time budget", "iter": it, "minutes": round((time.perf_counter() - started) / 60.0, 1)})
                break
            t0 = time.perf_counter()
            steps, returns = collector.collect(policy, episodes_per_iter, seed_base=1_000_000 + it * episodes_per_iter)
            t_collect = time.perf_counter() - t0
            ppo_update(policy, opt, steps, teacher=teacher, teacher_weight=teacher_weight, tau=teacher_tau)
            row = {"iter": it, "train_return": float(np.mean(returns)), "steps": len(steps),
                   "seconds": round(time.perf_counter() - t0, 1), "collect_seconds": round(t_collect, 1),
                   "steps_per_second": round(len(steps) / max(t_collect, 1e-9), 1)}
            if it % 5 == 0 or it == iterations - 1:
                ev = evaluate(env, policy, list(eval_seeds))
                row.update({"eval_" + k: v for k, v in ev.items()})
                if teacher:
                    row["teacher_accuracy"] = teacher_accuracy(policy, teacher, limit=500)
                if ev["gain"] > best[0]:
                    best = (ev["gain"], {k: v.detach().clone() for k, v in policy.state_dict().items()})
                    torch.save(policy.state_dict(), out_dir / "policy.pt")
            history.append(row)
            if log:
                log(row)
            (out_dir / "history.json").write_text(json.dumps(history, indent=1), encoding="utf-8")
    finally:
        collector.close()
    # the final policy is evaluated on the same seeds so that a best-so-far
    # checkpoint always exists even when the loop ended early
    if best[1] is None:
        ev = evaluate(env, policy, list(eval_seeds))
        best = (ev["gain"], None)
        torch.save(policy.state_dict(), out_dir / "policy.pt")
    return {"best_eval_gain": best[0], "history": history}
