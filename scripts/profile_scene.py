"""profile_scene.py <arm> <TASK:LAYOUT:SEED> <out.txt>: run the scene with every policy call under
cProfile; write the slowest call's stats (cumulative) and the per-call seconds."""
import cProfile, pstats, io, sys, time, pathlib
import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from bench.arms import make_arm
from bench.scenes import make_scene
from bench.episode import run_episode
arm = make_arm(sys.argv[1]); task, layout, seed = sys.argv[2].split(":")
scene = make_scene(int(seed), layout, task)
slowest = {"seconds": 0.0, "stats": None, "step": -1}; calls = []
class Wrapped:
    def __init__(self, agent): self.agent = agent
    def __getattr__(self, name): return getattr(self.agent, name)
    def policy(self, observation):
        pr = cProfile.Profile(); t0 = time.perf_counter(); pr.enable()
        try:
            return self.agent.policy(observation)
        finally:
            pr.disable(); dt = time.perf_counter() - t0; calls.append(dt)
            if dt > slowest["seconds"]:
                slowest.update(seconds=dt, stats=pstats.Stats(pr), step=len(calls) - 1)
def wrapped_arm(sc): return Wrapped(arm(sc))
wrapped_arm.describe = arm.describe
record = run_episode(scene, wrapped_arm, policy_budget=4.5, with_shake=False)
out = io.StringIO()
out.write(f"placed {record['metrics']['placed_count']} end {record['metrics']['end_reason']} slowest call step {slowest['step']} {slowest['seconds']:.2f}s (profiled)\n")
out.write("calls over 4.5 s: " + str([(i, round(c, 1)) for i, c in enumerate(calls) if c > 4.5]) + "\n")
st = slowest["stats"]; st.stream = out; st.sort_stats("cumulative").print_stats(45)
st.sort_stats("tottime").print_stats(25)
pathlib.Path(sys.argv[3]).write_text(out.getvalue())
print(out.getvalue()[:600])
