"""replay_dbg.py <repo> <armfile> <overrides> <layout> <seed> <record.json> <upto_step>: rebuild the settled board from a
physics record's steps up to a step, re-plan the scene, and say why the planned poses of the items not yet
placed fail the replay's validation there."""
import sys, json, contextlib, io, dataclasses
repo = sys.argv[1]; sys.path.insert(0, repo)
from bench.arms import make_arm
from bench.scenes import make_scene
from bench.episode import load_env_class
from rule_alpha import layer1
from rule_alpha.geometry import AABB
from rule_alpha.planner import _drop_height
spec = open(sys.argv[2]).read().strip() + "," + sys.argv[3]
arm = make_arm(spec); Env = load_env_class()
scene = make_scene(int(sys.argv[5]), sys.argv[4], "A")
with contextlib.redirect_stdout(io.StringIO()):
    env = Env(config=scene.sim_config(policy_timeout=8.0), verbose=False, render_mode=None)
    env.reset_settings(); agent = arm(scene); agent.get_init_states(env.get_init_states())
    items = env.get_info_for_optimization()
    agent.config = dataclasses.replace(agent.config, offline_dry_run=False)
    agent.optimize(items)
config = agent.config
by = {int(i["index"]): i for i in items}
plan = {int(e["index"]): e for e in agent.plan}
rec = json.load(open(sys.argv[6])); upto = int(sys.argv[7])
containers = [dict(c, packed_items=[]) for c in scene.rule_alpha_containers()]
placed = []
for s in rec["steps"]:
    if s["event"] != "step" or s["step"] >= upto:
        continue
    i = by[int(s["item_index"])]
    containers[int(s["container_idx"])]["packed_items"].append(
        dict(index=int(s["item_index"]), position=list(s["pos_local"]), dims=list(s["size"]),
             is_soft=bool(i.get("is_soft")), is_prioritized=bool(i.get("is_prioritized")),
             length=i["length"], width=i["width"], height=i["height"], mass=i.get("mass", 1.0)))
    placed.append(int(s["item_index"]))
print("board rebuilt with", len(placed), "items:", placed)
print("packed item keys the board expects:", list(containers[0]["packed_items"][0].keys()))
board = layer1.Board(containers, config)
clearance = min(config.settled_clearance, float(getattr(config, "plan_replay_clearance", 0.02)))
replay_config = dataclasses.replace(config, settled_clearance=clearance, transport_clearance=config.settled_clearance)
nudge = float(getattr(config, "plan_replay_nudge", 0.02))
shifts = sorted({0.0, nudge / 2.0, -nudge / 2.0, nudge, -nudge}, key=abs)
drop = float(getattr(config, "plan_replay_drop", 0.0))
for idx, e in sorted(plan.items(), key=lambda kv: kv[1]["step"]):
    if idx in placed:
        continue
    model = board.model(e["container_idx"]); container = board.container(e["container_idx"])
    size = tuple(e["size"]); pz = float(e["center"][2])
    rest = _drop_height(container, model, e["center"][0], e["center"][1], size[0], size[1], size[2]) + size[2] / 2
    heights = [pz] + ([rest] if rest < pz - 1e-4 and pz - rest <= drop else [])
    whys = {}
    ok_any = None
    for dy in shifts:
        for dx in shifts:
            for z in heights:
                box = AABB((e["center"][0] + dx, e["center"][1] + dy, z), size, "plan")
                ok, why = layer1.validate(box, model, container, replay_config)
                if ok:
                    ok_any = (dx, dy, z)
                    break
                whys[why] = whys.get(why, 0) + 1
            if ok_any:
                break
        if ok_any:
            break
    tag = ("S" if by[idx].get("is_soft") else "H") + ("P" if by[idx].get("is_prioritized") else " ")
    print(f"step {e['step']:3d} {tag} #{idx:3d} planned c=({e['center'][0]:+.2f},{e['center'][1]:+.2f},{pz:.3f}) rest z {rest:.3f} size {size[0]:.2f}x{size[1]:.2f}x{size[2]:.2f}: "
          + (f"OK at shift {ok_any}" if ok_any else f"FAILS {whys}"))
    if e["step"] > upto + 8:
        break
