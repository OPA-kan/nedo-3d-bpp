"""
Post-shake attribute instrument: rebuild recorded episodes, shake, rescore.

Preregistered in reports/hazard/post-shake-instrument-protocol.md. The
local soft/priority proxy reads the settled state BEFORE the shake; the
official procedure may score after it. This instrument closes the gap
offline: rebuild each recorded episode's final settled state in a DIRECT
pybullet world, apply the official shake, and recompute the coverage
rules on the post-shake poses.

## Reconstruction methods (and their limits)

Two sources of truth per episode, selected by --from-snapshots:

1. Default (step-metrics mode). The run directory's
   evaluation_results.json written by scripts/run_test.py via
   run_risk_ablation. Each step in evaluation.step_metrics whose
   status.is_placed_safe is true records the placed item's settled
   world pose (settle_final_position / settle_final_quaternion, world
   frame; containers offset on world X only). validator.place_item
   removes unsafely-placed items from the world, so the safely-placed
   steps are exactly the official shake's item population
   (Evaluator._live_poses walks container.packed_items). This mode
   FAILED its fidelity gate (reports/hazard/post-shake/verdict.md):
   each pose is recorded at the item's OWN placement step and later
   placements disturb it unrecorded.

2. --from-snapshots (pose-snapshot mode). The run directory's
   policy-trace.jsonl, recorded with NEDO_POSE_SNAPSHOT=1
   (run_risk_ablation --pose-snapshot): every policy step appends a
   pose_snapshot event carrying the CURRENT pose of every packed item
   as the env itself reports it in the observation's container_list
   (containers.update_packed_items refreshes ALL packed poses after
   each safe placement). The LAST snapshot therefore sees every
   disturbance up to the final decision. It cannot see the final
   placement itself (no observation follows it), so any safe placement
   at a step >= the snapshot step is supplemented from that step's own
   settle_final pose in step_metrics -- the freshest record that
   exists for it. Remaining residual: whatever the final placement (or
   a terminal UNSAFE attempt's 300-step settle) moves afterwards is
   unrecorded in both modes. The trace file may span several cases;
   it is split into per-episode segments at the agent's init events,
   which run in config order -- the same order evaluation_results.json
   preserves.

The world is rebuilt with the OFFICIAL classes imported from
simulator/src/ground_handling -- not copies: MultiContainerManager.build
creates the real container mesh (open loading face at y=-width/2,
closed top, corner cut, shelves) with Container._create_body dynamics;
Item(**config_entry).spawn applies the official item dynamics with the
episode config's per-item overrides riding along, exactly as in the
recorded run. World setup mirrors env.reset_settings verbatim:
deterministicOverlappingPairs=1, gravity (0,0,-9.8), plane.urdf.

Items respawn at their recorded settled poses, then the world re-settles
under the builder's own loop (max 480 steps, velocity check after step
60, threshold 1 mm/s -- constants from MultiContainerManager.build),
repeated up to 5 rounds until the loop's own quiescence criterion
holds, before the shake. The repetition exists because the live
pre-shake world is quiescent (each placement stepped it a further 300
steps); a shake over still-moving bodies would measure rebuild motion,
not the shake. resettle_converged reports whether quiescence was
reached; resettle_max_shift reports how far the recorded poses moved,
which is the per-episode reconstruction-quality signal. The shake schedule, step counts and peak-KE probe run
through Evaluator's own constants and helpers (SHAKE_TILT_FRACTION,
SHAKE_STEPS_PER_PHASE, SHAKE_SETTLE_STEPS, SHAKE_BASE_GRAVITY,
_live_poses, _kinetic_energy) and the metrics through the official
shake_response_metrics, so no shake constant exists in this file to
drift. The one deviation from Evaluator.shake_test: no saveState /
restoreState bracket, because this instrument needs the POST-shake poses
that the official method deliberately discards (it restores so the
episode can continue; nothing here continues).

Known limits, stated rather than hidden:

1. Stale poses (step-metrics mode). An item's pose is recorded at ITS
   placement step; later placements (including the 300-step settle of a
   final UNSAFE attempt) can nudge it afterwards, and no later record
   exists. The pre-shake re-settle re-derives consistent contacts but
   cannot recover a later shift. The fidelity gate measured this and it
   is exactly what failed. Snapshot mode shrinks the stale window to
   the final placement's own disturbance (and a terminal unsafe
   settle), which remains unrecorded in both modes.
2. The recorded shake ran in the live end-of-episode world; the cloned
   shake runs in the rebuilt one. Solver state (velocities are zero at
   rebuild; warm-start caches differ) is not reproduced.
3. Episodes that placed zero items rebuild to an empty world and score
   zeros on both sides, mirroring shake_response_metrics([], [], 0).

## Post-shake coverage contract

The soft/priority rules are the published ones behind placement_score
and soft_item_score, exactly as encoded twice in this repo:
simulator/src/ground_handling/diagnostics.py calculate_attribute_placement
(final-state form, AABB overlap + CONTACT_TOLERANCE vertical gap) and
agent/agent.py candidate_attribute_violations (incremental form, same
overlap + tolerance). This file reimplements the test as pure geometry
(testable without pybullet): item B covers item A from above when their
XY footprints overlap by more than FOOTPRINT_EPSILON and B's underside
sits within CONTACT_TOLERANCE of A's top; an attribute item is violated
when covered by an item LACKING that attribute (soft-on-soft and
priority-on-priority are free); a priority item is additionally violated
by routing into a non-priority container only when a priority container
existed; clean ratios are None when the stream carries no such items.
The constants are copied from diagnostics.py and drift-guarded by a test
that compares them against the official module.

Verdict semantics come from the protocol's fidelity gate: Spearman of
cloned vs recorded shake_max_shift and shake_items_shifted >= 0.8,
cloned shake_items_toppled within +-1 of recorded on >= 80% of
episodes, and the clone reproducing the recorded sign of quiet_guard's
peak-KE excess over base when both arms are present. No constant may be
tuned to pass.
"""
from __future__ import annotations

import argparse
import copy
import glob
import json
import math
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
SIMULATOR = ROOT / "simulator"

# Copied from simulator/src/ground_handling/diagnostics.py; the drift
# guard in tests/test_measure_post_shake.py asserts equality against the
# official module.
CONTACT_TOLERANCE = 0.02
FOOTPRINT_EPSILON = 1e-6

# Preregistered fidelity-gate thresholds
# (reports/hazard/post-shake-instrument-protocol.md). Not tunable.
GATE_SPEARMAN_MIN = 0.8
GATE_TOPPLED_TOLERANCE = 1
GATE_TOPPLED_MATCH_RATE = 0.8
DIRECTION_ARM_A = "base"
DIRECTION_ARM_B = "quiet_guard"


# --- Pure half: geometry, coverage, statistics, gates ---


def aabb_from_pose(position, quaternion, dimensions):
    """World AABB of an oriented box from its centre pose and full dims."""
    x, y, z, w = (float(value) for value in quaternion)
    rotation = (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )
    half = [float(value) / 2.0 for value in dimensions]
    reach = [
        sum(abs(rotation[row][col]) * half[col] for col in range(3))
        for row in range(3)
    ]
    center = [float(value) for value in position]
    return (
        [center[axis] - reach[axis] for axis in range(3)],
        [center[axis] + reach[axis] for axis in range(3)],
    )


def footprint_overlap(lower, upper):
    a_min, a_max = lower["aabb_min"], lower["aabb_max"]
    b_min, b_max = upper["aabb_min"], upper["aabb_max"]
    dx = min(a_max[0], b_max[0]) - max(a_min[0], b_min[0])
    dy = min(a_max[1], b_max[1]) - max(a_min[1], b_min[1])
    return max(0.0, dx) * max(0.0, dy)


def covers_from_above(lower, upper):
    if footprint_overlap(lower, upper) <= FOOTPRINT_EPSILON:
        return False
    gap = float(upper["aabb_min"][2]) - float(lower["aabb_max"][2])
    return -CONTACT_TOLERANCE <= gap <= CONTACT_TOLERANCE


def _covered_count(items, attribute):
    violated = 0
    for lower in items:
        if not lower.get(attribute):
            continue
        for upper in items:
            if upper is lower or upper.get(attribute):
                continue
            if covers_from_above(lower, upper):
                violated += 1
                break
    return violated


def _clean_ratio(total, violations):
    # None, not 1.0: a stream with no such items has no opinion.
    if total == 0:
        return None
    return max(0.0, (total - min(total, violations)) / total)


def attribute_coverage(items, has_priority_container):
    """Soft/priority coverage on a list of item AABB dicts.

    Each item dict carries aabb_min, aabb_max, is_soft, is_prioritized,
    container_is_prioritized. Same semantics as the official
    calculate_attribute_placement, keyed post_shake_*.
    """
    priority_items = [i for i in items if i.get("is_prioritized")]
    soft_items = [i for i in items if i.get("is_soft")]
    misrouted = (
        sum(
            1
            for item in priority_items
            if not item.get("container_is_prioritized")
        )
        if has_priority_container
        else 0
    )
    covered_priority = _covered_count(items, "is_prioritized")
    covered_soft = _covered_count(items, "is_soft")
    return {
        "post_shake_priority_items": len(priority_items),
        "post_shake_soft_items": len(soft_items),
        "post_shake_priority_covered": covered_priority,
        "post_shake_priority_misrouted": misrouted,
        "post_shake_soft_covered": covered_soft,
        "post_shake_priority_clean": _clean_ratio(
            len(priority_items), covered_priority + misrouted
        ),
        "post_shake_soft_clean": _clean_ratio(len(soft_items), covered_soft),
    }


def _average_ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        stop = start
        while (
            stop + 1 < len(order)
            and values[order[stop + 1]] == values[order[start]]
        ):
            stop += 1
        rank = (start + stop) / 2.0 + 1.0
        for position in range(start, stop + 1):
            ranks[order[position]] = rank
        start = stop + 1
    return ranks


def spearman(xs, ys):
    """Spearman rank correlation with average ranks for ties.

    None when fewer than two pairs or either side has zero variance.
    """
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    rx = _average_ranks([float(v) for v in xs])
    ry = _average_ranks([float(v) for v in ys])
    mean_x = sum(rx) / len(rx)
    mean_y = sum(ry) / len(ry)
    var_x = sum((v - mean_x) ** 2 for v in rx)
    var_y = sum((v - mean_y) ** 2 for v in ry)
    if var_x <= 0.0 or var_y <= 0.0:
        return None
    covariance = sum(
        (a - mean_x) * (b - mean_y) for a, b in zip(rx, ry)
    )
    return covariance / math.sqrt(var_x * var_y)


def _arm_mean(rows, arm, key):
    values = [
        float(row[key])
        for row in rows
        if row.get("arm") == arm and row.get(key) is not None
    ]
    if not values:
        return None
    return sum(values) / len(values)


def evaluate_gates(joined_rows):
    """The three preregistered gates plus the direction check.

    joined_rows: dicts with arm, cloned_max_shift, recorded_max_shift,
    cloned_items_shifted, recorded_items_shifted, cloned_items_toppled,
    recorded_items_toppled, cloned_peak_ke, recorded_peak_ke.
    """
    n = len(joined_rows)
    rho_shift = spearman(
        [row["cloned_max_shift"] for row in joined_rows],
        [row["recorded_max_shift"] for row in joined_rows],
    )
    rho_shifted = spearman(
        [row["cloned_items_shifted"] for row in joined_rows],
        [row["recorded_items_shifted"] for row in joined_rows],
    )
    toppled_within = sum(
        1
        for row in joined_rows
        if abs(
            int(row["cloned_items_toppled"])
            - int(row["recorded_items_toppled"])
        )
        <= GATE_TOPPLED_TOLERANCE
    )
    toppled_rate = toppled_within / n if n else None

    direction = {"computable": False}
    means = {
        (arm, side): _arm_mean(joined_rows, arm, f"{side}_peak_ke")
        for arm in (DIRECTION_ARM_A, DIRECTION_ARM_B)
        for side in ("cloned", "recorded")
    }
    if all(value is not None for value in means.values()) and all(
        means[(DIRECTION_ARM_A, side)] > 0.0
        for side in ("cloned", "recorded")
    ):
        recorded_excess = (
            means[(DIRECTION_ARM_B, "recorded")]
            / means[(DIRECTION_ARM_A, "recorded")]
            - 1.0
        )
        cloned_excess = (
            means[(DIRECTION_ARM_B, "cloned")]
            / means[(DIRECTION_ARM_A, "cloned")]
            - 1.0
        )
        direction = {
            "computable": True,
            "arm_a": DIRECTION_ARM_A,
            "arm_b": DIRECTION_ARM_B,
            "recorded_peak_ke_excess": recorded_excess,
            "cloned_peak_ke_excess": cloned_excess,
            "sign_match": (
                (recorded_excess > 0) == (cloned_excess > 0)
                or (recorded_excess == 0 and cloned_excess == 0)
            ),
        }

    gates = {
        "episodes": n,
        "spearman_max_shift": rho_shift,
        "spearman_items_shifted": rho_shifted,
        "toppled_within_tolerance": toppled_within,
        "toppled_match_rate": toppled_rate,
        "direction": direction,
        "gate_spearman_max_shift": (
            rho_shift is not None and rho_shift >= GATE_SPEARMAN_MIN
        ),
        "gate_spearman_items_shifted": (
            rho_shifted is not None and rho_shifted >= GATE_SPEARMAN_MIN
        ),
        "gate_toppled": (
            toppled_rate is not None
            and toppled_rate >= GATE_TOPPLED_MATCH_RATE
        ),
        "gate_direction": (
            direction["sign_match"] if direction["computable"] else None
        ),
    }
    required = [
        gates["gate_spearman_max_shift"],
        gates["gate_spearman_items_shifted"],
        gates["gate_toppled"],
    ]
    # The direction gate binds only when both arms are present.
    if gates["gate_direction"] is not None:
        required.append(gates["gate_direction"])
    gates["verdict"] = "pass" if all(required) else "fail"
    return gates


# --- Episode extraction from run directories ---


def extract_placed(case_config, case_record):
    """Placed items with their recorded settled world poses.

    Returns (placed, skipped_steps). Only steps whose
    status.is_placed_safe is true contributed an item to the live shake
    world (validator.place_item removes failures), so only those are
    rebuilt.
    """
    item_by_index = {
        int(entry["index"]): entry
        for entry in case_config["item_stream"]["item_list"]
    }
    placed = []
    skipped = []
    steps = (case_record.get("evaluation") or {}).get("step_metrics") or []
    for step in steps:
        status = step.get("status") or {}
        if status.get("is_placed_safe") is not True:
            continue
        index = step.get("selected_item_index")
        position = step.get("settle_final_position")
        quaternion = step.get("settle_final_quaternion")
        if (
            index is None
            or int(index) not in item_by_index
            or position is None
            or quaternion is None
        ):
            skipped.append(int(step.get("step", -1)))
            continue
        placed.append(
            {
                "item_config": item_by_index[int(index)],
                "container_index": int(step.get("container_index", 0)),
                "position": [float(value) for value in position],
                "quaternion": [float(value) for value in quaternion],
            }
        )
    return placed, skipped


def parse_label(run_dir_name):
    """{case-ids}-{arm}-r{repeat}: arm names carry no dashes."""
    parts = run_dir_name.rsplit("-", 2)
    if len(parts) == 3 and parts[2].startswith("r"):
        try:
            return parts[1], int(parts[2][1:])
        except ValueError:
            pass
    return None, None


def _item_configs_by_index(case_config):
    """Every item config the episode can contain, keyed by index.

    The stream items plus any pre-packed container items (pre-packed
    items appear in pose snapshots too; the stream never reuses their
    indices)."""
    configs = {
        int(entry["index"]): entry
        for entry in case_config["item_stream"]["item_list"]
    }
    for container in (case_config.get("containers") or {}).get(
        "container_list", []
    ):
        for entry in container.get("packed_items") or []:
            configs.setdefault(int(entry["index"]), entry)
    return configs


def split_trace_episodes(trace_events):
    """Split a policy-trace event stream into per-episode segments.

    The agent appends one init event per episode (get_init_states), and
    run_test executes cases in config order, so segment i belongs to
    the i-th case of the run's config/evaluation_results.json. Events
    before the first init (none in practice) form a leading segment.
    """
    episodes = []
    current = None
    for event in trace_events:
        if event.get("event") == "init":
            current = [event]
            episodes.append(current)
            continue
        if current is None:
            current = [event]
            episodes.append(current)
            continue
        current.append(event)
    return episodes


def extract_placed_from_snapshots(case_config, case_record, trace_events):
    """Placed items from the LAST pose_snapshot event of one episode.

    The snapshot at policy step S carries the env-refreshed current
    pose (pos + orn quaternion, world frame) of every item packed by
    env steps 0..S-1, disturbances included. Safe placements the
    snapshot cannot contain -- normally exactly the final step's --
    are supplemented from their own settle_final pose in step_metrics,
    the freshest record that exists for them. Returns
    (placed, skipped_steps, info); raises ValueError when the trace has
    no pose_snapshot events.
    """
    snapshots = [
        event
        for event in trace_events
        if event.get("event") == "pose_snapshot"
    ]
    if not snapshots:
        raise ValueError("no pose_snapshot events in policy trace")
    snapshot = snapshots[-1]
    item_configs = _item_configs_by_index(case_config)
    placed = []
    seen = set()
    missing_pose = []
    for container in snapshot.get("containers") or []:
        container_index = int(container.get("container_index", 0))
        for entry in container.get("packed_items") or []:
            index = int(entry.get("index", -1))
            config = item_configs.get(index)
            position = entry.get("pos")
            quaternion = entry.get("orn")
            if config is None or position is None or quaternion is None:
                missing_pose.append(index)
                continue
            placed.append(
                {
                    "item_config": config,
                    "container_index": container_index,
                    "position": [float(value) for value in position],
                    "quaternion": [float(value) for value in quaternion],
                }
            )
            seen.add(index)
    snapshot_items = len(placed)

    # Supplement: safely-placed items absent from the snapshot (their
    # placement postdates it, or their snapshot pose was unreadable).
    supplemented = []
    skipped = []
    steps = (case_record.get("evaluation") or {}).get("step_metrics") or []
    for step in steps:
        status = step.get("status") or {}
        if status.get("is_placed_safe") is not True:
            continue
        index = step.get("selected_item_index")
        if index is None or int(index) in seen:
            continue
        index = int(index)
        config = item_configs.get(index)
        position = step.get("settle_final_position")
        quaternion = step.get("settle_final_quaternion")
        if config is None or position is None or quaternion is None:
            skipped.append(int(step.get("step", -1)))
            continue
        placed.append(
            {
                "item_config": config,
                "container_index": int(step.get("container_index", 0)),
                "position": [float(value) for value in position],
                "quaternion": [float(value) for value in quaternion],
            }
        )
        seen.add(index)
        supplemented.append(index)

    info = {
        "reconstruction": "snapshots",
        "snapshot_step": int(snapshot.get("step", -1)),
        "snapshot_events": len(snapshots),
        "snapshot_items": snapshot_items,
        "supplemented_item_indices": supplemented,
        "snapshot_missing_pose_indices": missing_pose,
    }
    return placed, skipped, info


# --- Physics half: rebuild and shake (requires pybullet) ---


def rebuild_and_shake(config, case_record, placed=None, skipped=None):
    """Rebuild the recorded final state and run the official shake.

    Returns the official shake_response dict plus post-shake coverage
    and rebuild diagnostics. Imports the simulator's own modules so the
    container mesh, item dynamics, shake schedule and metrics are the
    official code, not copies.

    placed=None extracts the step-metrics reconstruction (default
    mode). A caller passing a snapshot reconstruction supplies placed
    (and skipped) itself; pre-packed container items are then spawned
    from the snapshot poses like everything else, so the manager builds
    empty containers to avoid duplicating them.
    """
    if str(SIMULATOR) not in sys.path:
        sys.path.insert(0, str(SIMULATOR))
    import pybullet
    import pybullet_data
    from pybullet_utils import bullet_client
    from src.ground_handling.containers import MultiContainerManager
    from src.ground_handling.evaluator import Evaluator
    from src.ground_handling.items import Item

    containers_config = config["containers"]
    if placed is None:
        placed, skipped = extract_placed(config, case_record)
    else:
        skipped = list(skipped or [])
        containers_config = copy.deepcopy(containers_config)
        for entry in containers_config["container_list"]:
            entry["packed_items"] = []

    client = bullet_client.BulletClient(
        connection_mode=pybullet.DIRECT
    )
    try:
        client.setAdditionalSearchPath(pybullet_data.getDataPath())
        # World setup verbatim from env.reset_settings.
        client.setPhysicsEngineParameter(deterministicOverlappingPairs=1)
        client.setGravity(0, 0, -9.8)
        client.loadURDF("plane.urdf")
        manager = MultiContainerManager(
            client=client, config=containers_config
        )
        manager.build()

        for entry in placed:
            item = Item(**entry["item_config"])
            item.spawn(
                client,
                initial_pos=tuple(entry["position"]),
                initial_orn=tuple(entry["quaternion"]),
            )
            item.register_pos_orn(
                entry["container_index"],
                tuple(entry["position"]),
                tuple(entry["quaternion"]),
            )
            manager.get_container(entry["container_index"]).add_item(item)

        # Pre-shake re-settle: the builder's own loop
        # (MultiContainerManager.build: max 480 steps, velocity check
        # after step 60, 1 mm/s threshold), repeated up to 5 rounds
        # until its own criterion holds. The live pre-shake world is
        # quiescent (every placement stepped it 300 further steps), so
        # a shake launched over still-moving bodies would measure the
        # rebuild's leftover motion, not the shake. The criterion and
        # per-round constants are the official builder's; only the
        # repetition is ours, and it cannot move a settled body.
        resettle_steps = 0
        resettle_converged = False
        for _round in range(5):
            for step in range(480):
                client.stepSimulation()
                resettle_steps += 1
                if step > 60:
                    all_sleeping = True
                    for container in manager.containers:
                        for item in container.packed_items:
                            if item.pybullet_id is None:
                                continue
                            linear_v, angular_v = client.getBaseVelocity(
                                item.pybullet_id
                            )
                            if (
                                sum(abs(v) for v in linear_v) > 0.001
                                or sum(abs(v) for v in angular_v) > 0.001
                            ):
                                all_sleeping = False
                                break
                        if not all_sleeping:
                            break
                    if all_sleeping:
                        resettle_converged = True
                        break
            if resettle_converged:
                break

        evaluator = Evaluator(
            client=client,
            config={
                "inclusion_margin": config["validator"]["inclusion_margin"]
            },
        )

        # Re-settle drift: how far the recorded poses moved before the
        # shake -- a reconstruction-quality diagnostic, not a gate.
        resettle_shift = 0.0
        for container in manager.containers:
            for item in container.packed_items:
                pos, _ = item.get_pose(client)
                if pos is None or item.pos is None:
                    continue
                resettle_shift = max(
                    resettle_shift,
                    math.dist(
                        [float(v) for v in pos],
                        [float(v) for v in item.pos],
                    ),
                )

        # The official shake, driven by Evaluator's own constants and
        # helpers; no saveState/restoreState because the post-shake
        # poses are the point (see module docstring).
        before = evaluator._live_poses(manager.containers)
        peak_energy = 0.0
        if before:
            g = Evaluator.SHAKE_BASE_GRAVITY
            lateral = Evaluator.SHAKE_TILT_FRACTION * g
            schedule = [
                (lateral, 0.0, -g),
                (-lateral, 0.0, -g),
                (0.0, lateral, -g),
                (0.0, -lateral, -g),
            ]
            for gravity in schedule:
                client.setGravity(*gravity)
                for _ in range(Evaluator.SHAKE_STEPS_PER_PHASE):
                    client.stepSimulation()
                    peak_energy = max(
                        peak_energy, evaluator._kinetic_energy(before)
                    )
            client.setGravity(0.0, 0.0, -g)
            for _ in range(Evaluator.SHAKE_SETTLE_STEPS):
                client.stepSimulation()
        after = evaluator._live_poses(manager.containers)

        from src.ground_handling.diagnostics import shake_response_metrics

        metrics = shake_response_metrics(before, after, peak_energy)

        # Post-shake coverage on the live AABBs, matching the data
        # source of the official settled_snapshot (client.getAABB).
        coverage_items = []
        has_priority_container = any(
            bool(entry.get("is_prioritized", False))
            for entry in config["containers"]["container_list"]
        )
        prioritized_by_index = {
            int(entry["index"]): bool(entry.get("is_prioritized", False))
            for entry in config["containers"]["container_list"]
        }
        for container in manager.containers:
            for item in container.packed_items:
                if item.pybullet_id is None:
                    continue
                aabb_min, aabb_max = client.getAABB(item.pybullet_id)
                coverage_items.append(
                    {
                        "aabb_min": [float(v) for v in aabb_min],
                        "aabb_max": [float(v) for v in aabb_max],
                        "is_soft": bool(item.is_soft),
                        "is_prioritized": bool(item.is_prioritized),
                        "container_is_prioritized": prioritized_by_index.get(
                            int(container.index), False
                        ),
                    }
                )
        metrics.update(
            attribute_coverage(coverage_items, has_priority_container)
        )
        metrics.update(
            {
                "items_rebuilt": len(placed),
                "steps_skipped": skipped,
                "resettle_max_shift": float(resettle_shift),
                "resettle_steps": int(resettle_steps),
                "resettle_converged": bool(resettle_converged),
            }
        )
        return metrics
    finally:
        client.disconnect()


# --- Run-directory driver ---


def load_configs(config_paths):
    cases = {}
    for path in config_paths:
        payload = json.loads(
            pathlib.Path(path).read_text(encoding="utf-8")
        )
        for case_id, case_config in payload.items():
            cases.setdefault(case_id, case_config)
    return cases


def measure_run_dir(run_dir, configs, from_snapshots=False):
    """One row per case in the run dir's evaluation_results.json."""
    run_dir = pathlib.Path(run_dir)
    results_path = run_dir / "evaluation_results.json"
    if not results_path.exists():
        return []
    payload = json.loads(results_path.read_text(encoding="utf-8"))
    arm, repeat = parse_label(run_dir.name)
    trace_episodes = None
    if from_snapshots:
        trace_path = run_dir / "policy-trace.jsonl"
        trace_events = []
        if trace_path.exists():
            for line in trace_path.read_text(
                encoding="utf-8"
            ).splitlines():
                line = line.strip()
                if line:
                    trace_events.append(json.loads(line))
        trace_episodes = split_trace_episodes(trace_events)
    rows = []
    for case_position, (case_id, case_record) in enumerate(
        payload.items()
    ):
        if not isinstance(case_record, dict):
            continue
        config = configs.get(case_id)
        row = {
            "run_dir": str(run_dir),
            "label": run_dir.name,
            "case_id": case_id,
            "arm": arm,
            "repeat": repeat,
            "recorded": (case_record.get("evaluation") or {}).get(
                "shake_response"
            )
            or None,
        }
        if config is None:
            row["error"] = "no config for case"
        elif from_snapshots:
            row["reconstruction_mode"] = "snapshots"
            if case_position >= len(trace_episodes):
                row["error"] = (
                    "policy trace has fewer episodes than "
                    "evaluation_results.json has cases"
                )
            else:
                try:
                    placed, skipped, info = extract_placed_from_snapshots(
                        config,
                        case_record,
                        trace_episodes[case_position],
                    )
                    row["reconstruction"] = info
                    row["cloned"] = rebuild_and_shake(
                        config, case_record, placed=placed, skipped=skipped
                    )
                except Exception as error:  # surface, never drop
                    row["error"] = f"{type(error).__name__}: {error}"
        else:
            row["reconstruction_mode"] = "step_metrics"
            try:
                row["cloned"] = rebuild_and_shake(config, case_record)
            except Exception as error:  # surface, never silently drop
                row["error"] = f"{type(error).__name__}: {error}"
        rows.append(row)
    return rows


def join_for_gates(rows):
    joined = []
    for row in rows:
        cloned = row.get("cloned")
        recorded = row.get("recorded")
        if not cloned or not recorded:
            continue
        joined.append(
            {
                "label": row["label"],
                "case_id": row["case_id"],
                "arm": row["arm"],
                "cloned_max_shift": float(cloned["shake_max_shift"]),
                "recorded_max_shift": float(recorded["shake_max_shift"]),
                "cloned_items_shifted": int(cloned["shake_items_shifted"]),
                "recorded_items_shifted": int(
                    recorded["shake_items_shifted"]
                ),
                "cloned_items_toppled": int(cloned["shake_items_toppled"]),
                "recorded_items_toppled": int(
                    recorded["shake_items_toppled"]
                ),
                "cloned_peak_ke": float(
                    cloned["shake_peak_kinetic_energy"]
                ),
                "recorded_peak_ke": float(
                    recorded["shake_peak_kinetic_energy"]
                ),
                "resettle_max_shift": float(
                    cloned.get("resettle_max_shift", 0.0)
                ),
            }
        )
    return joined


# Reconstruction-quality stratification threshold for the DIAGNOSTIC
# section only (never the gate): an episode whose rebuilt poses moved
# more than the validator's own displacement_threshold (0.3 in these
# configs) during the pre-shake re-settle was materially disturbed
# after its poses were recorded, so the clone shakes a different state.
DIAGNOSTIC_DRIFT_THRESHOLD = 0.3


def render_markdown(validation):
    gates = validation["gates"]
    direction = gates["direction"]

    def fmt(value, digits=4):
        if value is None:
            return "-"
        return f"{value:.{digits}f}"

    mode = validation.get("reconstruction_mode", "step_metrics")
    lines = [
        "# Post-shake instrument fidelity verdict",
        "",
        "Protocol: `reports/hazard/post-shake-instrument-protocol.md`. "
        "Cloned = official shake re-run on the rebuilt final state; "
        "recorded = the episode's own end-of-run shake_response. "
        f"Reconstruction mode: `{mode}` "
        + (
            "(last pose_snapshot trace event, settle_final supplement "
            "for placements the snapshot postdates)."
            if mode == "snapshots"
            else "(per-step settle_final poses only)."
        ),
        "",
        f"- episodes joined: {gates['episodes']} "
        f"(arms: {json.dumps(validation['episodes_by_arm'], sort_keys=True)})",
        f"- Spearman shake_max_shift: {fmt(gates['spearman_max_shift'])} "
        f"(gate >= {GATE_SPEARMAN_MIN}: "
        f"{gates['gate_spearman_max_shift']})",
        f"- Spearman shake_items_shifted: "
        f"{fmt(gates['spearman_items_shifted'])} "
        f"(gate >= {GATE_SPEARMAN_MIN}: "
        f"{gates['gate_spearman_items_shifted']})",
        f"- toppled within +-{GATE_TOPPLED_TOLERANCE}: "
        f"{gates['toppled_within_tolerance']}/{gates['episodes']} "
        f"= {fmt(gates['toppled_match_rate'])} "
        f"(gate >= {GATE_TOPPLED_MATCH_RATE}: {gates['gate_toppled']})",
    ]
    if direction.get("computable"):
        lines.append(
            f"- peak-KE excess {direction['arm_b']} over "
            f"{direction['arm_a']}: recorded "
            f"{fmt(direction['recorded_peak_ke_excess'])}, cloned "
            f"{fmt(direction['cloned_peak_ke_excess'])} "
            f"(sign match: {direction['sign_match']})"
        )
    else:
        lines.append(
            "- peak-KE direction check: not computable "
            "(needs both arms with positive base mean)"
        )
    lines += [
        "",
        f"## Verdict: **{gates['verdict']}**",
        "",
    ]
    diagnostic = validation.get("diagnostic_low_drift") or {}
    subset_gates = diagnostic.get("gates_nonbinding")
    if subset_gates is not None:
        subset_direction = subset_gates["direction"]
        lines += [
            "## Non-binding diagnostic: low re-settle-drift episodes",
            "",
            "Same arithmetic on episodes whose rebuilt poses moved "
            f"<= {diagnostic['threshold']} m during the pre-shake "
            "re-settle (recorded poses still consistent with the live "
            "end state). Localizes failure between state "
            "reconstruction and the shake clone; carries NO verdict "
            "weight.",
            "",
            f"- episodes: {subset_gates['episodes']}",
            f"- Spearman shake_max_shift: "
            f"{fmt(subset_gates['spearman_max_shift'])}",
            f"- Spearman shake_items_shifted: "
            f"{fmt(subset_gates['spearman_items_shifted'])}",
            f"- toppled within +-{GATE_TOPPLED_TOLERANCE}: "
            f"{subset_gates['toppled_within_tolerance']}"
            f"/{subset_gates['episodes']} "
            f"= {fmt(subset_gates['toppled_match_rate'])}",
            (
                f"- peak-KE excess sign match: "
                f"{subset_direction['sign_match']} (recorded "
                f"{fmt(subset_direction['recorded_peak_ke_excess'])}, "
                f"cloned "
                f"{fmt(subset_direction['cloned_peak_ke_excess'])})"
                if subset_direction.get("computable")
                else "- peak-KE direction: not computable on subset"
            ),
            "",
        ]
    lines += [
        "| label | arm | max shift c/r | shifted c/r | toppled c/r "
        "| peak KE c/r | resettle drift | soft clean | priority clean |",
        "|---|---|---|---|---|---|---:|---:|---:|",
    ]
    joined_by_label = {
        row["label"]: row for row in validation["joined_rows"]
    }
    for row in validation["rows"]:
        joined = joined_by_label.get(row["label"])
        cloned = row.get("cloned") or {}
        if joined is None:
            lines.append(
                f"| {row['label']} | {row.get('arm')} "
                f"| not joined ({row.get('error', 'missing record')}) "
                f"| | | | | | |"
            )
            continue
        lines.append(
            f"| {row['label']} | {row['arm']} "
            f"| {joined['cloned_max_shift']:.3f}/"
            f"{joined['recorded_max_shift']:.3f} "
            f"| {joined['cloned_items_shifted']}/"
            f"{joined['recorded_items_shifted']} "
            f"| {joined['cloned_items_toppled']}/"
            f"{joined['recorded_items_toppled']} "
            f"| {joined['cloned_peak_ke']:.2f}/"
            f"{joined['recorded_peak_ke']:.2f} "
            f"| {joined['resettle_max_shift']:.3f} "
            f"| {fmt(cloned.get('post_shake_soft_clean'), 3)} "
            f"| {fmt(cloned.get('post_shake_priority_clean'), 3)} |"
        )
    lines += [
        "",
        "Coverage columns are the POST-shake soft/priority clean ratios "
        "recomputed under the published rules "
        "(see module docstring for the contract source). They are the "
        "instrument's payload once the gate passes; they take no part "
        "in the gate itself.",
    ]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild recorded episodes and apply the official "
        "shake (see module docstring)."
    )
    parser.add_argument(
        "--runs",
        action="append",
        required=True,
        help="Glob of run directories containing "
        "evaluation_results.json; repeatable.",
    )
    parser.add_argument(
        "--configs",
        action="append",
        required=True,
        help="Glob of episode config JSON files keyed by case id; "
        "repeatable.",
    )
    parser.add_argument(
        "--from-snapshots",
        action="store_true",
        help="Rebuild each episode from the LAST pose_snapshot event "
        "in its run's policy-trace.jsonl (recorded with "
        "NEDO_POSE_SNAPSHOT=1), supplemented by settle_final poses for "
        "safe placements the snapshot postdates. Default: rebuild from "
        "per-step settle_final poses alone (the mode that failed its "
        "fidelity gate).",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Join cloned metrics with each episode's recorded "
        "shake_response and adjudicate the preregistered gates.",
    )
    parser.add_argument("--output-json", type=pathlib.Path, required=True)
    parser.add_argument("--output-md", type=pathlib.Path)
    args = parser.parse_args()

    config_paths = sorted(
        {path for pattern in args.configs for path in glob.glob(pattern)}
    )
    run_dirs = sorted(
        {path for pattern in args.runs for path in glob.glob(pattern)}
    )
    if not config_paths:
        raise SystemExit("no config files matched --configs")
    if not run_dirs:
        raise SystemExit("no run directories matched --runs")
    configs = load_configs(config_paths)

    rows = []
    for run_dir in run_dirs:
        rows.extend(
            measure_run_dir(
                run_dir, configs, from_snapshots=args.from_snapshots
            )
        )

    payload: dict[str, Any] = {
        "reconstruction_mode": (
            "snapshots" if args.from_snapshots else "step_metrics"
        ),
        "rows": rows,
    }
    if args.validate:
        joined = join_for_gates(rows)
        by_arm: dict[str, int] = {}
        for row in joined:
            by_arm[str(row["arm"])] = by_arm.get(str(row["arm"]), 0) + 1
        payload["joined_rows"] = joined
        payload["episodes_by_arm"] = by_arm
        payload["gates"] = evaluate_gates(joined)
        # Non-binding diagnostic: the same gate arithmetic on the
        # episodes whose recorded poses survived the re-settle intact.
        # Localizes a failure to state reconstruction vs shake clone;
        # the preregistered verdict above is the only verdict.
        low_drift = [
            row
            for row in joined
            if row["resettle_max_shift"] <= DIAGNOSTIC_DRIFT_THRESHOLD
        ]
        payload["diagnostic_low_drift"] = {
            "threshold": DIAGNOSTIC_DRIFT_THRESHOLD,
            "episodes": len(low_drift),
            "gates_nonbinding": evaluate_gates(low_drift)
            if len(low_drift) >= 2
            else None,
        }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(args.output_json)
    if args.validate and args.output_md is not None:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(
            render_markdown(payload), encoding="utf-8"
        )
        print(args.output_md)
    if args.validate:
        print(json.dumps(payload["gates"], indent=1, default=str))
        return 0 if payload["gates"]["verdict"] == "pass" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
