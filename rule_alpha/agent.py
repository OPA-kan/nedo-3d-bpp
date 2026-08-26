"""rule-alpha wearing the official agent interface.

This exists so the same Layer 1 rules can be driven by the real PyBullet
simulator (``rule_alpha/physics.py``) instead of the analytic model.  It is a
*prototype*, not a submission: it plans a first layer and then declines, which
is the honest behaviour for something that has no Layer 2.

``agent/agent.py`` remains the production policy and is untouched.
"""

from __future__ import annotations

import numpy as np

from . import classify as cls
from . import layer1
from .config import DEFAULT_CONFIG


class RuleAlphaAgent:
    """get_init_states / optimize / policy, the official three."""

    def __init__(self, module_path: str = "", config=None):
        self.config = config or DEFAULT_CONFIG
        self.board: layer1.Board | None = None
        self.profiles: dict[int, cls.ItemProfile] = {}
        self.last_decision: layer1.Decision | None = None
        self.zone_scales: dict | None = None
        self.triangle_profiles: list | None = None
        self.declined: list[int] = []

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

    # -- official interface ---------------------------------------------
    def get_init_states(self, init_states: dict):
        containers = init_states.get("container_list", [])
        self.board = layer1.Board(containers, self.config)
        return True

    def optimize(self, item_list: list):
        profiles = [
            cls.classify_item(int(item["index"]), item, self.config)
            for item in item_list
        ]
        self.profiles = {p.index: p for p in profiles}
        reference = None
        if self.board is not None and self.board.models:
            reference = next(
                (m for m in self.board.models if not m.is_prioritized),
                self.board.models[0],
            )
        if self.board is not None:
            self.zone_scales = self.board.set_zone_demand(profiles, self.config)
            self.triangle_profiles = profiles
        return layer1.constructive_order(profiles, self.config, reference)

    def policy(self, observation: dict):
        containers = observation.get("container_list", [])
        pool = observation.get("pool_list", [])
        # rebuild from the observation so the plan always reflects the settled
        # truth the simulator reports, not what rule-alpha hoped for
        self.board = layer1.Board(containers, self.config)
        self._reapply_zone_scales()

        profiles = []
        for pool_index, item in enumerate(pool):
            profile = cls.classify_item(int(item["index"]), item, self.config)
            profiles.append((pool_index, profile))

        ordered = sorted(
            profiles,
            key=lambda pair: (
                {
                    cls.NORMAL_HARD: 0,
                    cls.PRIORITY: 2,
                    cls.SOFT_PRIORITY: 3,
                    cls.SOFT: 4,
                }[pair[1].cargo_class],
                -round(pair[1].max_footprint, 6),
                pair[0],
            ),
        )

        for pool_index, profile in ordered:
            decision = layer1.choose_for_item(self.board, profile, self.config)
            if decision is None:
                continue
            self.last_decision = decision
            placement = decision.placement
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

        # Layer 1 is finished.  There is no Layer 2 in this prototype, so say so
        # rather than inventing a placement that would fail validation.
        self.last_decision = None
        self.declined.append(len(self.declined))
        return None


# The official loader imports the class by the fixed name ``Agent``.
Agent = RuleAlphaAgent
