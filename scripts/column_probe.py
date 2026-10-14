"""Official simulator: a soft column alone vs braced by hard columns.

Soft D box 0.50 x 0.40 x 0.40 (contactStiffness 3000), three high (top 1.24 m);
hard A box 0.55 x 0.40 x 0.24, five high (top 1.24 m) beside it along x with the
agent's 2.6 cm gap.  Every placement commanded as the agent does (floor lift 2 cm,
stacks at the settled top).  After the load: the bench's shake proxy.
"""
import contextlib, io, sys
import numpy as np
sys.path.insert(0, "/home/user/nedo-3d-bpp")
from rule_alpha.penetration import _config
from rule_alpha.physics import _load_env_module
from bench.metrics import terminal_metrics
from bench.scenes import SKUS

GAP = 0.026


def sku(name):
    for s in SKUS:
        if s[0] == name:
            return s
    raise KeyError(name)


def item(index, name):
    _n, l, w, h, mass, soft, phys, _wt = sku(name)
    d = {"index": index, "length": l, "width": w, "height": h, "mass": mass,
         "is_soft": soft, "is_prioritized": False}
    d.update(phys)
    return d


def run(plan, verbose=False):
    """plan: list of (sku name, x, y) placed in order, each on the column at (x, y)."""
    items = [item(i, name) for i, (name, _x, _y) in enumerate(plan)]
    Env = _load_env_module()
    sink = io.StringIO()
    tops = {}
    results = []
    with contextlib.redirect_stdout(sink):
        env = Env(config=_config(items, -0.005), verbose=False, render_mode=None)
        try:
            env.reset_settings(); env.reset_item_stream()
            obs, _ = env.reset(seed=1)
            for i, (name, x, y) in enumerate(plan):
                h = sku(name)[3]
                bottom = tops.get((x, y), 0.04)
                lift = 0.02 if (x, y) not in tops else 0.0
                z = bottom + lift + h / 2.0
                obs, _r, term, trunc, info = env.step({"item_idx": 0, "container_idx": 0,
                                                       "place_pos": np.array([x, y, z], dtype=np.float32), "orientation": 0})
                st = (info or {}).get("status", {})
                ok = bool(st.get("is_placed_safe"))
                packed = obs["container_list"][0]["packed_items"] if obs else []
                me = [p for p in packed if int(p["index"]) == i]
                settled_top = float(me[0]["pos"][2]) + h / 2.0 if me else None
                results.append((i, name, (x, y), round(bottom, 3), ok, round(settled_top, 3) if settled_top else None))
                if not ok:
                    break
                tops[(x, y)] = settled_top
            m = terminal_metrics(env, with_shake=True)
        finally:
            with contextlib.suppress(Exception):
                env.close()
    return results, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items() if k.startswith("shake")}, sink.getvalue()


if __name__ == "__main__":
    xs = 0.30
    soft3 = [("D", xs, 0.20)] * 3
    hard5 = lambda x: [("A", x, 0.20)] * 5
    dx = 0.55 / 2 + 0.50 / 2 + GAP   # hard beside the soft along x
    plans = {
        "soft column alone (3 D)": soft3,
        "hard-soft-hard (hard columns first)": hard5(xs - dx) + hard5(xs + dx) + soft3,
        "hard-soft-hard, soft first": soft3 + hard5(xs - dx) + hard5(xs + dx),
        "soft 4 high alone": [("D", xs, 0.20)] * 3 + [("E", xs, 0.20)],
        "soft 4 high braced": hard5(xs - dx) + hard5(xs + dx) + [("D", xs, 0.20)] * 3 + [("E", xs, 0.20)],
    }
    for name, plan in plans.items():
        res, shake, log = run(plan)
        fails = [r for r in res if not r[4]]
        print(f"== {name}: placed {sum(1 for r in res if r[4])}/{len(plan)}" + (f"  FAILED at {fails[0][:4]}" if fails else "") + f"  shake {shake}")
        for l in [l for l in log.splitlines() if "Not safe" in l][-1:]:
            print("   ", l)
