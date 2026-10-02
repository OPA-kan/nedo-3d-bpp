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
# v32: the "first" variant (the priority cargo before everything on
# every layout) planned alongside: on the Task A physics suite the
# priority cargo placed 0.66 -> 0.78 a share, the loads 0.01 lower, for
# 1.8 fill points, every episode over the count threshold (48 of 48).
PLAN_VARIANTS = "first;after-hard"
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
# v23 (not adopted): soft cargo carries load in the analytic support
# model (soft on soft), and in the online tasks a soft item goes to the
# shelf gallery, onto soft cargo or onto a top no hard box could use
# before the hard cargo is tried.  Physics suites: A +2.65, B +4.92, C
# +4.65 items a scene, the centre of mass +0.02-0.045; the platform
# (v24, 36.58 against v18's 43.05) priced the height, Task B's halved
# priority cargo and the hard volume the soft galleries displace at
# three times the soft score's +18.  Off: v18's loads again.
SOFT_STRUCTURE = False
# v25: the soft headroom reserve sized for 0.9 of the soft volume (0.75
# in v18).  v19 moved it the other way (0.5: items +1.33 a scene, the
# centre of mass +0.015) and the platform scored it -2.61; 0.9 reverses
# that move at about the same size on the analytic A suite (items
# -1.54, centre of mass -0.017, the soft count and every episode's
# place above the count threshold kept).
SOFT_HEADROOM_SHARE = 0.9
# v24: (1) the cover veto counts a packed item as under the box when its
# bottom is below the box's bottom, whatever its top (the old test, a top
# at or below the bottom to the micron, let the stack option rest hard
# boxes on a soft box whose settled top sat a fraction of a millimetre
# above the rounded support top: every covered soft item on the Task C
# probes; the physics suites go from 0.08 / 0.10 / 0.29 covered a scene
# to 0 / 0 / 0.02, Task C -1.1 items a scene, A and B unchanged); (2) in
# the online tasks a soft item the stack option places off the floor
# needs 80 % of its footprint in contact (the flat soft boxes it put on
# the soft pile with a corner in the air were the topples: Task C 0.56 ->
# 0.21 a scene, the count unchanged on B and C).  On Task A the same rule
# cost 1.5 items a scene for no topple, so the offline phase turns it off.
# v25: off -- the rule was measured on v23's loads (soft on soft), and
# v25 changes one thing against v18
STACK_SOFT_MIN_SUPPORT = 0.0
STACK_SOFT_MIN_SUPPORT_TASK_A = 0.0


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
    soft_is_structure=SOFT_STRUCTURE, soft_first_when_free=SOFT_STRUCTURE,
    stack_soft_min_support=STACK_SOFT_MIN_SUPPORT,
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
    # v19 (not adopted): the reserve sized for half the soft volume gave
    # +1.3 items a scene on the physics suite with the centre of mass
    # 0.015 higher and topples 21 against 11, and the platform scored it
    # 40.44 against v18's 43.05 (cog -4.5, stability -4.2, placement
    # -5.55): a fourth hard layer on standing boxes is height and topples
    # the count does not cover.  0.75 again.
    reserve_headroom_for_soft=True, soft_headroom_volume_share=SOFT_HEADROOM_SHARE, soft_headroom_slack=0.05,
    # priority cargo carries load (only priority cargo may sit on it under
    # the cover rule): the priority container gets its second layer
    priority_is_structure=True,
    # v26: every chosen pose is tried in a private pybullet world that
    # mirrors the official placement test (rule_alpha/shadow.py: the same
    # sweep and settle) before it is committed; a pose that would be
    # rejected or fall is replaced by the next survivor, or the decision
    # goes on.  Physics suites against v18: +0.44 / +0.85 / +0.56 items a
    # scene on A / B / C, settle ends 4 -> 1 on B and C, the tail shorter.
    # 0.2-0.5 s a check inside the 4.5 s budget; without pybullet the
    # agent is v18.
    shadow_check=True,
    # v27: before a decline, every pose the geometry allows on the floor or
    # on a packed top (a dense anchor lattice, the analytic vetoes off, the
    # cover rule kept), lowest and best supported first, tried in the
    # shadow world until one stands.  Physics suites against v26: items
    # +0.65 / +1.00 / +0.96 a scene on A / B / C with no scene worse, the
    # soft count +0.27 / +0.98 / +0.44, episodes over half the items 30 ->
    # 34 (B) and 11 -> 17 (C), topples unchanged, CoM +0.002-0.006.  On a
    # Task B pool the resort may run 1.5 s past the budget (limit 10 s).
    physics_resort=True,
    # v29: the pocket guard -- a soft box the ladder would put on the floor
    # goes instead where the load keeps the most room (level, reachable
    # slots) for the big hard classes still expected, a Dirichlet prior
    # over the sample stream's classes updated with the items seen (the
    # manifest's counts on Task A, where the guard stays off under a plan).
    # Physics suites against v28 at the submission's budget: items C +1.15
    # a scene (20 up, 7 down; episodes over half the items 17 -> 22), B
    # +0.17 (34 -> 38), A within 0.1.
    pocket_guard=True,
    # v30: the count mode (rule_alpha/config.py).  The platform scores
    # every component but the fill as zero for an episode under a count
    # threshold near half the items, and the boards that end one to three
    # items short still hold shadow-safe poses, all on priority or soft
    # cargo, that the cover rule alone declines.  Under the threshold the
    # physics resort runs once more with the cover vetoes off and soft
    # tops as structure; above it the strict rules are back.  Physics
    # suites against v29 at this budget: items C +1.83 a scene (23 up, 2
    # down; episodes over half the items 22 -> 39), B +0.33 (38 -> 45), A
    # -0.15 (noise on the two-container scenes; 45 -> 47); priority boxes
    # covered 0 -> 20 on C's 48 scenes, soft 0 -> 8, 4 on B.
    # v31: the count pass is one resort pass (the poses that cover
    # nothing first, the pool's smallest item first, whole-top poses
    # before partial ones, a pose group dropped after three settle
    # failures in a row, a settle stopped once the box has fallen or
    # tipped) with count_mode_extra_seconds past the budget under the
    # threshold.  Physics suites against v30 at this budget: C +0.40
    # items (episodes over half 39 -> 43), B +0.44 (45 -> 48).
    count_mode=True,
    # v32: the threshold as strictly more than half (42 of 82; the
    # two-container suites end at exactly half often: C 6, B 2 of 48),
    # and under the threshold the resort's support floor at a quarter,
    # the shadow judging (c-c1s-s0003 20 -> 21, c-c2-s0006 40 -> 41).
    count_mode_strict=True, count_mode_min_support=0.25,
    # v33: the sweep-shade veto on Task C (rule_alpha/config.py): a pose
    # that walls off more than 0.15 m^2 of lower floor behind it from the
    # simulator's sweep is replaced or passed on.  The seven C episodes
    # still at or under the threshold after v32 were all sweep-blocked
    # by the ladder's door-side stacks; with the veto the C suite has
    # 47-48 of 48 over the threshold, +1.4 items and +1.2 fill a scene,
    # priority boxes covered 22 -> 11, topples 21 -> 15, CoM +0.010.
    # Off on A (it broke the plan replay) and B (it cost crossings).
    shade_veto_area=0.15, resort_shade_step=0.1,
    # v34: Task A plays the row planner's plan whenever it exists
    # (rule_alpha/config.py); the ladder's dry-run plan only when the
    # planner made none or its plan is under the count threshold.  Which
    # plan won the optimize race depended on how far the dry-run got in
    # the budget, so on the machine: the A suite's two samples of the
    # v33 form differed by soft +0.9 and fill -1.0 a scene on the
    # thirteen scenes where the plans differed.  With the preference
    # (`prefplan-core-a` against `v33-core-a`): soft +1.35 a scene,
    # priority +0.42, fill -1.6, CoM -0.019, 47-48 of 48 over the
    # threshold.
    plan_prefer_planner=True,
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

    def optimize(self, item_list: list):
        """Task A (the only task that calls this): the stack option's soft
        support share is the offline value.  The option reads its own copy
        of the config, so both are replaced."""
        self.config = dataclasses.replace(self.config, stack_soft_min_support=STACK_SOFT_MIN_SUPPORT_TASK_A)
        if self.stack_option is not None:
            self.stack_option.config = dataclasses.replace(
                self.stack_option.config, stack_soft_min_support=STACK_SOFT_MIN_SUPPORT_TASK_A)
        return super().optimize(item_list)

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
