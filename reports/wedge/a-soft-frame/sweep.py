"""sweep.py <repo> <armfile> <out.jsonl> <overrides|-> <layout:seed,...> [verbose]: planner-only plans (no dry-run), one line a scene."""
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
verbose = len(sys.argv) > 6
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
    row = dict(ov=ov, scene=f"{layout}:{seed}", items=len(items), thr=len(items) // 2 + 1, planned=len(idx),
               soft=sum(1 for i in idx if by[i].get("is_soft")), prio=sum(1 for i in idx if by[i].get("is_prioritized")),
               maxtop=round(max((e["bottom"] + e["size"][2] for e in agent.plan), default=0), 2),
               cs=getattr(agent, "count_secure_log", None), secs=round(secs, 1), opt=getattr(agent, "optimize_stats", None))
    out.write(json.dumps(row) + "\n"); out.flush()
    cs = row["cs"] or {}
    vs = " | ".join(f"{v.get('side')}: {v.get('planned')} (fp {v.get('frame_planned')}, soft {v.get('soft')}, prio {v.get('priority')}, {v.get('seconds')}s{', SKIP' if v.get('skipped') else ''}{', CUT' if v.get('cut') else ''}{', ERR ' + str(v.get('error')) if v.get('error') else ''})" for v in cs.get("variants", []))
    print(f"{row['scene']:9s} thr {row['thr']:2d} planned {row['planned']:2d} soft {row['soft']:2d} prio {row['prio']:2d} top {row['maxtop']:.2f} {row['secs']:5.1f}s base {cs.get('base')} chosen {cs.get('chosen')} :: {vs}", flush=True)
    if verbose:
        for e in sorted(agent.plan, key=lambda e: e["step"]):
            i = by[e["index"]]
            tag = ("S" if i.get("is_soft") else "H") + ("P" if i.get("is_prioritized") else " ")
            print(f'  {e["step"]:3d} {tag} #{e["index"]:3d} c=({e["center"][0]:+.2f},{e["center"][1]:+.2f}) bot {e["bottom"]:.2f} top {e["bottom"]+e["size"][2]:.2f} size {e["size"][0]:.2f}x{e["size"][1]:.2f}x{e["size"][2]:.2f}')
