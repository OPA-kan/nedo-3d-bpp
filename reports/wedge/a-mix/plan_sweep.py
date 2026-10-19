"""plan_sweep.py <out.jsonl> <scenes: LAYOUT:SEED,... or suite:NAME> <name>=<armfile>...: the planner alone
(agent.optimize, the 30 s budget) per scene and arm; a jsonl line each with the re-plan's record, the chosen
plan's count / soft / priority and a digest of its poses (to compare arms plan for plan)."""
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, "/home/user/nedo-3d-bpp/.claude/worktrees/agent-a0a8cf4b6c63d51aa")
from bench.arms import make_arm  # noqa: E402
from bench.scenes import build_suite, make_scene  # noqa: E402

done = set()
try:
    for line in open(sys.argv[1]):
        r = json.loads(line)
        done.add((r["scene"], r["arm"]))
except FileNotFoundError:
    pass
out = open(sys.argv[1], "a")
if sys.argv[2].startswith("suite:"):
    scenes = build_suite(sys.argv[2][6:])
else:
    scenes = [make_scene(int(t.split(":")[1]), t.split(":")[0], "A") for t in sys.argv[2].split(",")]
arms = []
for spec in sys.argv[3:]:
    name, path = spec.split("=", 1)
    arms.append((name, open(path).read().strip() + ",offline_budget_seconds=" + os.environ.get("BUDGET", "30")))
for scene in scenes:
    items = [dict(i) for i in scene.items]
    by = {int(i["index"]): i for i in items}
    for name, arm in arms:
        if (scene.name, name) in done:
            continue
        agent = make_arm(arm)(scene)
        agent.get_init_states({"container_list": scene.rule_alpha_containers()})
        t0 = time.perf_counter()
        order = agent.optimize(items)
        secs = time.perf_counter() - t0
        plan = sorted(agent.plan, key=lambda e: e["step"])
        digest = hashlib.md5(json.dumps([(e["index"], [round(v, 4) for v in e["center"]], [round(v, 4) for v in e["size"]])
                                         for e in plan]).encode()).hexdigest()[:10]
        idx = [int(e["index"]) for e in plan]
        cs = getattr(agent, "count_secure_log", None) or {}
        row = dict(scene=scene.name, arm=name, items=len(items), thr=len(items) // 2 + 1, planned=len(idx),
                   soft=sum(1 for i in idx if by[i].get("is_soft")), prio=sum(1 for i in idx if by[i].get("is_prioritized")),
                   digest=digest, secs=round(secs, 1), chosen=cs.get("chosen"), replanned=cs.get("replanned"),
                   base=cs.get("base"), adaptive=cs.get("adaptive"),
                   variants=[{k: v.get(k) for k in ("side", "planned", "soft", "priority", "seconds", "skipped", "cut", "standing_cap")}
                             for v in cs.get("variants", [])],
                   spec=scene.spec, order=order[:3])
        out.write(json.dumps(row) + "\n")
        out.flush()
        print(f"{scene.name} {name:8s} thr {row['thr']:3d} planned {row['planned']:3d} soft {row['soft']:2d} prio {row['prio']:2d} "
              f"{secs:5.1f}s chosen {cs.get('chosen')} digest {digest}", flush=True)
