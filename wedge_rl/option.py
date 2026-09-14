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

from .env import (PASS, Candidate, grid_shape, play_region, strip_candidates, strip_observation,
                  wedge_reach)

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
            surface=surface, surface_name=surface, role=cls.ROLE_WEDGE_STEP if cand.gain > 0 else cls.ROLE_NONE,
            family="wedge-rl",
            features={"strip_gain": cand.gain, "support_ratio": cand.support_ratio,
                      "margin": cand.margin, "reach": float(model.x_floor_min - cand.box.minimum[0])},
            archetypes={ARCHETYPE},
        )
        # the learned pose is applied as it is: compaction would slide it and
        # the policy's staircase depends on the exact overhang it chose
        placement = layer1.Placement(
            profile=profile, orientation=orientation, container_idx=container_idx, box=cand.box,
            surface=surface, surface_name=surface, role=candidate.role, archetype=ARCHETYPE,
            reason=f"wedge-rl: strip gain {cand.gain:.4f} m^3 among {len(cands)} strip candidates",
            features=dict(candidate.features), container_is_prioritized=bool(model.is_prioritized),
            container_has_shelf=bool(model.shelves),
            layer=1 if cand.on_floor else 2,
        )
        return layer1.Decision(placement=placement, candidate_counts={ARCHETYPE: len(cands)},
                               veto_counts={}, considered=len(cands), ladder=[ARCHETYPE],
                               survivors=[candidate], chosen=candidate)


class _Region:
    """What ``Candidate.features`` reads from the environment (``model``,
    ``x_max_play``, ``z_top``, ``reach_of``), so the feature code stays shared
    with training."""

    def __init__(self, model, x_max_play, z_top):
        self.model = model
        self.x_max_play = x_max_play
        self.z_top = z_top

    def reach_of(self, box):
        return wedge_reach(self.model, box)


# ---------------------------------------------------------------------------
# The stack policy as rule-alpha's Layer 2
# ---------------------------------------------------------------------------
STACK_ARCHETYPE = "stack-rl"


class StackOption:
    """Asked only after the ladder has nothing for the item (Task C hands one
    item at a time, and a decline ends the episode).  The policy was trained
    with a PASS action on a 26-item leftover stream; inside an episode a pass
    forfeits every later item, so the option places the policy's preferred
    *pose* whenever the region offers any.  Containers whose grid differs from
    the one the policy was trained on (other layouts) are left alone."""

    def __init__(self, policy_dir: str | pathlib.Path, config, horizon: int = 26, max_candidates: int = 96,
                 tower_min: float | None = None, extra_clearance: float | None = None,
                 lookahead: dict | None = None):
        import torch

        from .ppo import Policy
        from .stack import StackEnv

        self.policy_dir = pathlib.Path(policy_dir)
        self.config = config
        self.horizon = horizon
        self.max_candidates = max_candidates
        self.tower_min = StackEnv.TOWER_MIN if tower_min is None else tower_min
        self.extra_clearance = StackEnv.EXTRA_CLEARANCE if extra_clearance is None else extra_clearance
        # {"k", "deadline", "samples", "length"}: finish the unsure decisions
        # over imagined continuations of the stream (Task C hides it)
        self.lookahead = lookahead
        self._torch = torch
        self._policy_cls = Policy
        self._policies: dict[tuple[int, int], object] = {}
        self._searchers: dict[tuple[int, int], object] = {}
        self.calls: dict[int, int] = {}
        self.placed = 0
        self.passed = 0
        self.silent = 0
        self.expanded = 0

    def _policy(self, nx: int, ny: int):
        key = (nx, ny)
        if key not in self._policies:
            policy = self._policy_cls(nx, ny)
            try:
                policy.load_state_dict(self._torch.load(self.policy_dir / "policy.pt"))
            except RuntimeError:
                # a different container grid than the one the policy was trained on
                self._policies[key] = None
                return None
            policy.eval()
            self._policies[key] = policy
        return self._policies[key]

    def propose(self, board: layer1.Board, profile: cls.ItemProfile) -> layer1.Decision | None:
        from .stack import (stack_candidates, stack_grid_shape, stack_observation, stack_profile,
                            stack_reach)

        item = profile.item
        for container_idx in layer1.routing_order(profile, board, self.config):
            model = board.model(container_idx)
            container = board.container(container_idx)
            nx, ny = stack_grid_shape(model)
            policy = self._policy(nx, ny)
            if policy is None:
                self.silent += 1
                continue
            cands = stack_candidates(model, container, self.config, profile, self.max_candidates,
                                     mass=float(item.get("mass", 0.0)), tower_min=self.tower_min,
                                     extra_clearance=self.extra_clearance)
            if not cands:
                continue
            seen = self.calls.get(container_idx, 0)
            remaining = max(0.0, (self.horizon - seen) / self.horizon)
            self.calls[container_idx] = seen + 1
            obs = stack_observation(model, container, nx, ny, stack_profile(model, nx), item, remaining)
            region = _StackRegion(model)
            feats = np.stack([c.features(region) for c in cands])
            with self._torch.no_grad():
                logits = policy.logits(policy.embed(obs), feats)
            # the last logit is PASS; an episode cannot pass, so take the best pose
            scores = logits[: len(cands)] if logits.shape[0] > len(cands) else logits
            action = int(self._torch.argmax(scores).item())
            if logits.shape[0] > len(cands) and int(self._torch.argmax(logits).item()) == len(cands):
                self.passed += 1  # the policy would rather have skipped this item
            if self.lookahead is not None:
                action = self._search(policy, nx, ny, model, container, item, remaining, cands, action)
            self.placed += 1
            return self._decision(cands[action], cands, profile, container_idx, model)
        return None

    def _search(self, policy, nx, ny, model, container, item, remaining, cands, action) -> int:
        """The look-ahead's choice over a scratch environment holding the
        live container and the item, the future imagined from the SKU mix.
        Falls back to ``action`` when the search returns PASS or nothing."""
        from .lookahead import Lookahead
        from .stack import StackEnv, sample_future

        cfg = self.lookahead
        key = (nx, ny)
        if key not in self._searchers:
            samples, length = int(cfg.get("samples", 1)), int(cfg.get("length", 6))
            self._searchers[key] = Lookahead(
                policy, k=int(cfg.get("k", 4)), threshold=float(cfg.get("threshold", 0.9)),
                deadline=cfg.get("deadline", 3.0), horizon=cfg.get("horizon"), use_value=True,
                futures=lambda env, rng: [sample_future(rng, length) for _ in range(samples)])
        searcher = self._searchers[key]
        env = StackEnv.from_container(container, model, self.config, max_candidates=self.max_candidates,
                                      tower_min=self.tower_min, extra_clearance=self.extra_clearance)
        env.stream = [dict(item)]
        env._cands = cands  # the same candidates, so the returned index is valid here
        before = searcher.expansions
        chosen = searcher.act(env)
        if searcher.expansions > before:
            self.expanded += 1
        if chosen == PASS or not (0 <= int(chosen) < len(cands)):
            return action
        return int(chosen)

    def _decision(self, cand: Candidate, cands, profile, container_idx, model) -> layer1.Decision:
        orientation = next(o for o in profile.orientations if o.index == cand.orientation)
        surface = "floor" if cand.on_floor else "item"
        candidate = layer1.Candidate(
            box=cand.box, profile=profile, orientation=orientation, container_idx=container_idx,
            surface=surface, surface_name=surface, role=cls.ROLE_NONE, family="stack-rl",
            features={"volume": cand.gain, "support_ratio": cand.support_ratio, "margin": cand.margin,
                      "tower_margin": float(getattr(cand, "tower_margin", float("inf")))},
            archetypes={STACK_ARCHETYPE},
        )
        placement = layer1.Placement(
            profile=profile, orientation=orientation, container_idx=container_idx, box=cand.box,
            surface=surface, surface_name=surface, role=candidate.role, archetype=STACK_ARCHETYPE,
            reason=f"stack-rl: {cand.gain:.4f} m^3 at {cand.bottom:.2f} m among {len(cands)} stack candidates",
            features=dict(candidate.features), container_is_prioritized=bool(model.is_prioritized),
            container_has_shelf=bool(model.shelves),
            layer=1 if cand.on_floor else 2,
        )
        return layer1.Decision(placement=placement, candidate_counts={STACK_ARCHETYPE: len(cands)},
                               veto_counts={}, considered=len(cands), ladder=[STACK_ARCHETYPE],
                               survivors=[candidate], chosen=candidate)


class _StackRegion:
    def __init__(self, model):
        self.model = model
        self.x_max_play = model.x_wall_max
        self.z_top = model.z_ceiling

    def reach_of(self, box):
        from .stack import stack_reach

        return stack_reach(self.model, box)
