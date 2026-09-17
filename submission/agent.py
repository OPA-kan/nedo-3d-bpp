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
    last_resort_relax=True, policy_budget_seconds=6.0,
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
