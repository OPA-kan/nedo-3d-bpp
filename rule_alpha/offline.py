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


def order_variant(name: str, order: list[int], is_soft, is_prioritized) -> list[int]:
    """The order a plan-search variant hands the dry-run (config.plan_search_orders).

    The constructive order plays the soft cargo last, after the hard
    boxes have taken the room, and the dry-run's plan then carries 2-4 of
    15 soft boxes; a soft box placed is worth about three hard boxes'
    fill on the platform.  ``soft-at-NN`` moves the soft cargo in after
    the first NN percent of the normal hard boxes (the priority hard
    boxes stay first); ``soft-split`` puts half of it at the middle and
    the rest at the end; ``soft-interleaved`` one soft box after every
    third hard box past the first third; ``small-hard-first`` reverses
    the normal hard boxes (smallest footprint first); ``base`` and
    ``count-always`` leave the order alone (the latter changes the
    scratch's rules instead).  On a-c1-s0001 the base plan held 30 items
    with 4 soft, soft-at-25 23 items with 14 soft."""
    soft = [i for i in order if is_soft(i)]
    hard = [i for i in order if not is_soft(i)]
    prio_hard = [i for i in hard if is_prioritized(i)]
    rest = [i for i in hard if not is_prioritized(i)]
    if name.startswith("soft-at-"):
        share = float(name[len("soft-at-"):]) / 100.0
        k = int(round(len(rest) * share))
        return prio_hard + rest[:k] + soft + rest[k:]
    if name == "soft-split":
        k, h = len(rest) // 2, len(soft) // 2
        return prio_hard + rest[:k] + soft[:h] + rest[k:] + soft[h:]
    if name == "soft-interleaved":
        k = len(rest) // 3
        out, queue = prio_hard + rest[:k], list(soft)
        for j, i in enumerate(rest[k:]):
            out.append(i)
            if j % 3 == 2 and queue:
                out.append(queue.pop(0))
        return out + queue
    if name == "small-hard-first":
        return prio_hard + list(reversed(rest)) + soft
    return list(order)


def dry_run_order(agent, item_list: list[dict], order: list[int], deadline: float,
                  log=None, overrides: dict | None = None) -> tuple[list[int], list[dict]]:
    """Returns ``(order, plan)``: the items the core placed in the order it
    placed them, then the items not reached before ``deadline`` in their
    given order, then the deferred (declined) items.  ``overrides`` are
    config fields the scratch agent runs with (the plan search's
    count-always variant)."""
    by_index = {int(item["index"]): item for item in item_list}
    containers = copy.deepcopy(agent.board.containers)
    for container in containers:
        container.setdefault("packed_items", [])
    scratch = agent.scratch_copy(containers, item_list, overrides=overrides)
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
