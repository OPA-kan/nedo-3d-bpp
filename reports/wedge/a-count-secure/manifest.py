"""manifest.py <repo> <layout> <seed>: the Task A manifest's items by class, sizes and the frame."""
import sys, collections, contextlib, io
sys.path.insert(0, sys.argv[1])
from bench.scenes import make_scene
from bench.episode import load_env_class
scene = make_scene(int(sys.argv[3]), sys.argv[2], "A")
Env = load_env_class()
with contextlib.redirect_stdout(io.StringIO()):
    env = Env(config=scene.sim_config(policy_timeout=8.0), verbose=False, render_mode=None)
    env.reset_settings()
    init = env.get_init_states()
    items = env.get_info_for_optimization()
for c in init["container_list"]:
    print({k: c[k] for k in c if k != "packed_items"})
cap = sum(c["length"] * c["width"] * c["height"] for c in init["container_list"])
vol = lambda i: i["length"] * i["width"] * i["height"]
kinds = collections.Counter((round(i["length"], 2), round(i["width"], 2), round(i["height"], 2), bool(i.get("is_soft")), bool(i.get("is_prioritized"))) for i in items)
for k, n in sorted(kinds.items(), key=lambda kv: kv[0][0] * kv[0][1] * kv[0][2]):
    print(n, k, round(k[0] * k[1] * k[2] * 1000), "L")
thr = len(items) // 2 + 1
s = sorted(items, key=vol)
print("items", len(items), "thr", thr, "manifest/cap %.2f" % (sum(map(vol, items)) / cap),
      "smallest thr+2 share %.2f" % (sum(map(vol, s[:thr + 2])) / cap),
      "soft in frame", sum(1 for i in s[:thr + 2] if i.get("is_soft")), "prio in frame", sum(1 for i in s[:thr + 2] if i.get("is_prioritized")))
