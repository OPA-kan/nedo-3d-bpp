"""rule-alpha wearing the official agent interface.

This exists so the same Layer 1 rules can be driven by the real PyBullet
simulator (``rule_alpha/physics.py``) instead of the analytic model.  It is a
*prototype*, not a submission: it plans a first layer and then declines, which
is the honest behaviour for something that has no Layer 2.

``agent/agent.py`` remains the production policy and is untouched.
"""

from __future__ import annotations

import dataclasses
import time

import numpy as np

from . import classify as cls
from . import layer1
from .config import DEFAULT_CONFIG


class RuleAlphaAgent:
    """get_init_states / optimize / policy, the official three."""

    def __init__(self, module_path: str = "", config=None, selector=None, wedge_option=None,
                 stack_option=None):
        self.config = config or DEFAULT_CONFIG
        # optional external pick among the ladder's survivors; see
        # layer1.choose_for_item
        self.selector = selector
        # optional learned option asked before the ladder: a placement in the
        # chamfer strip, or a pass (wedge_rl.option.WedgeOption)
        self.wedge_option = wedge_option
        self.stack_option = stack_option
        self.board: layer1.Board | None = None
        self.profiles: dict[int, cls.ItemProfile] = {}
        self.last_decision: layer1.Decision | None = None
        self.zone_scales: dict | None = None
        self.triangle_profiles: list | None = None
        self.declined: list[int] = []
        # Task A: what the offline dry-run would place, step by step
        self.plan: list[dict] = []
        self.last_resort_used = 0

    def _resize_zones_for_what_is_left(self) -> None:
        """Re-sizes the reserved strips from the cargo still to come.

        The strips were sized once, from the whole manifest, and reapplied
        unchanged every step.  So on task 000 the front-right quadrant -- 0.61
        m^2 of soft and priority zone -- stayed closed to hard cargo for the
        entire episode, including after every soft item had already been
        housed.  What the reservation is for is the typed cargo that has *not*
        been placed yet, and that is a number the agent has.
        """
        if self.board is None or not self.config.zones_shrink_with_demand:
            return
        if not self.profiles:
            return
        placed = set()
        for container in self.board.containers:
            for packed in container.get("packed_items", []):
                placed.add(int(packed.get("index", -1)))
        outstanding = [
            profile for index, profile in self.profiles.items()
            if index not in placed
        ]
        if outstanding:
            self.zone_scales = self.board.set_zone_demand(
                outstanding, self.config
            )

    def _reapply_zone_scales(self) -> None:
        """The board is rebuilt from the observation each step; the manifest-
        derived strip widths have to survive that."""
        if not self.zone_scales or self.board is None:
            return
        for idx, scale in self.zone_scales.items():
            if idx < len(self.board.models):
                self.board.models[idx].set_zone_scales(
                    scale["soft_zone_scale"], scale["priority_zone_scale"]
                )
        if self.triangle_profiles:
            self.board.set_triangle_demand(self.triangle_profiles, self.config)
            self.board.set_foundation_demand(self.triangle_profiles, self.config)
            for placements in self.board.placements:
                for placement in placements:
                    self.board.foundation_pending.pop(placement.profile.index, None)
            for container in self.board.containers:
                for packed in container.get("packed_items", []):
                    self.board.foundation_pending.pop(int(packed.get("index", -1)), None)

    # -- official interface ---------------------------------------------
    def get_init_states(self, init_states: dict):
        containers = init_states.get("container_list", [])
        self.board = layer1.Board(containers, self.config)
        return True

    def _prepare_manifest(self, item_list: list) -> list:
        """What the whole manifest tells the agent before the stream starts:
        the profiles, and the zone and foundation demand on the board."""
        profiles = [
            cls.classify_item(int(item["index"]), item, self.config)
            for item in item_list
        ]
        self.profiles = {p.index: p for p in profiles}
        if self.board is not None:
            self.zone_scales = self.board.set_zone_demand(profiles, self.config)
            self.triangle_profiles = profiles
            self.board.set_foundation_demand(profiles, self.config)
        return profiles

    def scratch_copy(self, containers: list, item_list: list) -> "RuleAlphaAgent":
        """The same agent -- config, selector, options -- on its own board,
        for dry-runs that must not disturb this one's state."""
        # strict margins in the dry-run: a relaxed pose must never enter the
        # plan mid-order, where a failure would forfeit everything behind it
        config = dataclasses.replace(self.config, last_resort_relax=False)
        scratch = RuleAlphaAgent(config=config, selector=self.selector,
                                 wedge_option=self.wedge_option, stack_option=self.stack_option)
        scratch.get_init_states({"container_list": containers})
        scratch._prepare_manifest(item_list)
        return scratch

    def optimize(self, item_list: list):
        started = time.perf_counter()
        profiles = self._prepare_manifest(item_list)
        reference = None
        if self.board is not None and self.board.models:
            reference = next(
                (m for m in self.board.models if not m.is_prioritized),
                self.board.models[0],
            )
        order = layer1.constructive_order(profiles, self.config, reference)
        self.plan = []
        if self.config.offline_dry_run and self.board is not None and len(order) > 1:
            from .offline import dry_run_order

            deadline = started + float(self.config.offline_budget_seconds)
            order, self.plan = dry_run_order(self, item_list, order, deadline)
        return order

    def policy(self, observation: dict):
        containers = observation.get("container_list", [])
        pool = observation.get("pool_list", [])
        # rebuild from the observation so the plan always reflects the settled
        # truth the simulator reports, not what rule-alpha hoped for
        self.board = layer1.Board(containers, self.config)
        self._reapply_zone_scales()
        self._resize_zones_for_what_is_left()

        profiles = []
        for pool_index, item in enumerate(pool):
            profile = cls.classify_item(int(item["index"]), item, self.config)
            profiles.append((pool_index, profile))

        ordered = layer1.pool_order(profiles, self.config)

        # the wedge option speaks first: a placement in the strip beats the
        # ladder, a pass leaves the item to it
        if self.wedge_option is not None:
            for pool_index, profile in ordered:
                decision = self.wedge_option.propose(self.board, profile)
                if decision is not None:
                    self.last_decision = decision
                    return self._action(pool_index, decision.placement)

        for pool_index, profile in ordered:
            decision = layer1.choose_for_item(
                self.board, profile, self.config, selector=self.selector
            )
            if decision is None:
                continue
            self.last_decision = decision
            return self._action(pool_index, decision.placement)

        # Layer 1 is finished.  The stack option is the learned Layer 2: it
        # places on the boxes the ladder left, under the tower rule.
        if self.stack_option is not None:
            for pool_index, profile in ordered:
                decision = self.stack_option.propose(self.board, profile)
                if decision is not None:
                    self.last_decision = decision
                    return self._action(pool_index, decision.placement)

        # A decline ends the episode and scores no lower than a failed
        # attempt, so before declining try once with the margins relaxed to
        # just above the official validator's own.
        if self.config.last_resort_relax:
            action = self._last_resort(containers, ordered)
            if action is not None:
                return action

        # Nothing else, so say so rather than inventing a placement that
        # would fail validation.
        self.last_decision = None
        self.declined.append(len(self.declined))
        return None

    def _last_resort(self, containers: list, ordered: list) -> dict | None:
        relaxed = dataclasses.replace(
            self.config,
            settled_clearance=min(self.config.settled_clearance, self.config.last_resort_settled_clearance),
            com_margin=min(self.config.com_margin, self.config.last_resort_com_margin),
        )
        strict_config, strict_board = self.config, self.board
        self.config = relaxed
        self.board = layer1.Board(containers, relaxed)
        self._reapply_zone_scales()
        self._resize_zones_for_what_is_left()
        try:
            for pool_index, profile in ordered:
                decision = layer1.choose_for_item(self.board, profile, relaxed, selector=self.selector)
                if decision is not None:
                    decision.placement.reason = "last-resort: " + decision.placement.reason
                    self.last_decision = decision
                    self.last_resort_used += 1
                    return self._action(pool_index, decision.placement)
            if self.stack_option is not None:
                for pool_index, profile in ordered:
                    decision = self.stack_option.propose(
                        self.board, profile, tower_min=self.config.last_resort_tower_min,
                        extra_clearance=self.config.last_resort_extra_clearance)
                    if decision is not None:
                        decision.placement.reason = "last-resort: " + decision.placement.reason
                        self.last_decision = decision
                        self.last_resort_used += 1
                        return self._action(pool_index, decision.placement)
        finally:
            self.config, self.board = strict_config, strict_board
        return None

    def _action(self, pool_index: int, placement) -> dict:
        model = self.board.model(placement.container_idx)
        centre = layer1.action_center(
            placement.box, model,
            self.board.container(placement.container_idx), self.config,
        )
        return {
            "item_idx": pool_index,
            # positional index into observation["container_list"], which is
            # what the environment indexes its containers by
            "container_idx": int(placement.container_idx),
            "place_pos": np.asarray(centre, dtype=np.float32),
            "orientation": int(placement.orientation.index),
        }


# The official loader imports the class by the fixed name ``Agent``.
Agent = RuleAlphaAgent
