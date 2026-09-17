"""A dense, layer-building placement core over the stack candidate generator.

Where the boards end today: at the decline the columns average 0.6 m of a
1.5 m ceiling and a fifth of the floor is bare, yet no pose is left.  The
poses die of "no support" -- the tops are at many different levels
(0.28, 0.29, 0.31, 0.39, 0.53 ...) and a box bridging two tops a few
centimetres apart is unsupported, physically as well as by the rule.
So the core here builds *level* layers: every item is placed, orientation
chosen, so that its top lands on an existing level (or the layer being
built), on full support, low and deep first.  The candidates are the
stack generator's (every legal pose on the floor and on packed tops, the
analytic validator, the tower rule, the transport gap); only the choice
is different: a lexicographic rule, no learning.
"""

from __future__ import annotations

import numpy as np

from rule_alpha import classify as cls
from rule_alpha import layer1
from rule_alpha._reuse import packed_aabbs_local

DENSE_ARCHETYPE = "dense-layer"


class DenseOption:
    """``propose(board, profile)`` -> ``layer1.Decision`` or None.

    ``level_tolerance``: how close a top has to be to an existing level to
    count as extending it.  ``min_support``: the smallest contact share a
    pose may have (the validator's own stability rule still applies)."""

    def __init__(self, config, level_tolerance: float = 0.012, min_support: float = 0.85,
                 max_candidates: int = 256, tower_min: float | None = None, extra_clearance: float | None = None):
        from .stack import StackEnv

        self.config = config
        self.level_tolerance = level_tolerance
        self.min_support = min_support
        self.max_candidates = max_candidates
        self.tower_min = StackEnv.TOWER_MIN if tower_min is None else tower_min
        self.extra_clearance = StackEnv.EXTRA_CLEARANCE if extra_clearance is None else extra_clearance
        self.placed = 0
        self.passed = 0

    # -- scoring -------------------------------------------------------------
    def _levels(self, container: dict, model) -> list[float]:
        levels = {round(float(model.z_floor), 3)}
        for b, _s, _p in packed_aabbs_local(container):
            levels.add(round(float(b.maximum[2]), 3))
        return sorted(levels)

    def _key(self, c, levels: list[float], model):
        top = float(c.box.maximum[2])
        matches = any(abs(top - lv) <= self.level_tolerance for lv in levels)
        full = c.support_ratio >= self.min_support
        # lower first; among those, a top on an existing level; full support;
        # the flattest pose (a standing box makes a pillar no level can use);
        # deep (large y) then left (small x); then the larger box
        return (round(c.bottom, 2), 0 if matches else 1, 0 if full else 1, round(c.dims[2], 3),
                -round(float(c.box.center[1]), 2), round(float(c.box.center[0]), 2), -c.gain)

    def propose(self, board: layer1.Board, profile: cls.ItemProfile) -> layer1.Decision | None:
        from .stack import stack_candidates

        item = profile.item
        for container_idx in layer1.routing_order(profile, board, self.config):
            model = board.model(container_idx)
            container = board.container(container_idx)
            cands = stack_candidates(model, container, self.config, profile, self.max_candidates,
                                     mass=float(item.get("mass", 0.0)), tower_min=self.tower_min,
                                     extra_clearance=self.extra_clearance)
            if not cands:
                continue
            levels = self._levels(container, model)
            best = min(cands, key=lambda c: self._key(c, levels, model))
            self.placed += 1
            return self._decision(best, cands, profile, container_idx, model)
        self.passed += 1
        return None

    def _decision(self, cand, cands, profile, container_idx, model) -> layer1.Decision:
        orientation = next(o for o in profile.orientations if o.index == cand.orientation)
        surface = "floor" if cand.on_floor else "item"
        candidate = layer1.Candidate(
            box=cand.box, profile=profile, orientation=orientation, container_idx=container_idx,
            surface=surface, surface_name=surface, role=cls.ROLE_NONE, family="dense-layer",
            features={"volume": cand.gain, "support_ratio": cand.support_ratio, "margin": cand.margin,
                      "tower_margin": float(getattr(cand, "tower_margin", float("inf")))},
            archetypes={DENSE_ARCHETYPE},
        )
        placement = layer1.Placement(
            profile=profile, orientation=orientation, container_idx=container_idx, box=cand.box,
            surface=surface, surface_name=surface, role=candidate.role, archetype=DENSE_ARCHETYPE,
            reason=f"dense-layer: {cand.gain:.4f} m^3 at {cand.bottom:.2f} m among {len(cands)} candidates",
            features=dict(candidate.features), container_is_prioritized=bool(model.is_prioritized),
            container_has_shelf=bool(model.shelves),
            layer=1 if cand.on_floor else 2,
        )
        return layer1.Decision(placement=placement, candidate_counts={DENSE_ARCHETYPE: len(cands)},
                               veto_counts={}, considered=len(cands), ladder=[DENSE_ARCHETYPE],
                               survivors=[candidate], chosen=candidate)
