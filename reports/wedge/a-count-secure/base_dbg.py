"""base_dbg.py <repo> <armfile> <layout> <seed> [overrides]: the planner's plan (no dry-run), item by item."""
import sys, time, json, contextlib, io, dataclasses
repo = sys.argv[1]
sys.path.insert(0, repo)
from bench.arms import make_arm
from bench.scenes import make_scene
from bench.episode import load_env_class
spec = open(sys.argv[2]).read().strip()
if len(sys.argv) > 5 and sys.argv[5]:
    spec += "," + sys.argv[5]
arm = make_arm(spec)
Env = load_env_class()
scene = make_scene(int(sys.argv[4]), sys.argv[3], "A")
with contextlib.redirect_stdout(io.StringIO()):
    env = Env(config=scene.sim_config(policy_timeout=8.0), verbose=False, render_mode=None)
    env.reset_settings()
    agent = arm(scene)
    agent.get_init_states(env.get_init_states())
    items = env.get_info_for_optimization()
    agent.config = dataclasses.replace(agent.config, offline_dry_run=False)
    agent.optimize(items)
by = {int(i["index"]): i for i in items}
print("planned", len(agent.plan), "src", agent.plan_source, getattr(agent, "count_secure_log", None))
for e in sorted(agent.plan, key=lambda e: e["step"]):
    i = by[e["index"]]
    tag = ("S" if i.get("is_soft") else "H") + ("P" if i.get("is_prioritized") else " ")
    print(f'{e["step"]:3d} {tag} #{e["index"]:3d} c=({e["center"][0]:+.2f},{e["center"][1]:+.2f}) bot {e["bottom"]:.2f} top {e["bottom"]+e["size"][2]:.2f} size {e["size"][0]:.2f}x{e["size"][1]:.2f}x{e["size"][2]:.2f}')
