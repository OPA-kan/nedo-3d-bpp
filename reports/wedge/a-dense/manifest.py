"""manifest.py <repo> <layout:seed,...>: the class mix of each scene and of its count frame."""
import sys, collections
sys.path.insert(0, sys.argv[1])
from bench.scenes import make_scene
from rule_alpha.count_secure import count_frame
for tok in sys.argv[2].split(","):
    layout, seed = tok.split(":")
    scene = make_scene(int(seed), layout, "A")
    items = [dict(index=k, length=it["length"], width=it["width"], height=it["height"],
                  is_soft=bool(it.get("is_soft")), is_prioritized=bool(it.get("is_prioritized")))
             for k, it in enumerate(scene.items)]

    def cls(i):
        d = tuple(sorted((i["length"], i["width"], i["height"]), reverse=True))
        return f"{d[0]:.2f}x{d[1]:.2f}x{d[2]:.2f}{'S' if i['is_soft'] else 'H'}{'P' if i['is_prioritized'] else ''}"
    n = len(items)
    thr = n // 2 + 1
    frame = set(count_frame(items, thr + 2))
    allc = collections.Counter(cls(i) for i in items)
    fc = collections.Counter(cls(i) for i in items if i["index"] in frame)
    print(f"{layout}:{seed} n={n} thr={thr} frame={len(frame)}")
    for k in sorted(allc, key=lambda k: -allc[k]):
        print(f"   {k:18s} all {allc[k]:2d}  frame {fc.get(k, 0):2d}")
