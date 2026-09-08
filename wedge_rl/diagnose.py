"""Why does the executor plateau?  Four measurements on held-out streams.

1. Regret per step.  Along the policy's own (deterministic) trajectory,
   every visited state is expanded: the top-k children by gain, a spread of
   others, and PASS, each finished to the end of the stream with the
   policy itself.  Regret is the best child's total minus the chosen
   child's total.  Summed over an episode it is the gap the policy leaves
   on the table *by its own one-step choices*, and it can be split by step
   index and by PASS/place, which says where the plateau lives.
2. Ambiguity.  At each state, how many children come within a tolerance
   of the best: many near-ties mean an imitation target is arbitrary.
3. Confidence.  Entropy of the action distribution and the probability of
   the chosen action; a policy that is already deterministic has stopped
   exploring.
4. Value head.  Predicted value against the realised return from the same
   state (deterministic decode), as a correlation.
"""

from __future__ import annotations

import json
import time

import numpy as np
import torch

from .env import PASS
from .ppo import _features, decode


def _place_entry(env, item, c):
    return {"index": int(item["index"]), "length": item["length"], "width": item["width"],
            "height": item["height"], "mass": item["mass"], "is_soft": bool(item["is_soft"]),
            "is_prioritized": False, "orientation": c.orientation, "dims": tuple(c.dims),
            "pos": tuple(float(v) for v in c.box.center), "layer": 1}


def _load(env, template, packed, t, stream):
    env.container = dict(template)
    env.container["packed_items"] = list(packed)
    env.cursor = t
    env.placed = []
    env.stream = stream
    env._cands = None


def _finish(env, template, packed, t, stream, act) -> float:
    """Total gain from state (packed, t) to the end under ``act``."""
    _load(env, template, packed, t, stream)
    total = 0.0
    while not env.done:
        _o, r, _d, _i = env.step(act(env))
        total += r
    return total


def _children(cands, k, spread):
    by_gain = sorted(range(len(cands)), key=lambda i: -cands[i].gain)[:k]
    chosen = list(by_gain)
    rest = [i for i in range(len(cands)) if i not in set(by_gain)]
    if spread and rest:
        step = max(1, len(rest) // spread)
        chosen.extend(rest[::step][:spread])
    return chosen


def diagnose_episode(env, policy, seed: int, k: int = 6, spread: int = 6, tol: float = 1e-3) -> dict:
    def act(e):
        feats = _features(e)
        with torch.no_grad():
            logits = policy.logits(policy.embed(e.observation()), feats)
        return decode(logits, len(feats))

    env.reset(seed)
    template = dict(env.container)
    stream = list(env.stream)
    n = len(stream)
    packed = []
    rows = []
    realised = []
    for t in range(n):
        _load(env, template, packed, t, stream)
        cands = env.candidates()
        feats = _features(env)
        obs = env.observation()
        with torch.no_grad():
            emb = policy.embed(obs)
            logits = policy.logits(emb, feats)
            v_pred = float(policy.value(emb))
        p = torch.softmax(logits, dim=0).numpy()
        entropy = float(-(p * np.log(p + 1e-12)).sum())
        a = decode(logits, len(feats))
        chosen_idx = len(feats) if a == PASS else a
        item = stream[t]
        # children: PASS plus the chosen plus top-k plus spread
        options = {PASS: list(packed)}
        if cands:
            for i in set(_children(cands, k, spread) + ([a] if a != PASS else [])):
                options[i] = list(packed) + [_place_entry(env, item, cands[i])]
        values = {}
        for opt, child_packed in options.items():
            own = 0.0 if opt == PASS else cands[opt].gain
            values[opt] = own + _finish(env, template, child_packed, t + 1, stream, act)
        best_opt = max(values, key=values.get)
        best = values[best_opt]
        chosen_value = values[a]
        near = sum(1 for v in values.values() if v >= best - tol)
        rows.append({
            "step": t, "n_cands": len(cands), "chosen_pass": a == PASS, "best_pass": best_opt == PASS,
            "regret": best - chosen_value, "best": best, "chosen_value": chosen_value,
            "chosen_gain": 0.0 if a == PASS else cands[a].gain,
            "best_gain": 0.0 if best_opt == PASS else cands[best_opt].gain,
            "near_ties": near, "entropy": entropy, "p_chosen": float(p[chosen_idx]), "p_pass": float(p[-1]),
            "v_pred": v_pred, "item_vol": float(item["length"] * item["width"] * item["height"]),
        })
        realised.append(chosen_value)
        packed = options[a]
    # realised return from each state along the chosen path is chosen_value
    return {"seed": seed, "steps": rows, "total": realised[0] if realised else 0.0}


def summarize(episodes: list[dict]) -> dict:
    steps = [s for e in episodes for s in e["steps"]]
    n = len(episodes)
    regret = np.array([s["regret"] for s in steps])
    by_step = {}
    for s in steps:
        by_step.setdefault(s["step"], []).append(s["regret"])
    by_pass = {"chosen_pass": [], "chosen_place": []}
    for s in steps:
        by_pass["chosen_pass" if s["chosen_pass"] else "chosen_place"].append(s["regret"])
    v_pred = np.array([s["v_pred"] for s in steps])
    v_real = np.array([s["chosen_value"] for s in steps])
    corr = float(np.corrcoef(v_pred, v_real)[0, 1]) if len(steps) > 2 else float("nan")
    return {
        "episodes": n,
        "mean_total": float(np.mean([e["total"] for e in episodes])),
        "regret_per_episode": float(regret.sum() / max(n, 1)),
        "steps_with_regret": float((regret > 1e-6).mean()),
        "regret_by_step": {int(k): float(np.mean(v)) for k, v in sorted(by_step.items())},
        "regret_by_choice": {k: (float(np.mean(v)) if v else 0.0, len(v)) for k, v in by_pass.items()},
        "pass_errors": {
            "chose_pass_should_place": sum(1 for s in steps if s["chosen_pass"] and not s["best_pass"] and s["regret"] > 1e-6),
            "chose_place_should_pass": sum(1 for s in steps if not s["chosen_pass"] and s["best_pass"] and s["regret"] > 1e-6),
            "wrong_pose": sum(1 for s in steps if not s["chosen_pass"] and not s["best_pass"] and s["regret"] > 1e-6),
        },
        "near_ties_mean": float(np.mean([s["near_ties"] for s in steps])),
        "near_ties_share_gt1": float(np.mean([s["near_ties"] > 1 for s in steps])),
        "entropy_mean": float(np.mean([s["entropy"] for s in steps])),
        "p_chosen_mean": float(np.mean([s["p_chosen"] for s in steps])),
        "p_chosen_gt09": float(np.mean([s["p_chosen"] > 0.9 for s in steps])),
        "value_corr": corr,
        "value_bias": float(np.mean(v_pred * 0.1 - v_real)),   # value head is trained on rewards x10
        "regret_when_confident": float(np.mean([s["regret"] for s in steps if s["p_chosen"] > 0.9]) if any(s["p_chosen"] > 0.9 for s in steps) else 0.0),
        "regret_when_unsure": float(np.mean([s["regret"] for s in steps if s["p_chosen"] <= 0.9]) if any(s["p_chosen"] <= 0.9 for s in steps) else 0.0),
    }


def run(region: str, layout: str, n_items: int, policy_dir: str, seeds, k: int = 6, spread: int = 6,
        out=None, log=print) -> dict:
    from .__main__ import load_ppo_policy  # noqa: F401  (import check)
    from .ppo import Policy
    from .regions import make_env

    env = make_env(region, layout, n_items)
    policy = Policy(env.nx, env.ny)
    import pathlib

    policy.load_state_dict(torch.load(pathlib.Path(policy_dir) / "policy.pt"))
    policy.eval()
    episodes = []
    for seed in seeds:
        t0 = time.perf_counter()
        ep = diagnose_episode(env, policy, seed, k=k, spread=spread)
        episodes.append(ep)
        if log:
            log(f"[{region} s{seed}] total {ep['total']:.4f} regret {sum(s['regret'] for s in ep['steps']):.4f} "
                f"in {time.perf_counter() - t0:.0f}s")
        if out is not None:
            import pathlib as _p

            _p.Path(out).parent.mkdir(parents=True, exist_ok=True)
            _p.Path(out).write_text(json.dumps({"region": region, "policy": str(policy_dir),
                                               "summary": summarize(episodes), "episodes": episodes}, indent=1))
    return {"summary": summarize(episodes), "episodes": episodes}
