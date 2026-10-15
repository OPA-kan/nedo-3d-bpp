"""frame_share.py <repo>: the dense-a manifests' count frames by volume (the threshold's smallest items over the
container's volume), soft share of the frame, and the manifest over the container."""
import sys, json, statistics
sys.path.insert(0, sys.argv[1])
from bench.scenes import make_scene

for n in (50, 60, 70, 80):
    rows = []
    for seed in range(1, 13):
        sc = make_scene(seed, f"c1x{n}", "A")
        cap = sum(c["length"] * c["width"] * c["height"] for c in sc.rule_alpha_containers())
        vol = lambda i: i["length"] * i["width"] * i["height"]
        items = sorted(sc.items, key=vol)
        thr = len(items) // 2 + 1
        rows.append((sum(map(vol, items)) / cap, sum(map(vol, items[:thr])) / cap,
                     sum(1 for i in items[:thr] if i["is_soft"]) / thr))
    print(json.dumps({"items": n, "manifest_over_container": round(statistics.mean(r[0] for r in rows), 3),
                      "threshold_smallest_over_container": round(statistics.mean(r[1] for r in rows), 3),
                      "soft_share_of_frame": round(statistics.mean(r[2] for r in rows), 3)}))
