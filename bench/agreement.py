"""Does the analytic model agree with the official validator?

At each decision the ladder makes, the bench takes the candidates that
survived rule-alpha's own vetoes (``Decision.survivors``, all of which the
analytic ``validate`` accepted), samples some of them, and asks the official
validator the same question: inclusion, transport sweep, 300-step settle.
It also builds *perturbed* candidates -- the same box shifted a few
centimetres, or raised off its support -- runs ``validate`` on those, and
asks the validator again.  That gives every cell of the confusion matrix:

    analytic accept / physics accept    the case the planner relies on
    analytic accept / physics reject    the planner's false confidence
    analytic reject / physics accept    what the analytic model forbids
                                        but the competition would allow
    analytic reject / physics reject    agreement on the negative side

Each probe is run against a saved PyBullet state and the state is restored
afterwards, so probing does not change the episode being played.
"""

from __future__ import annotations

import contextlib
import io
import math
import random

import numpy as np

from rule_alpha import layer1
from rule_alpha._reuse import AABB

PERTURBATIONS = (
    ("shift-x", (+0.03, 0.0, 0.0)), ("shift-x", (-0.03, 0.0, 0.0)),
    ("shift-y", (0.0, +0.03, 0.0)), ("shift-y", (0.0, -0.03, 0.0)),
    ("shift-x", (+0.08, 0.0, 0.0)), ("shift-y", (0.0, -0.08, 0.0)),
    ("raise", (0.0, 0.0, +0.05)), ("raise", (0.0, 0.0, +0.12)),
)


def physics_verdict(env, container_idx: int, item, local_center, orientation: int) -> dict:
    """Official inclusion, transport and settle verdicts for one pose.

    The world is saved before and restored after, and the probe item is
    removed, so the episode continues from exactly where it was.
    """
    client = env.client
    validator = env.validator
    container = env.container_manager.get_container(container_idx)
    global_pos = container.local_to_global(tuple(float(v) for v in local_center))
    state = client.saveState()
    sink = io.StringIO()
    included = valid = safe = False
    settle_shift = None
    settle_angle = None
    try:
        with contextlib.redirect_stdout(sink):
            included = bool(validator.check_inclusion(container, item, global_pos, orientation))
            if included:
                valid = bool(validator.check_transport_path(container, item, global_pos, orientation))
                if valid:
                    safe = bool(validator.place_item(item, global_pos, orientation))
                    if safe and item.pybullet_id is not None:
                        pos, orn = item.get_pose(client)
                        settle_shift = float(np.linalg.norm(np.asarray(pos) - np.asarray(global_pos)))
                        from ground_handling.utils import ORNS
                        import pybullet as p
                        target = p.getQuaternionFromEuler(ORNS[orientation])
                        dot = min(1.0, abs(float(np.dot(np.asarray(orn), np.asarray(target)))))
                        settle_angle = math.degrees(2.0 * math.acos(dot))
    finally:
        if item.pybullet_id is not None:
            item.remove(client)
        client.restoreState(stateId=state)
        client.removeState(state)
    return {
        "is_included": included, "is_valid": valid, "is_placed_safe": safe,
        "accepted": included and valid and safe,
        "settle_shift": settle_shift, "settle_angle_deg": settle_angle,
        "validator_log": sink.getvalue()[-300:] if not (included and valid and safe) else "",
    }


def _candidate_record(candidate, tag: str) -> dict:
    return {
        "kind": tag,
        "surface": candidate.surface,
        "role": candidate.role,
        "family": candidate.family,
        "orientation": int(candidate.orientation.index),
        "center": [round(float(v), 4) for v in candidate.box.center],
        "size": [round(float(v), 4) for v in candidate.box.size],
        "archetypes": sorted(candidate.archetypes),
    }


def make_probe(config, per_decision: int = 4, perturbed_per_decision: int = 4, seed: int = 0):
    """Build the ``probe`` callback ``bench.episode.run_episode`` accepts."""
    rng = random.Random(seed)

    def probe(env, agent, action, step_index: int) -> dict:
        decision = getattr(agent, "last_decision", None)
        board = getattr(agent, "board", None)
        if decision is None or board is None:
            return {"step": step_index, "probes": []}
        survivors = list(decision.survivors or [])
        chosen = decision.chosen
        container_idx = int(action["container_idx"])
        item = env.stream_manager.get_item(int(action["item_idx"]))
        model = board.model(container_idx)
        container = board.container(container_idx)

        sample = [c for c in survivors if c is chosen]
        others = [c for c in survivors if c is not chosen]
        rng.shuffle(others)
        sample.extend(others[: max(0, per_decision - len(sample))])

        records = []
        for candidate in sample:
            centre = layer1.action_center(candidate.box, model, container, config)
            verdict = physics_verdict(env, container_idx, item, centre, candidate.orientation.index)
            records.append({
                **_candidate_record(candidate, "chosen" if candidate is chosen else "survivor"),
                "analytic_ok": True, "analytic_reason": "survivor",
                **verdict,
            })

        base_pool = sample if sample else survivors
        for _ in range(perturbed_per_decision):
            if not base_pool:
                break
            source = rng.choice(base_pool)
            name, delta = rng.choice(PERTURBATIONS)
            box = AABB(
                center=tuple(float(a) + float(b) for a, b in zip(source.box.center, delta)),
                size=tuple(float(v) for v in source.box.size),
                name="perturbed",
            )
            analytic_ok, reason = layer1.validate(box, model, container, config)
            centre = layer1.action_center(box, model, container, config)
            verdict = physics_verdict(env, container_idx, item, centre, source.orientation.index)
            records.append({
                **_candidate_record(source, "perturbed"),
                "perturbation": name, "delta": list(delta),
                "center": [round(float(v), 4) for v in box.center],
                "analytic_ok": bool(analytic_ok), "analytic_reason": reason,
                **verdict,
            })
        return {"step": step_index, "survivor_count": len(survivors), "probes": records}

    return probe


def confusion(records: list[dict]) -> dict:
    """Aggregate probe records into the 2x2 matrix plus per-reason detail."""
    cells = {"aa": 0, "ar": 0, "ra": 0, "rr": 0}
    by_reason: dict[str, dict] = {}
    by_kind: dict[str, dict] = {}
    for episode in records:
        for step in episode.get("probes", []):
            for probe in step.get("probes", []):
                a = bool(probe["analytic_ok"])
                p = bool(probe["accepted"])
                key = ("a" if a else "r") + ("a" if p else "r")
                cells[key] += 1
                reason = probe.get("analytic_reason", "?")
                slot = by_reason.setdefault(reason, {"n": 0, "physics_accepted": 0})
                slot["n"] += 1
                slot["physics_accepted"] += int(p)
                kind = probe.get("kind", "?")
                slot = by_kind.setdefault(kind, {"n": 0, "both_accept": 0, "analytic_only": 0,
                                                 "physics_only": 0, "both_reject": 0})
                slot["n"] += 1
                slot[{"aa": "both_accept", "ar": "analytic_only",
                      "ra": "physics_only", "rr": "both_reject"}[key]] += 1
    n = sum(cells.values())
    analytic_accepts = cells["aa"] + cells["ar"]
    analytic_rejects = cells["ra"] + cells["rr"]
    return {
        "n": n,
        "cells": cells,
        "false_accept_rate": cells["ar"] / analytic_accepts if analytic_accepts else None,
        "false_reject_rate": cells["ra"] / analytic_rejects if analytic_rejects else None,
        "agreement": (cells["aa"] + cells["rr"]) / n if n else None,
        "by_analytic_reason": by_reason,
        "by_kind": by_kind,
    }
