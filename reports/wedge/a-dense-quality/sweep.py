"""sweep.py <out.jsonl> <layouts: c1x60,c1x70,c1x80> <seeds: 1-12> <variant>=<extra>...

One plan_dense per scene and variant on the on-edge form; a jsonl line each:
planned, soft, priority, frame planned, the plan's com ratio, the swap's, seconds.
"""
import json
import sys
import time

sys.path.insert(0, pathlib.Path(__file__).resolve().parents[3].as_posix())
from bench.arms import make_arm  # noqa: E402
from bench.scenes import make_scene  # noqa: E402
from rule_alpha import count_secure  # noqa: E402
from tests.test_count_secure import PLANNER  # noqa: E402

BASE = (PLANNER + ",plan_standing_rows=true,plan_soft_own_rows=true,plan_standing_rows_max_height=0.4,"
        "plan_count_secure_soft_cap=1.6")

out = open(sys.argv[1], "a")
layouts = sys.argv[2].split(",")
a, b = sys.argv[3].split("-")
seeds = range(int(a), int(b) + 1)
variants = [v.split("=", 1) for v in sys.argv[4:]]


def com_of(plan, by, H, shift=None):
    ms = mo = 0.0
    for e in plan:
        it = by[int(e["index"])]
        mass = float(it.get("mass", 1.0) or 1.0)
        z = e["center"][2] + (shift(e, it) if shift else 0.0)
        ms += mass
        mo += mass * z / H
    return mo / ms if ms else 0.0


for layout in layouts:
    for seed in seeds:
        scene = make_scene(seed, layout, "A")
        for name, extra in variants:
            agent = make_arm(BASE + extra)(scene)
            containers = scene.rule_alpha_containers()
            agent.get_init_states({"container_list": containers})
            items = [dict(i) for i in scene.items]
            agent._prepare_manifest(items)
            agent._manifest_total = len(items)
            agent.plan_source = "planner"
            thr = len(items) // 2 + 1
            frame = count_secure.count_frame(items, thr + 2)
            by = {int(i["index"]): i for i in items}
            H = float(containers[0]["height"])
            t0 = time.perf_counter()
            cap = count_secure._plan_soft_cap(agent.config)
            with cap:
                order, plan, info = count_secure.plan_dense(agent, items, time.perf_counter() + 120, frame)
            secs = time.perf_counter() - t0
            # the swap: the standing hard layer (standing poses off the floor, under 1.0 m) up by the soft stack
            # over it; the soft boxes on the standing tops (bottom 0.9-1.0 m and above) down by the standing height
            stand = [e for e in plan if not by[e["index"]]["is_soft"] and 0.5 < e["bottom"] < 0.6
                     and e["size"][2] > min(e["size"]) + 1e-9]
            soft_top = [e for e in plan if by[e["index"]]["is_soft"] and e["bottom"] > 0.9]
            h_stand = max((e["size"][2] for e in stand), default=0.0)
            h_soft = max((e["bottom"] + e["size"][2] for e in soft_top), default=0.0) - (0.54 + h_stand) if soft_top else 0.0

            def shift(e, it, stand=stand, soft_top=soft_top, h_stand=h_stand, h_soft=h_soft):
                if e in stand:
                    return h_soft
                if e in soft_top:
                    return -h_stand
                return 0.0

            rec = dict(layout=layout, seed=seed, variant=name, threshold=thr, planned=len(plan),
                       soft=sum(1 for e in plan if by[e["index"]]["is_soft"]),
                       priority=sum(1 for e in plan if by[e["index"]]["is_prioritized"]),
                       priority_hard=sum(1 for e in plan if by[e["index"]]["is_prioritized"] and not by[e["index"]]["is_soft"]),
                       soft_total=sum(1 for i in items if i["is_soft"]),
                       priority_total=sum(1 for i in items if i["is_prioritized"]),
                       frame_planned=info.get("frame_planned"), layers={k: info.get(k) for k in ("flat", "ledge", "standing", "soft")},
                       strip=info.get("priority_strip"), com=round(com_of(plan, by, H), 4),
                       com_swap=round(com_of(plan, by, H, shift), 4) if stand and soft_top else None,
                       volume=round(sum(by[e["index"]]["length"] * by[e["index"]]["width"] * by[e["index"]]["height"] for e in plan), 3),
                       seconds=round(secs, 1))
            out.write(json.dumps(rec) + "\n")
            out.flush()
            print(layout, seed, name, rec["planned"], rec["soft"], rec["priority"], rec["com"], rec["seconds"], flush=True)
