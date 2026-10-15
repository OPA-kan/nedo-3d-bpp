"""sweep.py <repo> <armfile> <out.jsonl> <overrides|-> <layout:seed,...>: planner-only plans (no dry-run), one line a scene."""
import sys, time, json, contextlib, io, dataclasses
repo = sys.argv[1]
sys.path.insert(0, repo)
from bench.arms import make_arm
from bench.scenes import make_scene
from bench.episode import load_env_class
spec = open(sys.argv[2]).read().strip()
ov = sys.argv[4]
if ov != "-":
    spec += "," + ov
arm = make_arm(spec)
Env = load_env_class()
out = open(sys.argv[3], "a")
for tok in sys.argv[5].split(","):
    layout, seed = tok.split(":")
    scene = make_scene(int(seed), layout, "A")
    with contextlib.redirect_stdout(io.StringIO()):
        env = Env(config=scene.sim_config(policy_timeout=8.0), verbose=False, render_mode=None)
        env.reset_settings()
        agent = arm(scene)
        agent.get_init_states(env.get_init_states())
        items = env.get_info_for_optimization()
        agent.config = dataclasses.replace(agent.config, offline_dry_run=False)
        t0 = time.time()
        agent.optimize(items)
        secs = time.time() - t0
    by = {int(i["index"]): i for i in items}
    idx = [int(e["index"]) for e in agent.plan]
    cap = sum(c["length"] * c["width"] * c["height"] for c in agent.board.containers)
    row = dict(ov=ov, scene=f"{layout}:{seed}", items=len(items), thr=len(items) // 2 + 1, planned=len(idx),
               soft=sum(1 for i in idx if by[i].get("is_soft")), prio=sum(1 for i in idx if by[i].get("is_prioritized")),
               maxtop=round(max((e["bottom"] + e["size"][2] for e in agent.plan), default=0), 2),
               cs=getattr(agent, "count_secure_log", None), secs=round(secs, 1))
    out.write(json.dumps(row) + "\n"); out.flush()
    print(json.dumps(row), flush=True)
