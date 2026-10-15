"""cf_probe.py <armfile> <out_dir> <mode> TASK:LAYOUT:SEED ...

At every declining call of an episode run with the arm's budget, the same
observation is asked again with larger budgets (6.5, 8.0, and 30 s with the
deterministic budgets): does more time find a pose the shadow accepts, at
which stage, after how long.  Also the validator room scan of the pool at
the decline (every 2 cm grid pose resting on the highest top under it,
copied from scripts/last_call_probe.py's ``_room``).

mode ``observe``: the decline stands (the episode ends as in the bench).
mode ``continue:<budget>``: when the re-ask at <budget> places, that action
is played and the episode goes on at the arm's budget (the value of a
longer declining call only)."""
import collections
import dataclasses
import itertools
import json
import pathlib
import sys
import time

sys.path.insert(0, "/home/user/nedo-3d-bpp")
from bench.arms import make_arm  # noqa: E402
from bench.episode import run_episode  # noqa: E402
from bench.scenes import make_scene  # noqa: E402
import rule_alpha.layer1 as layer1  # noqa: E402
from rule_alpha import fastgeom  # noqa: E402
from rule_alpha._reuse import AABB  # noqa: E402

BUDGETS = [(4.5, False), (6.5, False), (8.0, False), (30.0, True)]


def room(agent, pool, cell=0.02):
    board = agent.board
    config = dataclasses.replace(agent.config, lift_to_tops=5.0)
    out = []
    for item in pool:
        dims = (float(item["length"]), float(item["width"]), float(item["height"]))
        total = 0
        for ci in range(len(board.containers)):
            model = board.model(ci); container = board.container(ci)
            rect = model.floor_rect
            for dx, dy, dz in set(itertools.permutations(dims)):
                x = rect.x_min + dx / 2.0
                while x <= rect.x_max - dx / 2.0 + 1e-9:
                    y = rect.y_min + dy / 2.0
                    while y <= rect.y_max - dy / 2.0 + 1e-9:
                        box = AABB((x, y, model.z_floor + dz / 2.0), (dx, dy, dz), "probe")
                        box = fastgeom.lift_to_tops(box, container, config)
                        ok, _why = layer1.validate(box, model, container, config)
                        total += bool(ok)
                        y += cell
                    x += cell
        out.append(f"{'s' if item.get('is_soft') else 'h'}{dims[0]:.2f}x{dims[1]:.2f}x{dims[2]:.2f}:{total}")
    return out


class Wrapped:
    def __init__(self, agent, mode, log):
        self.agent, self.mode, self.log = agent, mode, log
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
                 "packed": sum(len(c.get("packed_items") or []) for c in observation.get("container_list", [])),
                 "retries": []}
        chosen = None
        want = float(self.mode.split(":")[1]) if self.mode.startswith("continue:") else None
        for budget, det in BUDGETS:
            a.config = dataclasses.replace(base_cfg, policy_budget_seconds=budget, deterministic_budgets=det)
            before = dict(a.shadow_stats)
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
            box_info = None
            if act is not None and d is not None and getattr(d, "placement", None) is not None:
                try:
                    from wedge_rl.stack import skyline
                    import numpy as _np
                    bx = d.placement.box
                    ci = d.placement.container_idx
                    cont = a.board.container(ci); mdl = a.board.model(ci)
                    xs, ys, tops = skyline(cont, mdl, step=0.02)
                    dx, dy, dz = [float(v) for v in bx.size]
                    cx, cy, cz = [float(v) for v in bx.center]
                    i0 = int(_np.searchsorted(xs, cx - dx / 2)); j0 = int(_np.searchsorted(ys, cy - dy / 2))
                    win = tops[max(0, i0):i0 + max(1, int(round(dx / 0.02))), max(0, j0):j0 + max(1, int(round(dy / 0.02)))]
                    bottom = cz - dz / 2
                    share = float(_np.mean(_np.abs(win - bottom) <= 0.006)) if win.size else None
                    dip = float(bottom - win.min()) if win.size else None
                    box_info = {"center": [round(cx, 3), round(cy, 3), round(cz, 3)], "size": [dx, dy, dz],
                                "contact_share": round(share, 2) if share is not None else None, "dip": round(dip, 3) if dip is not None else None,
                                "reason": getattr(d.placement, "reason", None)}
                except Exception as exc:
                    box_info = {"failed": repr(exc)}
            entry["retries"].append({"budget": budget, "deterministic": det, "seconds": round(secs, 2),
                                     "placed": act is not None, "box": box_info,
                                     "archetype": (d.placement.archetype if (act is not None and d is not None) else None),
                                     "shadow": (a.last_shadow or {}).get("outcome") if act is not None else None,
                                     "stats": stats})
            if want is not None and act is not None and abs(budget - want) < 1e-6 and chosen is None:
                chosen = act
        try:
            entry["room"] = room(a, pool)
        except Exception as exc:  # the scan is telemetry
            entry["room"] = [f"failed {exc!r}"]
        self.log.append(entry)
        print(json.dumps(entry), flush=True)
        if chosen is not None:
            return chosen
        return None


def main():
    S = "/tmp/claude-0/-home-user-nedo-3d-bpp/c555f0d0-1382-515f-857e-e77257cc9f93/scratchpad/"
    arm_spec = open(S + sys.argv[1]).read().strip()
    out = pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    mode = sys.argv[3]
    arm = make_arm(arm_spec)
    budget = float(arm.config.policy_budget_seconds)
    for spec in sys.argv[4:]:
        task, layout, seed = spec.split(":")
        scene = make_scene(int(seed), layout, task)
        log: list = []

        def wrapped_arm(sc):
            return Wrapped(arm(sc), mode, log)
        wrapped_arm.describe = arm.describe
        t0 = time.perf_counter()
        rec = run_episode(scene, wrapped_arm, policy_budget=10.0, with_shake=True)
        m = rec["metrics"]
        thr = m["total_items"] // 2 + 1
        print(f"== {scene.name} [{mode}]: placed {m['placed_count']}/{m['total_items']} (threshold {thr}, margin {m['placed_count'] - thr:+d}), "
              f"end {m.get('end_reason')}, policy max {m['policy_time_max']:.2f}, {time.perf_counter() - t0:.0f}s", flush=True)
        rec["cf"] = log
        (out / f"{scene.name}.json").write_text(json.dumps(rec, default=str))


if __name__ == "__main__":
    main()
