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


def _teacher_steps(spec: str, env=None, policy_dir: str = ""):
    """Teacher pickles from a directory (recursively) or a glob; with a
    starting policy, streams it already matches are dropped."""
    import glob

    from .search import load_teacher

    if not spec:
        return None
    path = pathlib.Path(spec)
    files = sorted(str(p) for p in path.rglob("s*.pkl")) if path.is_dir() else sorted(glob.glob(spec))
    policy = load_ppo_policy(policy_dir, env) if (policy_dir and env is not None) else None
    steps = load_teacher(files, env=env, policy=policy, log=lambda line: print(line, flush=True))
    print(f"teacher: {len(files)} streams, {len(steps)} steps", flush=True)
    return steps


def cmd_train(args) -> int:
    from .ppo import train

    factory = env_factory(args.region, _layout(args), args.items, args.seed)
    init_dir = str(pathlib.Path(args.init).parent) if args.init else ""
    teacher = _teacher_steps(args.teacher, env=factory() if args.teacher else None, policy_dir=init_dir)
    result = train(pathlib.Path(args.out), factory,
                   iterations=args.iterations, episodes_per_iter=args.episodes, lr=args.lr, seed=args.seed,
                   log=lambda row: print(row, flush=True),
                   init=pathlib.Path(args.init) if args.init else None, workers=args.workers,
                   max_minutes=args.max_minutes, teacher=teacher,
                   teacher_weight=args.teacher_weight, pretrain_epochs=args.pretrain_epochs,
                   teacher_tau=args.teacher_tau)
    print(json.dumps({"best_eval_gain": result["best_eval_gain"]}))
    return 0


def cmd_teach(args) -> int:
    """Searched trajectories for many streams, as imitation targets."""
    from .search import teach

    seeds = list(range(args.seed0, args.seed0 + args.episodes))
    if args.shard:
        i, n = (int(v) for v in args.shard.split("/"))
        seeds = seeds[i::n]
    rows = teach(args.region, _layout(args), args.items, seeds, args.width, args.k, args.spread, args.rollout,
                 args.out, workers=args.workers, policy_dir=args.policy, mode=args.mode,
                 explore_eps=args.explore_eps, log=lambda line: print(line, flush=True))
    done = [r for r in rows if not r.get("skipped")]
    if done:
        label = "regret" if args.mode == "values" else "gain"
        print(f"mean {label} {np.mean([r['gain'] for r in done]):.4f} over {len(done)} new streams "
              f"({np.mean([r['seconds'] for r in done]):.0f}s each)")
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
        elif name == "lookahead":
            import torch

            from .lookahead import Lookahead
            from .ppo import Policy

            net = Policy(env.nx, env.ny)
            net.load_state_dict(torch.load(pathlib.Path(args.policy) / "policy.pt"))
            net.eval()
            policies["lookahead"] = Lookahead(net, k=args.k, threshold=args.threshold, horizon=args.horizon,
                                              deadline=args.deadline).act
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


def cmd_ceiling(args) -> int:
    """Beam search on a few streams next to the policy and the hand rules."""
    from .search import ceilings

    env = make_env(args.region, _layout(args), args.items)
    seeds = list(range(args.seed0, args.seed0 + args.episodes))
    beam = ceilings(args.region, _layout(args), args.items, seeds, args.width, args.k, workers=args.workers,
                    spread=args.spread, rollout=args.rollout, policy_dir=args.policy,
                    log=lambda line: print(line, flush=True))
    rows = []
    ppo = load_ppo_policy(args.policy, env) if args.policy else None
    for r in beam:
        row = {"seed": r["seed"], "beam": r["gain"], "beam_placed": r["placed"], "beam_seconds": r["seconds"]}
        if ppo is not None:
            row["ppo"] = run_episode(env, ppo, r["seed"])["gain"]
        for name in ("greedy_any", "staircase"):
            row[name] = run_episode(env, POLICIES[name], r["seed"], random.Random(r["seed"]))["gain"]
        rows.append(row)
        print(" ".join(f"{k}={v:.4f}" if isinstance(v, float) else f"{k}={v}" for k, v in row.items()), flush=True)
    means = {k: float(np.mean([row[k] for row in rows])) for k in rows[0] if k != "seed"}
    print("mean: " + " ".join(f"{k}={v:.4f}" for k, v in means.items()))
    if args.out:
        pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.out).write_text(json.dumps({"region": args.region, "layout": _layout(args),
                                                       "items": args.items, "width": args.width, "k": args.k,
                                                       "rows": rows, "means": means,
                                                       "actions": {r["seed"]: r["actions"] for r in beam}}, indent=1))
    return 0


def cmd_evolve(args) -> int:
    """Genetic programming of a priority function; held-out evaluation at the end."""
    from . import gp

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    factory = env_factory(args.region, _layout(args), args.items, args.seed)
    train_seeds = list(range(args.train_seed0, args.train_seed0 + args.train_streams))

    def checkpoint(best, history):
        gp.save(best, out / "best.json", {"history": history})

    result = gp.evolve(factory, train_seeds, generations=args.generations, population=args.population,
                       seed=args.seed, max_depth=args.max_depth, parsimony=args.parsimony,
                       workers=args.workers, log=lambda row: print(row, flush=True), checkpoint=checkpoint,
                       max_minutes=args.max_minutes)
    best = result["best"]
    env = factory()
    seeds = list(range(args.seed0, args.seed0 + args.episodes))
    rows = {"gp": {}}
    res = [run_episode(env, gp.policy_of(best), s) for s in seeds]
    rows["gp"] = {"gain": float(np.mean([r["gain"] for r in res])), "gain_max": float(max(r["gain"] for r in res)),
                  "placed": float(np.mean([r["placed"] for r in res])),
                  "placed_volume": float(np.mean([r["placed_volume"] for r in res])), "n": len(seeds)}
    for name in ("greedy_any", "staircase"):
        res = [run_episode(env, POLICIES[name], s, random.Random(s)) for s in seeds]
        rows[name] = {"gain": float(np.mean([r["gain"] for r in res])), "placed": float(np.mean([r["placed"] for r in res]))}
    print("best:", str(best))
    for name, row in rows.items():
        print(f"{name:10s} gain {row['gain']:.4f} placed {row['placed']:.2f}")
    gp.save(best, out / "best.json", {"history": result["history"], "train_fitness": result["best_fitness"],
                                      "eval": {"seeds": seeds, "rows": rows}})
    return 0


def cmd_diagnose(args) -> int:
    """Where the policy loses: per-step regret against its own rollouts."""
    from .diagnose import run

    seeds = list(range(args.seed0, args.seed0 + args.episodes))
    result = run(args.region, _layout(args), args.items, args.policy, seeds, k=args.k, spread=args.spread,
                 out=args.out, log=lambda line: print(line, flush=True))
    print(json.dumps(result["summary"], indent=1))
    return 0


def cmd_lookahead(args) -> int:
    """The trained policy with selective one-step look-ahead, paired against itself."""
    import torch

    from .lookahead import Lookahead
    from .ppo import Policy

    env = make_env(args.region, _layout(args), args.items)
    policy = Policy(env.nx, env.ny)
    policy.load_state_dict(torch.load(pathlib.Path(args.policy) / "policy.pt"))
    policy.eval()
    seeds = list(range(args.seed0, args.seed0 + args.episodes))
    plain = load_ppo_policy(args.policy, env)
    base = [run_episode(env, plain, s)["gain"] for s in seeds]
    la = Lookahead(policy, k=args.k, by_gain=args.by_gain, threshold=args.threshold,
                   horizon=args.horizon, use_value=not args.no_value, deadline=args.deadline)
    rows = []
    for s in seeds:
        r = run_episode(env, la.act, s)
        rows.append(r["gain"])
        print(f"[{args.region} s{s}] plain {base[len(rows) - 1]:.4f} lookahead {r['gain']:.4f} "
              f"expansions {la.expansions}/{la.decisions} max {la.stats()['seconds_max']:.1f}s", flush=True)
    d = np.array(rows) - np.array(base)
    rng = np.random.default_rng(0)
    boot = [float(np.mean(rng.choice(d, len(d)))) for _ in range(2000)]
    summary = {"region": args.region, "policy": args.policy, "k": args.k, "by_gain": args.by_gain,
               "threshold": args.threshold, "horizon": args.horizon, "use_value": not args.no_value,
               "deadline": args.deadline,
               "seeds": seeds, "plain": float(np.mean(base)), "lookahead": float(np.mean(rows)),
               "diff": float(np.mean(d)), "ci": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
               "wins": int((d > 1e-9).sum()), "losses": int((d < -1e-9).sum()), **la.stats(),
               "per_seed": {"plain": base, "lookahead": rows}}
    print(json.dumps({k: v for k, v in summary.items() if k != "per_seed"}, indent=1))
    if args.out:
        pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.out).write_text(json.dumps(summary, indent=1))
    return 0


def cmd_boards(args) -> int:
    """Layer-1 boards for the stacking region: the ladder's declined state per seed."""
    from .stack import BOARDS_DIR, build_boards

    seeds = list(range(args.seed0, args.seed0 + args.episodes))
    rows = build_boards(args.layout or "c1", seeds, boards_dir=args.out or BOARDS_DIR, workers=args.workers,
                        log=lambda line: print(line, flush=True))
    if rows:
        print(f"{len(rows)} boards: ladder placed {np.mean([r['placed'] for r in rows]):.1f}, "
              f"{np.mean([len(r['remaining']) for r in rows]):.1f} remaining on average")
    return 0


def _common(p, episodes: int, seed0: int):
    p.add_argument("--region", default="wedge", choices=REGIONS)
    p.add_argument("--layout", default="", help="container layout (default: c1 for wedge, c1s for shelf)")
    p.add_argument("--items", type=int, default=None, help="items per stream (default 14; 27 for stack)")
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
    t.add_argument("--layout", default=""); t.add_argument("--items", type=int, default=None)
    t.add_argument("--iterations", type=int, default=100); t.add_argument("--episodes", type=int, default=16)
    t.add_argument("--lr", type=float, default=3e-4); t.add_argument("--seed", type=int, default=0)
    t.add_argument("--workers", type=int, default=1, help="episode-collection processes")
    t.add_argument("--max-minutes", type=float, default=None,
                   help="stop cleanly (between iterations) after this wall-clock budget")
    t.add_argument("--teacher", default="", help="directory (or glob) of teacher pickles from `teach`")
    t.add_argument("--teacher-weight", type=float, default=0.0, help="imitation term weight in the PPO loss")
    t.add_argument("--pretrain-epochs", type=int, default=0, help="behaviour-cloning epochs before PPO")
    t.add_argument("--teacher-tau", type=float, default=0.005, help="temperature (m^3) for soft child-value targets")
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
    r.add_argument("--k", type=int, default=4); r.add_argument("--threshold", type=float, default=0.9)
    r.add_argument("--horizon", type=int, default=None); r.add_argument("--deadline", type=float, default=None)
    r.add_argument("--out", default="", help="per-episode jsonl (appended; resumable)")
    r.add_argument("--summary", default="")
    r.set_defaults(fn=cmd_replay)
    c = sub.add_parser("ceiling", help="beam-search ceiling of the region on a few streams"); _common(c, 6, 20000)
    c.add_argument("--width", type=int, default=100); c.add_argument("--k", type=int, default=8)
    c.add_argument("--spread", type=int, default=0, help="extra children spread along the candidate order")
    c.add_argument("--rollout", default="", help="rank children by gain plus a rollout: staircase|greedy_any|ppo")
    c.add_argument("--workers", type=int, default=1)
    c.add_argument("--policy", default="", help="directory holding policy.pt to compare against")
    c.add_argument("--out", default="")
    c.set_defaults(fn=cmd_ceiling)
    h = sub.add_parser("teach", help="searched trajectories for many streams (imitation targets)")
    _common(h, 64, 30000)
    h.add_argument("--width", type=int, default=8); h.add_argument("--k", type=int, default=4)
    h.add_argument("--spread", type=int, default=4)
    h.add_argument("--rollout", default="", help="staircase (wedge), greedy_any (shelf) or ppo (needs --policy)")
    h.add_argument("--policy", default="", help="directory holding policy.pt (rollout ppo, or mode values)")
    h.add_argument("--mode", default="beam", choices=("beam", "values"),
                   help="beam: searched trajectory; values: child values at the policy's own states")
    h.add_argument("--explore-eps", type=float, default=0.2, help="mode values: exploration along the path")
    h.add_argument("--workers", type=int, default=1)
    h.add_argument("--shard", default="", help="i/n: this process takes every n-th seed starting at i")
    h.add_argument("--out", required=True, help="directory for s<seed>.pkl files (resumable)")
    h.set_defaults(fn=cmd_teach)
    g = sub.add_parser("evolve", help="genetic programming of a priority function"); _common(g, 40, 20000)
    g.add_argument("--train-seed0", type=int, default=1_000_000); g.add_argument("--train-streams", type=int, default=32)
    g.add_argument("--generations", type=int, default=40); g.add_argument("--population", type=int, default=120)
    g.add_argument("--max-depth", type=int, default=6); g.add_argument("--parsimony", type=float, default=1e-4)
    g.add_argument("--seed", type=int, default=0); g.add_argument("--workers", type=int, default=1)
    g.add_argument("--max-minutes", type=float, default=None, help="stop between generations after this budget")
    g.add_argument("--out", required=True)
    g.set_defaults(fn=cmd_evolve)
    d = sub.add_parser("diagnose", help="per-step regret, ambiguity, confidence and value accuracy"); _common(d, 20, 20000)
    d.add_argument("--policy", required=True); d.add_argument("--k", type=int, default=6)
    d.add_argument("--spread", type=int, default=6); d.add_argument("--out", default="")
    d.set_defaults(fn=cmd_diagnose)
    la = sub.add_parser("lookahead", help="selective one-step look-ahead over the policy"); _common(la, 40, 20000)
    la.add_argument("--policy", required=True); la.add_argument("--k", type=int, default=4)
    la.add_argument("--by-gain", type=int, default=1); la.add_argument("--threshold", type=float, default=0.9)
    la.add_argument("--horizon", type=int, default=None); la.add_argument("--no-value", action="store_true")
    la.add_argument("--deadline", type=float, default=None, help="seconds per decision before the search stops")
    la.add_argument("--out", default="")
    la.set_defaults(fn=cmd_lookahead)
    bo = sub.add_parser("boards", help="build the ladder's declined boards for the stacking region")
    bo.add_argument("--layout", default="c1"); bo.add_argument("--episodes", type=int, default=256)
    bo.add_argument("--seed0", type=int, default=1_000_000); bo.add_argument("--workers", type=int, default=1)
    bo.add_argument("--out", default="", help="boards directory (default reports/wedge/boards)")
    bo.set_defaults(fn=cmd_boards)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
