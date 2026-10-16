"""At every decline of the shipped C/B form: would the ladder without the
shadow gate have offered a pose, and does the official validator accept it?

    python probe_gate.py <arm_file> <task> <layout> <seed...>
"""
import contextlib, dataclasses, io, json, sys, time
sys.path.insert(0, "/home/user/nedo-3d-bpp")
from bench.scenes import make_scene
from bench.arms import make_arm
from bench.episode import load_env_class

arm_text = open(sys.argv[1]).read().strip()
task, layout = sys.argv[2], sys.argv[3]
seeds = [int(s) for s in sys.argv[4:]]
rows = []
for seed in seeds:
    scene = make_scene(seed, layout, task)
    arm = make_arm(arm_text)
    Env = load_env_class()
    env = Env(config=scene.sim_config(policy_timeout=4.5), verbose=False, render_mode=None)
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink):
        env.reset_settings()
        agent = arm(scene)
        agent.get_init_states(env.get_init_states())
        if scene.optimize:
            env.set_item_order(agent.optimize(env.get_info_for_optimization()))
        env.reset_item_stream()
        observation, _ = env.reset(seed=42)
    total = len(scene.items); thr = total // 2 + 1
    placed = 0; verdict = None
    for step in range(300):
        with contextlib.redirect_stdout(sink):
            action = agent.policy(observation)
        if action is None:
            # the same agent with the gate off, on the same board
            saved = agent.config
            agent.config = dataclasses.replace(agent.config, shadow_check=False, physics_resort=False)
            try:
                with contextlib.redirect_stdout(sink):
                    alt = agent.policy(observation)
            finally:
                agent.config = saved
            if alt is None:
                verdict = ("none", None)
            else:
                with contextlib.redirect_stdout(sink):
                    _obs, _r, _t, _tr, info = env.step(alt)
                st = (info or {}).get("status", {})
                ok = bool(st.get("is_included")) and bool(st.get("is_valid")) and bool(st.get("is_placed_safe"))
                verdict = ("safe" if ok else "fails", {k: bool(v) for k, v in st.items()})
            break
        with contextlib.redirect_stdout(sink):
            observation, _r, term, trunc, info = env.step(action)
        placed += 1
        if term or trunc:
            verdict = ("ended", None); break
    try:
        env.close()
    except Exception:
        pass
    row = dict(scene=scene.name, placed=placed, total=total, threshold=thr, before_threshold=placed < thr, gate_off=verdict[0], status=verdict[1],
               shadow=getattr(agent, "shadow_stats", None))
    rows.append(row)
    print(json.dumps(row), flush=True)
print("PROBE_GATE_DONE")
