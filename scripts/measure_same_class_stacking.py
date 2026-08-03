"""
Does the agent's stacking rule, which is stricter than the official one,
cost it the placements it dies on?

## The gap

`simulator/README.md:379` penalises a soft or priority item that is covered
from above by an item of a *different* attribute, and says so explicitly:
soft on soft and priority on priority are NOT penalised, and the two
attributes are evaluated independently.

`agent/agent.py` `support_surfaces()` admits a packed item as a support
surface only when it is neither soft nor prioritized. So the agent forbids
soft-on-soft and priority-on-priority, which the rules allow. If that ever
costs it a legal placement, it is throwing away candidates for nothing, and
the official log says placement_score 4.45 and soft_item_score 7.65 -- the
two worst components -- are exactly what those attributes govern.

## The question this answers, and only this one

46% of development episodes end at `unsafe_protocol_fallback` with zero
candidates. **At those states, would the relaxation have produced a valid
placement?**

If yes, the over-constraint is a cause and the fix is worth making. If no,
the fallback is not the cause but the final display: the episode was already
finished and the fallback is only where it became visible.

## Predictions, registered before the run

1. If no packed item at the fallback state is soft or prioritized, the
   over-constraint cannot be the cause. Decisive negative, and cheap.
2. If such items exist but the relaxation still yields nothing, the surfaces
   are unusable for other reasons (headroom, container inclusion, transport
   path). Negative, and it says the fix is cosmetic.
3. A positive requires a validated candidate that actually *rests on* a soft
   or priority packed item. A candidate that appears merely because the
   second search got luckier does not count, which is why both arms run at a
   fixed attempt budget rather than a wall-clock deadline.

## Method

The shipped agent drives a real episode. At every step where it falls back,
the observation is captured. On that captured state each visible item is
searched twice with the same fixed attempt budget: once with the shipped
support rule, once with `support_surfaces` patched to the official rule.
The relaxed hit is only counted when the winning candidate's underside sits
on a soft or priority packed item.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import importlib
import json
import pathlib
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
SIMULATOR = ROOT / "simulator"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_ATTEMPT_BUDGET = 4096


def official_stack_is_legal(
    packed_is_soft: bool,
    packed_is_priority: bool,
    item_is_soft: bool,
    item_is_priority: bool,
) -> bool:
    """simulator/README.md:379, transcribed.

    A soft item covered from above by a non-soft one loses points, and a
    priority item covered by a non-priority one loses points. Same-attribute
    stacking is explicitly free, and the two attributes are independent, so
    a packed item that is both needs a cover that is both.
    """
    if packed_is_soft and not item_is_soft:
        return False
    if packed_is_priority and not item_is_priority:
        return False
    return True


@contextlib.contextmanager
def relaxed_support_surfaces(agent_module, item):
    """Swap in the official rule for one item's search, then put it back."""
    original = agent_module.support_surfaces
    item_is_soft = bool(item.get("is_soft", False))
    item_is_priority = bool(item.get("is_prioritized", False))

    def patched(container):
        thickness = float(container["thickness"])
        buffer = float(container.get("buffer", 0.0))
        surfaces = [
            agent_module.AABB(
                center=(0.0, 0.0, thickness + buffer),
                size=(
                    float(container["length"]),
                    float(container["width"]),
                    0.0,
                ),
                name="floor",
            )
        ]
        surfaces.extend(agent_module.shelf_aabbs(container))
        for box, is_soft, is_priority in agent_module.packed_aabbs_local(
            container
        ):
            if official_stack_is_legal(
                is_soft, is_priority, item_is_soft, item_is_priority
            ):
                surfaces.append(box)
        return surfaces

    agent_module.support_surfaces = patched
    try:
        yield
    finally:
        agent_module.support_surfaces = original


def rests_on_restricted_item(agent_module, decision, containers):
    """Is this candidate standing on a soft or priority packed item?

    The whole claim is that the relaxation unlocked a surface. A candidate
    that landed on the floor proves nothing, so it is not counted.
    """
    index = int(decision.action["container_idx"])
    if not (0 <= index < len(containers)):
        return None
    container = containers[index]
    candidate = decision.candidate
    bottom = float(candidate.minimum[2])
    for box, is_soft, is_priority in agent_module.packed_aabbs_local(container):
        if not (is_soft or is_priority):
            continue
        if abs(bottom - float(box.top)) > agent_module.CONTACT_TOLERANCE:
            continue
        if agent_module.xy_overlap_area(candidate, box) <= agent_module.EPS:
            continue
        return {"is_soft": bool(is_soft), "is_prioritized": bool(is_priority)}
    return None


def restricted_surface_census(agent_module, containers):
    census = {"soft": 0, "prioritized": 0, "both": 0, "plain": 0}
    for container in containers:
        for _box, is_soft, is_priority in agent_module.packed_aabbs_local(
            container
        ):
            if is_soft and is_priority:
                census["both"] += 1
            elif is_soft:
                census["soft"] += 1
            elif is_priority:
                census["prioritized"] += 1
            else:
                census["plain"] += 1
    return census


def probe_state(agent_module, observation, attempt_budget, sweep=()):
    """Search every visible item under both rules at equal fixed work.

    The sweep is not decoration. The headline probe gives one item the
    whole budget, while the live search had to spread its 6.5 s over
    every (item, orientation, container) unit. Without knowing the
    budget at which placements start appearing, "a placement existed"
    cannot be separated from "we bought it with work the agent could
    never have spent", so the sweep is what makes the claim payable.
    """
    containers = observation.get("container_list", [])
    pool = observation.get("pool_list", [])
    census = restricted_surface_census(agent_module, containers)

    baseline_hits = []
    relaxed_hits = []
    total_seconds = 0.0
    for pool_index, item in enumerate(pool):
        indexed = [(pool_index, item)]
        # A fresh copy per search: the packed-AABB and board caches key on
        # list identity, and a patched run must not poison the baseline.
        baseline_observation = copy.deepcopy(observation)
        started = time.perf_counter()
        decision = agent_module.PlacementCore.choose(
            baseline_observation,
            indexed,
            attempt_budget=attempt_budget,
        )
        total_seconds += time.perf_counter() - started
        if decision is not None:
            baseline_hits.append(
                {
                    "pool_index": pool_index,
                    "item_index": int(item.get("index", pool_index)),
                    "kind": decision.candidate.name,
                }
            )
            continue

        relaxed_observation = copy.deepcopy(observation)
        with relaxed_support_surfaces(agent_module, item):
            relaxed = agent_module.PlacementCore.choose(
                relaxed_observation,
                indexed,
                attempt_budget=attempt_budget,
            )
        if relaxed is None:
            continue
        support = rests_on_restricted_item(
            agent_module, relaxed, relaxed_observation["container_list"]
        )
        if support is None:
            continue
        relaxed_hits.append(
            {
                "pool_index": pool_index,
                "item_index": int(item.get("index", pool_index)),
                "kind": relaxed.candidate.name,
                "item_is_soft": bool(item.get("is_soft", False)),
                "item_is_prioritized": bool(item.get("is_prioritized", False)),
                "stands_on": support,
            }
        )

    budget_curve = []
    for budget in sweep:
        hits = 0
        seconds = 0.0
        for pool_index, item in enumerate(pool):
            probe_observation = copy.deepcopy(observation)
            started = time.perf_counter()
            found = agent_module.PlacementCore.choose(
                probe_observation,
                [(pool_index, item)],
                attempt_budget=budget,
            )
            seconds += time.perf_counter() - started
            hits += found is not None
        budget_curve.append(
            {
                "attempts_per_item": int(budget),
                "items_with_a_placement": hits,
                "seconds_for_the_whole_pool": round(seconds, 3),
            }
        )

    return {
        "visible_items": len(pool),
        "packed_census": census,
        "baseline_hits": baseline_hits,
        "relaxed_only_hits": relaxed_hits,
        "headline_seconds_for_the_whole_pool": round(total_seconds, 3),
        "budget_curve": budget_curve,
    }


def run_case(
    agent_module,
    task_config,
    *,
    case_id: str,
    attempt_budget: int,
    max_states: int,
    sweep=(),
):
    if str(SIMULATOR) not in sys.path:
        sys.path.insert(0, str(SIMULATOR))
    from src.ground_handling.env import GroundHandlingEnv

    env = GroundHandlingEnv(config=task_config, verbose=False, render_mode=None)
    solver = agent_module.Agent("")
    states: list[dict[str, Any]] = []
    steps = 0
    try:
        env.reset_settings()
        solver.get_init_states(env.get_init_states())
        if env.optimize:
            order = solver.optimize(env.get_info_for_optimization())
            if not env.set_item_order(order):
                raise RuntimeError("agent returned an invalid optimized order")
        env.reset_item_stream()
        observation, _info = env.reset(seed=42)
        terminated = truncated = False
        while not terminated and not truncated:
            captured = copy.deepcopy(observation)
            action = solver.policy(observation)
            if (
                solver.last_action_source == "unsafe_protocol_fallback"
                and len(states) < max_states
            ):
                print(
                    f"  {case_id} step {steps}: fallback, probing",
                    flush=True,
                )
                probe = probe_state(
                    agent_module, captured, attempt_budget, sweep=sweep
                )
                probe["step"] = steps
                states.append(probe)
            observation, _reward, terminated, truncated, _info = env.step(
                action
            )
            steps += 1
    finally:
        with contextlib.suppress(Exception):
            env.close()
    return {"case_id": case_id, "steps": steps, "fallback_states": states}


def summarize(rows):
    probed = [s for row in rows for s in row["fallback_states"]]
    unlocked = [s for s in probed if s["relaxed_only_hits"]]
    with_surface = [
        s
        for s in probed
        if s["packed_census"]["soft"]
        + s["packed_census"]["prioritized"]
        + s["packed_census"]["both"]
        > 0
    ]
    leaked = [s for s in probed if s["baseline_hits"]]
    return {
        "episodes": len(rows),
        "fallback_states_probed": len(probed),
        "states_with_a_restricted_surface": len(with_surface),
        "states_unlocked_by_the_official_rule": len(unlocked),
        "states_where_the_baseline_itself_found_something": len(leaked),
        "verdict": (
            "no fallback state was probed"
            if not probed
            else "over-constraint is a cause"
            if unlocked
            else "over-constraint is not the cause at these states"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=pathlib.Path, action="append", required=True)
    parser.add_argument("--attempt-budget", type=int, default=DEFAULT_ATTEMPT_BUDGET)
    parser.add_argument("--max-states-per-case", type=int, default=2)
    parser.add_argument(
        "--sweep",
        default="16,64,256,1024",
        help=(
            "attempts-per-item budgets to sweep at each fallback state, "
            "so a found placement can be priced against what the live "
            "search could afford. Empty string disables."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=ROOT / "reports" / "same-class-stacking",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    sweep = tuple(
        int(value) for value in args.sweep.split(",") if value.strip()
    )

    agent_module = importlib.import_module("agent.agent")

    rows = []
    for config_path in args.config:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        for case_id, task_config in config.items():
            print(f"{case_id}: running", flush=True)
            rows.append(
                run_case(
                    agent_module,
                    task_config,
                    case_id=case_id,
                    attempt_budget=args.attempt_budget,
                    max_states=args.max_states_per_case,
                    sweep=sweep,
                )
            )

    summary = summarize(rows)
    payload = {
        "attempt_budget": args.attempt_budget,
        "official_rule": (
            "simulator/README.md:379 -- a soft or priority item may be "
            "covered by an item sharing that attribute without penalty; the "
            "two attributes are independent."
        ),
        "shipped_rule": (
            "agent/agent.py support_surfaces() admits a packed item only "
            "when it is neither soft nor prioritized."
        ),
        "summary": summary,
        "cases": rows,
    }
    (args.output_dir / "result.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
