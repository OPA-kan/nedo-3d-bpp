"""frame_dbg.py <repo> <armfile> <layout> <seed> <side> [overrides]: one count-secured plan, item by item."""
import sys, time, json, contextlib, io, dataclasses
repo = sys.argv[1]
sys.path.insert(0, repo)
from bench.arms import make_arm
from bench.scenes import make_scene
from bench.episode import load_env_class
from rule_alpha import count_secure
spec = open(sys.argv[2]).read().strip()
if len(sys.argv) > 6 and sys.argv[6]:
    spec += "," + sys.argv[6]
arm = make_arm(spec)
Env = load_env_class()
scene = make_scene(int(sys.argv[4]), sys.argv[3], "A")
with contextlib.redirect_stdout(io.StringIO()):
    env = Env(config=scene.sim_config(policy_timeout=8.0), verbose=False, render_mode=None)
    env.reset_settings()
    agent = arm(scene)
    agent.get_init_states(env.get_init_states())
    items = env.get_info_for_optimization()
    agent.config = dataclasses.replace(agent.config, offline_budget_seconds=0.01, offline_dry_run=False)
    agent.optimize(items)
agent.plan_source = "planner"
by = {int(i["index"]): i for i in items}
thr = len(items) // 2 + 1
frame = count_secure.count_frame(items, thr + 2)
t0 = time.time()
logs = []
order, plan, info = count_secure.plan_frame(agent, items, time.perf_counter() + 60, frame, sys.argv[5], log=lambda s: logs.append(s))
print(json.dumps(info), "secs %.1f" % (time.time() - t0))
fs = set(frame)
for e in sorted(plan, key=lambda e: e["step"]):
    i = by[e["index"]]
    tag = ("S" if i.get("is_soft") else "H") + ("P" if i.get("is_prioritized") else " ") + ("F" if e["index"] in fs else " ")
    print(f'{e["step"]:3d} {tag} #{e["index"]:3d} c=({e["center"][0]:+.2f},{e["center"][1]:+.2f}) bot {e["bottom"]:.2f} size {e["size"][0]:.2f}x{e["size"][1]:.2f}x{e["size"][2]:.2f}')
missing = [i for i in frame if i not in {e["index"] for e in plan}]
print("frame missing:", [(i, "S" if by[i].get("is_soft") else "H", round(by[i]["length"],2), round(by[i]["width"],2), round(by[i]["height"],2)) for i in missing])
if "--log" in sys.argv:
    for s in logs:
        if "[plan] container" in s or "count" in s:
            print(s)
