"""Official simulator: standing soft / priority rows against the back wall,
with and without a hard row beside them, under the bench's shake proxy.

The typed-standing plan (``plan_typed_standing``) stands the count frame's
soft and priority boxes on their smallest face in rows against the back wall
and lays the hard rows in front of them.  This probe builds those rows by
hand in the c1 container and reads, per arrangement: whether every box was
placed safe, how far the standing boxes moved while settling, and the shake
proxy's topples and shifts (``bench.metrics.terminal_metrics``).

A standing box is the item with its dimensions permuted so that the smallest
face is down (orientation 0 of a box of the same size and mass), so the
simulator's own placement and settle rules apply unchanged.  Placements are
commanded as the agent commands them: on the floor 2 cm over its rest
height, on a stack at the settled top; gaps of 2.6 cm (the planner's
clearance plus slack).

Run: python scripts/standing_rows_probe.py   (about a minute)
"""
from __future__ import annotations

import contextlib
import io
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from bench.metrics import terminal_metrics  # noqa: E402
from bench.scenes import SKUS  # noqa: E402
from rule_alpha.penetration import _config  # noqa: E402
from rule_alpha.physics import _load_env_module  # noqa: E402

GAP = 0.026
FLOOR = 0.04
Y_BACK = 0.669     # the planner's back line (floor rect y_max) in the c1 container
X_LEFT = -0.528    # the floor's left edge over the chamfer
X_RIGHT = 0.944


def sku(name):
    for s in SKUS:
        if s[0] == name:
            return s
    raise KeyError(name)


def item(index, name, dims=None, priority=False):
    _n, l, w, h, mass, soft, phys, _wt = sku(name)
    if dims is not None:
        l, w, h = dims
    d = {"index": index, "length": l, "width": w, "height": h, "mass": mass,
         "is_soft": soft, "is_prioritized": priority}
    d.update(phys)
    return d


def standing(name):
    """(dx, dy, dz) of the SKU on its smallest face: the two smallest sides
    as the footprint, the shallower along y."""
    _n, l, w, h, *_rest = sku(name)
    a, b, c = sorted((l, w, h))
    return (b, a, c)


def flat(name):
    _n, l, w, h, *_rest = sku(name)
    a, b, c = sorted((l, w, h))
    return (c, b, a)


def row(names, y_back, x0=X_LEFT, dims_of=standing, priority=()):
    """A row of boxes from ``x0`` to the right, their back faces on
    ``y_back``: list of (name, dims, x, y, prio)."""
    out, x = [], x0
    for k, name in enumerate(names):
        dx, dy, dz = dims_of(name)
        if x + dx > X_RIGHT + 1e-9:
            break
        out.append((name, (dx, dy, dz), x + dx / 2.0, y_back - dy / 2.0, k in priority))
        x += dx + GAP
    return out


def hard_row(y_back, layers=2, top_standing=True):
    """The planner's hard row on a dense manifest: B boxes 0.45 x 0.65 x 0.25
    across, two flat layers, then (``top_standing``) A boxes standing 0.55 x
    0.24 x 0.40 on top (the third flat layer is in the mid-height band)."""
    out = []
    for layer in range(layers):
        out += row(["B"] * 3, y_back, dims_of=lambda n: (0.45, 0.65, 0.25))
    if top_standing:
        out += row(["A"] * 2, y_back, x0=X_LEFT + 0.05, dims_of=lambda n: (0.55, 0.24, 0.40))
        out += row(["A"] * 2, y_back - 0.24 - GAP, x0=X_LEFT + 0.05, dims_of=lambda n: (0.55, 0.24, 0.40))
    return out


def run(plan):
    """plan: list of (sku, dims, x, y, prio) placed in order, each dropped on
    whatever is under its footprint."""
    items = [item(i, name, dims, prio) for i, (name, dims, _x, _y, prio) in enumerate(plan)]
    Env = _load_env_module()
    sink = io.StringIO()
    placed = []
    with contextlib.redirect_stdout(sink):
        env = Env(config=_config(items, -0.005), verbose=False, render_mode=None)
        try:
            env.reset_settings()
            env.reset_item_stream()
            obs, _ = env.reset(seed=1)
            for i, (name, dims, x, y, _p) in enumerate(plan):
                dx, dy, dz = dims
                bottom = FLOOR
                for (bx, by, bdx, bdy, btop) in placed:
                    if min(x + dx / 2, bx + bdx / 2) - max(x - dx / 2, bx - bdx / 2) > 0.01 and \
                            min(y + dy / 2, by + bdy / 2) - max(y - dy / 2, by - bdy / 2) > 0.01:
                        bottom = max(bottom, btop)
                lift = 0.02 if bottom <= FLOOR + 1e-6 else 0.0
                z = bottom + lift + dz / 2.0
                obs, _r, _t, _tr, info = env.step({"item_idx": 0, "container_idx": 0,
                                                   "place_pos": np.array([x, y, z], dtype=np.float32), "orientation": 0})
                st = (info or {}).get("status", {})
                if not bool(st.get("is_placed_safe")):
                    return {"failed_at": i, "name": name, "status": {k: bool(v) for k, v in st.items()}}
                packed = obs["container_list"][0]["packed_items"]
                me = [p for p in packed if int(p["index"]) == i][0]
                pos = [float(v) for v in me["pos"]]
                placed.append((x, y, dx, dy, pos[2] + dz / 2.0))
            m = terminal_metrics(env, with_shake=True)
            # the settle shift of every box from where it was commanded
            final = {int(p["index"]): p for p in obs["container_list"][0]["packed_items"]}
            settle = [float(np.hypot(float(final[i]["pos"][0]) - x, float(final[i]["pos"][1]) - y))
                      for i, (_n, _d, x, y, _p) in enumerate(plan) if i in final]
        finally:
            with contextlib.suppress(Exception):
                env.close()
    standing_ids = [i for i, (_n, dims, _x, _y, _p) in enumerate(plan) if dims[2] > max(dims[0], dims[1]) - 1e-9]
    toppled = list(m.get("shake_toppled_items", []))
    return {
        "placed": len(plan), "settle_max_cm": round(100 * max(settle), 2) if settle else 0.0,
        "topples": int(m.get("shake_topples", 0)), "standing_toppled": sum(1 for i in toppled if i in standing_ids),
        "standing": len(standing_ids),
        "shake_max_cm": round(100 * float(m.get("shake_max_shift", 0.0)), 1),
        "shake_mean_cm": round(100 * float(m.get("shake_mean_shift", 0.0)), 2),
        "com": round(float(m.get("com_z_above_floor_ratio", 0.0)), 3),
    }


def arrangements():
    soft_mix = ["E", "G", "F", "E", "G", "F"]
    g_row = ["G"] * 6
    a = {}
    y_hard = Y_BACK - 0.30 - GAP      # a hard row right in front of a 0.30 m gallery row
    y_mid = 0.10                       # a row in the open floor
    # one standing row against the back wall
    a["G row, wall only"] = row(g_row, Y_BACK)
    a["G row, wall + hard row"] = row(g_row, Y_BACK) + hard_row(y_hard)
    a["G row, hard row first, then G"] = hard_row(y_hard) + row(g_row, Y_BACK)
    a["G row, open floor"] = row(g_row, y_mid)
    a["G row, hard row behind only"] = hard_row(Y_BACK) + row(g_row, Y_BACK - 0.65 - GAP)
    a["mixed soft row, wall only"] = row(soft_mix, Y_BACK)
    a["mixed soft row, wall + hard row"] = row(soft_mix, Y_BACK) + hard_row(Y_BACK - 0.35 - GAP)
    a["mixed soft row, open floor"] = row(soft_mix, y_mid)
    a["mixed soft row, hard row behind only"] = hard_row(Y_BACK) + row(soft_mix, Y_BACK - 0.65 - GAP)
    # the priority boxes standing (A on 0.40 x 0.24, B on 0.45 x 0.25)
    pri = ["A", "B", "A", "B", "A"]
    a["priority A/B row, wall only"] = row(pri, Y_BACK, priority=range(5))
    a["priority A/B row, wall + hard row"] = row(pri, Y_BACK, priority=range(5)) + hard_row(Y_BACK - 0.25 - GAP)
    a["priority A/B row, open floor"] = row(pri, y_mid, priority=range(5))
    # two standing rows, braced by the wall and the hard row
    two = row(soft_mix, Y_BACK) + row(g_row, Y_BACK - 0.35 - GAP)
    a["two soft rows, wall only"] = two
    a["two soft rows, wall + hard row"] = two + hard_row(Y_BACK - 0.35 - GAP - 0.30 - GAP)
    # the soft flat on the floor (the ordinary pose) for comparison
    a["G row flat, wall only"] = row(["G"] * 3, Y_BACK, dims_of=flat)
    return a


if __name__ == "__main__":
    print(f"{'arrangement':42s} | placed | standing | settle max | topples (standing) | shake max / mean | CoM")
    for name, plan in arrangements().items():
        r = run(plan)
        if "failed_at" in r:
            print(f"{name:42s} | FAILED at box {r['failed_at']} ({r['name']}): {r['status']}")
            continue
        print(f"{name:42s} | {r['placed']:6d} | {r['standing']:8d} | {r['settle_max_cm']:7.2f} cm | "
              f"{r['topples']:3d} ({r['standing_toppled']:2d})          | {r['shake_max_cm']:5.1f} / {r['shake_mean_cm']:5.2f} cm | {r['com']:.3f}")
