"""rule-alpha wearing the official agent interface.

This exists so the same Layer 1 rules can be driven by the real PyBullet
simulator (``rule_alpha/physics.py``) instead of the analytic model.  It is a
*prototype*, not a submission: it plans a first layer and then declines, which
is the honest behaviour for something that has no Layer 2.

``agent/agent.py`` remains the production policy and is untouched.
"""

from __future__ import annotations

import dataclasses
import os
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
        # Task A with the offline planner: settled pose per item index, and
        # how often a planned pose no longer fitted the settled board
        self.plan_by_index: dict[int, dict] = {}
        self.plan_source = ""
        self.plan_misses = 0
        self.plan_replayed = 0
        self.last_resort_used = 0
        self._longest_call = 0.0

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
        if (self.config.priority_cargo_first and self.board is not None
                and any(m.is_prioritized for m in self.board.models)):
            by_index = {p.index: p for p in profiles}
            first = [i for i in order if by_index[i].is_prioritized]
            order = first + [i for i in order if not by_index[i].is_prioritized]
        self.plan = []
        self.plan_by_index = {}
        self.plan_source = ""
        deadline = started + float(self.config.offline_budget_seconds)
        by_index = {int(item["index"]): item for item in item_list}
        capacity = sum(float(c.get("length", 0)) * float(c.get("width", 0)) * float(c.get("height", 0))
                       for c in (self.board.containers if self.board is not None else [])) or 1.0
        soft_total = sum(1 for i in item_list if i.get("is_soft")) or 1
        prio_total = sum(1 for i in item_list if i.get("is_prioritized")) or 1

        import re

        # "," or ";" between the weights: an arm spec's overrides are
        # themselves comma-separated
        weights = [float(w) for w in re.split(r"[,;]", str(getattr(self.config, "plan_score_weights", "1,0.5,0.5,0"))) if w]
        weights = (weights + [0.0, 0.0, 0.0, 0.0])[:4]
        n_items = max(1, len(item_list))

        def score_of(plan):
            """What the official score is made of, each part in [0, 1]:
            the fill, the share of the soft cargo placed, the share of the
            priority cargo placed -- weighted by ``plan_score_weights``."""
            items = [by_index[int(e["index"])] for e in plan if int(e["index"]) in by_index]
            volume = sum(float(i["length"]) * float(i["width"]) * float(i["height"]) for i in items)
            return (weights[0] * volume / capacity
                    + weights[1] * sum(1 for i in items if i.get("is_soft")) / soft_total
                    + weights[2] * sum(1 for i in items if i.get("is_prioritized")) / prio_total
                    + weights[3] * len(items) / n_items)

        self.plan_score = score_of
        planned = None
        use_planner = bool(getattr(self.config, "offline_planner", "")) and self.board is not None and len(order) > 1
        use_dry_run = bool(self.config.offline_dry_run) and self.board is not None and len(order) > 1
        # with a main shelf the ladder's shelf archetypes pack ten fill
        # points more than the rows (a-c1s-s0002: 46 against 36), so there
        # the dry-run goes first and takes the budget; the planner only
        # runs if time is left.  On the evaluation machine the dry-run
        # fills the budget, so this decides which plan a layout gets.
        dry_run_first = use_dry_run and getattr(self.config, "plan_dry_run_first_with_shelf", False) \
            and any(getattr(m, "main_shelf", None) is not None for m in self.board.models)

        def run_planner():
            from .planner import plan_packing

            # the headroom reserve belongs to the planner's plan (see
            # _soft_headroom_reserve); it is set while planning
            self.plan_source = "planner"
            result = plan_packing(self, item_list, deadline)
            self.plan_source = ""
            return result

        def run_dry_run():
            from .offline import dry_run_order

            return dry_run_order(self, item_list, order, deadline)

        dry = None
        if dry_run_first:
            dry = run_dry_run()
            if use_planner and time.perf_counter() < deadline - float(getattr(self.config, "plan_min_seconds", 15.0)):
                planned = run_planner()
        else:
            if use_planner:
                planned = run_planner()
            if use_dry_run and time.perf_counter() < deadline:
                # the ladder's own dry-run with what is left of the budget;
                # the plan that scores higher (fill, soft placed, priority
                # placed) decides.  On a slow machine the dry-run is cut
                # short and the planner's full plan wins by itself
                dry = run_dry_run()
        if dry is not None:
            dry_order, dry_plan = dry
            if planned is None or score_of(dry_plan) > score_of(planned[1]) + 1e-9:
                order, self.plan, self.plan_source = dry_order, dry_plan, "dry-run"
                planned = None
        if planned is not None:
            order, self.plan = planned
            self.plan_by_index = {int(entry["index"]): entry for entry in self.plan}
            self.plan_source = "planner"
        return [int(i) for i in order]

    def policy(self, observation: dict):
        started = time.perf_counter()
        budget = float(self.config.policy_budget_seconds)
        # the ladder may use most of the budget, the options what is left;
        # the first item is always tried
        ladder_deadline = started + 0.6 * budget
        option_deadline = started + 0.85 * budget
        # strict accounting: no call is started that the slowest call of
        # this decision so far would carry past its deadline
        self._longest_call = 0.0
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
        reserve = self._soft_headroom_reserve(containers)
        self.board.soft_headroom_reserve = reserve
        self.board.soft_headroom_reserve_by_container = {
            ci: self._soft_headroom_reserve(containers, ci) for ci in range(len(containers))
        } if getattr(self.config, "soft_headroom_per_container", False) else {}
        if self.stack_option is not None:
            self.stack_option.headroom_reserve = reserve

        # Task A with a plan: the planned pose, when it still fits the board
        # as it settled; otherwise the item goes down the ladder like any other
        if self.plan_by_index and getattr(self.config, "plan_replay", True):
            from .planner import replay

            hit = self._timed(replay, self, self.board, ordered, self.plan_by_index)
            if hit is not None:
                pool_index, decision = hit
                self.last_decision = decision
                self.plan_replayed += 1
                return self._action(pool_index, decision.placement)

        # soft cargo where it costs the hard stacks nothing (Task B, and any
        # item off the plan): the pool order puts every soft item behind
        # every hard one, so on the Task B suite the ladder placed 23 % of
        # the soft cargo (two classes at 1 % and 4 %), all of it at the end
        # on rugged tops.  Before the hard cargo is tried, a soft item that
        # has a pose on a shelf, on soft cargo, or on a top nothing hard
        # could use any more goes first: a count point and a soft-score
        # point that add no height the hard cargo would not add.
        if (getattr(self.config, "soft_first_when_free", False)
                and (not self.plan_by_index or self.plan_source != "planner")):
            # its own share of the budget: with the ladder's whole deadline
            # the pass ran a full ladder decision per soft item in the pool
            # and left the ladder's first item, the option's and the last
            # resort to run after it (v24: three times v18's calls over
            # 5.5 s on the Task B suite, 7.03 s on the platform)
            share = float(getattr(self.config, "soft_first_budget_share", 1.0))
            action = self._soft_first(ordered, min(ladder_deadline, started + share * budget))
            if action is not None:
                return action

        # the online planner (Tasks B and C, or a Task A item off the plan):
        # the lowest legal pose over every anchor -- the floor filled before
        # anything is stacked, so a large flat area stays for the big boxes
        # the ladder's terraces leave no room for (Task C ended on a decline
        # with the floor 52 % covered, 27 of 41 items placed)
        name = str(getattr(self.config, "online_planner", "") or "")
        if name == "rows" and (not self.plan_by_index or self.plan_source != "planner"):
            # fixed row lines per container (the canonical depths of the
            # cargo classes, back to front), the item at the lowest legal
            # pose on them: the floor of every row fills before anything is
            # stacked and the layers rest on whole rows
            from .planner import _Pose, _placement, online_row_lines, online_row_pose

            import re

            spec = str(getattr(self.config, "online_row_depths", "0.56,0.45,0.4"))
            # "auto": the row lines chosen per container (planner.online_row_lines)
            depths = [] if spec.strip() == "auto" else [float(d) for d in re.split(r"[,;+|]", spec) if d]
            for n, (pool_index, profile) in enumerate(ordered):
                if n and not self._can_start(ladder_deadline):
                    break
                t0 = time.perf_counter()
                hit = None
                for container_idx in layer1.routing_order(profile, self.board, self.config):
                    model = self.board.model(container_idx)
                    lines = online_row_lines(model, self.config, depths)
                    box, orientation = online_row_pose(self.board, container_idx, profile, self.config, lines,
                                                       standing=bool(getattr(self.config, "plan_standing", True)))
                    if box is not None:
                        hit = (container_idx, model, box, orientation)
                        break
                self._longest_call = max(self._longest_call, time.perf_counter() - t0)
                if hit is None:
                    continue
                container_idx, model, box, orientation = hit
                placement = _placement(_Pose(box, orientation, model.z_floor), 1, profile, container_idx, model)
                placement.archetype = "online-rows"
                self.last_decision = layer1.Decision(placement=placement, candidate_counts={"online": 1},
                                                     veto_counts={}, considered=1, ladder=[])
                return self._action(pool_index, placement)
        elif name and (not self.plan_by_index or self.plan_source != "planner"):
            from .planner import _key, _placement
            from wedge_rl.stack import stack_candidates

            from .planner import online_layers_key

            key = _key(name, float(getattr(self.config, "plan_band", 0.22))) if name != "layers" else None
            standing_cap = float(getattr(self.config, "online_standing_max_height", 10.0))
            # with a pool to choose from (Task B) every item's best pose is
            # found and the item whose pose ranks best goes first: the one
            # that fills the floor gap in front of the wall, not the
            # smallest one whatever it fits
            pool_best = bool(getattr(self.config, "online_pool_best", False)) and len(ordered) > 1
            best_overall = None
            for n, (pool_index, profile) in enumerate(ordered):
                if n and not self._can_start(ladder_deadline):
                    break
                t0 = time.perf_counter()
                chosen = None
                for container_idx in layer1.routing_order(profile, self.board, self.config):
                    model = self.board.model(container_idx)
                    container = self.board.container(container_idx)
                    if name == "layers" and (profile.is_soft or (profile.is_prioritized and not model.is_prioritized)):
                        # the shelf gallery first for the cargo nothing may
                        # rest on: the room above a shelf is the least the
                        # hard stacks want
                        from .planner import _Pose, online_shelf_pose

                        t_shelf = time.perf_counter()
                        box, orientation = online_shelf_pose(self.board, container_idx, profile, self.config)
                        if os.environ.get("ONLINE_DEBUG"):
                            print(f"[online-time] item {profile.index} c{container_idx} shelf scan {time.perf_counter() - t_shelf:.2f}s hit={box is not None}")
                        if box is not None:
                            pose = _Pose(box, orientation, model.z_floor)
                            chosen = (container_idx, model, pose, 1)
                            break
                    t_c = time.perf_counter()
                    # the stack option's tower rule (the combined centre of
                    # mass of everything a pose loads inside every support
                    # polygon by a margin) and its transport clearance:
                    # without them the layer policy's high poses knocked
                    # their towers over on landing (v22: 9 of 48 Task C
                    # episodes ended on a settle failure, all of them
                    # layer poses at 0.8-1.25 m, one on full support)
                    tower_min, extra = None, 0.0
                    if getattr(self.config, "online_tower_rule", False):
                        from wedge_rl.stack import StackEnv

                        tower_min = self.stack_option.tower_min if self.stack_option is not None else StackEnv.TOWER_MIN
                        extra = self.stack_option.extra_clearance if self.stack_option is not None else StackEnv.EXTRA_CLEARANCE
                    cands = stack_candidates(model, container, self.config, profile, max_candidates=10 ** 6,
                                             mass=float(pool[pool_index].get("mass", 0.0)), z_top=None,
                                             tower_min=tower_min, extra_clearance=extra)
                    if os.environ.get("ONLINE_DEBUG"):
                        print(f"[online-time] item {profile.index} c{container_idx} stack_candidates {time.perf_counter() - t_c:.2f}s n={len(cands)}")
                    # a standing pose taller than the cap is height and a
                    # topple the count does not pay for (v19)
                    cands = [c for c in cands if float(c.dims[2]) <= standing_cap + 1e-9
                             or abs(float(c.dims[2]) - min(c.dims)) < 1e-6]
                    if cands:
                        if name == "layers":
                            from . import planner as _planner

                            _planner._MODEL_CONTAINER[id(model)] = container
                            item_key = online_layers_key(profile, model, self.config)
                            best = min(cands, key=item_key)
                            if os.environ.get("ONLINE_DEBUG"):
                                ranked = sorted(cands, key=item_key)[:4]
                                print(f"[online] item {profile.index} c{container_idx} {len(cands)} cands; bottoms {sorted({round(float(c.bottom), 2) for c in cands})}; top:",
                                      [(item_key(c), [round(float(v), 2) for v in c.box.center], [round(float(v), 2) for v in c.dims]) for c in ranked])
                        else:
                            best = min(cands, key=lambda c: key(c, model))
                        chosen = (container_idx, model, best, len(cands))
                        break
                self._longest_call = max(self._longest_call, time.perf_counter() - t0)
                if chosen is None:
                    continue
                if pool_best and name == "layers":
                    container_idx, model, cand, count = chosen
                    rank = (0 if profile.is_soft or profile.is_prioritized else 1) if False else 0
                    item_key = online_layers_key(profile, model, self.config)
                    score = (rank, item_key(cand), n)
                    if best_overall is None or score < best_overall[0]:
                        best_overall = (score, pool_index, profile, chosen)
                    continue
                container_idx, model, cand, count = chosen
                placement = _placement(cand, count, profile, container_idx, model)
                placement.archetype = "online-" + name
                self.last_decision = layer1.Decision(placement=placement, candidate_counts={"online": count},
                                                     veto_counts={}, considered=count, ladder=[])
                return self._action(pool_index, placement)
            if best_overall is not None:
                _score, pool_index, profile, (container_idx, model, cand, count) = best_overall
                placement = _placement(cand, count, profile, container_idx, model)
                placement.archetype = "online-" + name
                self.last_decision = layer1.Decision(placement=placement, candidate_counts={"online": count},
                                                     veto_counts={}, considered=count, ladder=[])
                return self._action(pool_index, placement)

        # the wedge option speaks first: a placement in the strip beats the
        # ladder, a pass leaves the item to it
        if self.wedge_option is not None:
            for pool_index, profile in ordered:
                decision = self.wedge_option.propose(self.board, profile)
                if decision is not None:
                    self.last_decision = decision
                    return self._action(pool_index, decision.placement)

        for n, (pool_index, profile) in enumerate(ordered):
            if n and not self._can_start(ladder_deadline):
                break
            decision = self._timed(layer1.choose_for_item, self.board, profile, self.config,
                                   selector=self.selector)
            if decision is None:
                continue
            self.last_decision = decision
            return self._action(pool_index, decision.placement)

        # Layer 1 is finished.  The stack option is the learned Layer 2: it
        # places on the boxes the ladder left, under the tower rule.
        if self.stack_option is not None:
            for n, (pool_index, profile) in enumerate(ordered):
                if n and not self._can_start(option_deadline):
                    break
                decision = self._timed(self.stack_option.propose, self.board, profile)
                if decision is not None:
                    self.last_decision = decision
                    return self._action(pool_index, decision.placement)

        # A decline ends the episode and scores no lower than a failed
        # attempt, so before declining try once with the margins relaxed to
        # just above the official validator's own.
        if self.config.last_resort_relax and self._can_start(started + budget):
            action = self._last_resort(containers, ordered, started + budget)
            if action is not None:
                return action

        # Nothing else, so say so rather than inventing a placement that
        # would fail validation.
        self.last_decision = None
        self.declined.append(len(self.declined))
        return None

    def _soft_first(self, ordered: list, deadline: float):
        """A soft item's pose that costs the hard stacks nothing: on a
        shelf, on soft cargo, or on a top too high for another hard box.
        The ladder chooses the pose (its shelf preference for soft cargo
        included); only where it lands is judged here."""
        from ._reuse import packed_aabbs_local

        wall = self.config.inclusion_clearance + self.config.anchor_slack
        min_hard = float(getattr(self.config, "soft_first_min_hard_height", 0.24))
        from .planner import _Pose, _placement, online_shelf_pose

        # normal soft cargo before soft priority cargo: nothing but priority
        # cargo may rest on priority cargo, so a soft priority box on the
        # shelf floor blocks the gallery above it, while it may itself rest
        # on normal soft cargo
        soft_pairs = sorted(((pi, pr) for pi, pr in ordered if pr.is_soft),
                            key=lambda pp: (1 if pp[1].is_prioritized else 0, round(pp[1].max_footprint, 6)))
        # "free": a shelf, soft cargo or a top too high for hard cargo (v23:
        # the soft score doubled on the platform, but the load rose, the
        # priority cargo lost the shelf and the count did not pay for it);
        # "floor-gap": a floor pose in a gap no hard box in the pool fits,
        # which adds a light item low and takes nothing from the hard cargo
        mode = str(getattr(self.config, "soft_first_mode", "free") or "free")
        # the shelf gallery first, flat and packed from the back, for every
        # soft item before any ladder decision (the scan is cheap, a ladder
        # decision is not): the ladder stands soft boxes on the shelf on
        # their narrow side (three of fifteen fitted that way on b-c1-s0001)
        for pool_index, profile in soft_pairs:
            if mode != "free" or not self._can_start(deadline):
                break
            for container_idx in layer1.routing_order(profile, self.board, self.config):
                model = self.board.model(container_idx)
                t0 = time.perf_counter()
                box, orientation = online_shelf_pose(self.board, container_idx, profile, self.config)
                self._longest_call = max(self._longest_call, time.perf_counter() - t0)
                if box is not None:
                    placement = _placement(_Pose(box, orientation, model.z_floor), 1, profile, container_idx, model)
                    placement.surface = "shelf"
                    placement.surface_name = "shelf"
                    placement.archetype = "soft-first-shelf"
                    placement.reason = "soft-first: the shelf gallery"
                    self.last_decision = layer1.Decision(placement=placement, candidate_counts={"soft-first": 1},
                                                         veto_counts={}, considered=1, ladder=[])
                    self.soft_first_used = getattr(self, "soft_first_used", 0) + 1
                    return self._action(pool_index, placement)
        max_items = int(getattr(self.config, "soft_first_max_items", 0) or 0)
        for n, (pool_index, profile) in enumerate(soft_pairs):
            if not self._can_start(deadline) or (max_items and n >= max_items):
                break
            decision = self._timed(layer1.choose_for_item, self.board, profile, self.config, selector=self.selector)
            if decision is None:
                continue
            placement = decision.placement
            box = placement.box
            model = self.board.model(placement.container_idx)
            container = self.board.container(placement.container_idx)
            if mode == "floor-gap":
                if placement.surface != "floor" or self._hard_box_fits_over(
                        ordered, model, container, placement.container_idx, box):
                    continue
                placement.reason = "soft-first (floor gap): " + placement.reason
                self.last_decision = decision
                self.soft_first_used = getattr(self, "soft_first_used", 0) + 1
                return self._action(pool_index, placement)
            free = placement.surface == "shelf"
            if not free:
                # on soft cargo: the support under the box is soft
                for packed, (b, so, _pr) in zip(container.get("packed_items", []), packed_aabbs_local(container)):
                    if not packed.get("is_soft"):
                        continue
                    if abs(float(b.maximum[2]) - float(box.minimum[2])) < 0.02 and \
                            min(float(box.maximum[0]), float(b.maximum[0])) - max(float(box.minimum[0]), float(b.minimum[0])) > 0.05 and \
                            min(float(box.maximum[1]), float(b.maximum[1])) - max(float(box.minimum[1]), float(b.minimum[1])) > 0.05:
                        free = True
                        break
            if not free and float(box.minimum[2]) + min_hard > model.z_ceiling - wall:
                # a top no hard box fits on any more
                free = True
            if not free:
                continue
            placement.reason = "soft-first: " + placement.reason
            self.last_decision = decision
            self.soft_first_used = getattr(self, "soft_first_used", 0) + 1
            return self._action(pool_index, placement)
        return None

    def _hard_box_fits_over(self, ordered: list, model, container: dict, container_idx: int, box) -> bool:
        """Would the smallest hard box in the pool (or the smallest hard
        SKU, when the pool has none: the stream may bring one) have a legal
        floor pose over the footprint of ``box``?  Then the gap is hard
        cargo's, not a soft item's."""
        from wedge_rl.stack import stack_candidates

        hard = [pr for _pi, pr in ordered if not pr.is_soft and pr.orientations]
        if hard:
            ref = min(hard, key=lambda pr: pr.max_footprint)
        else:
            ref = cls.classify_item(-1, {"index": -1, "length": 0.55, "width": 0.40, "height": 0.24, "mass": 8.0,
                                         "is_soft": False, "is_prioritized": False}, self.config)
        if not ref.orientations:
            return False
        t0 = time.perf_counter()
        try:
            cands = stack_candidates(model, container, self.config, ref, max_candidates=10 ** 6, mass=8.0)
        finally:
            self._longest_call = max(self._longest_call, time.perf_counter() - t0)
        for c in cands:
            if not c.on_floor:
                continue
            ox = min(float(c.box.maximum[0]), float(box.maximum[0])) - max(float(c.box.minimum[0]), float(box.minimum[0]))
            oy = min(float(c.box.maximum[1]), float(box.maximum[1])) - max(float(c.box.minimum[1]), float(box.minimum[1]))
            if ox > 0.01 and oy > 0.01:
                return True
        return False

    def _soft_headroom_reserve(self, containers: list, container_idx: int | None = None) -> float:
        """Task A: the height the flattest pose of the soft cargo still to
        come needs on top of the hard stacks, so the stacks stop short of
        the ceiling by that much while any of it is unplaced.  With
        ``soft_headroom_per_container`` and a container given, only the
        soft cargo that may enter that container counts: in a priority
        container that is the soft priority cargo alone (soft-only cargo
        never enters it), so its top is not kept for cargo that will never
        come."""
        if not self.config.reserve_headroom_for_soft or not self.profiles:
            return 0.0
        # the reserve is the planner's: the ladder packs worse under it (24
        # against 31 of 41 on a-c1-s0001) and its dry-run plan, and the
        # online ladder replaying or completing that plan, keep the ceiling
        if getattr(self, "plan_source", "") != "planner":
            return 0.0
        placed = {int(p.get("index", -1)) for c in containers for p in c.get("packed_items", [])}
        soft = [pr for i, pr in self.profiles.items() if i not in placed and pr.is_soft and pr.orientations]
        if (container_idx is not None and getattr(self.config, "soft_headroom_per_container", False)
                and len(containers) > 1 and bool(containers[container_idx].get("is_prioritized", False))):
            soft = [pr for pr in soft if pr.is_prioritized]
        if not soft:
            return 0.0
        share = float(getattr(self.config, "soft_headroom_volume_share", 1.0))
        flattest = sorted(((min(o.dz for o in pr.orientations),
                            pr.orientations[0].dx * pr.orientations[0].dy * pr.orientations[0].dz) for pr in soft))
        total = sum(v for _h, v in flattest)
        # the height under which the given share of the soft volume fits
        # (1.0: the tallest item's); the tall few take what is left
        reserve, seen = flattest[-1][0], 0.0
        for h, v in flattest:
            seen += v
            if seen >= share * total - 1e-9:
                reserve = h
                break
        factor = float(getattr(self.config, "soft_headroom_volume_factor", 0.0) or 0.0)
        if factor > 0.0 and self.board is not None and self.board.models:
            # the layer the soft volume needs over the whole floor, at the
            # packing density the factor allows for
            volume = sum(pr.orientations[0].dx * pr.orientations[0].dy * pr.orientations[0].dz for pr in soft)
            area = sum(max(m.floor_rect.area, 1e-9) for m in self.board.models)
            reserve = max(reserve, factor * volume / area)
        return reserve + float(self.config.soft_headroom_slack)

    def _can_start(self, deadline: float) -> bool:
        return time.perf_counter() + getattr(self, "_longest_call", 0.0) <= deadline

    def _timed(self, fn, *args, **kwargs):
        t0 = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            self._longest_call = max(getattr(self, "_longest_call", 0.0), time.perf_counter() - t0)

    def _last_resort(self, containers: list, ordered: list, deadline: float = float("inf")) -> dict | None:
        """Two stages before a decline: every container with the strict
        margins (when there is a priority container and the item may not
        use it yet), then the relaxed margins."""
        strict = self.config
        stages = []
        if strict.last_resort_any_container and any(m.is_prioritized for m in self.board.models) \
                and len(self.board.models) > 1:
            stages.append(("any-container", dataclasses.replace(strict, routing_any_container=True)))
        stages.append(("relaxed", dataclasses.replace(
            strict,
            settled_clearance=min(strict.settled_clearance, strict.last_resort_settled_clearance),
            com_margin=min(strict.com_margin, strict.last_resort_com_margin),
            routing_any_container=strict.last_resort_any_container,
        )))
        strict_board = self.board
        # the headroom kept for the soft cargo is lifted here: a decline
        # forfeits the rest of the stream, a box in the top layer does not
        reserve = self.stack_option.headroom_reserve if self.stack_option is not None else 0.0
        try:
            if self.stack_option is not None:
                self.stack_option.headroom_reserve = 0.0
            for label, config in stages:
                if not self._can_start(deadline):
                    break
                self.config = config
                self.board = layer1.Board(containers, config)
                self._reapply_zone_scales()
                self._resize_zones_for_what_is_left()
                action = self._last_resort_stage(label, config, ordered, deadline)
                if action is not None:
                    return action
        finally:
            self.config, self.board = strict, strict_board
            if self.stack_option is not None:
                self.stack_option.headroom_reserve = reserve
        return None

    def _last_resort_stage(self, label: str, config, ordered: list, deadline: float) -> dict | None:
        relaxed_margins = label == "relaxed"
        for n, (pool_index, profile) in enumerate(ordered):
            if n and not self._can_start(deadline):
                break
            decision = self._timed(layer1.choose_for_item, self.board, profile, config, selector=self.selector)
            if decision is not None:
                decision.placement.reason = f"last-resort {label}: " + decision.placement.reason
                self.last_decision = decision
                self.last_resort_used += 1
                return self._action(pool_index, decision.placement)
        if self.stack_option is not None:
            for n, (pool_index, profile) in enumerate(ordered):
                if n and not self._can_start(deadline):
                    break
                decision = self._timed(
                    self.stack_option.propose, self.board, profile,
                    tower_min=config.last_resort_tower_min if relaxed_margins else None,
                    extra_clearance=config.last_resort_extra_clearance if relaxed_margins else None)
                if decision is not None:
                    decision.placement.reason = f"last-resort {label}: " + decision.placement.reason
                    self.last_decision = decision
                    self.last_resort_used += 1
                    return self._action(pool_index, decision.placement)
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
