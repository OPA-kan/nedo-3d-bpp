"""The same episode on rule-alpha's analytic model instead of PyBullet.

A learning loop cannot afford the physics for every rollout, so it will run
on the analytic model (rule-alpha's ``validate``, transport sweep and
static stability).  That is only sound if the analytic episode's outcome
tracks the physics episode's outcome scene by scene.  This runner produces
records with the same schema as ``bench.episode`` so ``bench.compare`` can
put the two side by side: same scenes, same arm, same terminal quantities
where they exist.  Quantities that only physics can produce (evaluator
fill, shake) are omitted rather than invented.

The control flow mirrors the official one: ``optimize`` only on Task A, a
pool of ``look_ahead`` refilled after every pick, the episode ending when
the policy declines.  There is no failed placement on the analytic model --
every candidate it offers passed its own validator -- so ``inclusion``,
``transport`` and ``settle`` never appear as end reasons here.
"""

from __future__ import annotations

import time

import numpy as np

from rule_alpha import layer1

from .metrics import attribute_violations
from .scenes import SPACING


def _board_items(board: layer1.Board) -> list[dict]:
    items = []
    for idx, placements in enumerate(board.placements):
        model = board.model(idx)
        offset = idx * SPACING
        for placement in placements:
            lo = placement.box.minimum
            hi = placement.box.maximum
            items.append({
                "index": int(placement.profile.index),
                "container": int(model.index),
                "container_is_prioritized": bool(model.is_prioritized),
                "mass": float(placement.profile.mass),
                "volume": float(placement.volume),
                "pos": [float(placement.box.center[0]) + offset,
                        float(placement.box.center[1]), float(placement.box.center[2])],
                "aabb_min": [float(lo[0]) + offset, float(lo[1]), float(lo[2])],
                "aabb_max": [float(hi[0]) + offset, float(hi[1]), float(hi[2])],
                "is_soft": bool(placement.profile.is_soft),
                "is_prioritized": bool(placement.profile.is_prioritized),
            })
    return items


def analytic_metrics(board: layer1.Board, total_items: int) -> dict:
    items = _board_items(board)
    usable = sum(float(m.usable_volume) for m in board.models)
    placed_volume = sum(i["volume"] for i in items)
    total_mass = sum(i["mass"] for i in items)
    model0 = board.models[0]
    com_z = (sum(i["mass"] * i["pos"][2] for i in items) / total_mass) if total_mass else 0.0
    out = {
        "placed_count": len(items),
        "total_items": int(total_items),
        "placed_fraction": len(items) / total_items if total_items else 0.0,
        "placed_volume_m3": placed_volume,
        "fill_volume": 100.0 * placed_volume / usable if usable else 0.0,
        "com_z": com_z,
        "com_z_above_floor_ratio": (com_z - model0.z_floor) / model0.height if model0.height else 0.0,
        "per_container_count": {
            str(m.index): sum(1 for i in items if i["container"] == m.index) for m in board.models
        },
    }
    out.update(attribute_violations(items, any(m.is_prioritized for m in board.models)))
    return out


def run_analytic_episode(scene, arm, max_steps: int = 400, policy_budget: float = 8.0) -> dict:
    started = time.perf_counter()
    config = arm.config
    containers = scene.rule_alpha_containers()
    agent = arm(scene)
    agent.get_init_states({
        "optimize": scene.optimize, "lookahead_k": scene.look_ahead,
        "container_list": containers,
    })
    items = [dict(item) for item in scene.items]
    order = None
    optimize_seconds = 0.0
    if scene.optimize:
        t0 = time.perf_counter()
        order = agent.optimize([dict(item) for item in items])
        optimize_seconds = time.perf_counter() - t0
        by_index = {int(item["index"]): item for item in items}
        items = [by_index[int(i)] for i in order]

    board = layer1.Board(containers, config)
    queue = list(items)
    pool: list[dict] = []
    while len(pool) < scene.look_ahead and queue:
        pool.append(queue.pop(0))

    steps: list[dict] = []
    end_reason = "max-steps"
    for step_index in range(max_steps):
        if not pool:
            end_reason = "stream-exhausted"
            break
        observation = {
            "optimize": scene.optimize, "lookahead_k": scene.look_ahead,
            "container_list": board.containers, "pool_list": [dict(i) for i in pool],
        }
        t0 = time.perf_counter()
        action = agent.policy(observation)
        policy_seconds = time.perf_counter() - t0
        if action is None:
            steps.append({"step": step_index, "event": "declined",
                          "policy_seconds": round(policy_seconds, 4)})
            end_reason = "declined"
            break
        decision = agent.last_decision
        placement = decision.placement
        pool_index = int(action["item_idx"])
        item = pool.pop(pool_index)
        placement.step = step_index + 1
        board.apply(placement)
        steps.append({
            "step": step_index, "event": "step",
            "item_index": int(item["index"]), "pool_index": pool_index,
            "container_idx": int(action["container_idx"]),
            "orientation": int(action["orientation"]),
            "place_pos": [round(float(v), 4) for v in np.asarray(action["place_pos"])],
            "is_included": True, "is_valid": True, "is_placed_safe": True,
            "policy_seconds": round(policy_seconds, 4),
            "archetype": placement.archetype, "role": placement.role,
            "surface": placement.surface, "layer": int(placement.layer),
            "considered": int(decision.considered),
            "survivors": len(decision.survivors or []),
            "pos_local": [round(float(v), 4) for v in placement.box.center],
            "size": [round(float(v), 4) for v in placement.box.size],
        })
        while len(pool) < scene.look_ahead and queue:
            pool.append(queue.pop(0))
        if not pool:
            end_reason = "stream-exhausted"
            break

    metrics = analytic_metrics(board, len(scene.items))
    policy_times = [s["policy_seconds"] for s in steps]
    metrics.update({
        "policy_time_max": max(policy_times) if policy_times else 0.0,
        "policy_time_mean": float(np.mean(policy_times)) if policy_times else 0.0,
        "over_budget_steps": sum(1 for t in policy_times if t > policy_budget),
        "optimize_seconds": round(optimize_seconds, 3),
        "end_reason": end_reason,
        "attempted": sum(1 for s in steps if s.get("event") == "step"),
    })
    return {
        "scene": scene.name,
        "scene_spec": {k: v for k, v in scene.to_dict().items() if k not in ("items", "containers")},
        "arm": arm.describe(),
        "simulator": "analytic",
        "runtime_seconds": round(time.perf_counter() - started, 2),
        "order": order,
        "metrics": metrics,
        "steps": steps,
        "final_items": [
            {"index": i["index"], "container": i["container"], "pos": [round(v, 4) for v in i["pos"]]}
            for i in _board_items(board)
        ],
    }
