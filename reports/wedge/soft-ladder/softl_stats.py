"""softl_stats.py <dir> [<dir> ...]: per record directory, soft placements by
support (floor / shelf / soft top / hard top / priority top / mixed) and by
archetype; soft-on-soft by archetype; per-episode soft placed and covered."""
import collections
import glob
import json
import os
import sys

sys.path.insert(0, os.environ.get("REPO", "/home/user/nedo-3d-bpp"))
from bench.scenes import make_scene  # noqa: E402


def scene_items(sp):
    per = sp["item_count"] // (2 if sp["layout"].startswith("c2") else 1)
    sc = make_scene(sp["seed"], sp["layout"], sp["task"], items_per_container=per)
    return {int(it.get("index", i)): it for i, it in enumerate(sc.items)}


def analyse(path):
    by_support = collections.Counter()
    sos_arch = collections.Counter()
    floor_arch = collections.Counter()
    per_ep = []
    for f in sorted(glob.glob(os.path.join(path, "[abc]-*.json"))):
        d = json.load(open(f))
        sp = d["scene_spec"]
        items = scene_items(sp)
        placed = []  # (container, box min, box max, soft, prio)
        m = d["metrics"]
        for s in d["steps"]:
            if s.get("event") != "step" or s.get("pos_local") is None or not s.get("is_placed_safe", True):
                continue
            it = items.get(int(s["item_index"]))
            soft = bool(it["is_soft"]) if it else False
            prio = bool(it["is_prioritized"]) if it else False
            c = s["pos_local"]; z = s["size"]
            lo = [c[k] - z[k] / 2 for k in range(3)]; hi = [c[k] + z[k] / 2 for k in range(3)]
            ci = s.get("container_idx", 0)
            arch = s.get("archetype")
            if soft:
                kinds = set()
                if s.get("surface") == "floor":
                    kinds.add("floor")
                elif s.get("surface") == "shelf":
                    kinds.add("shelf")
                else:
                    for (pc, plo, phi, ps, pp) in placed:
                        if pc != ci:
                            continue
                        if abs(phi[2] - lo[2]) > 0.03:
                            continue
                        if min(hi[0], phi[0]) - max(lo[0], plo[0]) > 0.01 and min(hi[1], phi[1]) - max(lo[1], plo[1]) > 0.01:
                            kinds.add("soft" if ps else "prio" if pp else "hard")
                    if not kinds:
                        kinds.add("floor" if lo[2] < 0.2 else "shelf/other")
                key = "+".join(sorted(kinds))
                by_support[key] += 1
                if "soft" in kinds:
                    sos_arch[arch] += 1
                if kinds == {"floor"}:
                    floor_arch[arch] += 1
            placed.append((ci, lo, hi, soft, prio))
        per_ep.append((d["scene"], m["soft_count"], m.get("soft_covered", 0), sp.get("soft_total", 0),
                       m["priority_count"], m.get("priority_covered", 0), m["placed_count"], m["total_items"]))
    return by_support, sos_arch, floor_arch, per_ep


if __name__ == "__main__":
    for p in sys.argv[1:]:
        bs, sa, fa, pe = analyse(p)
        n = len(pe)
        print(f"== {p} n {n}")
        print("  soft by support:", dict(bs.most_common()))
        print("  soft-on-soft by archetype:", dict(sa.most_common()))
        print("  soft floor by archetype:", dict(fa.most_common()))
        if n:
            sc = sum(r[1] for r in pe) / n; cov = sum(r[2] for r in pe) / n
            pr = sum(r[4] for r in pe) / n; pcov = sum(r[5] for r in pe) / n
            print(f"  per episode: soft placed {sc:.2f}, soft covered {cov:.2f}, credited {sc - cov:.2f}; "
                  f"prio placed {pr:.2f} covered {pcov:.2f}; placed {sum(r[6] for r in pe) / n:.2f}; "
                  f"crossings {sum(1 for r in pe if r[6] >= r[7] // 2 + 1)}")
