"""suite_stats.py <dir>...: per run directory, the suite's counts (crossings, placed, fill, soft / priority placed and
covered, topples, CoM, end reasons, policy max), and by stratum for dense-a (the manifest's count)."""
import sys, json, glob, collections, re


def load(d):
    out = {}
    for f in glob.glob(d + "/[abc]-*.json"):
        r = json.load(open(f))
        out[r["scene"]] = r
    return out


def stats(rs):
    n = len(rs)
    ms = [r["metrics"] for r in rs]
    thr = [m["total_items"] // 2 + 1 for m in ms]
    ends = collections.Counter(m.get("end_reason") for m in ms)
    return dict(n=n, cross=sum(m["placed_count"] >= t for m, t in zip(ms, thr)),
                cross2=sum(m["placed_count"] >= t + 2 for m, t in zip(ms, thr)),
                placed=sum(m["placed_count"] for m in ms) / n, fill=sum(m["fill_volume"] for m in ms) / n,
                soft=sum(m["soft_count"] for m in ms), soft_cov=sum(m["soft_covered"] for m in ms),
                prio=sum(m["priority_count"] for m in ms), prio_cov=sum(m["priority_covered"] for m in ms),
                topples=sum(m["shake_topples"] for m in ms), com=sum(m["com_z_above_floor_ratio"] for m in ms) / n,
                pmax=max(m["policy_time_max"] for m in ms), opt=max(m.get("optimize_seconds", 0) for m in ms),
                ends=dict(ends))


def fmt(s):
    return (f"n {s['n']:2d} cross {s['cross']:2d} (+2: {s['cross2']:2d}) placed {s['placed']:6.2f} fill {s['fill']:5.1f} "
            f"soft {s['soft']:4d}/{s['soft_cov']:2d} prio {s['prio']:4d}/{s['prio_cov']:2d} topples {s['topples']:3d} "
            f"com {s['com']:.3f} pmax {s['pmax']:.2f} opt {s['opt']:.0f} ends {s['ends']}")


def main(dirs):
  for d in dirs:
    runs = load(d)
    print(d)
    print("  all     ", fmt(stats(list(runs.values()))))
    groups = collections.defaultdict(list)
    for name, r in runs.items():
        m = re.match(r"a-(c1x\d+|c1s|c1|c2p|c2|hard)", name)
        groups[m.group(1) if m else "?"].append(r)
    if len(groups) > 1:
        for g in sorted(groups):
            print(f"  {g:8s}", fmt(stats(groups[g])))


if __name__ == "__main__":
    main(sys.argv[1:])
