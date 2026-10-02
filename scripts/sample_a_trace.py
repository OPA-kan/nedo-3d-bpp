"""sample_a_trace.py <shade_area> <resort_step>: replay the official sample's
Task A episode with the submission agent and print, per policy call, the
stage, the reason and the shadow stats -- the probe that found v33's
dry-run leak (reports/wedge/findings.md, "v33 on the platform").

Run from the simulator directory after scripts/build_rule_alpha_submission.py:

    cd simulator && ../.venv312/bin/python ../scripts/sample_a_trace.py 0.0 0.0
"""
import contextlib
import io
import json
import sys
import time

sys.path.insert(0, "..")
sys.path.insert(0, "../dist/submit")
from bench.episode import load_env_class  # noqa: E402
import agent as submit_agent  # noqa: E402  (dist/submit/agent.py)

area = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
step = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
submit_agent.OVERRIDES["shade_veto_area"] = area
submit_agent.OVERRIDES["resort_shade_step"] = step
cfg = json.load(open("../reports/submission/a_config.json"))["000"]
Env = load_env_class()
env = Env(config=cfg, verbose=False, render_mode=None)
sink = io.StringIO()
with contextlib.redirect_stdout(sink):
    env.reset_settings()
    ag = submit_agent.Agent()
    ag.get_init_states(env.get_init_states())
    t0 = time.perf_counter()
    order = ag.optimize(env.get_info_for_optimization())
    dt = time.perf_counter() - t0
    env.set_item_order(order)
    env.reset_item_stream()
    obs, _ = env.reset(seed=42)
print(f"optimize {dt:.1f} s source={ag.plan_source!r} plan={len(ag.plan or [])} order={order}", flush=True)
for i in range(200):
    t0 = time.perf_counter()
    with contextlib.redirect_stdout(sink):
        action = ag.policy(obs)
    dt = time.perf_counter() - t0
    d = ag.last_decision
    pl = d.placement if d is not None else None
    item = None if action is None else env.stream_manager.get_item(int(action["item_idx"]))
    sh = ag.last_shadow
    print(f"call {i:2d} {dt:5.2f}s item={None if item is None else int(item.index)} "
          f"{'DECLINE' if action is None else ''} arch={getattr(pl, 'archetype', None)!r} "
          f"reason={getattr(pl, 'reason', None)!r} "
          f"shadow={None if sh is None else {k: v for k, v in sh.items() if k != 'tried'}} "
          f"stats={ag.shadow_stats}", flush=True)
    if action is None:
        break
    with contextlib.redirect_stdout(sink):
        obs, _r, term, trunc, info = env.step(action)
    st = (info or {}).get("status", {})
    if not all(st.get(k, False) for k in ("is_included", "is_valid", "is_placed_safe")):
        print("  platform status", st, flush=True)
    if term or trunc:
        break
logs = [line for line in sink.getvalue().splitlines() if line.startswith("[")]
print("agent log lines:", len(logs))
print("\n".join(logs[-20:]))
try:
    env.close()
except Exception:
    pass
