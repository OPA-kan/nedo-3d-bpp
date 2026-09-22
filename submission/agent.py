"""NEDO ground-handling challenge: the rule-alpha agent with the learned
stack option, packaged for submission.

The official loader imports this module by name, constructs ``Agent`` with
the directory it lives in, and calls ``get_init_states``, ``optimize``
(Task A only) and ``policy``.  Everything else travels next to this file:
``rule_alpha`` (the ladder, its analytic model and the offline phase),
``wedge_rl`` (the stack option and its policy in numpy) and ``weights``.
No torch, no network; numpy only.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import sys

import numpy as np

_HERE = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from rule_alpha.agent import RuleAlphaAgent  # noqa: E402
from rule_alpha.config import DEFAULT_CONFIG  # noqa: E402

PLAN_LAYOUTS = 1
# v14 (not adopted): the three priority orders (after the normal hard
# cargo, mixed into the size order, last) planned one after the other,
# the best complete plan by the plan score used -- the physics suite had
# +0.67 priority items a scene and nothing covered by its AABB test, the
# platform scored placement -1.9 and soft -2.25 (total 37.38 against
# v12's 38.21 with more items placed): its contact-from-above test finds
# what the mixed and last orders put under other cargo.  v15 is v12's
# order again.
PLAN_VARIANTS = "after-hard"
PLAN_STANDING = True
REPLAY_CLEARANCE = 0.026
REPLAY_NUDGE = 0.0
CONSERVATIVE_TRANSPORT = False
COUNT_FIRST = True
# v13 (not adopted): a standing box only where its bottom is at or below
# this height -- the standing boxes the rows put on the fourth level
# (bottom 0.86 m) were 9 of v12's 15 topples on the physics suite, but
# v12's official stability score rose 8 points with those topples in, and
# the cap cost 0.7 items a scene; the count is what the platform pays for
PLAN_STANDING_MAX_BOTTOM = 10.0
# v18: the priority container's room.  Its priority rows are built up one
# row at a time (back rows to the ceiling, the front rows' floor free),
# the normal hard cargo the normal containers leave goes into its spare
# rows, the cover veto lets a pair a shelf separates through (the rule
# reads contact from above, and nothing touches through a shelf), and the
# soft headroom reserve counts only the soft cargo that may enter the
# container (in a priority container the soft priority cargo alone).  On
# three priority-container scenes the plan goes 48/42/40 -> 59/53/50 of
# 82 items (analytic).
PRIORITY_CONTAINER_ROOM = True

# the "ladder-stable" settings the benchmarks were run with, plus the Task A
# offline phase, the relaxed last attempt before a decline and the time
# budgets inside the official limits (8 s a decision, 180 s offline)
OVERRIDES = dict(
    anchor_slack=0.0005, anchor_clamp=True, key_quantum=0.005,
    settle_sink_allowance=0.02, compaction_keeps_support=True,
    offline_dry_run=True, offline_budget_seconds=140.0,
    # the evaluation platform measured 7.2 s for the slowest decision with
    # a 6 s budget (its machine is slower than ours) and 7.31 s with 5 s
    # once the pool was tried smallest first (v12); a call over the 8 s
    # limit is answered with a random action, so 4.5 s from v14
    last_resort_relax=True, policy_budget_seconds=4.5,
    # nothing above cargo of another attribute: on the 48-scene physics
    # suites it clears soft/priority coverage and halves the shake proxies
    # for -0.7 fill points (not significant) on Task C, nothing on Task A
    no_cover_other_attribute=True,
    # Task A with a priority container: priority cargo first, so it takes
    # that container's floor (three more priority boxes placed a scene on
    # that layout, shake energy 239 -> 168, fill -0.3 on the suite, n.s.)
    priority_cargo_first=True,
    # Task A: the manifest is packed offline by the row planner
    # (rule_alpha/planner.py) instead of dry-running the ladder: rows back
    # to front, layers on whole rows, the soft cargo on top under a
    # headroom the hard stacks keep free; the plan is replayed online and
    # the ladder takes over wherever a pose no longer fits the settled
    # board.  The planner takes a few seconds where the dry-run took the
    # whole budget on the evaluation machine.
    # With offline_dry_run on as well, the ladder's dry-run gets what is
    # left of the budget and the plan with the more volume is used: on a
    # slow machine the planner's full plan wins by itself.
    # v5's planner settings (one layout, standing boxes allowed): the v7
    # build (three layouts, flat only) scored 29.5 on the platform against
    # v5's 35.1 while the bench had it ahead, so the two are probed one at
    # a time from here; the replay tolerance and the conservative
    # transport model (safety fixes) are on
    offline_planner="rows", plan_variants=PLAN_VARIANTS, plan_layouts=PLAN_LAYOUTS, plan_min_support=0.0,
    plan_standing=PLAN_STANDING, plan_standing_max_bottom=PLAN_STANDING_MAX_BOTTOM,
    plan_normal_in_priority_container=PRIORITY_CONTAINER_ROOM, plan_priority_deep_first=PRIORITY_CONTAINER_ROOM,
    cover_veto_ignores_shelf=PRIORITY_CONTAINER_ROOM, soft_headroom_per_container=PRIORITY_CONTAINER_ROOM,
    # the two "safety fixes" of v9 (a tolerant re-check with a 2 cm nudge
    # at replay, the conservative transport model) cost 2.4 points on the
    # platform (cog -3.7, stability -4.2, placement -4.1) for nothing the
    # bench could see, so the replay is strict again and the production
    # transport rules are used: this reproduces the v5 build's decisions
    plan_replay_clearance=REPLAY_CLEARANCE, plan_replay_nudge=REPLAY_NUDGE,
    conservative_transport=CONSERVATIVE_TRANSPORT,
    # the platform zeroes every component but the fill for an episode
    # that places too few items, and the five official runs order by the
    # fraction placed: so the count comes first (small cargo first, rows
    # with the most boxes, the pool tried smallest first), and a plan is
    # judged by its count share above all
    count_first=COUNT_FIRST, plan_score_weights="1,0.5,0.5,3",
    # containers with a main shelf: the ladder's dry-run first would pack
    # 0.4 fill points more on the shelf layouts (30 s budget, analytic) but
    # place 3 of 15 soft items fewer; the official v5 result priced soft
    # and placement above that, so the planner goes first everywhere
    plan_dry_run_first_with_shelf=False,
    reserve_headroom_for_soft=True, soft_headroom_volume_share=0.75, soft_headroom_slack=0.05,
    # priority cargo carries load (only priority cargo may sit on it under
    # the cover rule): the priority container gets its second layer
    priority_is_structure=True,
)
STACK_POLICY = "weights/stack"


class Agent(RuleAlphaAgent):
    def __init__(self, module_path: str = ""):
        from wedge_rl.option import StackOption

        config = dataclasses.replace(DEFAULT_CONFIG, **OVERRIDES)
        base = pathlib.Path(module_path) if module_path else _HERE
        policy_dir = base / STACK_POLICY
        if not (policy_dir / "policy.npz").exists():
            policy_dir = _HERE / STACK_POLICY
        stack = StackOption(policy_dir, config) if (policy_dir / "policy.npz").exists() else None
        super().__init__(module_path=module_path, config=config, stack_option=stack)
        self.surrendered = 0

    def policy(self, observation: dict):
        """Always a well-formed action: the official app reads the action's
        keys before anything else, so a ``None`` (rule-alpha's decline)
        would crash it and lose the task instead of ending the episode.
        When nothing can be placed, a placement far above the container
        fails the inclusion check and ends the episode cleanly."""
        try:
            action = super().policy(observation)
        except Exception:
            action = None
        if action is not None:
            return action
        self.surrendered += 1
        return {"item_idx": 0, "container_idx": 0,
                "place_pos": np.asarray([0.0, 0.0, 50.0], dtype=np.float32), "orientation": 0}
