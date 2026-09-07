"""The wedge policy as an option inside rule-alpha.

rule-alpha keeps the upper level: which item to try, which container, every
attribute rule, the ladder.  Before the ladder looks at an item, the option
is asked once: given the strip as it is now (neighbours included), does the
learned policy put this item in the strip, or pass?  A placement wins over
the ladder; a pass hands the item back unchanged.  When the strip is closed
the generator yields no candidate and the option is silent, so no gate has
to be written by hand.

Scope, deliberately narrow for the first integration:

* hard, non-priority items only.  The policy was trained without attribute
  rules, so soft and priority cargo stay with the ladder, which knows them.
* the strip of the container rule-alpha would route the item to first.
* ``remaining`` was the fraction of a 14-item stream left during training;
  here it counts down from the option's first call in each container, which
  reproduces what the policy saw (a fresh strip with about 14 items to come).
"""

from __future__ import annotations

import pathlib

import numpy as np

from rule_alpha import classify as cls
from rule_alpha import layer1

from .env import (FEATURE_SIZE, PASS, Candidate, grid_shape, play_region, strip_candidates,
                  strip_observation)

ARCHETYPE = "wedge-rl"


class WedgeOption:
    def __init__(self, policy_dir: str | pathlib.Path, config, x_extent: float = 0.80,
                 horizon: int = 14, max_candidates: int = 96):
        import torch

        from .ppo import Policy

        self.policy_dir = pathlib.Path(policy_dir)
        self.config = config
        self.x_extent = x_extent
        self.horizon = horizon
        self.max_candidates = max_candidates
        self._torch = torch
        self._policy_cls = Policy
        self._policies: dict[tuple[int, int], object] = {}
        self.calls: dict[int, int] = {}      # container idx -> items offered so far
        self.placed = 0
        self.passed = 0

    # ------------------------------------------------------------------
    def _policy(self, nx: int, ny: int):
        key = (nx, ny)
        if key not in self._policies:
            policy = self._policy_cls(nx, ny)
            policy.load_state_dict(self._torch.load(self.policy_dir / "policy.pt"))
            policy.eval()
            self._policies[key] = policy
        return self._policies[key]

    def wants(self, profile: cls.ItemProfile) -> bool:
        return profile.cargo_class == cls.NORMAL_HARD

    def propose(self, board: layer1.Board, profile: cls.ItemProfile) -> layer1.Decision | None:
        """The policy's placement for this item, or None for pass."""
        if not self.wants(profile):
            return None
        item = profile.item
        for container_idx in layer1.routing_order(profile, board, self.config):
            model = board.model(container_idx)
            container = board.container(container_idx)
            x_max_play, z_top = play_region(model, self.x_extent)
            cands = strip_candidates(model, container, self.config, profile, x_max_play, z_top,
                                     self.max_candidates)
            if not cands:
                continue
            nx, ny = grid_shape(model, x_max_play)
            seen = self.calls.get(container_idx, 0)
            remaining = max(0.0, (self.horizon - seen) / self.horizon)
            self.calls[container_idx] = seen + 1
            obs = strip_observation(model, container, nx, ny, z_top, item, remaining)
            action = self._decide(nx, ny, obs, cands, _Region(model, x_max_play, z_top))
            if action == PASS:
                self.passed += 1
                return None
            self.placed += 1
            return self._decision(cands[action], cands, profile, container_idx, model)
        return None

    def _decide(self, nx, ny, obs, cands, region) -> int:
        from .ppo import decode

        policy = self._policy(nx, ny)
        feats = np.stack([c.features(region) for c in cands])
        with self._torch.no_grad():
            logits = policy.logits(policy.embed(obs), feats)
        return decode(logits, len(cands))

    def _decision(self, cand: Candidate, cands, profile, container_idx, model) -> layer1.Decision:
        orientation = next(o for o in profile.orientations if o.index == cand.orientation)
        surface = "floor" if cand.on_floor else "item"
        candidate = layer1.Candidate(
            box=cand.box, profile=profile, orientation=orientation, container_idx=container_idx,
            surface=surface, surface_name=surface, role=cls.ROLE_WEDGE_STEP if cand.strip_gain > 0 else cls.ROLE_NONE,
            family="wedge-rl",
            features={"strip_gain": cand.strip_gain, "support_ratio": cand.support_ratio,
                      "margin": cand.margin, "reach": float(model.x_floor_min - cand.box.minimum[0])},
            archetypes={ARCHETYPE},
        )
        # the learned pose is applied as it is: compaction would slide it and
        # the policy's staircase depends on the exact overhang it chose
        placement = layer1.Placement(
            profile=profile, orientation=orientation, container_idx=container_idx, box=cand.box,
            surface=surface, surface_name=surface, role=candidate.role, archetype=ARCHETYPE,
            reason=f"wedge-rl: strip gain {cand.strip_gain:.4f} m^3 among {len(cands)} strip candidates",
            features=dict(candidate.features), container_is_prioritized=bool(model.is_prioritized),
            container_has_shelf=bool(model.shelves),
            layer=1 if cand.on_floor else 2,
        )
        return layer1.Decision(placement=placement, candidate_counts={ARCHETYPE: len(cands)},
                               veto_counts={}, considered=len(cands), ladder=[ARCHETYPE],
                               survivors=[candidate], chosen=candidate)


class _Region:
    """What ``Candidate.features`` reads from the environment (``model``,
    ``x_max_play``, ``z_top``), so the feature code stays shared with training."""

    def __init__(self, model, x_max_play, z_top):
        self.model = model
        self.x_max_play = x_max_play
        self.z_top = z_top
