"""rank_sweep.py <out.jsonl> <layouts> <seeds a-b> <name>=<arm file>...: the planner alone (``agent.optimize``, the
30 s budget) per scene and arm; a jsonl line each with the re-plan's record (``count_secure_log``: every variant's
planned / soft / priority / score and the one chosen) and the chosen plan's count, soft, priority, volume and
centre-of-mass ratio.  Prices the arms with ``tab.py``."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from bench.arms import make_arm  # noqa: E402
from bench.scenes import make_scene  # noqa: E402

out = open(sys.argv[1], "a")
layouts = sys.argv[2].split(",")
a, b = sys.argv[3].split("-")
arms = []
for spec in sys.argv[4:]:
    name, path = spec.split("=", 1)
    arms.append((name, open(path).read().strip() + ",offline_budget_seconds=30"))
for layout in layouts:
    for seed in range(int(a), int(b) + 1):
        scene = make_scene(seed, layout, "A")
        items = [dict(i) for i in scene.items]
        by = {int(i["index"]): i for i in items}
        for name, arm in arms:
            agent = make_arm(arm)(scene)
            containers = scene.rule_alpha_containers()
            agent.get_init_states({"container_list": containers})
            t0 = time.perf_counter()
            agent.optimize([dict(i) for i in items])
            secs = time.perf_counter() - t0
            plan = list(agent.plan or [])
            H = float(containers[0]["height"])
            ms = mo = 0.0
            for e in plan:
                it = by[int(e["index"])]
                mass = float(it.get("mass", 1.0) or 1.0)
                ms += mass
                mo += mass * float((e.get("center") or e.get("place_pos"))[2]) / H
            log = agent.count_secure_log or {}
            rec = dict(layout=layout, seed=seed, variant=name, threshold=len(items) // 2 + 1, planned=len(plan),
                       soft=sum(1 for e in plan if by[int(e["index"])]["is_soft"]),
                       priority=sum(1 for e in plan if by[int(e["index"])]["is_prioritized"]),
                       priority_hard=sum(1 for e in plan if by[int(e["index"])]["is_prioritized"]
                                         and not by[int(e["index"])]["is_soft"]),
                       soft_total=sum(1 for i in items if i["is_soft"]),
                       priority_total=sum(1 for i in items if i["is_prioritized"]),
                       com=round(mo / ms, 4) if ms else 0.0,
                       volume=round(sum(by[int(e["index"])]["length"] * by[int(e["index"])]["width"]
                                        * by[int(e["index"])]["height"] for e in plan), 3),
                       chosen=log.get("chosen"), variants=log.get("variants"), seconds=round(secs, 1))
            out.write(json.dumps(rec) + "\n")
            out.flush()
            print(layout, seed, name, rec["planned"], rec["soft"], rec["priority"], rec["chosen"], rec["seconds"],
                  flush=True)
