"""frame_dbg.py: plan_frame("soft") on c1x60 seed 2 with the test's planner arm, entry by entry."""
import sys, time
sys.path.insert(0, '/home/user/nedo-3d-bpp/.claude/worktrees/agent-a67fbe9a22b0417ad')
from tests.test_count_secure import PLANNER
from bench.arms import make_arm
from bench.scenes import make_scene
from rule_alpha import count_secure
scene = make_scene(2, "c1x60", "A")
agent = make_arm(PLANNER)(scene)
containers = scene.rule_alpha_containers()
agent.get_init_states({"container_list": containers})
items = [dict(i) for i in scene.items]
agent._prepare_manifest(items)
agent._manifest_total = len(items)
agent.plan_source = "planner"
frame = count_secure.count_frame(items, 33)
by = {int(i["index"]): i for i in items}
lines = []
order, plan, info = count_secure.plan_frame(agent, items, time.perf_counter() + 90, frame, "soft", log=lines.append)
print(info, "planned", len(plan))
for e in sorted(plan, key=lambda e: e["step"]):
    i = by[e["index"]]
    tag = ("S" if i.get("is_soft") else "H") + ("P" if i.get("is_prioritized") else " ") + ("F" if e["index"] in set(frame) else " ")
    print(f'{e["step"]:3d} {tag} #{e["index"]:3d} c=({e["center"][0]:+.2f},{e["center"][1]:+.2f}) bot {e["bottom"]:.2f} top {e["bottom"]+e["size"][2]:.2f} size {e["size"][0]:.2f}x{e["size"][1]:.2f}x{e["size"][2]:.2f}')
print("\n".join(l for l in lines if "[typed]" in l or "pass" in l)[:3000])
