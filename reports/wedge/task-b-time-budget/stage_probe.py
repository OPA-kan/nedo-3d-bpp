"""stage_probe.py <armfile> <out_dir> TASK:LAYOUT:SEED ...

Runs episodes with the arm and times every policy call by stage
(exclusive time, a stack of wrapped stages): the ladder (choose_for_item
outside the other stages), the pocket guard, the stack option, the last
resort, the physics resort, the grid rescue, the shadow checks (_emit and
_shadow_verdict), the rest.  Writes per-call rows to <out>/<scene>.stages.json.
Nothing in the repository is changed: the wrapping is on the instance /
module objects of this process."""
import json
import pathlib
import sys
import time

sys.path.insert(0, "/home/user/nedo-3d-bpp")
from bench.arms import make_arm  # noqa: E402
from bench.episode import run_episode  # noqa: E402
from bench.scenes import make_scene  # noqa: E402
import rule_alpha.layer1 as layer1  # noqa: E402
import rule_alpha.agent as ragent  # noqa: E402


class Clock:
    def __init__(self):
        self.stack = []
        self.acc = {}
        self.mark = time.perf_counter()

    def enter(self, name):
        now = time.perf_counter()
        top = self.stack[-1] if self.stack else "other"
        self.acc[top] = self.acc.get(top, 0.0) + now - self.mark
        if top == "last_resort" and name in ("ladder", "stack", "pocket"):
            name = "last_resort"  # the relaxed ladder / option inside the last resort
        self.stack.append(name); self.mark = now

    def leave(self):
        now = time.perf_counter()
        top = self.stack.pop()
        self.acc[top] = self.acc.get(top, 0.0) + now - self.mark
        self.mark = now

    def reset(self):
        self.stack, self.acc, self.mark = [], {}, time.perf_counter()


CLOCK = Clock()


def wrap(fn, name):
    def inner(*a, **k):
        CLOCK.enter(name)
        try:
            return fn(*a, **k)
        finally:
            CLOCK.leave()
    return inner


layer1.choose_for_item = wrap(layer1.choose_for_item, "ladder")
for meth, name in (("_pocket_guarded", "pocket"), ("_last_resort", "last_resort"), ("_physics_resort", "resort"),
                   ("_grid_rescue", "grid"), ("_shadow_verdict", "shadow"), ("_checkmate_guard", "checkmate")):
    setattr(ragent.RuleAlphaAgent, meth, wrap(getattr(ragent.RuleAlphaAgent, meth), name))


class Wrapped:
    def __init__(self, agent, rows):
        self.agent, self.rows = agent, rows
        if agent.stack_option is not None:
            agent.stack_option.propose = wrap(agent.stack_option.propose, "stack")

    def __getattr__(self, name):
        return getattr(self.agent, name)

    def policy(self, observation):
        CLOCK.reset()
        t0 = time.perf_counter()
        action = self.agent.policy(observation)
        total = time.perf_counter() - t0
        CLOCK.acc["other"] = CLOCK.acc.get("other", 0.0) + time.perf_counter() - CLOCK.mark
        d = self.agent.last_decision
        self.rows.append({"total": round(total, 3), "placed": action is not None,
                          "archetype": (d.placement.archetype if action is not None and d is not None else None),
                          "packed": sum(len(c.get("packed_items") or []) for c in observation.get("container_list", [])),
                          "stages": {k: round(v, 3) for k, v in CLOCK.acc.items()}})
        return action


def main():
    S = "/tmp/claude-0/-home-user-nedo-3d-bpp/c555f0d0-1382-515f-857e-e77257cc9f93/scratchpad/"
    arm = make_arm(open(S + sys.argv[1]).read().strip())
    out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    for spec in sys.argv[3:]:
        task, layout, seed = spec.split(":")
        scene = make_scene(int(seed), layout, task)
        rows: list = []

        def wrapped_arm(sc):
            return Wrapped(arm(sc), rows)
        wrapped_arm.describe = arm.describe
        rec = run_episode(scene, wrapped_arm, policy_budget=10.0, with_shake=True)
        m = rec["metrics"]
        print(f"== {scene.name}: placed {m['placed_count']}/{m['total_items']} end {m['end_reason']} max {m['policy_time_max']:.2f}", flush=True)
        (out / f"{scene.name}.stages.json").write_text(json.dumps(rows))


if __name__ == "__main__":
    main()
