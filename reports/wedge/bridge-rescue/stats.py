"""stats.py <dir> [<dir> ...]: per bench record directory, the rescue
placements by archetype, the ladder / stack-option placements, the policy
time (max, mean over calls, placing calls over the platform-risk line:
5.3 s on C, 6.7 s on B = the 8 s / 10 s limits at a 1.5x machine
factor), and the episode metrics the judge does not print (soft
uncovered, cog, fill)."""
import collections
import glob
import json
import os
import sys

RESCUE = ("physics-resort", "count-mode", "grid-rescue", "grid-rescue-cover")
NOT_LADDER = set(RESCUE) | {"stack-rl", "fallback", "pocket-soft", "pocket-hard", None}

for d in sys.argv[1:]:
    files = sorted(glob.glob(os.path.join(d, "[bc]-*.json")))
    if not files:
        print(d, "no records")
        continue
    arch = collections.Counter()
    times, placing_over, decl_over, n_calls = [], 0, 0, 0
    soft_unc = fill = com = placed = 0.0
    task = None
    for f in files:
        r = json.load(open(f))
        task = r["scene_spec"].get("task")
        line = 5.3 if task == "C" else 6.7
        m = r["metrics"]
        placed += m["placed_count"]
        soft_unc += m["soft_count"] - m.get("soft_covered", 0)
        fill += m["fill_volume"]
        com += m["com_z_above_floor_ratio"]
        for s in r["steps"]:
            t = float(s.get("policy_seconds") or 0.0)
            times.append(t)
            n_calls += 1
            if s.get("event") == "step":
                arch[s.get("archetype")] += 1
                placing_over += t > line
            else:
                decl_over += t > line
    n = len(files)
    rescue = {a: arch[a] for a in RESCUE}
    ladder = sum(v for a, v in arch.items() if a not in NOT_LADDER)
    print(f"{os.path.basename(d.rstrip('/')):22s} n {n:3d} placed {placed / n:6.2f} soft-uncov {soft_unc / n:5.2f} fill {fill / n:.4f} "
          f"cog {com / n:.4f} | rescue {sum(rescue.values()):4d} {rescue} | ladder {ladder} stack {arch['stack-rl']} "
          f"fallback {arch['fallback']} | time max {max(times):.2f} mean {sum(times) / len(times):.2f} "
          f"placing>{5.3 if task == 'C' else 6.7} {placing_over} declining> {decl_over}")
