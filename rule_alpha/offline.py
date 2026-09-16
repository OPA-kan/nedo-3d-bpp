"""Task A offline phase: the agent dry-runs itself over the order.

``optimize`` has the whole manifest, the containers and three minutes; the
online phase has one item at a time and ends at the first placement the
environment cannot make (there is no skip).  So the order handed back must
not carry an unplaceable item ahead of placeable ones.  The constructive
order is a rule and cannot know which items the core will decline on the
board as it will actually stand; the dry-run finds out by running the core
-- the same ladder and options, on a scratch copy of the containers, on the
analytic model -- and moves every declined item to the tail.

The dry-run also yields the plan the core would follow (item, container,
orientation, position per step), kept on the agent for a later replay.
"""

from __future__ import annotations

import copy
import time

from . import layer1


def dry_run_order(agent, item_list: list[dict], order: list[int], deadline: float,
                  log=None) -> tuple[list[int], list[dict]]:
    """Returns ``(order, plan)``: the items the core placed in the order it
    placed them, then the items not reached before ``deadline`` in their
    given order, then the deferred (declined) items."""
    by_index = {int(item["index"]): item for item in item_list}
    containers = copy.deepcopy(agent.board.containers)
    for container in containers:
        container.setdefault("packed_items", [])
    scratch = agent.scratch_copy(containers, item_list)
    board = layer1.Board(containers, agent.config)

    placed: list[int] = []
    deferred: list[int] = []
    plan: list[dict] = []
    remaining = list(order)
    longest = 0.0
    while remaining:
        # a decision that would overrun the deadline is not started: the
        # slowest one so far is the estimate of the next
        now = time.perf_counter()
        if now + longest >= deadline:
            break
        index = remaining.pop(0)
        item = by_index.get(index)
        if item is None:
            placed.append(index)
            continue
        # the board's own container dicts: ``Board.apply`` writes the packed
        # items there, and the scratch agent must see them
        observation = {"optimize": True, "lookahead_k": 1,
                       "container_list": board.containers, "pool_list": [dict(item)]}
        t0 = time.perf_counter()
        action = scratch.policy(observation)
        longest = max(longest, time.perf_counter() - t0)
        decision = scratch.last_decision
        if action is None or decision is None:
            deferred.append(index)
            if log:
                log(f"  [offline] item {index} declined -> tail")
            continue
        placement = decision.placement
        placement.step = len(placed) + 1
        board.apply(placement)
        placed.append(index)
        plan.append({"step": len(placed), "index": index,
                     "container_idx": int(action["container_idx"]),
                     "orientation": int(action["orientation"]),
                     "place_pos": [float(v) for v in action["place_pos"]],
                     "archetype": getattr(placement, "archetype", ""),
                     "packed_before": len(board.containers[int(action["container_idx"])]["packed_items"]) - 1})
    return placed + remaining + deferred, plan
