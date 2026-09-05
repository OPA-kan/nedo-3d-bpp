"""Command line for the bench.

    python -m bench scenes  --suite core
    python -m bench run     --arm ladder --suite smoke --out reports/bench/ladder-smoke
    python -m bench compare reports/bench/A reports/bench/B --out reports/bench/A-vs-B.md
    python -m bench agree   --arm ladder --suite smoke --out reports/bench/agree-smoke
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

from . import agreement, compare
from .analytic import run_analytic_episode
from .arms import make_arm
from .episode import run_episode, write_record
from .scenes import SUITES, build_suite, make_scene

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _scenes(args) -> list:
    if args.scene:
        task, layout, seed = args.scene.split(":")
        return [make_scene(int(seed), layout, task.upper())]
    scenes = build_suite(args.suite)
    if args.limit:
        scenes = scenes[: args.limit]
    return scenes


def cmd_scenes(args) -> int:
    for scene in _scenes(args):
        classes = {"hard": 0, "soft": 0, "priority": 0, "soft+priority": 0}
        for item in scene.items:
            key = ("soft+priority" if item["is_soft"] and item["is_prioritized"]
                   else "soft" if item["is_soft"] else "priority" if item["is_prioritized"] else "hard")
            classes[key] += 1
        print(f"{scene.name:18s} task {scene.task} pool {scene.look_ahead:2d} "
              f"containers {len(scene.containers)} items {len(scene.items):3d} {classes}")
    return 0


def _summary_row(record: dict) -> dict:
    m = record["metrics"]
    return {
        "scene": record["scene"],
        "placed": m["placed_count"], "total": m["total_items"],
        "fill_volume": round(m["fill_volume"], 3),
        "fill_shipped": round(m["fill_evaluator_shipped"], 3) if "fill_evaluator_shipped" in m else None,
        "fill_tolerant": round(m["fill_evaluator_tolerant"], 3) if "fill_evaluator_tolerant" in m else None,
        "com_z_ratio": round(m["com_z_above_floor_ratio"], 4),
        "priority_covered": m["priority_covered"], "priority_misrouted": m["priority_misrouted"],
        "soft_covered": m["soft_covered"],
        "shake_mean_shift": round(m["shake_mean_shift"], 4) if "shake_mean_shift" in m else None,
        "shake_topples": m.get("shake_topples"),
        "policy_time_max": round(m["policy_time_max"], 3),
        "over_budget_steps": m["over_budget_steps"],
        "end_reason": m["end_reason"],
        "runtime_seconds": record["runtime_seconds"],
    }


def _write_summary(out: pathlib.Path, rows: list[dict], arm_desc: dict, extra: dict | None = None) -> None:
    (out / "summary.json").write_text(
        json.dumps({"arm": arm_desc, "rows": rows, **(extra or {})}, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    if not rows:
        return
    keys = list(rows[0].keys())
    lines = [f"# bench run: `{arm_desc.get('arm')}`", "",
             "| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
    for row in rows:
        lines.append("| " + " | ".join(str(row[k]) for k in keys) + " |")
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_run(args) -> int:
    arm = make_arm(args.arm)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for scene in _scenes(args):
        started = time.perf_counter()
        existing = out / f"{scene.name}.json"
        if args.resume and existing.exists():
            record = json.loads(existing.read_text(encoding="utf-8"))
            rows.append(_summary_row(record))
            _write_summary(out, rows, arm.describe())
            continue
        if args.sim == "analytic":
            record = run_analytic_episode(scene, arm, policy_budget=args.budget)
        else:
            record = run_episode(scene, arm, policy_budget=args.budget, with_shake=not args.no_shake)
        write_record(record, out)
        rows.append(_summary_row(record))
        m = record["metrics"]
        print(f"[{scene.name}] placed {m['placed_count']}/{m['total_items']} "
              f"fill_vol {m['fill_volume']:.2f} end {m['end_reason']} "
              f"policy_max {m['policy_time_max']:.2f}s in {time.perf_counter() - started:.0f}s",
              flush=True)
        _write_summary(out, rows, arm.describe())
    return 0


def cmd_compare(args) -> int:
    run_a = compare.load_run(pathlib.Path(args.run_a))
    run_b = compare.load_run(pathlib.Path(args.run_b))
    label_a = args.label_a or pathlib.Path(args.run_a).name
    label_b = args.label_b or pathlib.Path(args.run_b).name
    result = compare.compare_runs(run_a, run_b, label_a, label_b)
    text = compare.markdown(result)
    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        out.with_suffix(".json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(text)
    return 0


def cmd_agree(args) -> int:
    arm = make_arm(args.arm)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    probe = agreement.make_probe(arm.config, per_decision=args.per_decision,
                                 perturbed_per_decision=args.perturbed, seed=args.seed)
    records = []
    for scene in _scenes(args):
        started = time.perf_counter()
        existing = out / f"{scene.name}.json"
        if args.resume and existing.exists():
            record = json.loads(existing.read_text(encoding="utf-8"))
        else:
            record = run_episode(scene, arm, policy_budget=args.budget, probe=probe, with_shake=False)
            write_record(record, out)
        records.append(record)
        partial = agreement.confusion(records)
        print(f"[{scene.name}] probes so far {partial['n']} cells {partial['cells']} "
              f"in {time.perf_counter() - started:.0f}s", flush=True)
        (out / "agreement.json").write_text(json.dumps(partial, indent=1), encoding="utf-8")
        (out / "agreement.md").write_text(_agreement_markdown(partial, arm.describe()), encoding="utf-8")
    return 0


def cmd_rollouts(args) -> int:
    from .rollouts import rollout_scene, write_jsonl

    arm = make_arm(args.arm)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    scenes = _scenes(args)
    if args.shard:
        index, _sep, count = args.shard.partition("/")
        scenes = [s for i, s in enumerate(scenes) if i % int(count) == int(index)]
    for scene in scenes:
        path = out / f"{scene.name}.jsonl"
        if args.resume and path.exists():
            continue
        started = time.perf_counter()
        records = rollout_scene(scene, arm, horizon=args.horizon, k=args.k, seed=args.seed)
        write_jsonl(records, path)
        decisions = len({r["step"] for r in records})
        print(f"[{scene.name}] {len(records)} labels over {decisions} decisions "
              f"in {time.perf_counter() - started:.0f}s", flush=True)
    return 0


def _agreement_markdown(result: dict, arm_desc: dict) -> str:
    c = result["cells"]
    lines = [
        f"# Analytic model vs official validator: `{arm_desc.get('arm')}`",
        "",
        f"Probes: {result['n']}",
        "",
        "| | physics accepts | physics rejects |",
        "|---|---:|---:|",
        f"| analytic accepts | {c['aa']} | {c['ar']} |",
        f"| analytic rejects | {c['ra']} | {c['rr']} |",
        "",
        f"False-accept rate (analytic accepts, physics rejects): "
        f"{_fmt(result['false_accept_rate'])}",
        f"False-reject rate (analytic rejects, physics accepts): "
        f"{_fmt(result['false_reject_rate'])}",
        f"Agreement: {_fmt(result['agreement'])}",
        "",
        "## By probe kind",
        "",
        "| kind | n | both accept | analytic only | physics only | both reject |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for kind, row in sorted(result["by_kind"].items()):
        lines.append(f"| {kind} | {row['n']} | {row['both_accept']} | {row['analytic_only']} | "
                     f"{row['physics_only']} | {row['both_reject']} |")
    lines += ["", "## By analytic reason", "", "| analytic reason | n | physics accepted |", "|---|---:|---:|"]
    for reason, row in sorted(result["by_analytic_reason"].items()):
        lines.append(f"| {reason} | {row['n']} | {row['physics_accepted']} |")
    return "\n".join(lines) + "\n"


def _fmt(value) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="bench", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def scene_args(p):
        p.add_argument("--suite", default="smoke", choices=sorted(SUITES))
        p.add_argument("--scene", default="", help="single scene as TASK:LAYOUT:SEED, e.g. C:c1s:7")
        p.add_argument("--limit", type=int, default=0)
        p.add_argument("--resume", action="store_true",
                       help="skip scenes whose record already exists in --out")

    p = sub.add_parser("scenes"); scene_args(p); p.set_defaults(fn=cmd_scenes)
    p = sub.add_parser("run"); scene_args(p)
    p.add_argument("--arm", default="ladder"); p.add_argument("--out", required=True)
    p.add_argument("--budget", type=float, default=8.0); p.add_argument("--no-shake", action="store_true")
    p.add_argument("--sim", default="physics", choices=("physics", "analytic"),
                   help="physics: the official PyBullet environment; analytic: rule-alpha's model")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("compare")
    p.add_argument("run_a"); p.add_argument("run_b"); p.add_argument("--out", default="")
    p.add_argument("--label-a", default=""); p.add_argument("--label-b", default="")
    p.set_defaults(fn=cmd_compare)
    p = sub.add_parser("rollouts"); scene_args(p)
    p.add_argument("--arm", default="ladder-stable"); p.add_argument("--out", required=True)
    p.add_argument("--horizon", type=int, default=999, help="continuation length; 999 = to the end")
    p.add_argument("--k", type=int, default=5, help="candidates labelled per decision")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--shard", default="", help="i/n: take every n-th scene starting at i")
    p.set_defaults(fn=cmd_rollouts)
    p = sub.add_parser("agree"); scene_args(p)
    p.add_argument("--arm", default="ladder"); p.add_argument("--out", required=True)
    p.add_argument("--budget", type=float, default=8.0)
    p.add_argument("--per-decision", type=int, default=4)
    p.add_argument("--perturbed", type=int, default=4)
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(fn=cmd_agree)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
