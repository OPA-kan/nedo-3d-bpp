"""cf_flags.py <armfile> <out_dir> TASK:LAYOUT:SEED ...

Adapted from reports/wedge/bridge-spots/cf_probe_b.py: the episode runs
with the arm; at every declining call the same observation is asked
again at the arm's budget (4.5 s) under flag variants (the bridge-rescue
flags), and once with 8.0 s for reference.  The decline stands (observe
mode).  The episode-long timing state (_shadow_longest,
_resort_gen_longest) is restored before every variant."""
import dataclasses
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, os.environ.get("BRESC_ROOT", "/home/user/nedo-3d-bpp/.claude/worktrees/agent-aeca172b996317a87"))
from bench.arms import make_arm  # noqa: E402
from bench.episode import run_episode  # noqa: E402
from bench.scenes import make_scene  # noqa: E402

VARIANTS = [
    ("base", {}),
    ("A", {"grid_rescue_min_support": 0.25}),
    ("B1.5", {"low_phase_rescue_seconds": 1.5}),
    ("AB1.5", {"grid_rescue_min_support": 0.25, "low_phase_rescue_seconds": 1.5}),
    ("AB2.0", {"grid_rescue_min_support": 0.25, "low_phase_rescue_seconds": 2.0}),
    ("AB2.5", {"grid_rescue_min_support": 0.25, "low_phase_rescue_seconds": 2.5}),
    ("base8", {"policy_budget_seconds": 8.0}),
]
if os.environ.get("BRESC_VARIANTS"):
    keep = set(os.environ["BRESC_VARIANTS"].split(","))
    VARIANTS = [v for v in VARIANTS if v[0] in keep]


class Wrapped:
    def __init__(self, agent, log):
        self.agent, self.log = agent, log
        self.step = 0

    def __getattr__(self, name):
        return getattr(self.agent, name)

    def policy(self, observation):
        a = self.agent
        t0 = time.perf_counter()
        action = a.policy(observation)
        t_first = time.perf_counter() - t0
        self.step += 1
        if action is not None:
            return action
        base_cfg = a.config
        pool = observation.get("pool_list") or []
        entry = {"step": self.step - 1, "first_seconds": round(t_first, 2), "pool": len(pool),
                 "phase_low": bool(getattr(a, "_phase_low", False)),
                 "packed": sum(len(c.get("packed_items") or []) for c in observation.get("container_list", [])),
                 "retries": []}
        saved = {k: getattr(a, k) for k in ("_shadow_longest", "_resort_gen_longest")}
        trace: list = []
        real_action, real_verdict, real_grid = a._action, a._shadow_verdict, a._grid_rescue
        t_call = [0.0]

        def _action(pool_index, placement):
            trace.append([round(time.perf_counter() - t_call[0], 2), getattr(placement, "reason", None) or placement.archetype, None])
            return real_action(pool_index, placement)

        def _verdict(sim, action, item):
            v = real_verdict(sim, action, item)
            if trace:
                trace[-1][2] = (not a._shadow_hard(v), round(time.perf_counter() - t_call[0], 2))
            return v

        def _grid(*args, **kw):
            trace.append([round(time.perf_counter() - t_call[0], 2), "grid start deadline %.2f need %.2f" % (
                args[2] - t_call[0], max(a._shadow_longest, 0.2)), None])
            r = real_grid(*args, **kw)
            trace.append([round(time.perf_counter() - t_call[0], 2), "grid end", None])
            return r
        a._action, a._shadow_verdict, a._grid_rescue = _action, _verdict, _grid
        for label, over in VARIANTS:
            trace.clear()
            t_call[0] = time.perf_counter()
            for k, v in saved.items():
                setattr(a, k, v)
            a.config = dataclasses.replace(base_cfg, **over)
            before = dict(a.shadow_stats)
            pbefore = dict(a.phase_stats)
            t1 = time.perf_counter()
            try:
                act = a.policy(observation)
            finally:
                a.config = base_cfg
            secs = time.perf_counter() - t1
            d = a.last_decision
            stats = {k: a.shadow_stats.get(k, 0) - before.get(k, 0) for k in a.shadow_stats
                     if isinstance(a.shadow_stats.get(k, 0), (int, float)) and a.shadow_stats.get(k, 0) != before.get(k, 0)}
            stats = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in stats.items()}
            pstats = {k: a.phase_stats.get(k, 0) - pbefore.get(k, 0) for k in ("low_rescue", "low_rescue_skip_stack")}
            box = None
            if act is not None and d is not None and getattr(d, "placement", None) is not None:
                bx = d.placement.box
                box = {"center": [round(float(v), 3) for v in bx.center], "size": [round(float(v), 3) for v in bx.size],
                       "reason": getattr(d.placement, "reason", None)}
            entry["retries"].append({"variant": label, "seconds": round(secs, 2), "placed": act is not None,
                                     "archetype": (d.placement.archetype if (act is not None and d is not None) else None),
                                     "box": box, "stats": stats, "phase": pstats, "trace": [list(t) for t in trace]})
        del a._action, a._shadow_verdict, a._grid_rescue
        for k, v in saved.items():
            setattr(a, k, v)
        self.log.append(entry)
        print(json.dumps(entry), flush=True)
        return None


def main():
    S = "/tmp/claude-0/-home-user-nedo-3d-bpp/c555f0d0-1382-515f-857e-e77257cc9f93/scratchpad/"
    arm = make_arm(open(S + sys.argv[1]).read().strip())
    out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    for spec in sys.argv[3:]:
        task, layout, seed = spec.split(":")
        scene = make_scene(int(seed), layout, task)
        log: list = []

        def wrapped_arm(sc):
            return Wrapped(arm(sc), log)
        wrapped_arm.describe = arm.describe
        t0 = time.perf_counter()
        rec = run_episode(scene, wrapped_arm, policy_budget=10.0, with_shake=True)
        m = rec["metrics"]
        thr = m["total_items"] // 2 + 1
        print(f"== {scene.name}: placed {m['placed_count']}/{m['total_items']} (threshold {thr}, margin {m['placed_count'] - thr:+d}), "
              f"end {m.get('end_reason')}, policy max {m['policy_time_max']:.2f}, {time.perf_counter() - t0:.0f}s", flush=True)
        rec["cf"] = log
        (out / f"{scene.name}.json").write_text(json.dumps(rec, default=str))


if __name__ == "__main__":
    main()
