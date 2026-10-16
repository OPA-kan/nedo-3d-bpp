"""The platform's score, read off bench records.

    python -m bench.platform_score <base_dir> <new_dir> [<new_dir> ...]
        [--mix core-a=9,core-b=11,core=3] [--json out.json]

Every episode record (`reports/bench/<run>/<scene>.json`) is priced the way
the platform prices an episode, from what the diagnostics established
(reports/wedge/platform-refit.md, stability-lattice.md):

- the five components at the official weights (fill .287, cog .219,
  stability .210, placement .143, soft .141);
- the count gate: an episode that places no more than half its items
  scores zero on everything but the fill (the lattice: a counted episode
  is worth 100 / N on each gated component);
- fill: the official evaluator's fill with the tolerant inclusion check
  (`fill_evaluator_tolerant`; the platform's inclusion test is the looser
  one), the bench's own `fill_volume` reported beside it;
- cog: 125 - 137 x the load's centre-of-mass height ratio
  (`com_z_above_floor_ratio`), the slope from the refit's price of the
  centre of mass (-0.01 of ratio over the three tasks = +0.30 total
  points) and the level from the diagnostics' per-episode cog of the
  three tasks at N = 23 (A 87, B 77, C 72);
- stability: 97 - 3.8 x the shake topples (the lattice's constant 0.961
  at N = 23 and its -0.165 per topple an episode);
- placement: the share of the priority cargo placed, not covered by
  another attribute and not misrouted; soft: the share of the soft cargo
  placed and not covered (soft on soft is not charged).

The suite score is the mean over its episodes; a platform mix weights
suites by the platform's task shares (the diagnostics: A about 9, B 11,
C 3 of 23 episodes).  Against a base run the differences are paired by
scene with a bootstrap interval.  This is the bench's objective: what a
change is worth where the platform pays, not a crossing count.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import random
import statistics
import sys
from typing import Iterable

WEIGHTS = dict(fill=0.287, cog=0.219, stability=0.210, placement=0.143, soft=0.141)
COG_LEVEL, COG_SLOPE = 125.0, 137.0
STAB_LEVEL, STAB_PER_TOPPLE = 97.0, 3.8
COMPONENTS = ("fill", "cog", "stability", "placement", "soft")

_scene_cache: dict = {}


def _scene_totals(spec: dict) -> tuple[int, int]:
    """(soft total, priority total) of the record's scene, rebuilt."""
    key = (spec.get("seed"), spec.get("layout"), spec.get("task"))
    if key not in _scene_cache:
        try:
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from bench.scenes import make_scene

            sc = make_scene(int(spec["seed"]), str(spec["layout"]), str(spec["task"]))
            _scene_cache[key] = (sum(1 for i in sc.items if i.get("is_soft")),
                                 sum(1 for i in sc.items if i.get("is_prioritized")))
        except Exception:
            _scene_cache[key] = (0, 0)
    return _scene_cache[key]


def score_episode(record: dict) -> dict:
    """The platform-like components and total of one episode record."""
    m = record["metrics"]
    total = int(m["total_items"])
    placed = int(m["placed_count"])
    counted = placed > total // 2
    fill = float(m.get("fill_evaluator_tolerant", m.get("fill_volume", 0.0)))
    ratio = float(m.get("com_z_above_floor_ratio", 0.0) or 0.0)
    cog = max(0.0, min(100.0, COG_LEVEL - COG_SLOPE * ratio)) if placed else 0.0
    topples = int(m.get("shake_topples", 0) or 0)
    stability = max(0.0, min(100.0, STAB_LEVEL - STAB_PER_TOPPLE * topples)) if placed else 0.0
    soft_total, prio_total = _scene_totals(record.get("scene_spec", {}))
    soft_ok = int(m.get("soft_count", 0) or 0) - int(m.get("soft_covered", 0) or 0)
    prio_ok = (int(m.get("priority_count", 0) or 0) - int(m.get("priority_covered", 0) or 0)
               - int(m.get("priority_misrouted", 0) or 0))
    placement = 100.0 * max(0, prio_ok) / prio_total if prio_total else 100.0
    soft = 100.0 * max(0, soft_ok) / soft_total if soft_total else 100.0
    gate = 1.0 if counted else 0.0
    comps = dict(fill=fill, cog=gate * cog, stability=gate * stability, placement=gate * placement, soft=gate * soft)
    score = sum(WEIGHTS[k] * comps[k] for k in COMPONENTS)
    return dict(scene=record.get("scene"), counted=counted, placed=placed, total=total, score=score,
                fill_bench=float(m.get("fill_volume", 0.0)), ratio=ratio, topples=topples,
                soft_ok=soft_ok, soft_total=soft_total, prio_ok=prio_ok, prio_total=prio_total,
                policy_max=float(m.get("policy_time_max", 0.0) or 0.0), **comps)


def load_run(path: str) -> dict:
    out = {}
    for f in sorted(glob.glob(os.path.join(path, "[abc]-*-s*.json"))):
        try:
            r = json.load(open(f))
        except Exception:
            continue
        if "metrics" not in r:
            continue
        e = score_episode(r)
        out[e["scene"]] = e
    return out


def summarize(eps: Iterable[dict]) -> dict:
    eps = list(eps)
    n = len(eps)
    if not n:
        return {}
    return dict(n=n, score=statistics.mean(e["score"] for e in eps),
                counted=sum(1 for e in eps if e["counted"]),
                placed=statistics.mean(e["placed"] for e in eps),
                policy_max=max(e["policy_max"] for e in eps),
                **{k: statistics.mean(e[k] for e in eps) for k in COMPONENTS})


def paired_delta(base: dict, new: dict, boot: int = 2000, seed: int = 7) -> dict:
    scenes = sorted(set(base) & set(new))
    if not scenes:
        return {}
    d = [new[s]["score"] - base[s]["score"] for s in scenes]
    rng = random.Random(seed)
    means = []
    for _ in range(boot):
        sample = [d[rng.randrange(len(d))] for _ in d]
        means.append(sum(sample) / len(sample))
    means.sort()
    comp = {k: statistics.mean(new[s][k] - base[s][k] for s in scenes) for k in COMPONENTS}
    return dict(n=len(scenes), delta=statistics.mean(d), lo=means[int(0.025 * boot)], hi=means[int(0.975 * boot)],
                counted=sum(new[s]["counted"] for s in scenes) - sum(base[s]["counted"] for s in scenes),
                up=sum(1 for x in d if x > 1e-9), down=sum(1 for x in d if x < -1e-9), **comp)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base")
    ap.add_argument("new", nargs="*")
    ap.add_argument("--mix", default="", help="suite weights for a platform mix, e.g. core-a=9,core-b=11,core=3 "
                    "(the runs are then <base>/<new> prefixes: <prefix>-<suite>)")
    ap.add_argument("--json", default="")
    args = ap.parse_args()
    out = {}
    if args.mix:
        weights = {k: float(v) for k, v in (kv.split("=") for kv in args.mix.split(","))}
        print("| run | " + " | ".join(f"{s} (w {w:g})" for s, w in weights.items()) + " | platform mix |")
        print("|---|" + "---:|" * (len(weights) + 1))
        for prefix in [args.base, *args.new]:
            cells, total, wsum = [], 0.0, 0.0
            for suite, w in weights.items():
                run = load_run(f"{prefix}-{suite}")
                s = summarize(run.values())
                if s:
                    cells.append(f"{s['score']:.2f} ({s['counted']}/{s['n']})"); total += w * s["score"]; wsum += w
                else:
                    cells.append("-")
            print(f"| {prefix} | " + " | ".join(cells) + f" | {total / wsum if wsum else float('nan'):.2f} |")
            out[prefix] = total / wsum if wsum else None
    else:
        base = load_run(args.base)
        sb = summarize(base.values())
        print(f"base {args.base}: n {sb['n']} score {sb['score']:.2f} counted {sb['counted']} placed {sb['placed']:.2f} "
              + " ".join(f"{k} {sb[k]:.1f}" for k in COMPONENTS) + f" policy max {sb['policy_max']:.1f}s")
        print("\n| run | n | score | delta [95 % CI] | counted | up / down | fill | cog | stability | placement | soft | placed | policy max |")
        print("|---|---:|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|")
        out[args.base] = sb
        for new in args.new:
            run = load_run(new)
            s = summarize(run.values())
            d = paired_delta(base, run)
            if not s or not d:
                print(f"| {new} | 0 | - | - | - | - | - | - | - | - | - | - | - |")
                continue
            print(f"| {new} | {d['n']} | {s['score']:.2f} | {d['delta']:+.2f} [{d['lo']:+.2f}, {d['hi']:+.2f}] | "
                  f"{s['counted']} ({d['counted']:+d}) | {d['up']} / {d['down']} | "
                  + " | ".join(f"{d[k]:+.1f}" for k in COMPONENTS)
                  + f" | {s['placed'] - sb['placed']:+.2f} | {s['policy_max']:.1f}s |")
            out[new] = dict(summary=s, delta=d)
    if args.json:
        json.dump(out, open(args.json, "w"), indent=1, default=float)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
