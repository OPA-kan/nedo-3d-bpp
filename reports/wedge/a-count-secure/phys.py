"""phys.py <repo> <armfile> <override|-> <out.jsonl> <layout:seed,...>: physics episodes (Task A), key metrics a line."""
import sys, json, time
repo = sys.argv[1]
sys.path.insert(0, repo)
from bench.arms import make_arm
from bench.scenes import make_scene
from bench.episode import run_episode
import rule_alpha.planner as planner
spec = open(sys.argv[2]).read().strip()
ov = sys.argv[3]
if ov != "-":
    spec += "," + ov
arm = make_arm(spec)
LOGS = {}
orig = planner.plan_packing
def wrapped(agent, item_list, deadline, log=None):
    out = orig(agent, item_list, deadline, log)
    LOGS["cs"] = getattr(agent, "count_secure_log", None)
    LOGS["plan_n"] = len(out[1])
    return out
planner.plan_packing = wrapped
out = open(sys.argv[4], "a")
for tok in sys.argv[5].split(","):
    layout, seed = tok.split(":")
    LOGS.clear()
    t0 = time.time()
    rec = run_episode(make_scene(int(seed), layout, "A"), arm, policy_budget=8.0, with_shake=True)
    m = rec["metrics"]
    row = dict(ov=ov, scene=f"{layout}:{seed}", total=m["total_items"], thr=m["total_items"] // 2 + 1,
               placed=m["placed_count"], fill=round(m["fill_volume"], 2), soft=m["soft_count"], soft_cov=m["soft_covered"],
               prio=m["priority_count"], prio_cov=m["priority_covered"], topples=m["shake_topples"],
               com=round(m["com_z_above_floor_ratio"], 3), end=m["end_reason"], src=rec.get("plan_source"),
               plan_n=LOGS.get("plan_n"), cs=LOGS.get("cs"), pmax=m["policy_time_max"], secs=round(time.time() - t0))
    out.write(json.dumps(row) + "\n"); out.flush()
