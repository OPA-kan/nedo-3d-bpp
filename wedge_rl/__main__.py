"""    python -m wedge_rl baselines --region wedge --layout c1 --episodes 20
    python -m wedge_rl train --region shelf --layout c1s --out runs/shelf --iterations 100 --workers 4
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys

import numpy as np

from .baselines import greedy_any, greedy_gain, random_policy, run_episode, staircase
from .regions import DEFAULT_LAYOUT, REGIONS, env_factory, make_env

POLICIES = {"greedy_gain": greedy_gain, "greedy_any": greedy_any, "staircase": staircase,
            "random": random_policy}


def _layout(args) -> str:
    return args.layout or DEFAULT_LAYOUT[args.region]


def cmd_baselines(args) -> int:
    env = make_env(args.region, _layout(args), args.items)
    seeds = list(range(args.seed0, args.seed0 + args.episodes))
    rows = {}
    for name, pol in POLICIES.items():
        res = [run_episode(env, pol, s, random.Random(s)) for s in seeds]
        rows[name] = {k: float(np.mean([r[k] for r in res])) for k in ("gain", "placed_volume", "placed", "passes")}
        rows[name]["gain_max"] = float(max(r["gain"] for r in res))
        print(f"{name:13s} " + " ".join(f"{k}={v:.3f}" for k, v in rows[name].items()))
    if args.out:
        pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.out).write_text(json.dumps({"region": args.region, "layout": _layout(args),
                                                       "items": args.items, "seeds": seeds, "rows": rows}, indent=1))
    return 0


def cmd_train(args) -> int:
    from .ppo import train

    result = train(pathlib.Path(args.out), env_factory(args.region, _layout(args), args.items, args.seed),
                   iterations=args.iterations, episodes_per_iter=args.episodes, lr=args.lr, seed=args.seed,
                   log=lambda row: print(row, flush=True),
                   init=pathlib.Path(args.init) if args.init else None, workers=args.workers,
                   max_minutes=args.max_minutes)
    print(json.dumps({"best_eval_gain": result["best_eval_gain"]}))
    return 0


def load_ppo_policy(policy_dir: str, env):
    """The saved PPO policy as a ``policy(env, rng) -> action`` callable."""
    import torch

    from .ppo import Policy, _features, decode

    policy = Policy(env.nx, env.ny)
    policy.load_state_dict(torch.load(pathlib.Path(policy_dir) / "policy.pt"))
    policy.eval()

    def act(env, _rng=None) -> int:
        feats = _features(env)
        with torch.no_grad():
            logits = policy.logits(policy.embed(env.observation()), feats)
        return decode(logits, len(feats))

    return act


def cmd_eval(args) -> int:
    """The saved policy against every baseline on fresh seeds."""
    import torch

    from .ppo import Policy, evaluate

    env = make_env(args.region, _layout(args), args.items)
    seeds = list(range(args.seed0, args.seed0 + args.episodes))
    policy = Policy(env.nx, env.ny)
    policy.load_state_dict(torch.load(pathlib.Path(args.policy) / "policy.pt"))
    policy.eval()
    rows = {"ppo": evaluate(env, policy, seeds)}
    for name, pol in POLICIES.items():
        res = [run_episode(env, pol, s, random.Random(s)) for s in seeds]
        rows[name] = {"gain": float(np.mean([r["gain"] for r in res])),
                      "gain_max": float(max(r["gain"] for r in res)),
                      "placed": float(np.mean([r["placed"] for r in res])),
                      "placed_volume": float(np.mean([r["placed_volume"] for r in res])), "n": len(seeds)}
    for name, row in rows.items():
        print(f"{name:13s} gain {row['gain']:.4f} (max {row['gain_max']:.4f})  placed {row['placed']:.2f}  volume {row['placed_volume']:.3f}")
    if args.out:
        pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.out).write_text(json.dumps({"region": args.region, "layout": _layout(args),
                                                       "items": args.items, "seeds": seeds, "rows": rows}, indent=1))
    return 0


def cmd_replay(args) -> int:
    """Plan with each policy, replay the boxes in PyBullet, report acceptance."""
    from .replay import replay_many

    env = make_env(args.region, _layout(args), args.items)
    seeds = list(range(args.seed0, args.seed0 + args.episodes))
    policies = {}
    for name in args.policies.split(","):
        if name == "ppo":
            policies["ppo"] = load_ppo_policy(args.policy, env)
        else:
            policies[name] = POLICIES[name]
    out = pathlib.Path(args.out) if args.out else None
    summary = replay_many(env, policies, seeds, out, with_shake=not args.no_shake,
                          log=lambda line: print(line, flush=True))
    for label, row in summary.items():
        print(f"{label:10s} accept {row['acceptance']:.3f} clean {row['clean_episodes']:.2f} "
              f"gain {row['planned_strip']:.4f}->{row['realized_strip']:.4f} "
              f"overhang {row['overhang_steps']} ok {row['overhang_acceptance']} "
              f"xy max {row['xy_shift_max']:.3f} ends {row['end_reasons']}")
    if args.summary:
        pathlib.Path(args.summary).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.summary).write_text(json.dumps({"region": args.region, "layout": _layout(args),
                                                           "items": args.items, "seeds": seeds, "rows": summary}, indent=1))
    return 0


def _common(p, episodes: int, seed0: int):
    p.add_argument("--region", default="wedge", choices=REGIONS)
    p.add_argument("--layout", default="", help="container layout (default: c1 for wedge, c1s for shelf)")
    p.add_argument("--items", type=int, default=14)
    p.add_argument("--episodes", type=int, default=episodes)
    p.add_argument("--seed0", type=int, default=seed0)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="wedge_rl", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("baselines"); _common(b, 20, 10000)
    b.add_argument("--out", default="")
    b.set_defaults(fn=cmd_baselines)
    t = sub.add_parser("train")
    t.add_argument("--region", default="wedge", choices=REGIONS)
    t.add_argument("--layout", default=""); t.add_argument("--items", type=int, default=14)
    t.add_argument("--iterations", type=int, default=100); t.add_argument("--episodes", type=int, default=16)
    t.add_argument("--lr", type=float, default=3e-4); t.add_argument("--seed", type=int, default=0)
    t.add_argument("--workers", type=int, default=1, help="episode-collection processes")
    t.add_argument("--max-minutes", type=float, default=None,
                   help="stop cleanly (between iterations) after this wall-clock budget")
    t.add_argument("--out", required=True)
    t.add_argument("--init", default="", help="policy.pt to start from")
    t.set_defaults(fn=cmd_train)
    e = sub.add_parser("eval"); _common(e, 40, 20000)
    e.add_argument("--policy", required=True, help="directory holding policy.pt")
    e.add_argument("--out", default="")
    e.set_defaults(fn=cmd_eval)
    r = sub.add_parser("replay", help="replay planned boxes in the official simulator"); _common(r, 40, 20000)
    r.add_argument("--policies", default="ppo,staircase", help="comma list of ppo and/or baseline names")
    r.add_argument("--policy", default="", help="directory holding policy.pt (for ppo)")
    r.add_argument("--no-shake", action="store_true")
    r.add_argument("--out", default="", help="per-episode jsonl (appended; resumable)")
    r.add_argument("--summary", default="")
    r.set_defaults(fn=cmd_replay)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
