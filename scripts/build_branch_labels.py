"""
Long-horizon paired labels: run each sibling branch to the end of the episode.

Every short-horizon label this project has tried is now known to be unusable
for a board-value question:

* `placed-to-go` is confounded by step and occupied volume (Stage A, and the
  step correlations in Stage A');
* immediate settle survival is unrelated to option counts (Stage B, sign
  agreement exactly 0.500);
* 95.2% of Q-band sibling pairs tie on any short-horizon outcome at all.

So the label has to come from actually finishing the episode. For one state
`s` and siblings `a_1..a_K` drawn from the SAME candidate set, this forces
each `a_i` at its step and lets the shipped policy run free afterwards,
recording the final placed count and fill. The result is a genuinely paired
`Y(T_{a_i}(s))` that a board functional can later be scored against.

Three properties the design depends on, in order of how badly they would
break it:

1. **The prefix must be reproducible.** Branch labels are only comparable if
   every branch shares the same history. The control branch - forcing the
   action the unforced policy chose anyway - must reproduce the plain
   episode exactly. That is checked and reported per state rather than
   assumed; the search is deadline-limited, so reproducibility is an
   empirical property of the machine, not a guarantee.
2. **The agent is untouched.** Injection lives entirely in this driver's
   loop, so no shipped code path differs between the labelled run and a
   normal one.
3. **Siblings are selected offline** from the captured observation with a
   fixed attempt budget, using the same class-diverse rule as the rollout
   Top-K. Selecting them from a live deadline-limited search would make the
   sibling set itself depend on machine timing.

A forced action that the environment rejects is a legitimate outcome, not an
error: the branch simply ends there and its label is the placed count it
reached.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import statistics
import sys
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
SIMULATOR = ROOT / "simulator"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SIMULATOR) not in sys.path:
    sys.path.insert(0, str(SIMULATOR))

from scripts.measure_anchor_recall import (  # noqa: E402
    load_agent_module,
    policy_indexed_items,
    policy_observation,
)
from scripts.measurement_budget import record_from_env  # noqa: E402

SCHEMA_VERSION = 4


def _packed_world_aabb(packed: dict) -> tuple:
    """World AABB of a packed item from its observed pose and quaternion."""
    x, y, z, w = (float(v) for v in packed["orn"])
    rotation = np.asarray([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])
    dims = np.asarray([
        float(packed["length"]), float(packed["width"]), float(packed["height"])
    ])
    extent = np.abs(rotation) @ dims / 2.0
    center = np.asarray([float(v) for v in packed["pos"]])
    return center - extent, center + extent


def support_ledger(observation, container_idx, item, world_center, size):
    """Book the usable-support surface an action consumes and creates.

    Settled anchors exclude every soft/priority top, so a soft or
    prioritized item's own top is forbidden future support while a plain
    item's top is usable. Supporters are packed items in the same container
    whose top plane sits within the vertical window under the commanded
    base; their overlapped top area is booked by attribute. The commanded
    base is the release center for release candidates, so base heights are
    upper bounds there; `kind` is recorded beside this ledger for that
    reason.
    """
    base_z = float(world_center[2]) - float(size[2]) / 2.0
    x0 = float(world_center[0]) - float(size[0]) / 2.0
    x1 = float(world_center[0]) + float(size[0]) / 2.0
    y0 = float(world_center[1]) - float(size[1]) / 2.0
    y1 = float(world_center[1]) + float(size[1]) / 2.0
    footprint_area = (x1 - x0) * (y1 - y0)
    overlap = {"plain": 0.0, "soft": 0.0, "priority": 0.0}
    containers = observation.get("container_list", [])
    packed_items = (
        containers[container_idx].get("packed_items", [])
        if 0 <= container_idx < len(containers) else []
    )
    for packed in packed_items:
        low, high = _packed_world_aabb(packed)
        if not (base_z - 0.03 <= high[2] <= base_z + 0.01):
            continue
        width = min(x1, high[0]) - max(x0, low[0])
        depth = min(y1, high[1]) - max(y0, low[1])
        if width <= 0.0 or depth <= 0.0:
            continue
        if packed.get("is_soft", False):
            overlap["soft"] += width * depth
        elif packed.get("is_prioritized", False):
            overlap["priority"] += width * depth
        else:
            overlap["plain"] += width * depth
    item_is_plain = not (
        bool(item.get("is_soft", False)) or bool(item.get("is_prioritized", False))
    )
    on_floor = base_z <= 0.03
    consumed_usable = overlap["plain"] + (footprint_area if on_floor else 0.0)
    gained_usable = footprint_area if item_is_plain else 0.0
    return {
        "item_is_soft": bool(item.get("is_soft", False)),
        "item_is_prioritized": bool(item.get("is_prioritized", False)),
        "footprint_area": footprint_area,
        "base_z": base_z,
        "on_floor": on_floor,
        "supporter_overlap": overlap,
        "delta_usable_support": gained_usable - consumed_usable,
    }


BOARD_GRID_SIZE = 4


def board_features(observation) -> dict:
    """Whole-board decision-time features for the branch state.

    A per-container max-height grid in the container's local frame plus
    the visible-pool composition. Everything here is observable before the
    action is chosen; the deviation-trigger audit needs it because the
    sibling-set statistics alone scored chance on final placed.
    """
    grids = []
    heights = []
    for container in observation.get("container_list", []):
        length = float(container["length"])
        width = float(container["width"])
        center = [float(v) for v in container.get("center", (0.0, 0.0, 0.0))]
        grid = [[0.0] * BOARD_GRID_SIZE for _ in range(BOARD_GRID_SIZE)]
        for packed in container.get("packed_items", []):
            low, high = _packed_world_aabb(packed)
            x0, x1 = low[0] - center[0], high[0] - center[0]
            y0, y1 = low[1] - center[1], high[1] - center[1]
            for row in range(BOARD_GRID_SIZE):
                cell_x0 = -length / 2 + row * length / BOARD_GRID_SIZE
                cell_x1 = -length / 2 + (row + 1) * length / BOARD_GRID_SIZE
                for column in range(BOARD_GRID_SIZE):
                    cell_y0 = -width / 2 + column * width / BOARD_GRID_SIZE
                    cell_y1 = (
                        -width / 2 + (column + 1) * width / BOARD_GRID_SIZE
                    )
                    if (
                        x1 > cell_x0 and x0 < cell_x1
                        and y1 > cell_y0 and y0 < cell_y1
                    ):
                        grid[row][column] = max(
                            grid[row][column], float(high[2])
                        )
        grids.append([cell for row in grid for cell in row])
        heights.append(float(container.get("height", 0.0)))
    pool = observation.get("pool_list", [])
    return {
        "grid_size": BOARD_GRID_SIZE,
        "height_grids": grids,
        "container_heights": heights,
        "packed_count": sum(
            len(c.get("packed_items", []))
            for c in observation.get("container_list", [])
        ),
        "pool_count": len(pool),
        "pool_soft": sum(1 for p in pool if p.get("is_soft", False)),
        "pool_priority": sum(
            1 for p in pool if p.get("is_prioritized", False)
        ),
        "pool_volume": sum(
            float(p.get("length", 0.0)) * float(p.get("width", 0.0))
            * float(p.get("height", 0.0)) for p in pool
        ),
    }


def _top_candidate_decisions(decisions, limit, *, min_center_distance=0.05):
    """Greedy score-ordered pick with a spatial-diversity guard.

    A pool of one item offers no cross-item choice, so siblings must be
    alternative placements of the same item; near-duplicate poses would
    only produce tied pairs, hence the minimum center separation unless
    the container or orientation differs.
    """
    ordered = sorted(decisions, key=lambda d: -float(d.score))
    selected = []
    for decision in ordered:
        if len(selected) >= limit:
            break
        distinct = True
        for kept in selected:
            same_container = (
                kept.action["container_idx"] == decision.action["container_idx"]
            )
            same_orientation = (
                kept.action["orientation"] == decision.action["orientation"]
            )
            gap = float(np.linalg.norm(
                np.asarray(kept.action["place_pos"], dtype=float)
                - np.asarray(decision.action["place_pos"], dtype=float)
            ))
            if same_container and same_orientation and gap < min_center_distance:
                distinct = False
                break
        if distinct:
            selected.append(decision)
    return selected


def reconstruct_siblings(agent, observation, *, budget, limit,
                         mode="class_diverse"):
    """
    Deterministic sibling set from a fixed attempt budget.

    ``class_diverse`` keeps the rollout Top-K rule (best candidate per item
    class); ``top_candidates`` keeps the best-scored spatially distinct
    candidates regardless of item, which is the only informative axis when
    the visible pool holds a single item. No deadline is involved, so the
    sibling set does not depend on how fast this machine happens to be.
    """
    containers = observation.get("container_list", [])
    has_priority = any(
        bool(c.get("is_prioritized", False)) for c in containers
    )
    risk_lambda = (
        agent.RELEASE_RISK_RERANK_LAMBDA
        if agent.RELEASE_RISK_LIVE_RERANK
        else None
    )
    collector = agent.VisiblePoolRolloutCollector()
    indexed = policy_indexed_items(agent, observation)
    stream = agent.iter_prioritized_candidates(
        observation, indexed, attempt_budget=int(budget)
    )
    components_by_key = {}
    all_decisions = []
    for item_idx, item, container_idx, orientation, candidate in stream:
        container = containers[container_idx]
        score = agent.Ranker.score(candidate, item, container, has_priority)
        score, _p = agent.risk_adjusted_score(
            score, candidate, item, container, orientation, risk_lambda
        )
        immediate = agent.Ranker.evaluate(
            candidate, item, container, has_priority
        )
        decision = agent.PlacementDecision(
            action={
                "item_idx": int(item_idx),
                "container_idx": int(container_idx),
                "place_pos": np.asarray(
                    agent.simulator_action_center(candidate, container),
                    dtype=np.float32,
                ),
                "orientation": int(orientation),
            },
            candidate=candidate,
            score=float(score),
        )
        components_by_key[
            json.dumps(action_signature(decision.action), sort_keys=True)
        ] = {
            "components": {
                **immediate.components(),
                "immediate_total": float(immediate.total),
                "risk_penalty": float(immediate.total) - float(score),
            },
            "support_ledger": support_ledger(
                observation, int(container_idx), item,
                decision.action["place_pos"], candidate.size,
            ),
        }
        collector.observe(item_idx, item, container_idx, orientation, decision)
        all_decisions.append(decision)
    if mode == "top_candidates":
        selected = _top_candidate_decisions(all_decisions, max(1, int(limit)))
    else:
        selected = collector.snapshot(max(1, int(limit)))
    return selected, {
        json.dumps(action_signature(decision.action), sort_keys=True):
        components_by_key.get(
            json.dumps(action_signature(decision.action), sort_keys=True)
        )
        for decision in selected
    }


def state_fingerprint(observation):
    """
    Canonical digest of the parent state.

    Branch outcomes are only comparable if the state they branch FROM is the
    same object. Comparing terminal results without checking this would
    silently mix "this action is better" with "this repeat started somewhere
    else".
    """
    payload = {
        "containers": [
            sorted(
                (
                    int(item["index"]),
                    tuple(round(float(v), 6) for v in item.get("pos", ())),
                    tuple(round(float(v), 6) for v in item.get("orn", ())),
                )
                for item in container.get("packed_items", [])
            )
            for container in observation.get("container_list", [])
        ],
        "pool": [
            int(item.get("index", -1))
            for item in observation.get("pool_list", [])
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


def action_signature(action):
    return {
        "item_idx": int(action["item_idx"]),
        "container_idx": int(action["container_idx"]),
        "orientation": int(action["orientation"]),
        "place_pos": [round(float(v), 6) for v in action["place_pos"]],
    }


def run_episode(agent, task, *, force=None, capture_steps=()):
    """
    One episode driven directly, mirroring the reference driver's call order.

    `force` is {step: action}, applied instead of the policy's own. The policy
    is still called on a forced step, so its internal per-step state advances
    exactly as in an unforced run - only the emitted action is replaced.
    """
    from src.ground_handling.env import GroundHandlingEnv

    record_from_env(1)
    env = GroundHandlingEnv(config=task, verbose=False, render_mode=None)
    solver = agent.Agent("")
    captured: dict[int, Any] = {}
    fingerprints: dict[int, str] = {}
    chosen: dict[int, Any] = {}
    forced_accepted: dict[int, bool] = {}
    step = 0
    try:
        env.reset_settings()
        solver.get_init_states(env.get_init_states())
        env.reset_item_stream()
        raw_observation, _info = env.reset(seed=42)
        terminated = truncated = False
        while not terminated and not truncated:
            observation = policy_observation(env, raw_observation)
            if step in capture_steps:
                captured[step] = copy.deepcopy(observation)
            if force and step in force:
                fingerprints[step] = state_fingerprint(observation)
            action = solver.policy(observation)
            chosen[step] = action_signature(action)
            forcing = bool(force and step in force)
            if forcing:
                action = force[step]
            raw_observation, _reward, terminated, truncated, info = env.step(
                action
            )
            if forcing:
                forced_accepted[step] = bool(
                    isinstance(info, dict) and info.get("is_included")
                )
            step += 1
        evaluation = env.evaluate()
    finally:
        env.close()
    return {
        "steps": step,
        "captured": captured,
        "fingerprints": fingerprints,
        "forced_accepted": forced_accepted,
        "chosen": chosen,
        "evaluation": {
            key: value
            for key, value in evaluation.items()
            if key != "step_metrics"
        },
        "terminated": bool(terminated),
        "truncated": bool(truncated),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument(
        "--step", type=int, action="append", default=[],
        help="branch point; repeatable",
    )
    parser.add_argument("--siblings", type=int, default=3)
    parser.add_argument("--sibling-budget", type=int, default=4096)
    parser.add_argument(
        "--sibling-mode", default="class_diverse",
        choices=("class_diverse", "top_candidates"),
        help="top_candidates is for pool-1 cases where the only choice axis "
             "is where to place the single visible item",
    )
    parser.add_argument(
        "--repeats", type=int, default=1,
        help="re-runs of each forced branch; >1 measures sigma_branch",
    )
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    task_id = next(iter(config))
    task = config[task_id]
    agent = load_agent_module()
    steps = sorted(set(args.step or [6, 8, 10, 12]))

    # Two references. The capturing one supplies the parent observations; the
    # capture-free one is what controls are compared against, because
    # deep-copying an observation at every branch step can itself perturb a
    # deadline-limited search, and then the "control" would be measured
    # against a reference that this harness disturbed.
    print("reference A (capturing)", file=sys.stderr, flush=True)
    capturing = run_episode(agent, task, capture_steps=set(steps))
    print("reference B (capture-free)", file=sys.stderr, flush=True)
    clean = run_episode(agent, task)
    harness_perturbs = clean["evaluation"] != capturing["evaluation"]

    states = []
    for step in steps:
        observation = capturing["captured"].get(step)
        if observation is None:
            print(f"  step {step} unreached", file=sys.stderr)
            continue
        parent = state_fingerprint(observation)
        siblings, sibling_components = reconstruct_siblings(
            agent, observation,
            budget=args.sibling_budget, limit=args.siblings,
            mode=args.sibling_mode,
        )
        branches = []
        for index, decision in enumerate(siblings):
            forced = {
                "item_idx": int(decision.action["item_idx"]),
                "container_idx": int(decision.action["container_idx"]),
                "place_pos": np.asarray(
                    decision.action["place_pos"], dtype=np.float32
                ),
                "orientation": int(decision.action["orientation"]),
            }
            runs = []
            for repeat in range(max(1, int(args.repeats))):
                branch = run_episode(agent, task, force={step: forced})
                runs.append({
                    "repeat": repeat,
                    "steps": branch["steps"],
                    "evaluation": branch["evaluation"],
                    "parent_state_matches": (
                        branch["fingerprints"].get(step) == parent
                    ),
                    "forced_action_accepted": branch["forced_accepted"].get(
                        step
                    ),
                    "prefix_reproduced": all(
                        branch["chosen"].get(k) == capturing["chosen"].get(k)
                        for k in range(step)
                    ),
                })
                print(
                    f"  step {step} sib {index} run {repeat}: "
                    f"steps={branch['steps']} "
                    f"parent_ok={runs[-1]['parent_state_matches']} "
                    f"accepted={runs[-1]['forced_action_accepted']}",
                    file=sys.stderr, flush=True,
                )
            placed = [
                float(r["evaluation"].get("num_placed_items", 0.0))
                for r in runs
            ]
            fills = [
                float(r["evaluation"].get("fill_score", 0.0)) for r in runs
            ]
            branches.append({
                "sibling_index": index,
                "is_control": (
                    action_signature(forced) == capturing["chosen"].get(step)
                ),
                "action": action_signature(forced),
                "q": float(decision.score),
                "q_components": (sibling_components.get(
                    json.dumps(action_signature(forced), sort_keys=True)
                ) or {}).get("components"),
                "support_ledger": (sibling_components.get(
                    json.dumps(action_signature(forced), sort_keys=True)
                ) or {}).get("support_ledger"),
                "kind": str(decision.candidate.name),
                "runs": runs,
                "reproducibility": {
                    "repeats": len(runs),
                    "placed_identical": len(set(placed)) == 1,
                    "fill_identical": len(set(fills)) == 1,
                    "placed_sd": (
                        round(statistics.stdev(placed), 6)
                        if len(placed) > 1 else None
                    ),
                    "fill_sd": (
                        round(statistics.stdev(fills), 6)
                        if len(fills) > 1 else None
                    ),
                    "parent_state_matches_all": all(
                        r["parent_state_matches"] for r in runs
                    ),
                    "prefix_reproduced_all": all(
                        r["prefix_reproduced"] for r in runs
                    ),
                },
            })
        states.append({
            "step": step,
            "parent_fingerprint": parent,
            "board": board_features(observation),
            "branches": branches,
        })

    # State-level outcomes. A pair-level sign test would inflate n: three
    # siblings give three pairs out of three numbers, so at most two are
    # independent. One observation per branch state instead.
    state_outcomes = []
    for state in states:
        usable = [
            b for b in state["branches"]
            if b["reproducibility"]["prefix_reproduced_all"]
            and b["reproducibility"]["parent_state_matches_all"]
        ]
        if len(usable) < 2:
            continue
        def mean_placed(branch):
            return statistics.fmean(
                float(r["evaluation"].get("num_placed_items", 0.0))
                for r in branch["runs"]
            )
        q_best = max(usable, key=lambda b: b["q"])
        best = max(usable, key=mean_placed)
        ranked = sorted(usable, key=mean_placed, reverse=True)
        state_outcomes.append({
            "step": state["step"],
            "usable_branches": len(usable),
            "q_argmax_rank_by_outcome": ranked.index(q_best) + 1,
            "terminal_regret_placed_fraction": round(
                mean_placed(best) - mean_placed(q_best), 6
            ),
        })

    report = {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "config": args.config.as_posix(),
        "estimand": (
            "V^pi(T_a(s)): the value of a first action UNDER THE CURRENT "
            "SHIPPED POLICY, not an intrinsic board value V*. Everything "
            "downstream of the forced step differs - candidate sets, chosen "
            "actions, settle outcomes, search time, fallbacks. Only the map "
            "pi is held fixed, not the behaviour it produces."
        ),
        "instrument_validity": {
            "harness_perturbs_reference": harness_perturbs,
            "capturing_reference": capturing["evaluation"],
            "capture_free_reference": clean["evaluation"],
            "note": (
                "sigma_branch is the correct error term for a branch "
                "difference. The permutation sd measures variation across "
                "arrival orders of whole episodes and is a different "
                "variance axis; it must not be used to threshold branch "
                "differences."
            ),
        },
        "branch_steps": steps,
        "siblings_per_step": args.siblings,
        "sibling_mode": args.sibling_mode,
        "repeats": args.repeats,
        "states": states,
        "state_level_outcomes": state_outcomes,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "branch-labels.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "instrument_validity": report["instrument_validity"],
        "state_level_outcomes": state_outcomes,
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
