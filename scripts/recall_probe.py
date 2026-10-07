"""recall_probe.py <arm> <out.jsonl> TASK:LAYOUT:SEED...: candidate recall of the ladder.

For every decision the physics resort or the count pass made (the ladder
and the stack option found nothing), the pose that stood is compared
with what the ladder generated for that item:

* ``no-orientation``: the ladder generated no candidate in that orientation;
* ``no-position``: it did, but none within 5 cm (xy) and 5 cm (z) of the pose;
* ``vetoed:<reason>``: a candidate within 5 cm failed the analytic validator
  with that reason;
* ``survived``: a candidate within 5 cm passed the validator (lost in the
  ranking, or to the shadow check).

The ladder's generation and validation are captured by wrapping
``layer1.generate_candidates`` and ``layer1.validate``; the resort's pose
is the step's.  One line of JSON per resort decision, and a summary."""
import collections
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from bench.arms import make_arm  # noqa: E402
from bench.scenes import make_scene  # noqa: E402
from bench.episode import run_episode  # noqa: E402
import rule_alpha.layer1 as layer1  # noqa: E402

RADIUS_XY = 0.05
RADIUS_Z = 0.05

generated: list = []      # candidates generated in the current policy call
verdicts: dict = {}       # box key -> validator reason in the current call
_orig_generate = layer1.generate_candidates
_orig_validate = layer1.validate


def _key(center, size):
    return tuple(round(float(v), 3) for v in center) + tuple(round(float(v), 3) for v in size)


def generate_candidates(*args, **kwargs):
    out = _orig_generate(*args, **kwargs)
    generated.extend(out)
    return out


def validate(box, model, container, config):
    ok, why = _orig_validate(box, model, container, config)
    k = _key(box.center, box.size)
    if k not in verdicts or ok:
        verdicts[k] = "ok" if ok else why
    return ok, why


layer1.generate_candidates = generate_candidates
layer1.validate = validate

records: list = []


class Wrapped:
    def __init__(self, agent):
        self.agent = agent

    def __getattr__(self, name):
        return getattr(self.agent, name)

    def policy(self, observation):
        generated.clear()
        verdicts.clear()
        t0 = time.perf_counter()
        action = self.agent.policy(observation)
        decision = getattr(self.agent, "last_decision", None)
        placement = getattr(decision, "placement", None) if decision is not None else None
        arch = getattr(placement, "archetype", None) if placement is not None else None
        if action is not None and arch in ("physics-resort", "count-mode") and placement is not None:
            box = placement.box
            cx, cy, cz = (float(v) for v in box.center)
            sx, sy, sz = (float(v) for v in box.size)
            same = [c for c in generated
                    if int(c.container_idx) == int(placement.container_idx)
                    and all(abs(float(a) - b) < 1e-3 for a, b in zip(c.box.size, (sx, sy, sz)))]
            kind = "no-orientation"
            nearest = None
            if same:
                def dist(c):
                    x, y, z = (float(v) for v in c.box.center)
                    return max(abs(x - cx), abs(y - cy)), abs(z - cz)
                same.sort(key=lambda c: dist(c))
                near = [c for c in same if dist(c)[0] <= RADIUS_XY and dist(c)[1] <= RADIUS_Z]
                if not near:
                    kind = "no-position"
                    nearest = dist(same[0])
                else:
                    reasons = [verdicts.get(_key(c.box.center, c.box.size), "unvalidated") for c in near]
                    if "ok" in reasons:
                        kind = "survived"
                    else:
                        kind = "vetoed:" + collections.Counter(reasons).most_common(1)[0][0]
            records.append({"archetype": arch, "kind": kind, "generated": len(generated),
                            "same_orientation": len(same), "nearest": nearest,
                            "bottom": round(cz - sz / 2, 3), "soft": bool(placement.profile.is_soft),
                            "seconds": round(time.perf_counter() - t0, 2)})
        return action


def main():
    arm = make_arm(sys.argv[1])
    out = pathlib.Path(sys.argv[2])

    def wrapped_arm(scene):
        return Wrapped(arm(scene))
    wrapped_arm.describe = arm.describe
    with out.open("w") as fh:
        for spec in sys.argv[3:]:
            task, layout, seed = spec.split(":")
            scene = make_scene(int(seed), layout, task)
            records.clear()
            rec = run_episode(scene, wrapped_arm, policy_budget=4.5, with_shake=False)
            for r in records:
                r["scene"] = scene.name
                fh.write(json.dumps(r) + "\n")
            fh.flush()
            kinds = collections.Counter(r["kind"].split(":")[0] for r in records)
            print(f"[{scene.name}] placed {rec['metrics']['placed_count']} resort decisions {len(records)}: {dict(kinds)}", flush=True)
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    kinds = collections.Counter(r["kind"] for r in rows)
    print(f"== {len(rows)} resort decisions over {len(sys.argv) - 3} scenes")
    for k, n in kinds.most_common():
        print(f"   {k}: {n} ({n / max(len(rows), 1) * 100:.0f}%)")


if __name__ == "__main__":
    main()
