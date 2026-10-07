"""recall_probe.py <arm> <out.jsonl> TASK:LAYOUT:SEED...: candidate recall of the ladder.

For every decision the physics resort or the count pass made (the ladder
and the stack option found nothing), the pose that stood is compared
with every anchor pose the ladder put through the analytic validator in
that call (``layer1.generate_candidates`` validates each anchor pose
before it becomes a candidate, so the anchors are read off the
validator's calls, by the box name "candidate"):

* ``no-anchor``: no anchor pose in that orientation within 5 cm (xy) and
  5 cm (z) of the pose -- the generator never offered the place;
* ``vetoed:<reason>``: an anchor pose within 5 cm failed the validator
  with that reason (and none passed);
* ``survived``: an anchor pose within 5 cm passed the validator and became
  a candidate (lost in the ranking, or to the shadow check).

``no-orientation`` is the case with no anchor pose of that orientation at
all.  One line of JSON per resort decision, and a summary."""
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

anchors: list = []        # (container index, center, size, verdict) in the current policy call
_orig_validate = layer1.validate


def validate(box, model, container, config):
    ok, why = _orig_validate(box, model, container, config)
    if getattr(box, "name", "") == "candidate":
        anchors.append((int(container.get("index", 0)), tuple(float(v) for v in box.center),
                        tuple(float(v) for v in box.size), "ok" if ok else why))
    return ok, why


layer1.validate = validate

records: list = []


class Wrapped:
    def __init__(self, agent):
        self.agent = agent

    def __getattr__(self, name):
        return getattr(self.agent, name)

    def policy(self, observation):
        anchors.clear()
        t0 = time.perf_counter()
        action = self.agent.policy(observation)
        decision = getattr(self.agent, "last_decision", None)
        placement = getattr(decision, "placement", None) if decision is not None else None
        arch = getattr(placement, "archetype", None) if placement is not None else None
        if action is not None and arch in ("physics-resort", "count-mode") and placement is not None:
            box = placement.box
            cx, cy, cz = (float(v) for v in box.center)
            sx, sy, sz = (float(v) for v in box.size)
            ci = int(placement.container_idx)
            mine = [a for a in anchors if a[0] == ci]
            same = [a for a in mine if all(abs(p - q) < 1e-3 for p, q in zip(a[2], (sx, sy, sz)))]
            kind = "no-orientation"
            nearest = None
            if same:
                def dist(a):
                    x, y, z = a[1]
                    return (max(abs(x - cx), abs(y - cy)), abs(z - cz))
                same.sort(key=dist)
                nearest = [round(v, 3) for v in dist(same[0])]
                near = [a for a in same if dist(a)[0] <= RADIUS_XY and dist(a)[1] <= RADIUS_Z]
                if not near:
                    kind = "no-anchor"
                else:
                    reasons = [a[3] for a in near]
                    kind = "survived" if "ok" in reasons else "vetoed:" + collections.Counter(reasons).most_common(1)[0][0]
            sizes = sorted({tuple(round(v, 2) for v in a[2]) for a in mine})
            records.append({"archetype": arch, "kind": kind, "anchors": len(mine), "same_orientation": len(same),
                            "nearest": nearest, "size": [round(sx, 2), round(sy, 2), round(sz, 2)],
                            "anchor_sizes": sizes, "surface": getattr(placement, "surface", None),
                            "bottom": round(cz - sz / 2, 3), "soft": bool(placement.profile.is_soft),
                            "verdicts": dict(collections.Counter(a[3] for a in mine).most_common(4)),
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
    verdicts = collections.Counter()
    for r in rows:
        verdicts.update(r["verdicts"])
    print("   the ladder's anchor verdicts in those calls:", dict(verdicts.most_common(6)))


if __name__ == "__main__":
    main()
