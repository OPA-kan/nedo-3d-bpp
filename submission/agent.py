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

# the "ladder-stable" settings the benchmarks were run with, plus the Task A
# offline phase, the relaxed last attempt before a decline and the time
# budgets inside the official limits (8 s a decision, 180 s offline)
OVERRIDES = dict(
    anchor_slack=0.0005, anchor_clamp=True, key_quantum=0.005,
    settle_sink_allowance=0.02, compaction_keeps_support=True,
    offline_dry_run=True, offline_budget_seconds=140.0,
    # the evaluation platform measured 7.2 s for the slowest decision with
    # a 6 s budget (its machine is slower than ours); 5 s keeps the same
    # decisions in almost every call and leaves room under the 8 s limit
    last_resort_relax=True, policy_budget_seconds=5.0,
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
    offline_planner="rows", plan_variants="after-hard", plan_min_support=0.0,
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
