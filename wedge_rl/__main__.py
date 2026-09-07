"""    python -m wedge_rl baselines --layout c1 --episodes 20
    python -m wedge_rl train --out runs/wedge --iterations 100
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys

import numpy as np

from .baselines import greedy_any, greedy_strip, random_policy, run_episode, staircase
from .env import WedgeEnv

POLICIES = {"greedy_strip": greedy_strip, "greedy_any": greedy_any, "staircase": staircase,
            "random": random_policy}


def cmd_baselines(args) -> int:
    env = WedgeEnv(args.layout, n_items=args.items)
    seeds = list(range(args.seed0, args.seed0 + args.episodes))
    rows = {}
    for name, pol in POLICIES.items():
        res = [run_episode(env, pol, s, random.Random(s)) for s in seeds]
        rows[name] = {k: float(np.mean([r[k] for r in res])) for k in ("strip_volume", "placed_volume", "placed", "passes")}
        rows[name]["strip_max"] = float(max(r["strip_volume"] for r in res))
        print(f"{name:13s} " + " ".join(f"{k}={v:.3f}" for k, v in rows[name].items()))
    if args.out:
        pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.out).write_text(json.dumps({"layout": args.layout, "items": args.items,
                                                       "seeds": seeds, "rows": rows}, indent=1))
    return 0


def cmd_train(args) -> int:
    from .ppo import train

    result = train(pathlib.Path(args.out), layout=args.layout, n_items=args.items,
                   iterations=args.iterations, episodes_per_iter=args.episodes, lr=args.lr, seed=args.seed,
                   log=lambda row: print(row, flush=True))
    print(json.dumps({"best_eval_strip_volume": result["best_eval_strip_volume"]}))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="wedge_rl", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("baselines")
    b.add_argument("--layout", default="c1"); b.add_argument("--items", type=int, default=14)
    b.add_argument("--episodes", type=int, default=20); b.add_argument("--seed0", type=int, default=10000)
    b.add_argument("--out", default="")
    b.set_defaults(fn=cmd_baselines)
    t = sub.add_parser("train")
    t.add_argument("--layout", default="c1"); t.add_argument("--items", type=int, default=14)
    t.add_argument("--iterations", type=int, default=100); t.add_argument("--episodes", type=int, default=16)
    t.add_argument("--lr", type=float, default=3e-4); t.add_argument("--seed", type=int, default=0)
    t.add_argument("--out", required=True)
    t.set_defaults(fn=cmd_train)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
