"""Why do stacked boxes fail in the simulator?  (``wedge_rl probe``)

Replays the stack arrangements of one policy on the held-out boards in
PyBullet with the validator's own log captured, and records for every
stacked placement: the analytic features at planning time (support
patches, contact ratio, centre-of-mass margin, bottom, orientation, what it
rests on, commanded lift, transport height) and the physics outcome
(accepted; settle displacement and angle when it failed; the collision
partner when the transport failed; how far the supporting boxes had
drifted from their planned poses before the placement).
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import random
import re
import numpy as np

from bench.episode import run_episode
from rule_alpha import layer1, stability

from .env import PASS
from .replay import FixedPose, ScriptedArm, scene_for

NOT_SAFE = re.compile(r"Not safe place \(disp: ([0-9.]+)m, angle: ([0-9.]+)deg\)\. Item (\d+) removed")
COLLISION = re.compile(r"collision: (\d+) and (\d+)(\((?:small )?shelf\))? at \((.*?)\)(?:, distance ([-0-9.e]+))?$", re.M)
FLOAT = re.compile(r"-?[0-9]+\.?[0-9]*(?:e-?[0-9]+)?")


def plan_with_features(env, policy, seed):
    """(item, candidate, features) for every placement, the board's boxes first."""
    env.reset(seed)
    rng = random.Random(seed)
    cfg = env.config
    placed = []
    for packed in env.board["container"]["packed_items"]:
        placed.append((dict(packed), FixedPose(packed), None))
    while not env.done:
        item = env.item
        a = policy(env, rng)
        cands = env.candidates()
        if a != PASS and cands:
            c = cands[a]
            st = stability.evaluate(c.box, env.container, cfg)
            supports = stability.supporting_items(c.box, env.container, cfg.contact_tolerance)
            commanded = layer1.action_center(c.box, env.model, env.container, cfg)
            samples = layer1.transport_samples(c.box, env.container)
            dx, dy, dz = c.dims
            feats = {
                "bottom": float(c.bottom), "dims": [dx, dy, dz], "tall": bool(dz > max(dx, dy) + 1e-9),
                "footprint": dx * dy, "contact_ratio": float(min(1.0, st.contact_area / max(dx * dy, 1e-9))),
                "patches": int(st.contact_count), "com_margin": float(st.margin) if np.isfinite(st.margin) else -9.0,
                "supports": [{"index": int(p["index"]), "layer": int(p.get("layer", 1)), "soft": bool(p.get("is_soft")),
                              "top": round(float(p["pos"][2]) + float(p["dims"][2]) / 2.0, 4),
                              "dims": [round(float(v), 3) for v in p["dims"]]} for p in supports],
                "lift": float(commanded[2] - c.box.center[2]),
                "transport_z_bottom": float(samples[0].minimum[2]) if samples else None,
                "mass": float(item["mass"]), "soft": bool(item["is_soft"]),
                "n_stack_below": sum(1 for p in supports if int(p.get("layer", 1)) == 2),
            }
            placed.append((item, c, feats))
        env.step(a)
    return placed


def probe_factory(plan, records):
    def probe(env, agent, action, step_index):
        container = env.container_manager.get_container(0)
        drift = {}
        for it in container.packed_items:
            if it.pybullet_id is None:
                continue
            pos, _orn = it.get_pose(env.client)
            local = container.global_to_local(tuple(float(v) for v in pos))
            planned = plan[int(it.index)].box.center
            drift[int(it.index)] = [round(float(local[0] - planned[0]), 4), round(float(local[1] - planned[1]), 4),
                                    round(float(local[2] - planned[2]), 4)]
        records[step_index] = drift
        return {"n": len(drift)}
    return probe


def probe_many(env, policy, label: str, seeds, out_path, log=print):
    """Every stacked placement of ``policy`` on ``seeds``, one JSON row each,
    appended to ``out_path``."""
    out = pathlib.Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fh:
        for seed in seeds:
            placed = plan_with_features(env, policy, seed)
            plan = {i: c for i, (_it, c, _f) in enumerate(placed)}
            scene = scene_for([(it, c) for it, c, _f in placed], env.layout, seed)
            drifts = {}
            sink = io.StringIO()
            with contextlib.redirect_stdout(sink):
                record = run_episode(scene, ScriptedArm(plan, env.config, label), max_steps=len(placed) + 1,
                                     probe=probe_factory(plan, drifts), with_shake=False, verbose=True)
            log = sink.getvalue()
            not_safe = {int(m.group(3)): (float(m.group(1)), float(m.group(2))) for m in NOT_SAFE.finditer(log)}
            collisions = {}
            for m in COLLISION.finditer(log):
                at = [float(v) for v in FLOAT.findall(m.group(4))]
                at = [v for v in at if abs(v) < 10][-3:] if len(at) > 3 else at  # np.float32(...) wrappers carry no digits
                collisions.setdefault(int(m.group(1)), []).append({"with": int(m.group(2)), "kind": (m.group(3) or "item").strip("()"),
                                                                   "at": at, "distance": float(m.group(5)) if m.group(5) else None})
            fixed = sum(1 for _it, c, _f in placed if isinstance(c, FixedPose))
            for s in record["steps"]:
                if s.get("event") != "step":
                    continue
                idx = int(s["item_index"])
                if idx < fixed:
                    continue
                _it, c, feats = placed[idx]
                drift = drifts.get(int(s["step"]), {})
                sup_drift = [drift.get(p["index"]) for p in feats["supports"]]
                sup_drift = [d for d in sup_drift if d is not None]
                colls = collisions.get(idx)
                if colls:
                    for cl in colls:
                        if cl["kind"] == "item" and cl["with"] < len(placed):
                            pc = placed[cl["with"]][1]
                            cl["partner_top"] = round(float(pc.box.maximum[2]), 4)
                            cl["partner_drift"] = drift.get(cl["with"])
                row = {"label": label, "seed": seed, "item": idx, "ok": bool(s["is_included"] and s["is_valid"] and s["is_placed_safe"]),
                       "is_valid": bool(s["is_valid"]), "is_placed_safe": bool(s["is_placed_safe"]),
                       "end_reason": record["metrics"]["end_reason"] if not (s["is_valid"] and s["is_placed_safe"]) else None,
                       **feats,
                       "support_drift_xy_max": max((float(np.hypot(d[0], d[1])) for d in sup_drift), default=0.0),
                       "support_drift_z_max": max((abs(d[2]) for d in sup_drift), default=0.0),
                       "any_drift_xy_max": max((float(np.hypot(d[0], d[1])) for d in drift.values()), default=0.0),
                       "settle": not_safe.get(idx), "collisions": colls}
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                log(f"[{label} s{seed} item {idx}] ok={row['ok']} bottom={feats['bottom']:.2f} ratio={feats['contact_ratio']:.2f} "
                      f"margin={feats['com_margin']:.3f} patches={feats['patches']} lift={feats['lift']:.3f} "
                      f"drift={row['support_drift_xy_max']:.3f} settle={row['settle']} coll={len(collisions.get(idx, []))}")
