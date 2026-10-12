"""last_call_probe.py <arm> <out_dir> TASK:LAYOUT:SEED...: what the declining call saw.

Runs the episode and, on the call that declines, reports every anchor
pose the ladder put through the analytic validator (per container and
orientation: passed, or the veto reason), the stack option's and the
resort's shadow checks in that call, and the time it took; the episode's
record is written as JSON (the bench's format) for the end-state readers.
"""
import collections
import dataclasses
import itertools
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from bench.arms import make_arm  # noqa: E402
from bench.scenes import make_scene  # noqa: E402
from bench.episode import run_episode  # noqa: E402
import rule_alpha.layer1 as layer1  # noqa: E402
from rule_alpha import classify as cls  # noqa: E402
from rule_alpha import fastgeom  # noqa: E402
from rule_alpha._reuse import AABB  # noqa: E402

anchors: list = []
_orig_validate = layer1.validate


def validate(box, model, container, config):
    ok, why = _orig_validate(box, model, container, config)
    if getattr(box, "name", "") == "candidate":
        anchors.append((int(container.get("index", 0)), tuple(float(v) for v in box.center),
                        tuple(float(v) for v in box.size), "ok" if ok else why))
    return ok, why


layer1.validate = validate
reports: list = []


class Wrapped:
    def __init__(self, agent):
        self.agent = agent

    def __getattr__(self, name):
        return getattr(self.agent, name)

    def _room(self, pool, cell: float = 0.02) -> str:
        """Every grid pose of every pool item through the agent's own validator,
        resting on the highest top under its footprint: what passes, and what
        the verdicts are for the rest (the room the generators did not offer)."""
        board = self.agent.board
        config = dataclasses.replace(self.agent.config, lift_to_tops=5.0)
        out = []
        for item in pool:
            dims = (float(item["length"]), float(item["width"]), float(item["height"]))
            for ci in range(len(board.containers)):
                model = board.model(ci); container = board.container(ci)
                rect = model.floor_rect
                verdicts = collections.Counter(); passed = []
                for dx, dy, dz in set(itertools.permutations(dims)):
                    x = rect.x_min + dx / 2.0
                    while x <= rect.x_max - dx / 2.0 + 1e-9:
                        y = rect.y_min + dy / 2.0
                        while y <= rect.y_max - dy / 2.0 + 1e-9:
                            box = AABB((x, y, model.z_floor + dz / 2.0), (dx, dy, dz), "probe")
                            box = fastgeom.lift_to_tops(box, container, config)
                            ok, why = layer1.validate(box, model, container, config)
                            verdicts["ok" if ok else why] += 1
                            if ok:
                                passed.append((round(float(box.minimum[2]), 2), (dx, dy, dz)))
                            y += cell
                        x += cell
                tag = "soft" if item.get("is_soft") else "hard"
                heights = collections.Counter(z for z, _o in passed)
                out.append(f"  room for {tag} {dims[0]:.2f}x{dims[1]:.2f}x{dims[2]:.2f} in c{ci}: {len(passed)} grid poses pass the validator"
                           + (f" (bottoms {dict(sorted(heights.items()))})" if passed else "")
                           + "; verdicts " + ", ".join(f"{k} {v}" for k, v in verdicts.most_common(5)))
        return "\n".join(out)

    def policy(self, observation):
        anchors.clear()
        before = dict(getattr(self.agent, "shadow_stats", {}) or {})
        t0 = time.perf_counter()
        action = self.agent.policy(observation)
        if action is None:
            after = dict(getattr(self.agent, "shadow_stats", {}) or {})
            pool = observation.get("pool_list") or []
            by = collections.defaultdict(collections.Counter)
            for ci, _c, size, verdict in anchors:
                by[(ci, tuple(round(v, 2) for v in size))][verdict] += 1
            lines = [f"declined after {time.perf_counter() - t0:.2f}s; pool {[(round(i['length'], 2), round(i['width'], 2), round(i['height'], 2), 's' if i.get('is_soft') else 'h') for i in pool]}",
                     f"shadow stats in this call: { {k: after.get(k, 0) - before.get(k, 0) for k in after if after.get(k, 0) != before.get(k, 0)} }",
                     f"anchors validated: {len(anchors)}"]
            for (ci, size), cnt in sorted(by.items()):
                lines.append(f"  c{ci} {size[0]:.2f}x{size[1]:.2f}x{size[2]:.2f}: " + ", ".join(f"{k} {v}" for k, v in cnt.most_common(6)))
            ok = [a for a in anchors if a[3] == "ok"]
            if ok:
                zs = collections.Counter(round(a[1][2] - a[2][2] / 2, 1) for a in ok)
                lines.append(f"  passed anchors by bottom height: {dict(sorted(zs.items()))}")
            lines.append(self._room(pool))
            reports.append("\n".join(lines))
            self.last_anchors = [{'c': a[0], 'center': [round(v, 3) for v in a[1]], 'size': [round(v, 3) for v in a[2]], 'verdict': a[3]} for a in anchors]
        return action


def main():
    arm = make_arm(sys.argv[1])
    out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)

    def wrapped_arm(scene):
        wrapped_arm.last = Wrapped(arm(scene))
        return wrapped_arm.last
    wrapped_arm.describe = arm.describe
    for spec in sys.argv[3:]:
        task, layout, seed = spec.split(":")
        scene = make_scene(int(seed), layout, task)
        reports.clear()
        rec = run_episode(scene, wrapped_arm, policy_budget=4.5, with_shake=False)
        m = rec["metrics"]
        thr = m["total_items"] // 2 + 1
        print(f"== {scene.name}: placed {m['placed_count']}/{m['total_items']} (threshold {thr}, margin {m['placed_count'] - thr:+d}), end {m.get('end_reason')}")
        for r in reports:
            print(r)
        (out / f"{scene.name}.json").write_text(json.dumps(rec, default=str))
        la = getattr(wrapped_arm.last, 'last_anchors', None)
        if la is not None:
            (out / f"{scene.name}-anchors.json").write_text(json.dumps(la))


if __name__ == "__main__":
    main()
