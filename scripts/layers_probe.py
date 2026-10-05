"""layers_probe.py [scenes]: the layer packer's plan on A scenes (count, soft, prio, volume, time, levels)."""
import io, json, sys, time, contextlib
sys.path.insert(0, ".")

from bench.scenes import make_scene
from bench.arms import make_arm
from rule_alpha.layers import pack_layers
ARM = open("/home/user/nedo-3d-bpp/reports/bench/v32arm.txt").read().strip()
scenes = sys.argv[1:] or ["a-c1-s0001", "a-c1-s0005", "a-c1s-s0002", "a-c1s-s0006", "a-c2-s0012", "a-c2p-s0006"]
arm = make_arm(ARM)
for sc in scenes:
    r = json.load(open(f"/home/user/nedo-3d-bpp/reports/bench/v34-core-a/{sc}.json")); sp = r["scene_spec"]
    scene = make_scene(sp["seed"], sp["layout"], sp["task"], items_per_container=sp["item_count"] // (2 if sp["layout"].startswith("c2") else 1))
    agent = arm(scene)
    items = [dict(it) for it in scene.items]
    agent.get_init_states({"container_list": scene.rule_alpha_containers()})
    agent._prepare_manifest(items); agent._manifest_total = len(items); agent._manifest = {int(i["index"]): i for i in items}
    if agent.pocket is not None: agent.pocket.set_manifest(items, len(agent.board.models))
    logs = []
    t0 = time.perf_counter()
    order, plan = pack_layers(agent, items, time.perf_counter() + 140, log=logs.append)
    dt = time.perf_counter() - t0
    by = {int(i["index"]): i for i in items}; idx = [int(e["index"]) for e in plan]
    cap = sum(float(c["length"]) * float(c["width"]) * float(c["height"]) for c in agent.board.containers)
    vol = sum(by[i]["length"] * by[i]["width"] * by[i]["height"] for i in idx)
    soft = sum(1 for i in idx if by[i]["is_soft"]); prio = sum(1 for i in idx if by[i]["is_prioritized"])
    ns = sum(1 for i in items if i["is_soft"]); npr = sum(1 for i in items if i["is_prioritized"])
    tops = sorted({round(e["bottom"], 2) for e in plan})
    masses = sum(by[i]["mass"] for i in idx); com = sum(by[i]["mass"] * e["center"][2] for e, i in zip(plan, idx)) / max(masses, 1e-9)
    print(f"{sc}: {len(idx)}/{len(items)} planned (soft {soft}/{ns}, prio {prio}/{npr}), fill {100*vol/cap:.1f}%, levels {tops}, com_z {com:.2f} m, {dt:.0f}s; suite v34 placed {r['metrics']['placed_count']}", flush=True)
    for l in logs[-3:]: print("   ", l)
