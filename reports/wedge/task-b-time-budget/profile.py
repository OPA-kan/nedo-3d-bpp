"""profile.py <dir> [<dir> ...]: the B time profile of bench records.

Per run directory: policy_seconds by archetype (the stage that placed), by
board size (items placed before the call), the calls near / over the
budget, the declines' last calls, the settle endings, the shadow and rescue
stats.  The budget is read from the record's arm config."""
import collections
import glob
import json
import os
import statistics
import sys

RESCUE = {"physics-resort", "count-mode", "grid-rescue", "grid-rescue-cover"}


def q(xs, p):
    if not xs:
        return float("nan")
    xs = sorted(xs)
    i = min(len(xs) - 1, max(0, int(round(p * (len(xs) - 1)))))
    return xs[i]


def load(d):
    out = []
    for f in sorted(glob.glob(os.path.join(d, "b-*.json"))):
        out.append(json.load(open(f)))
    return out


def stratum(r):
    return (r.get("scene_spec") or {}).get("stratum", "all")


def row(label, xs, budget):
    if not xs:
        return f"| {label} | 0 | | | | | | |"
    return (f"| {label} | {len(xs)} | {statistics.median(xs):.2f} | {q(xs, 0.9):.2f} | {q(xs, 0.99):.2f} | {max(xs):.2f} | "
            f"{sum(1 for x in xs if x > 0.8 * budget)} | {sum(1 for x in xs if x > budget)} |")


def main(dirs):
    for d in dirs:
        recs = load(d)
        name = os.path.basename(d.rstrip("/"))
        budget = float(recs[0]["arm"]["config"]["policy_budget_seconds"])
        extra = float(recs[0]["arm"]["config"].get("physics_resort_extra_seconds", 2.5))
        cextra = float(recs[0]["arm"]["config"].get("count_mode_extra_seconds_pool", 3.0))
        print(f"\n## {name}: {len(recs)} episodes, budget {budget}")
        by_arch = collections.defaultdict(list)
        by_size = collections.defaultdict(list)
        near = collections.Counter()
        over = collections.Counter()
        all_calls = []
        for r in recs:
            for s in r["steps"]:
                t = s.get("policy_seconds")
                if t is None:
                    continue
                a = s.get("archetype") or ("DECLINE" if s.get("event") == "declined" else str(s.get("event")))
                by_arch[a].append(t)
                n = int(s["step"])
                b = "0-9" if n < 10 else "10-19" if n < 20 else "20-29" if n < 30 else "30-39" if n < 40 else "40-49" if n < 50 else "50-79" if n < 80 else "80+"
                by_size[b].append(t)
                all_calls.append((t, r["scene"], n, a))
                if 0.8 * budget < t <= budget + 0.5:
                    near[a] += 1
                if t > budget:
                    over[a] += 1
        print(f"\ncalls {len(all_calls)}; over budget {sum(1 for c in all_calls if c[0] > budget)}; over 6.7 s {sum(1 for c in all_calls if c[0] > 6.7)}; "
              f"over 8.0 s {sum(1 for c in all_calls if c[0] > 8.0)}; over 10 s {sum(1 for c in all_calls if c[0] > 10.0)}")
        print("\n| archetype | n | median | p90 | p99 | max | >0.8 budget | >budget |\n|---|---|---|---|---|---|---|---|")
        for a, xs in sorted(by_arch.items(), key=lambda kv: -len(kv[1])):
            print(row(a, xs, budget))
        print("\n| items placed | n | median | p90 | p99 | max | >0.8 budget | >budget |\n|---|---|---|---|---|---|---|---|")
        for b in ("0-9", "10-19", "20-29", "30-39", "40-49", "50-79", "80+"):
            print(row(b, by_size.get(b, []), budget))
        print(f"\nnear budget ({0.8 * budget:.1f}-{budget + 0.5:.1f} s) by stage: {dict(near.most_common())}")
        print(f"over budget by stage: {dict(over.most_common())}")
        # placement calls over budget excluding the stack option
        nonstack = [c for c in all_calls if c[0] > budget and c[3] not in ("stack-rl", "DECLINE")]
        print(f"placing calls over budget, not stack-rl: {len(nonstack)}; by stage {dict(collections.Counter(c[3] for c in nonstack))}")
        print("slowest 8 calls: " + ", ".join(f"{s} st{n} {a} {t:.1f}" for t, s, n, a in sorted(all_calls, reverse=True)[:8]))
        print("slowest 8 non-stack-rl calls: " + ", ".join(f"{s} st{n} {a} {t:.1f}" for t, s, n, a in sorted([c for c in all_calls if c[3] != 'stack-rl'], reverse=True)[:8]))

        # the declines' last calls
        dec = []
        for r in recs:
            m = r["metrics"]
            last = r["steps"][-1]
            thr = m["total_items"] // 2 + 1
            under = m["placed_count"] < 41 * len(m.get("per_container_count", {}) or {0: 0})  # rough
            dec.append(dict(scene=r["scene"], stratum=stratum(r), end=m["end_reason"], t=last.get("policy_seconds", 0.0),
                            placed=m["placed_count"], total=m["total_items"], margin=m["placed_count"] - thr,
                            sh=m.get("shadow", {}), ph=m.get("phase", {}), last=last))
        declines = [x for x in dec if x["end"] == "declined"]
        ts = [x["t"] for x in declines]
        t_res = budget + extra - 0.05
        t_cnt = budget + cextra - 0.05
        bands = collections.Counter()
        for x in declines:
            t = x["t"]
            if t < budget - 0.3:
                bands[f"a <{budget - 0.3:.1f} (stages ran out of poses)"] += 1
            elif t < t_res - 0.3:
                bands[f"b {budget - 0.3:.1f}-{t_res - 0.3:.2f}"] += 1
            elif t < t_cnt - 0.3:
                bands[f"c {t_res - 0.3:.2f}-{t_cnt - 0.3:.2f} (resort deadline, over count)"] += 1
            else:
                bands[f"d >={t_cnt - 0.3:.2f} (count deadline)"] += 1
        print(f"\ndeclines {len(declines)}: last call median {statistics.median(ts):.2f}, p10 {q(ts, 0.1):.2f}, p90 {q(ts, 0.9):.2f}, max {max(ts):.2f}")
        for k in sorted(bands):
            print(f"  {k}: {bands[k]}")
        # by stratum and margin
        strata = collections.defaultdict(list)
        for x in declines:
            strata[x["stratum"]].append(x)
        for st, xs in strata.items():
            fast = sum(1 for x in xs if x["t"] < budget - 0.3)
            print(f"  stratum {st}: {len(xs)} declines, fast {fast}, at a rescue deadline {sum(1 for x in xs if x['t'] >= t_res - 0.3)}; "
                  f"near misses (margin -3..-1) {sum(1 for x in xs if -3 <= x['margin'] < 0)} of which at a deadline "
                  f"{sum(1 for x in xs if -3 <= x['margin'] < 0 and x['t'] >= t_res - 0.3)}")
        nm = sorted([x for x in declines if -3 <= x["margin"] < 0], key=lambda x: x["margin"], reverse=True)
        print("  near misses: " + ", ".join(f"{x['scene']}({x['stratum']},{x['margin']:+d},{x['t']:.1f}s)" for x in nm))
        # settle endings
        settle = [x for x in dec if x["end"] != "declined"]
        for x in settle:
            last = x["last"]
            print(f"  ending {x['end']}: {x['scene']} st{last.get('step')} {last.get('archetype')} {x['t']:.2f}s shadow {'yes' if 'shadow' in last else 'NO'} "
                  f"placed {x['placed']}/{x['total']} margin {x['margin']:+d}")
        # shadow / rescue totals
        tot = collections.Counter()
        for x in dec:
            for k, v in x["sh"].items():
                if isinstance(v, (int, float)):
                    tot[k] += v
        print("  shadow totals: " + ", ".join(f"{k} {round(v, 1)}" for k, v in sorted(tot.items())))
        # rescue placements: how long their calls took, and how many came late
        resc = [(c[0], c[1], c[2], c[3]) for c in all_calls if c[3] in RESCUE]
        late = [c for c in resc if c[0] > budget]
        print(f"  rescue placements {len(resc)}: median {statistics.median([c[0] for c in resc]):.2f} s, over budget {len(late)}, "
              f"over {t_res - 0.5:.2f} s {sum(1 for c in resc if c[0] > t_res - 0.5)}; by stage over budget {dict(collections.Counter(c[3] for c in late))}")
        # skipped shadow checks: placements with no shadow digest by stage, and their call times
        noshadow = collections.Counter()
        for r in recs:
            for s in r["steps"]:
                if s.get("event") == "step" and "shadow" not in s:
                    noshadow[s.get("archetype")] += 1
        print(f"  placements without a shadow digest: {sum(noshadow.values())} {dict(noshadow.most_common())}")


if __name__ == "__main__":
    main(sys.argv[1:])
