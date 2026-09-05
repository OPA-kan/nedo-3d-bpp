"""Terminal quantities read from the official environment at episode end.

Everything here is read from PyBullet's settled state, never from the
planner's intent.  Each quantity is named by what it measures, and the two
fill definitions are both reported because they disagree on the shipped
config: ``inclusion_margin = -0.005`` drops every floor-resting item from
the evaluator's fill, so ``fill_evaluator_shipped`` is what the bundled
evaluator prints and ``fill_evaluator_tolerant`` is the same test with the
sign flipped to a 5 mm penetration tolerance.  ``fill_volume`` ignores the
inclusion test altogether.  None of them is the official score.
"""

from __future__ import annotations

import contextlib
import io
import math

import numpy as np

CONTACT_TOLERANCE = 0.02   # a cover: underside within this of the top below
TOPPLE_ANGLE_DEG = 30.0

SHAKE_TILT_FRACTION = 0.3
SHAKE_STEPS_PER_PHASE = 60
SHAKE_SETTLE_STEPS = 120
SHAKE_BASE_GRAVITY = 9.8


def _quiet(fn, *args, **kwargs):
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink):
        return fn(*args, **kwargs)


def _settled_items(env) -> list[dict]:
    client = env.client
    out = []
    for container in env.container_manager.containers:
        for item in container.packed_items:
            if item.pybullet_id is None:
                continue
            pos, orn = item.get_pose(client)
            if pos is None:
                continue
            aabb_min, aabb_max = client.getAABB(item.pybullet_id)
            out.append({
                "index": int(item.index),
                "container": int(container.index),
                "container_is_prioritized": bool(container.is_prioritized),
                "mass": float(item.mass),
                "volume": float(item.volume),
                "pos": [float(v) for v in pos],
                "orn": [float(v) for v in orn],
                "aabb_min": [float(v) for v in aabb_min],
                "aabb_max": [float(v) for v in aabb_max],
                "is_soft": bool(item.is_soft),
                "is_prioritized": bool(item.is_prioritized),
                "pybullet_id": item.pybullet_id,
            })
    return out


def _footprint_overlap(lower: dict, upper: dict) -> float:
    a0, a1 = lower["aabb_min"], lower["aabb_max"]
    b0, b1 = upper["aabb_min"], upper["aabb_max"]
    dx = min(a1[0], b1[0]) - max(a0[0], b0[0])
    dy = min(a1[1], b1[1]) - max(a0[1], b0[1])
    return max(0.0, dx) * max(0.0, dy)


def _covers_from_above(lower: dict, upper: dict) -> bool:
    if _footprint_overlap(lower, upper) <= 1e-6:
        return False
    gap = upper["aabb_min"][2] - lower["aabb_max"][2]
    return -CONTACT_TOLERANCE <= gap <= CONTACT_TOLERANCE


def attribute_violations(items: list[dict], has_priority_container: bool) -> dict:
    """The two published attribute rules, as counts (see COMPETITION_RULES)."""
    def covered(attribute: str) -> int:
        count = 0
        for lower in items:
            if not lower[attribute]:
                continue
            if any(
                upper is not lower and not upper[attribute]
                and _covers_from_above(lower, upper)
                for upper in items
            ):
                count += 1
        return count

    priority_items = [i for i in items if i["is_prioritized"]]
    soft_items = [i for i in items if i["is_soft"]]
    misrouted = (
        sum(1 for i in priority_items if not i["container_is_prioritized"])
        if has_priority_container else 0
    )
    return {
        "priority_count": len(priority_items),
        "priority_covered": covered("is_prioritized"),
        "priority_misrouted": misrouted,
        "soft_count": len(soft_items),
        "soft_covered": covered("is_soft"),
    }


def evaluator_fill(env, margin: float) -> float:
    from ground_handling.evaluator import Evaluator

    evaluator = Evaluator(client=env.client, config={"inclusion_margin": margin})
    score, _out = _quiet(evaluator.calculate_fill_rate, env.container_manager.containers)
    return float(score)


def shake_proxy(env, items: list[dict]) -> dict:
    """Vary gravity over the settled state; restore it afterwards.

    A local stand-in for the undisclosed stability test: reported as what
    moved, how far, and the peak kinetic energy.  No lid is modelled.
    """
    client = env.client
    if not items:
        return {"shake_mean_shift": 0.0, "shake_max_shift": 0.0,
                "shake_topples": 0, "shake_peak_kinetic_energy": 0.0}
    g = SHAKE_BASE_GRAVITY
    lateral = SHAKE_TILT_FRACTION * g
    schedule = [(lateral, 0, -g), (-lateral, 0, -g), (0, lateral, -g), (0, -lateral, -g)]
    state = client.saveState()
    peak = 0.0
    try:
        for gravity in schedule:
            client.setGravity(*gravity)
            for _ in range(SHAKE_STEPS_PER_PHASE):
                client.stepSimulation()
                energy = 0.0
                for entry in items:
                    lin, ang = client.getBaseVelocity(entry["pybullet_id"])
                    energy += 0.5 * entry["mass"] * (
                        sum(v * v for v in lin) + sum(v * v for v in ang)
                    )
                peak = max(peak, energy)
        client.setGravity(0, 0, -g)
        for _ in range(SHAKE_SETTLE_STEPS):
            client.stepSimulation()
        shifts, topples = [], 0
        for entry in items:
            pos, orn = client.getBasePositionAndOrientation(entry["pybullet_id"])
            shifts.append(float(np.linalg.norm(np.asarray(pos) - np.asarray(entry["pos"]))))
            dot = min(1.0, abs(float(np.dot(np.asarray(orn), np.asarray(entry["orn"])))))
            if math.degrees(2.0 * math.acos(dot)) > TOPPLE_ANGLE_DEG:
                topples += 1
    finally:
        client.setGravity(0, 0, -g)
        client.restoreState(stateId=state)
        client.removeState(state)
    return {
        "shake_mean_shift": float(np.mean(shifts)),
        "shake_max_shift": float(np.max(shifts)),
        "shake_topples": int(topples),
        "shake_peak_kinetic_energy": float(peak),
    }


def terminal_metrics(env, with_shake: bool = True) -> dict:
    items = _settled_items(env)
    containers = env.container_manager.containers
    total_items = int(env.num_total_items)
    usable = sum(float(c.volume) for c in containers)
    placed_volume = sum(i["volume"] for i in items)
    total_mass = sum(i["mass"] for i in items)
    floor_z = float(containers[0].thickness) if containers else 0.0
    com_z = (sum(i["mass"] * i["pos"][2] for i in items) / total_mass) if total_mass else 0.0
    height = float(containers[0].height) if containers else 1.0

    out = {
        "placed_count": len(items),
        "total_items": total_items,
        "placed_fraction": len(items) / total_items if total_items else 0.0,
        "placed_volume_m3": placed_volume,
        "fill_volume": 100.0 * placed_volume / usable if usable else 0.0,
        "fill_evaluator_shipped": evaluator_fill(env, -0.005),
        "fill_evaluator_tolerant": evaluator_fill(env, +0.005),
        "com_z": com_z,
        "com_z_above_floor_ratio": (com_z - floor_z) / height if height else 0.0,
        "per_container_count": {
            str(c.index): sum(1 for i in items if i["container"] == c.index)
            for c in containers
        },
    }
    out.update(attribute_violations(items, any(c.is_prioritized for c in containers)))
    if with_shake:
        out.update(shake_proxy(env, items))
    return out


# metrics whose paired difference is reported by bench.compare, with the
# direction that counts as an improvement
COMPARED = {
    "placed_count": "up",
    "fill_volume": "up",
    "fill_evaluator_tolerant": "up",
    "fill_evaluator_shipped": "up",
    "com_z_above_floor_ratio": "down",
    "priority_covered": "down",
    "priority_misrouted": "down",
    "soft_covered": "down",
    "shake_mean_shift": "down",
    "shake_topples": "down",
    "shake_peak_kinetic_energy": "down",
    # wall clock is reported, never used as evidence: it depends on the
    # machine and on what else was running
    "policy_time_max": "timing",
}
