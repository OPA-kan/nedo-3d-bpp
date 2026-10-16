"""Official simulator: hard cargo on a soft floor (``plan_soft_floor_under_count``).

Does a hard box placed on soft boxes survive the placement (the validator's
settle check: 0.3 m, 45 degrees), the settle, and the bench's shake proxy,
and how far does a soft box compress under it?  Each case builds a private
world with the official validator and physics (the ULD of the sample, no
shelf), places the boxes the way the agent commands them (2 cm floor lift,
a stacked box at the settled top of what is under it, carried in from the
door), and records per placement: placed safe, the settle displacement
(commanded centre to settled centre) and the settled tilt; after the load:
each box's settled top against its nominal top (the compression of the
soft boxes under it), the evaluator's fill inclusion, the cover counts and
the shake proxy (topples over 30 degrees, the largest shift).

The item classes are the bench's (``bench.scenes.SKUS`` / ``EXTRA_SKUS``)
with their physics: the soft boxes carry contactStiffness 2000-3000,
contactDamping 600-800, linearDamping 0.8.

    .venv312/bin/python -m scripts.soft_floor_probe [--json out.json] [--only PREFIX] [--jobs N]

Needs the simulator extras (see docs/rule_alpha/README.md).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from bench.metrics import terminal_metrics, _settled_items
from bench.scenes import EXTRA_SKUS, SKUS
from rule_alpha.penetration import _config
from rule_alpha.physics import _load_env_module

GAP = 0.026            # the agent's settled clearance plus slack between neighbours
FLOOR = 0.04           # the ULD's floor top (thickness)
X_LEFT = -0.50         # the floor's left edge clear of the chamfer
Y_BACK = 0.664         # the back wall less the slack
CEILING = 1.57


def sku(name: str):
    for s in SKUS + EXTRA_SKUS:
        if s[0] == name:
            return s
    raise KeyError(name)


def dims(name: str, orn: int = 0) -> tuple[float, float, float]:
    _n, l, w, h, *_ = sku(name)
    return {0: (l, w, h), 1: (l, h, w), 2: (h, w, l), 3: (w, l, h), 4: (w, h, l), 5: (h, l, w)}[orn]


def flat_orn(name: str) -> int:
    """The orientation with the smallest height, the long side along x."""
    best = None
    for o in range(6):
        dx, dy, dz = dims(name, o)
        key = (round(dz, 4), -dx)
        if best is None or key < best[0]:
            best = (key, o)
    return best[1]


CONTROL = False
"""``--control``: every soft box replaced by a hard box of the same size and
mass with the hard physics, to tell the soft's effect from the geometry's
(the transport bands at the shelf level, an overhang)."""


def item(index: int, name: str) -> dict:
    _n, l, w, h, mass, soft, phys, _wt = sku(name)
    if CONTROL and soft:
        soft, phys = False, dict(SKUS[0][6])
    d = {"index": index, "length": l, "width": w, "height": h, "mass": mass,
         "is_soft": soft, "is_prioritized": False}
    d.update(phys)
    return d


def _tilt_deg(orn_a, orn_b) -> float:
    dot = min(1.0, abs(float(np.dot(np.asarray(orn_a), np.asarray(orn_b)))))
    return math.degrees(2.0 * math.acos(dot))


def run(placements: list[tuple]) -> dict:
    """``placements``: (sku, x, y[, orientation]) in order; each box drops
    onto the settled tops under its footprint (an overlap of 1 cm counts)."""
    import pybullet as p

    plan = [(pl[0], float(pl[1]), float(pl[2]), int(pl[3]) if len(pl) > 3 else flat_orn(pl[0])) for pl in placements]
    items = [item(i, name) for i, (name, *_r) in enumerate(plan)]
    Env = _load_env_module()
    sink = io.StringIO()
    steps = []
    out: dict = {}
    with contextlib.redirect_stdout(sink):
        env = Env(config=_config(items, -0.005), verbose=False, render_mode=None)
        try:
            env.reset_settings()
            env.reset_item_stream()
            obs, _ = env.reset(seed=1)
            nominal_top: dict[int, float] = {}
            for i, (name, x, y, orn) in enumerate(plan):
                dx, dy, dz = dims(name, orn)
                settled = _settled_items(env)
                bottom, nominal_bottom, under = FLOOR, FLOOR, []
                for s in settled:
                    ox = min(x + dx / 2, s["aabb_max"][0]) - max(x - dx / 2, s["aabb_min"][0])
                    oy = min(y + dy / 2, s["aabb_max"][1]) - max(y - dy / 2, s["aabb_min"][1])
                    if ox > 0.01 and oy > 0.01:
                        bottom = max(bottom, float(s["aabb_max"][2]))
                        nominal_bottom = max(nominal_bottom, nominal_top.get(s["index"], 0.0))
                        under.append(s["index"])
                lift = 0.02 if not under else 0.0
                z = bottom + lift + dz / 2.0
                target_orn = p.getQuaternionFromEuler(_orns()[orn])
                obs, _r, term, trunc, info = env.step({"item_idx": 0, "container_idx": 0,
                                                       "place_pos": np.array([x, y, z], dtype=np.float32),
                                                       "orientation": orn})
                status = (info or {}).get("status", {})
                ok = bool(status.get("is_placed_safe"))
                me = [s for s in _settled_items(env) if s["index"] == i]
                rec = {"i": i, "sku": name, "on": under, "commanded_bottom": round(bottom, 4), "ok": ok,
                       "status": {k: bool(v) for k, v in status.items()}}
                if me:
                    m = me[0]
                    rec["settle_disp"] = round(float(np.linalg.norm(np.asarray(m["pos"]) - np.array([x, y, z]))), 4)
                    rec["settle_tilt_deg"] = round(_tilt_deg(m["orn"], target_orn), 2)
                nominal_top[i] = nominal_bottom + dz
                steps.append(rec)
                if not ok:
                    break
            final = _settled_items(env)
            boxes = []
            for s in final:
                name, _x, _y, orn = plan[s["index"]]
                h = dims(name, orn)[2]
                target_orn = p.getQuaternionFromEuler(_orns()[orn])
                boxes.append({"i": s["index"], "sku": name, "soft": s["is_soft"],
                              "tilt_deg": round(_tilt_deg(s["orn"], target_orn), 2),
                              "floor_pen": round(FLOOR - float(s["aabb_min"][2]), 4) if not steps[s["index"]]["on"] else None,
                              "top": round(float(s["aabb_max"][2]), 4),
                              "nominal_top": round(nominal_top[s["index"]], 4),
                              "sink": round(nominal_top[s["index"]] - float(s["aabb_max"][2]), 4),
                              "own_height": round(float(s["aabb_max"][2] - s["aabb_min"][2]), 4),
                              "bottom": round(float(s["aabb_min"][2]), 4),
                              "nominal_height": round(h, 4)})
            from ground_handling.evaluator import Evaluator

            outside = {}
            for margin in (-0.005, 0.005):
                evaluator = Evaluator(client=env.client, config={"inclusion_margin": margin})
                _fill, out_items = evaluator.calculate_fill_rate(env.container_manager.containers)
                outside[str(margin)] = sorted(int(it.index) for it in out_items)
            metrics = terminal_metrics(env, with_shake=True)
            out = {"steps": steps, "boxes": boxes,
                   "placed": sum(1 for r in steps if r["ok"]), "planned": len(plan),
                   "fill_outside": outside,
                   "soft_covered": metrics.get("soft_covered"), "contact_covered": metrics.get("contact_covered"),
                   "shake_topples": metrics.get("shake_topples"), "shake_toppled": metrics.get("shake_toppled_items"),
                   "shake_max_shift": round(float(metrics.get("shake_max_shift", 0.0)), 4),
                   "shake_mean_shift": round(float(metrics.get("shake_mean_shift", 0.0)), 4)}
        finally:
            with contextlib.suppress(Exception):
                env.close()
    log = sink.getvalue().splitlines()
    out["not_safe"] = [l for l in log if "Not safe" in l or "not packable" in l or "collision" in l][-3:]
    return out


def _orns():
    from ground_handling.utils import ORNS

    return ORNS


# ---------------------------------------------------------------- the cases

SOFT = ["D", "E", "F", "G", "J"]
HARD = ["A", "B", "C", "H"]


def at_back(name: str, x_left: float, orn: int | None = None, y_back: float = Y_BACK):
    o = flat_orn(name) if orn is None else orn
    dx, dy, _dz = dims(name, o)
    return (name, x_left + dx / 2.0, y_back - dy / 2.0, o)


def case_single(soft: str, hard: str) -> list:
    """One hard box centred on one soft box."""
    s = at_back(soft, X_LEFT + 0.3)
    hd = dims(hard, flat_orn(hard))
    return [s, (hard, s[1], Y_BACK - hd[1] / 2.0, flat_orn(hard))]


def case_bridge(soft_a: str, soft_b: str, hard: str) -> list:
    """Two soft boxes side by side along x (the agent's gap), one hard box
    centred over the gap, its back on the back line."""
    a = at_back(soft_a, X_LEFT + 0.1)
    da = dims(soft_a, a[3])
    b = at_back(soft_b, X_LEFT + 0.1 + da[0] + GAP)
    gap_x = X_LEFT + 0.1 + da[0] + GAP / 2.0
    hd = dims(hard, flat_orn(hard))
    return [a, b, (hard, gap_x, Y_BACK - hd[1] / 2.0, flat_orn(hard))]


def row(names: list[str], x_left: float = X_LEFT, y_back: float = Y_BACK, x_right: float = 0.94) -> list:
    out, x = [], x_left
    for n in names:
        o = flat_orn(n)
        dx, _dy, _dz = dims(n, o)
        if x + dx > x_right + 1e-9:
            break
        out.append(at_back(n, x, o, y_back))
        x += dx + GAP
    return out


def case_rows(soft: list[str], hard: str, layers: int) -> list:
    """A soft row along the back wall, then ``layers`` hard rows on it."""
    out = row(soft)
    for _ in range(layers):
        out += row([hard] * 4)
    return out


def case_soft_storeys(soft: str, hard: str, storeys: int = 2) -> list:
    """``storeys`` soft boxes in a column, a hard box on top."""
    s = at_back(soft, X_LEFT + 0.3)
    hd = dims(hard, flat_orn(hard))
    return [s] * storeys + [(hard, s[1], Y_BACK - hd[1] / 2.0, flat_orn(hard))]


def case_hard_column(soft: str, hard: str, n_hard: int) -> list:
    """One soft box, ``n_hard`` hard boxes stacked on it."""
    s = at_back(soft, X_LEFT + 0.3)
    hd = dims(hard, flat_orn(hard))
    return [s] + [(hard, s[1], Y_BACK - hd[1] / 2.0, flat_orn(hard))] * n_hard


def case_block(soft: str, hard: str, layers: int, depth_rows: int = 2) -> list:
    """A soft floor of ``depth_rows`` rows from the back, then ``layers``
    hard layers of rows on it (the planner's form: soft first at the back,
    the hard rows riding on it)."""
    out = []
    y = Y_BACK
    soft_lines = []
    for _ in range(depth_rows):
        r = row([soft] * 4, y_back=y)
        out += r
        soft_lines.append(y)
        y -= dims(soft, flat_orn(soft))[1] + GAP
    hd = dims(hard, flat_orn(hard))
    depth_total = Y_BACK - y - GAP
    for _ in range(layers):
        yy = Y_BACK
        while Y_BACK - (yy - hd[1]) <= depth_total + 0.05:
            out += row([hard] * 4, y_back=yy)
            yy -= hd[1] + GAP
    return out


Y_FRONT = -0.704


def case_floor(soft_rows: list[str], hard: str, layers: int, front: bool = False) -> list:
    """The planner's form: soft rows on the floor from the back wall (one
    class a row, as many as fit the width), then ``layers`` layers of hard
    rows, over the soft rows only or (``front``) over the whole floor depth,
    the front rows on the floor."""
    out = []
    y = Y_BACK
    for name in soft_rows:
        out += row([name] * 4, y_back=y)
        y -= dims(name, flat_orn(name))[1] + GAP
    soft_front = y + GAP
    hd = dims(hard, flat_orn(hard))
    for _ in range(layers):
        yy = Y_BACK
        while yy - hd[1] >= (Y_FRONT if front else soft_front - 0.05):
            out += row([hard] * 4, y_back=yy)
            yy -= hd[1] + GAP
    return out


def cases() -> dict:
    c = {}
    for s in SOFT:
        for h in HARD:
            c[f"single/{s}+{h}"] = case_single(s, h)
    for s in ["D", "E", "F", "G"]:
        for h in ["A", "B", "C"]:
            c[f"bridge/{s}{s}+{h}"] = case_bridge(s, s, h)
    for a, b in [("E", "F"), ("F", "G"), ("E", "G"), ("D", "G")]:
        for h in ["A", "B", "C"]:
            c[f"bridge-mixed/{a}{b}+{h}"] = case_bridge(a, b, h)
    for s in ["E", "F", "G", "D"]:
        for h in ["A", "B"]:
            for layers in (1, 2, 3, 4):
                c[f"rows/{s}row+{layers}x{h}"] = case_rows([s] * 4, h, layers)
    for h in ["A", "B"]:
        for layers in (1, 2, 3):
            c[f"rows/mixed(FGEF)+{layers}x{h}"] = case_rows(["F", "G", "E", "F"], h, layers)
    for s in ["D", "E", "F", "G"]:
        for h in ["A", "B", "C"]:
            c[f"storeys/2x{s}+{h}"] = case_soft_storeys(s, h, 2)
    for s in ["E", "F", "G", "D"]:
        for h in ["A", "B", "C"]:
            for n in (2, 3, 4):
                c[f"column/{s}+{n}x{h}"] = case_hard_column(s, h, n)
    for s in ["E", "F", "G"]:
        for h in ["A", "B"]:
            for layers in (1, 2, 3):
                c[f"block/{s}2rows+{layers}x{h}"] = case_block(s, h, layers)
    for s in ["E", "F", "G"]:
        for h in ["A", "B"]:
            for layers in (3, 4, 5):
                c[f"floor-full/{s}x4+{layers}x{h}"] = case_floor([s] * 4, h, layers)
                c[f"floor-half/{s}x2+{layers}x{h}"] = case_floor([s] * 2, h, layers, front=True)
    for rows_ in (["G", "F", "F", "E"], ["F", "G", "F", "G"], ["G", "E", "G", "E"]):
        for h in ["A", "B"]:
            for layers in (3, 4):
                c[f"floor-mixed/{''.join(rows_)}+{layers}x{h}"] = case_floor(rows_, h, layers)
    return c


def _one(args):
    name, placements, control = args
    global CONTROL
    CONTROL = control
    try:
        return name, run(placements)
    except Exception as exc:  # pragma: no cover - a probe
        return name, {"error": repr(exc)}


def summary_line(name: str, r: dict) -> str:
    if "error" in r:
        return f"{name:34s} ERROR {r['error']}"
    hard = [b for b in r["boxes"] if not b["soft"]]
    hard_sink = max((b["sink"] for b in hard), default=0.0)
    disp = max((s.get("settle_disp", 0.0) for s in r["steps"]), default=0.0)
    tilt = max((b["tilt_deg"] for b in r["boxes"]), default=0.0)
    pen = max((b["floor_pen"] for b in r["boxes"] if b["soft"] and b["floor_pen"] is not None), default=0.0)
    top = max((b["top"] for b in r["boxes"]), default=0.0)
    soft_out = sum(1 for b in r["boxes"] if b["soft"] and b["i"] in r["fill_outside"]["0.005"])
    hard_out = sum(1 for b in r["boxes"] if not b["soft"] and b["i"] in r["fill_outside"]["0.005"])
    return (f"{name:30s} placed {r['placed']:2d}/{r['planned']:2d}  disp {disp:.3f}  tilt {tilt:5.2f}  "
            f"soft floor pen {pen:.3f}  hard sink {hard_sink:.3f}  top {top:.3f}  "
            f"topples {r['shake_topples']}  shake max {r['shake_max_shift']:.3f}  out(+5mm) soft {soft_out} hard {hard_out}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--control", action="store_true")
    args = ap.parse_args()
    global CONTROL
    CONTROL = bool(args.control)
    todo = [(k, v, CONTROL) for k, v in cases().items() if k.startswith(args.only)]
    results = {}
    with ProcessPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for name, r in pool.map(_one, todo):
            results[name] = r
            print(summary_line(name, r), flush=True)
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(results, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
