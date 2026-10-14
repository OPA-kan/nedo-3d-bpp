"""platform_adj.py <dir> [<dir> ...]: the platform's reading of B records.

A placing call whose bench time times the machine factor passes the 10 s
limit is answered with a random action on the platform, which fails and
ends the episode there.  Per factor (1.2, 1.5): the episodes cut, the items
lost, the crossings lost; also with the stack option's calls left out (the
measured arm lacks the shipped stack_deadline)."""
import collections
import glob
import json
import os
import sys

LIMIT = 10.0


def main(dirs):
    for d in dirs:
        recs = [json.load(open(f)) for f in sorted(glob.glob(os.path.join(d, "b-*.json")))]
        name = os.path.basename(d.rstrip("/"))
        print(f"\n## {name} ({len(recs)} episodes)")
        for factor in (1.2, 1.5):
            for skip_stack in (False, True):
                cut = 0; lost = 0; xlost = 0; placed = 0; placed_adj = 0; cross = 0; cross_adj = 0
                where = collections.Counter(); scenes = []
                for r in recs:
                    m = r["metrics"]; thr = m["total_items"] // 2 + 1
                    n = m["placed_count"]
                    adj = n
                    for s in r["steps"]:
                        if s.get("event") != "step":
                            continue
                        if skip_stack and s.get("archetype") == "stack-rl":
                            continue
                        if s["policy_seconds"] * factor > LIMIT:
                            adj = int(s["step"])
                            where[s.get("archetype")] += 1
                            scenes.append(f"{r['scene']}@{s['step']}({s.get('archetype')},{s['policy_seconds']:.1f})")
                            break
                    placed += n; placed_adj += adj
                    cross += n >= thr; cross_adj += adj >= thr
                    if adj < n:
                        cut += 1; lost += n - adj; xlost += (n >= thr) and (adj < thr)
                tag = "no stack-rl" if skip_stack else "all calls"
                print(f"factor {factor} ({tag}): episodes cut {cut}, items lost {lost} ({lost / len(recs):.2f} a scene), "
                      f"crossings {cross} -> {cross_adj}, by stage {dict(where)}")
                if scenes and factor == 1.5:
                    print("   " + ", ".join(scenes[:20]))


if __name__ == "__main__":
    main(sys.argv[1:])
