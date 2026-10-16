"""softl_vetoes.py <dir> ...: steps whose shadow verdict on the chosen pose
was not ok, with the item's attribute and what it rests on, and whether the
official simulator then accepted the placed pose."""
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


def support_of(placed, ci, lo, hi, surface):
    if surface in ("floor", "shelf"):
        return {surface}
    kinds = set()
    for (pc, plo, phi, ps, pp) in placed:
        if pc != ci or abs(phi[2] - lo[2]) > 0.03:
            continue
        if min(hi[0], phi[0]) - max(lo[0], plo[0]) > 0.01 and min(hi[1], phi[1]) - max(lo[1], plo[1]) > 0.01:
            kinds.add("soft" if ps else "prio" if pp else "hard")
    return kinds or {"?"}


for path in sys.argv[1:]:
    tally = collections.Counter()
    rows = []
    for f in sorted(glob.glob(os.path.join(path, "[abc]-*.json"))):
        d = json.load(open(f))
        items = scene_items(d["scene_spec"])
        placed = []
        for s in d["steps"]:
            if s.get("event") != "step" or s.get("pos_local") is None:
                continue
            it = items.get(int(s["item_index"]))
            soft = bool(it["is_soft"]); prio = bool(it["is_prioritized"])
            c = s["pos_local"]; z = s["size"]
            lo = [c[k] - z[k] / 2 for k in range(3)]; hi = [c[k] + z[k] / 2 for k in range(3)]
            ci = s.get("container_idx", 0)
            sh = s.get("shadow") or {}
            ch = sh.get("chosen") or {}
            if ch and not ch.get("ok", True):
                sup = support_of(placed, ci, lo, hi, s.get("surface"))
                why = ("transport" if not ch.get("transport_ok", True) else "settle" if not ch.get("settle_ok", True)
                       else "shade" if ch.get("shade", 0) > 0.15 and ch.get("drift_xy", 0) <= 0.02 and ch.get("angle_deg", 0) <= 5 else "wobble")
                key = ("soft" if soft else "prio" if prio else "hard", "+".join(sorted(sup)) if sh.get("outcome") == "kept-after-veto" else "(replaced)", sh.get("outcome"), why)
                tally[key] += 1
                if soft and "soft" in sup and sh.get("outcome") == "kept-after-veto":
                    rows.append((d["scene"], s["step"], s.get("archetype"), round(ch.get("drift_xy", 0), 3), round(ch.get("angle_deg", 0), 1), s.get("is_placed_safe"), c, z))
            placed.append((ci, lo, hi, soft, prio))
    print("==", path)
    for k, v in sorted(tally.items(), key=lambda kv: -kv[1]):
        print("  ", v, k)
    for r in rows[:30]:
        print("   soft-on-soft kept after veto:", r)
