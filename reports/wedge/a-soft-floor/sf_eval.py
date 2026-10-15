"""Analytic: base plan vs soft-floor plan counts over many scenes in parallel.
usage: sf_eval.py ARMFILE EXTRA SCENES(comma list or 'dense12'|'dense24')"""
import contextlib, io, pathlib, re, sys, time
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, str(pathlib.Path('.').resolve()))

SPEC = open(sys.argv[1]).read().strip() + sys.argv[2]


def one(s):
    from bench.arms import make_arm
    from bench.scenes import make_scene
    from rule_alpha.planner import plan_packing
    task, layout, seed = s.split(':')
    scene = make_scene(int(seed), layout, task)
    agent = make_arm(SPEC)(scene)
    agent.get_init_states({"container_list": scene.rule_alpha_containers()})
    items = scene.items
    agent._prepare_manifest(items)
    agent._manifest_total = len(items)
    agent._manifest = {int(i["index"]): i for i in items}
    agent.plan_source = "planner"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        order, plan = plan_packing(agent, items, time.perf_counter() + 90)
    m = re.search(r"soft floor: (\d+) planned \((\d+) on the soft floor, (\d+) over it\) against (\d+)", buf.getvalue())
    by = {int(i["index"]): i for i in items}
    soft = sum(1 for e in plan if by[int(e["index"])].get("is_soft"))
    return s, len(items) // 2 + 1, len(plan), soft, (m.groups() if m else None)


if __name__ == "__main__":
    arg = sys.argv[3]
    if arg == 'dense12':
        scenes = [f"A:c1x{n}:{s}" for n in (50, 60) for s in range(1, 7)]
    elif arg == 'dense24':
        scenes = [f"A:c1x{n}:{s}" for n in (50, 60) for s in range(1, 13)]
    elif arg == 'dense48':
        scenes = [f"A:c1x{n}:{s}" for n in (50, 60, 70, 80) for s in range(1, 13)]
    else:
        scenes = arg.split(',')
    tot_b = tot_s = 0
    with ProcessPoolExecutor(4) as ex:
        for s, thr, n, soft, g in ex.map(one, scenes):
            base = int(g[3]) if g else n
            sf = int(g[0]) if g else None
            tot_b += base; tot_s += max(base, sf or 0)
            print(f"{s:14s} thr {thr} base {base} sf {sf} (floor {g[1] if g else '-'}, over {g[2] if g else '-'}) chosen {n} soft {soft}", flush=True)
    print("total base", tot_b, "best-of", tot_s)
