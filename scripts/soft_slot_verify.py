"""soft_slot_verify.py <arm> TASK:LAYOUT:SEED...: at the call that declines,
the geometric slots the pool's soft items have on the live board, and
what the analytic validator says of a pose in each.

The slot finder is scripts/soft_slots_b.py's (a level patch the flat
footprint fits with 3 cm of clearance and the height plus 3 cm free
above it); the pose is put through ``layer1.validate`` (walls, the
commanded pose, the transport sweep, overlaps, the support model) and
the verdict printed, and the ladder's own anchors of that footprint
within 5 cm are counted (recall).  Run from the repo root; prints to
stderr."""
import collections
import functools
import pathlib
import sys

print = functools.partial(print, file=sys.stderr, flush=True)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from bench.arms import make_arm  # noqa: E402
from bench.episode import run_episode  # noqa: E402
from bench.scenes import make_scene  # noqa: E402
import rule_alpha.layer1 as layer1  # noqa: E402
from rule_alpha._reuse import AABB, packed_aabbs_local  # noqa: E402
from soft_slots_b import Load  # noqa: E402

anchors: list = []
_ov = layer1.validate


def validate(box, model, container, config):
    ok, why = _ov(box, model, container, config)
    if getattr(box, "name", "") == "candidate":
        anchors.append((int(container.get("index", 0)), tuple(float(v) for v in box.center),
                        tuple(round(float(v), 2) for v in box.size), "ok" if ok else why))
    return ok, why


layer1.validate = validate


class W:
    def __init__(self, agent):
        self.a = agent
        self.calls = 0

    def __getattr__(self, n):
        return getattr(self.a, n)

    def policy(self, obs):
        anchors.clear()
        act = self.a.policy(obs)
        declined = act is None or (isinstance(act, dict) and act.get("position", [0, 0, 0])[2] > 5)
        if declined:
            pool = obs.get("pool_list", [])
            board = self.a.board
            print(f"DECLINE at call {self.calls}: pool {[(p['index'], round(p['length'], 2), round(p['width'], 2), round(p['height'], 2), 'S' if p.get('is_soft') else 'H') for p in pool]}")
            for ci in range(len(board.models)):
                container = board.container(ci)
                model = board.model(ci)
                load = Load(container)
                for b, _s, _p in packed_aabbs_local(container):
                    load.add(tuple(float(v) for v in b.center), tuple(float(v) for v in b.size))
                for p in pool:
                    if not p.get("is_soft"):
                        continue
                    d = sorted((p["length"], p["width"], p["height"]), reverse=True)
                    found = load.slot_pose((d[0], d[1], d[2]))
                    if not found:
                        print(f"  c{ci} item {p['index']} {d[0]:.2f}x{d[1]:.2f}x{d[2]:.2f}: no slot")
                        continue
                    kind, centre, dims = found
                    box = AABB(centre, dims, "probe")
                    ok, why = _ov(box, model, container, self.a.config)
                    near = [a for a in anchors if a[0] == ci and all(abs(q - r) < 1e-3 for q, r in zip(a[2], tuple(round(v, 2) for v in dims)))
                            and max(abs(a[1][0] - centre[0]), abs(a[1][1] - centre[1])) <= 0.05 and abs(a[1][2] - centre[2]) <= 0.05]
                    verdicts = collections.Counter(a[3] for a in near)
                    print(f"  c{ci} item {p['index']} {d[0]:.2f}x{d[1]:.2f}x{d[2]:.2f}: slot on {kind} at {tuple(round(v, 3) for v in centre)} as {tuple(round(v, 2) for v in dims)} -> validator {'ok' if ok else why}; ladder anchors within 5 cm: {dict(verdicts) or 'none'}")
        self.calls += 1
        return act


def main():
    arm = make_arm(sys.argv[1])

    def wa(scene):
        return W(arm(scene))
    wa.describe = arm.describe
    for spec in sys.argv[2:]:
        task, layout, seed = spec.split(":")
        rec = run_episode(make_scene(int(seed), layout, task), wa, policy_budget=4.5, with_shake=False)
        print(f"[{rec['scene']}] placed {rec['metrics']['placed_count']} end {rec['metrics']['end_reason']}")


if __name__ == "__main__":
    main()
