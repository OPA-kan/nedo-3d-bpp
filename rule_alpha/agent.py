"""rule-alpha wearing the official agent interface.

This exists so the same Layer 1 rules can be driven by the real PyBullet
simulator (``rule_alpha/physics.py``) instead of the analytic model.  It is a
*prototype*, not a submission: it plans a first layer and then declines, which
is the honest behaviour for something that has no Layer 2.

``agent/agent.py`` remains the production policy and is untouched.
"""

from __future__ import annotations

import dataclasses
import math
import os
import re
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
        if selector is None and getattr(self.config, "rollout_selector", False):
            from .room import RolloutSelector

            selector = RolloutSelector(self.config)
        elif selector is None and getattr(self.config, "room_selector", False):
            from .room import RoomSelector

            selector = RoomSelector(self.config)
        self.selector = selector
        # the pocket guard (config.pocket_guard): soft cargo keeps the room
        # the hard cargo still to come will need (rule_alpha/pocket.py)
        self.pocket = None
        if getattr(self.config, "pocket_guard", False):
            from .pocket import PocketGuard

            self.pocket = PocketGuard(self.config)
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
        self._pool: list = []
        # the shadow check (config.shadow_check): a private pybullet world
        # that tries the chosen pose the way the simulator will
        self._shadow = None
        self._shadow_failed = False
        self._shadow_longest = 0.0
        # the slowest candidate generation of the physics resort so far
        # (its first one is let through: 0.3 s is the typical cost)
        self._resort_gen_longest = 0.3
        self._shadow_observation = None
        self._shadow_synced = False
        self._shadow_fallback = None
        # the manifest's size (Task A), for the count mode's threshold
        self._manifest_total: int | None = None
        self.shadow_stats = {"checks": 0, "vetoes": 0, "replaced": 0, "kept": 0, "skipped": 0, "seconds": 0.0}
        self.last_shadow: dict | None = None

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

    def scratch_copy(self, containers: list, item_list: list, overrides: dict | None = None) -> "RuleAlphaAgent":
        """The same agent -- config, selector, options -- on its own board,
        for dry-runs that must not disturb this one's state."""
        # strict margins in the dry-run: a relaxed pose must never enter the
        # plan mid-order, where a failure would forfeit everything behind it
        config = dataclasses.replace(self.config, last_resort_relax=False, **(overrides or {}))
        scratch = RuleAlphaAgent(config=config, selector=self.selector,
                                 wedge_option=self.wedge_option, stack_option=self.stack_option)
        scratch.get_init_states({"container_list": containers})
        scratch._prepare_manifest(item_list)
        # the scratch is a Task A agent like its parent: without the
        # manifest the dry-run ran the Task C rules (the sweep-shade veto
        # and the resort's shade order, exempt under a manifest) and its
        # plans differed from the parent's replay rules (v33: the sample's
        # A episode 25 -> 28 items, the suite soft -0.9 a scene with two
        # crossings lost, on a veto that was meant to leave A alone)
        if getattr(self.config, "scratch_manifest", True):
            scratch._manifest = {int(i["index"]): i for i in item_list} if item_list else None
            scratch._manifest_total = len(item_list) if item_list else None
        return scratch

    def _plan_value(self, plan: list, item_list: list, capacity: float) -> float:
        """A plan priced at the official weights (config.plan_value_weights):
        the fill share, and -- only when the plan holds the count threshold
        plus ``plan_value_margin`` items -- the soft and priority shares."""
        weights = [float(w) for w in re.split(r"[,;]", str(getattr(self.config, "plan_value_weights", "28.7;14.1;14.3"))) if w]
        weights = (weights + [0.0, 0.0, 0.0])[:3]
        by_index = {int(i["index"]): i for i in item_list}
        items = [by_index[int(e["index"])] for e in plan if int(e["index"]) in by_index]
        volume = sum(float(i["length"]) * float(i["width"]) * float(i["height"]) for i in items)
        soft_total = sum(1 for i in item_list if i.get("is_soft")) or 1
        prio_total = sum(1 for i in item_list if i.get("is_prioritized")) or 1
        threshold = self._count_threshold()
        gate = 1.0 if threshold is None or len(items) >= threshold + int(getattr(self.config, "plan_value_margin", 2)) else 0.0
        return (weights[0] * volume / max(capacity, 1e-9)
                + gate * (weights[1] * sum(1 for i in items if i.get("is_soft")) / soft_total
                          + weights[2] * sum(1 for i in items if i.get("is_prioritized")) / prio_total))

    def _valuable_before_tail(self, order: list, item_list: list) -> list:
        """config.plan_valuable_before_tail: the soft and priority items
        that the constructive order would play after the last share of
        the hard items go ahead of that hard tail.  Applied to the order
        the dry-run simulates, so the plan it builds has the soft items
        placed where they fit and the hard tail in what is left (applied
        after the plan instead, the hard tail lost its spots: valtail02
        placed -0.7 a scene)."""
        share = float(getattr(self.config, "plan_valuable_before_tail", 0.0))
        order = [int(i) for i in order]
        if share <= 0.0 or len(order) < 3:
            return order
        attrs = {int(it["index"]): (bool(it.get("is_soft")) or bool(it.get("is_prioritized"))) for it in item_list}
        hard = [i for i in order if not attrs.get(i, False)]
        keep = len(hard) - int(round(len(hard) * share))
        tail = set(hard[max(0, keep):])
        if not tail:
            return order
        first = min(order.index(i) for i in tail)
        moved = [i for i in order[first:] if i not in tail]
        if moved:
            print(f"[optimize] {len(moved)} soft/priority items ahead of the last {len(tail)} hard items", flush=True)
        return order[:first] + moved + [i for i in order[first:] if i in tail]

    def optimize(self, item_list: list):
        started = time.perf_counter()
        profiles = self._prepare_manifest(item_list)
        self._manifest_total = len(item_list) if item_list else None
        self._manifest = {int(i["index"]): i for i in item_list} if item_list else None
        if self.pocket is not None:
            # Task A: the pocket guard counts the classes still to come
            # from the manifest instead of estimating them
            try:
                self.pocket.set_manifest(item_list, len(self.board.models) if self.board is not None else 1)
            except Exception as exc:
                print(f"[pocket] manifest failed: {exc!r}", flush=True)
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
        order = self._valuable_before_tail(order, item_list)
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
        dry_seconds = 0.0
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
                t0 = time.perf_counter()
                dry = run_dry_run()
                dry_seconds = time.perf_counter() - t0
        base_order = order
        if dry is not None:
            dry_order, dry_plan = dry
            prefer = bool(getattr(self.config, "plan_prefer_planner", False)) and planned is not None and planned[1]
            if prefer:
                # the preference stops at the count threshold: a planner
                # plan under it (a-c1s-s0010: 17 of 41, the planner done
                # in 16 s) yields to a dry-run plan with more items
                threshold = self._count_threshold()
                if threshold is not None and len(planned[1]) < threshold < len(dry_plan) + 1:
                    prefer = False
            if not prefer and (planned is None or score_of(dry_plan) > score_of(planned[1]) + 1e-9):
                order, self.plan, self.plan_source = dry_order, dry_plan, "dry-run"
                planned = None
        if planned is not None:
            order, self.plan = planned
            self.plan_by_index = {int(entry["index"]): entry for entry in self.plan}
            self.plan_source = "planner"
        if dry is not None and self.plan and getattr(self.config, "plan_search", False):
            # the plan search (config.plan_search): the dry-run again over
            # the variant orders while the budget lasts, every plan priced
            # at the official weights; a variant replaces the plan chosen
            # above only when it is worth more and holds the count gate
            # (the base choice keeps its own rules: a planner plan at the
            # threshold replays to a count or two more, a dry-run plan
            # that beat it on value alone replayed to 24 items with no
            # priority box and the load 0.1 higher, -31 on a-c1-s0002)
            from .offline import dry_run_order, order_variant

            soft_of = {int(i["index"]): bool(i.get("is_soft")) for i in item_list}
            prio_of = {int(i["index"]): bool(i.get("is_prioritized")) for i in item_list}
            threshold = self._count_threshold()
            gate = (threshold or 0) + int(getattr(self.config, "plan_value_margin", 2))
            base_label = self.plan_source
            best = (self._plan_value(self.plan, item_list, capacity), len(self.plan), base_label, order, self.plan)
            log = [best]
            longest = max(dry_seconds, 1.0)
            names = [n for n in re.split(r"[;|]", str(getattr(self.config, "plan_search_orders", ""))) if n]
            for name in names:
                # a run that may not finish is not started: the slowest
                # dry-run so far, with a margin, is the estimate
                if time.perf_counter() + 1.3 * longest + 2.0 >= deadline:
                    break
                overrides = {"count_mode_always": True, "count_mode_min_value": 0.0} if name == "count-always" else None
                variant = order_variant(name, base_order, lambda i: soft_of.get(int(i), False), lambda i: prio_of.get(int(i), False))
                t0 = time.perf_counter()
                try:
                    v_order, v_plan = dry_run_order(self, item_list, variant, deadline, overrides=overrides)
                except Exception as exc:
                    print(f"[plan-search] {name} failed: {exc!r}", flush=True)
                    continue
                longest = max(longest, time.perf_counter() - t0)
                entry = (self._plan_value(v_plan, item_list, capacity), len(v_plan), name, v_order, v_plan)
                log.append(entry)
                if len(v_plan) >= gate and (entry[0], entry[1]) > (best[0], best[1]):
                    best = entry
            log.sort(key=lambda c: (c[0], c[1]), reverse=True)
            self.plan_search_log = [{"plan": label, "value": round(value, 2), "items": n} for value, n, label, _o, _p in log]
            value, _n, label, order, self.plan = best
            if label != base_label:
                # a dry-run plan, the variants included, replays through
                # the step-keyed replay of the ladder's own poses, for which
                # plan_by_index must stay empty (planner.replay reads the
                # planner's entries)
                self.plan_by_index = {}
                self.plan_source = f"search:{label}"
        self._order = [int(i) for i in order]
        return list(self._order)

    def policy(self, observation: dict):
        # the shadow check's per-call state: the world is synced from this
        # observation before the first check, and the first hard-vetoed
        # pose is what the call answers with when nothing else is found
        self._shadow_observation = observation if getattr(self.config, "shadow_check", False) else None
        self._shadow_synced = False
        self._shadow_fallback = None
        self.last_shadow = None
        return self._policy_inner(observation)

    # -- the shadow check ----------------------------------------------------
    def _shadow_sim(self):
        if self._shadow is None and not self._shadow_failed:
            try:
                from . import shadow

                if not shadow.available():
                    raise RuntimeError("pybullet is not available")
                self._shadow = shadow.ShadowSim()
            except Exception as exc:  # the check is optional: without it the agent is v18
                self._shadow_failed = True
                print(f"[shadow] disabled: {exc!r}", flush=True)
        return self._shadow

    def _shadow_wants_shake(self, action: dict, item: dict) -> bool:
        """The shake is for the poses that topple: high ones and standing
        ones (config.shadow_shake)."""
        if not getattr(self.config, "shadow_shake", False):
            return False
        from .shadow import get_half_ext

        half = get_half_ext([float(item["length"]), float(item["width"]), float(item["height"])],
                            int(action["orientation"]))
        bottom = float(action["place_pos"][2]) - half[2]
        standing = half[2] > min(half) + 1e-6
        return bottom >= float(getattr(self.config, "shadow_shake_min_bottom", 0.5)) or (
            standing and bool(getattr(self.config, "shadow_shake_standing", True)))

    def _shadow_verdict(self, sim, action: dict, item: dict) -> dict:
        t0 = time.perf_counter()
        try:
            out = sim.check(int(action["container_idx"]), item,
                            tuple(float(v) for v in action["place_pos"]), int(action["orientation"]),
                            shake=self._shadow_wants_shake(action, item))
        finally:
            spent = time.perf_counter() - t0
            self._shadow_longest = max(self._shadow_longest, spent)
            # the stages' deadlines count the check with the decision
            self._longest_call = max(getattr(self, "_longest_call", 0.0), spent)
            self.shadow_stats["checks"] += 1
            self.shadow_stats["seconds"] += spent
        shake = out.get("shake")
        out["shake_ok"] = bool(shake["ok"]) if shake else True
        if shake:
            self.shadow_stats["shaken"] = self.shadow_stats.get("shaken", 0) + 1
            if not shake["ok"]:
                self.shadow_stats["shake_vetoes"] = self.shadow_stats.get("shake_vetoes", 0) + 1
        out["ok"] = bool(out["transport_ok"] and out["settle_ok"] and out["shake_ok"]
                         and out["drift_xy"] <= float(getattr(self.config, "shadow_max_drift_xy", 0.02))
                         and out["angle_deg"] <= float(getattr(self.config, "shadow_max_angle_deg", 5.0)))
        return out

    def _shadow_hard(self, verdict: dict) -> bool:
        # (the settled-pose inclusion the shadow reports is telemetry: the
        # validator tests the commanded pose, which the analytic validate
        # already checks; as a veto it refused 70 planned poses on the A
        # suite the platform accepts)
        return bool(not verdict["transport_ok"] or not verdict["settle_ok"] or not verdict.get("shake_ok", True)
                    or verdict["drift_xy"] > float(getattr(self.config, "shadow_hard_drift_xy", 0.10))
                    or verdict["angle_deg"] > float(getattr(self.config, "shadow_hard_angle_deg", 15.0)))

    def _shade_of(self, placement) -> float:
        """The floor area a pose walls off from the sweep (wedge_rl.stack.shade_area)."""
        if float(getattr(self.config, "shade_veto_area", 0.0)) <= 0.0:
            return 0.0
        try:
            from wedge_rl.stack import shade_area, skyline

            ci = int(placement.container_idx)
            model = self.board.model(ci)
            return float(shade_area(placement.box, skyline(self.board.container(ci), model), float(model.z_ceiling)))
        except Exception as exc:
            print(f"[shade] failed: {exc!r}", flush=True)
            return 0.0

    def _emit(self, pool_index: int, placement) -> dict | None:
        """The action for a placement, through the shadow check when it is
        on.  The chosen pose is tried in the shadow world; on a veto the
        decision's other survivors are tried in the ladder's order.  A soft
        veto (a slide under the hard limits) without an alternative keeps
        the pose.  A hard veto (the sweep or the settle rejects it, or it
        lands far away) without one answers None, so the caller goes on to
        its next item or stage; the first such pose is kept as the call's
        fallback (``_shadow_fallback``), played only before a decline."""
        action = self._action(pool_index, placement)
        observation = getattr(self, "_shadow_observation", None)
        if observation is None:
            return action
        sim = self._shadow_sim()
        if sim is None:
            return action
        started = float(getattr(self, "_policy_started", time.perf_counter()))
        deadline = started + float(getattr(self.config, "shadow_budget_share", 0.95)) * float(self.config.policy_budget_seconds)

        def room() -> bool:
            return time.perf_counter() + self._shadow_longest <= deadline

        if not room():
            self.shadow_stats["skipped"] += 1
            return action
        pool = observation.get("pool_list", [])
        item = pool[int(action["item_idx"])]
        try:
            if not self._shadow_synced:
                sim.sync(observation.get("container_list", []))
                self._shadow_synced = True
            verdict = self._shadow_verdict(sim, action, item)
        except Exception as exc:
            self._shadow_failed, self._shadow = True, None
            print(f"[shadow] disabled after an error: {exc!r}", flush=True)
            return action
        digest = {k: verdict[k] for k in ("transport_ok", "settle_ok", "shake_ok", "drift", "drift_xy", "angle_deg", "ok") if k in verdict}
        # the sweep-shade veto (config.shade_veto_area): a pose that walls
        # off lower floor behind it from the simulator's sweep
        shaded = self._shade_of(placement)
        digest["shade"] = round(shaded, 3)
        shade_limit = float(getattr(self.config, "shade_veto_area", 0.0))
        if getattr(self, "_manifest", None):
            # Task A: the plan's rows are already back to front, and the
            # veto broke the replay (a-c2-s0011: planned poses 51 -> 28,
            # items 57 -> 53; under the dry-run's order 57 -> 51 with no
            # soft item placed)
            shade_limit = 0.0
        elif len(pool) > 1 and not getattr(self.config, "shade_veto_with_pool", False):
            # Task B: the veto fired on half the decisions (2246 of 4298
            # checks) and cost four episodes their crossing (48 -> 44)
            shade_limit = 0.0
        shade_veto = shade_limit > 0.0 and shaded > shade_limit
        if verdict["ok"] and not shade_veto:
            self.shadow_stats["kept"] += 1
            self.last_shadow = {"chosen": digest, "outcome": "kept"}
            return action
        if shade_veto:
            self.shadow_stats["shade_vetoes"] = self.shadow_stats.get("shade_vetoes", 0) + 1
        self.shadow_stats["vetoes"] += 1
        decision = self.last_decision
        tried = []
        if decision is not None and decision.survivors and decision.placement is placement:
            profile = placement.profile
            container_idx = int(placement.container_idx)
            limit = int(getattr(self.config, "shadow_alternatives", 4))
            for cand in decision.survivors:
                if cand is decision.chosen or len(tried) >= limit or not room():
                    continue
                try:
                    alt_placement = layer1.build_placement(cand, placement.archetype, self.board,
                                                           container_idx, profile, self.config)
                    if shade_limit > 0.0 and self._shade_of(alt_placement) > shade_limit:
                        continue
                    alt = self._action(pool_index, alt_placement)
                    v = self._shadow_verdict(sim, alt, item)
                except Exception as exc:
                    print(f"[shadow] alternative failed: {exc!r}", flush=True)
                    break
                tried.append({k: v[k] for k in ("transport_ok", "settle_ok", "drift_xy", "angle_deg", "ok")})
                if v["ok"]:
                    alt_placement.reason = "shadow: " + alt_placement.reason
                    self.last_decision = dataclasses.replace(decision, placement=alt_placement, chosen=cand)
                    self.shadow_stats["replaced"] += 1
                    self.last_shadow = {"chosen": digest, "outcome": "replaced", "tried": tried}
                    return alt
        if not self._shadow_hard(verdict) and not shade_veto:
            self.shadow_stats["kept_soft"] = self.shadow_stats.get("kept_soft", 0) + 1
            self.last_shadow = {"chosen": digest, "outcome": "kept-after-veto", "tried": tried}
            return action
        self.shadow_stats["continued"] = self.shadow_stats.get("continued", 0) + 1
        if self._shadow_fallback is None:
            self._shadow_fallback = (action, self.last_decision,
                                     {"chosen": digest, "outcome": "fallback-after-veto", "tried": tried})
        return None

    def _policy_inner(self, observation: dict):
        started = time.perf_counter()
        self._policy_started = started
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
        self._pool = pool
        # the pocket guard's class frequencies: every item seen so far
        if self.pocket is not None:
            try:
                self.pocket.observe(pool, len(containers))
            except Exception as exc:
                print(f"[pocket] observe failed: {exc!r}", flush=True)
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

        # Task B: the visible pool is a known partial stream, and what the
        # row planner has over the ladder is the order (the rows of one
        # depth and one height the manifest lets it build).  The pool is
        # planned on a scratch board whenever no planned item is left in
        # it, and the plan is replayed like Task A's.
        if (getattr(self.config, "pool_planner", False) and len(pool) > 1
                and not (self.plan_by_index and self.plan_source == "planner")):
            self._timed(self._pool_plan, containers, profiles, started + 0.6 * budget)

        # Task A with a plan: the planned pose, when it still fits the board
        # as it settled; otherwise the item goes down the ladder like any other
        if self.plan_by_index and getattr(self.config, "plan_replay", True):
            from .planner import replay

            hit = self._timed(replay, self, self.board, ordered, self.plan_by_index)
            if hit is not None:
                pool_index, decision = hit
                self.last_decision = decision
                self.plan_replayed += 1
                action = self._emit(pool_index, decision.placement)
                if action is not None:
                    return action

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
            # "auto": the row lines chosen per container (planner.online_row_lines);
            # "mix": the planner's layout over the expected manifest (once a container)
            depths = [] if spec.strip() in ("auto", "mix") else [float(d) for d in re.split(r"[,;+|]", spec) if d]
            if spec.strip() == "mix" and getattr(self, "_mix_rows", None) is None:
                from .planner import mix_row_lines

                self._mix_rows = {ci: mix_row_lines(self, self.board, ci, self.config) for ci in range(len(self.board.models))}
            for n, (pool_index, profile) in enumerate(ordered):
                if n and not self._can_start(ladder_deadline):
                    break
                if profile.is_soft and getattr(self.config, "online_rows_hard_only", True):
                    # soft cargo carries nothing in the support model, so a
                    # soft box in a row's floor kills the column above it;
                    # the ladder's soft archetypes (edges, shelves, tops)
                    # place it instead
                    continue
                t0 = time.perf_counter()
                hit = None
                for container_idx in layer1.routing_order(profile, self.board, self.config):
                    model = self.board.model(container_idx)
                    lines = self._mix_rows[container_idx] if spec.strip() == "mix" else online_row_lines(model, self.config, depths)
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
                action = self._emit(pool_index, placement)
                if action is not None:
                    return action
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
                action = self._emit(pool_index, placement)
                if action is not None:
                    return action
            if best_overall is not None:
                _score, pool_index, profile, (container_idx, model, cand, count) = best_overall
                placement = _placement(cand, count, profile, container_idx, model)
                placement.archetype = "online-" + name
                self.last_decision = layer1.Decision(placement=placement, candidate_counts={"online": count},
                                                     veto_counts={}, considered=count, ladder=[])
                action = self._emit(pool_index, placement)
                if action is not None:
                    return action

        # Task B: which of the visible items goes next (see the config's
        # ``pool_item_search``); the ladder's own item is tried first, so
        # the search never costs a placement
        self._pool_exhausted = False
        if (getattr(self.config, "pool_item_search", False) and len(ordered) > 1
                and not (self.plan_by_index and self.plan_source == "planner")):
            hit = self._pool_item_search(ordered, pool, started + float(getattr(self.config, "pool_item_search_seconds", 3.5)))
            if hit is not None:
                pool_index, decision = hit
                self.last_decision = decision
                action = self._emit(pool_index, decision.placement)
                if action is not None:
                    return action
        # the rolling search tried the ladder and the stack option on every
        # pool item within its deadline and found nothing: the loops below
        # would find the same nothing at the same cost
        exhausted = bool(getattr(self, "_pool_exhausted", False))

        # the wedge option speaks first: a placement in the strip beats the
        # ladder, a pass leaves the item to it
        if self.wedge_option is not None and not exhausted:
            for pool_index, profile in ordered:
                decision = self.wedge_option.propose(self.board, profile)
                if decision is not None:
                    self.last_decision = decision
                    action = self._emit(pool_index, decision.placement)
                    if action is not None:
                        return action

        for n, (pool_index, profile) in enumerate(ordered if not exhausted else []):
            if n and not self._can_start(ladder_deadline):
                break
            decision = self._timed(layer1.choose_for_item, self.board, profile, self.config,
                                   selector=self.selector)
            if decision is None:
                continue
            self.last_decision = decision
            action = self._emit(pool_index, self._pocket_guarded(pool, pool_index, profile, decision))
            if action is not None:
                return action

        # Layer 1 is finished.  The stack option is the learned Layer 2: it
        # places on the boxes the ladder left, under the tower rule.
        if self.stack_option is not None and not exhausted:
            for n, (pool_index, profile) in enumerate(ordered):
                if n and not self._can_start(option_deadline):
                    break
                decision = self._timed(self.stack_option.propose, self.board, profile)
                if decision is not None:
                    self.last_decision = decision
                    action = self._emit(pool_index, decision.placement)
                    if action is not None:
                        return action

        # A decline ends the episode and scores no lower than a failed
        # attempt, so before declining try once with the margins relaxed to
        # just above the official validator's own.
        # the last resort runs to the budget's end; with the shadow on it
        # leaves the slowest check so far's room, since its relaxed poses
        # are the ones most worth checking (a skipped check at the end of
        # b-c2p-s0006 was the episode's settle end)
        end = started + budget
        physics_resort = bool(getattr(self.config, "physics_resort", False)) and self._shadow_observation is not None
        if self._shadow_observation is not None and self._shadow is not None:
            end -= min(max(self._shadow_longest, 0.3), 1.0) + 0.05
        if physics_resort and len(pool) <= 1:
            # one item (Tasks A and C): the resort's window comes out of
            # the budget.  With a pool (Task B) it runs past the budget
            # instead (physics_resort_extra_seconds): shortening the stages
            # cost b-c2p-s0011 a soft-edge decision at 3.7 s and the seven
            # items after it
            end -= float(getattr(self.config, "physics_resort_seconds", 1.8))
        if self.config.last_resort_relax and self._can_start(end):
            action = self._last_resort(containers, ordered, end)
            if action is not None:
                return action

        # the physics resort: what the analytic rules refuse but the
        # simulator would accept (see the config)
        if physics_resort:
            # with a pool (Task B, limit 10 s against A and C's 8 s) the
            # resort may run past the budget by physics_resort_extra_seconds:
            # the call that declines is the episode's last, and the stages
            # before it have spent the budget on the pool
            extra = float(getattr(self.config, "physics_resort_extra_seconds", 1.5)) if len(pool) > 1 else 0.0
            # the count mode: under the platform's count threshold every
            # component but the fill is zero, so a pose on priority or soft
            # cargo (the cover rule's refusals) beats the decline that ends
            # the episode (see config.count_mode); the one pass tries the
            # poses that cover nothing first, and gets more time
            under = self._under_count(containers)
            if under:
                extra = max(extra, float(getattr(
                    self.config, "count_mode_extra_seconds_pool" if len(pool) > 1 else "count_mode_extra_seconds", 1.0)))
            action = self._physics_resort(ordered, pool, started + budget + extra - 0.05, count=under)
            if action is not None:
                return action

        # a pose the shadow vetoed and nothing replaced: a failed placement
        # ends the episode the way a decline does, and the shadow can be wrong
        fallback = getattr(self, "_shadow_fallback", None)
        if fallback is not None:
            action, decision, digest = fallback
            self.last_decision = decision
            self.last_shadow = digest
            self.shadow_stats["fallback"] = self.shadow_stats.get("fallback", 0) + 1
            return action

        # Nothing else, so say so rather than inventing a placement that
        # would fail validation.
        self.last_decision = None
        self.declined.append(len(self.declined))
        return None

    def _pool_item_search(self, ordered: list, pool: list, deadline: float):
        """The item after which the most of the other pool items still fit
        (``room.fit_count``), among the first ``pool_item_search_k`` of the
        ladder's order and the largest hard box; each is placed by the
        ladder on the board and withdrawn.  Returns (pool_index, decision)
        or None (the ladder goes on as usual)."""
        from .room import RoomScorer, fit_count

        mode = str(getattr(self.config, "pool_item_search_mode", "fit"))
        if mode == "continue":
            return self._pool_item_continue(ordered, pool, deadline)
        if mode == "rolling":
            return self._pool_item_rolling(ordered, pool, deadline)
        k = int(getattr(self.config, "pool_item_search_k", 3))
        margin = float(getattr(self.config, "pool_item_search_margin", 0.5))
        hard = [(pi, pr) for pi, pr in ordered if not pr.is_soft]
        if getattr(self.config, "pool_item_search_soft", False):
            # the ceiling's gain was soft cargo placed earlier where the
            # pool's continuation lost nothing (soft 3.98 -> 6.10 a scene of
            # the +2.49): the ladder's own item, then the soft items
            candidates = list(ordered[:1]) + [(pi, pr) for pi, pr in ordered[1:] if pr.is_soft][: max(0, k - 1)]
        else:
            candidates = list(ordered[:k])
            if hard:
                biggest = max(hard, key=lambda pp: pp[1].max_footprint)
                if biggest not in candidates:
                    candidates.append(biggest)
        scorer = getattr(self, "_room_scorer", None)
        if scorer is None:
            scorer = self._room_scorer = RoomScorer(self.config, [], cell=0.05, tolerance=0.02)
        clearance = float(self.config.settled_clearance)
        best = None
        ladder_score = None
        first_decision = None
        for n, (pool_index, profile) in enumerate(candidates):
            if n and time.perf_counter() > deadline:
                break
            decision = self._timed(layer1.choose_for_item, self.board, profile, self.config, selector=self.selector)
            if decision is None:
                continue
            ci = decision.placement.container_idx
            self.board.apply(decision.placement)
            applied = [ci]
            try:
                others = [(j, item) for j, item in enumerate(pool) if j != pool_index]
                # a few true continuation steps: the ladder places the next
                # items of the pool (its own order) before the rest is
                # counted by the fit test
                steps = int(getattr(self.config, "pool_item_search_steps", 0))
                placed_on = 0
                if steps > 0:
                    order = [(pi, pr) for pi, pr in ordered if pi != pool_index]
                    for pi, pr in order:
                        if placed_on >= steps or time.perf_counter() > deadline:
                            break
                        d2 = self._timed(layer1.choose_for_item, self.board, pr, self.config, selector=self.selector)
                        if d2 is None:
                            continue
                        self.board.apply(d2.placement)
                        applied.append(d2.placement.container_idx)
                        placed_on += 1
                        others = [(j, item) for j, item in others if j != pi]
                score = placed_on + fit_count(scorer, self.board, [item for _j, item in others], clearance)
            finally:
                for c in reversed(applied):
                    self.board.undo_last(c)
            if first_decision is None:
                first_decision = (pool_index, decision)
                ladder_score = score
            if best is None or score > best[0] + 1e-9:
                best = (score, pool_index, decision)
        self.pool_item_searches = getattr(self, "pool_item_searches", 0) + 1
        if os.environ.get("ONLINE_DEBUG"):
            print("[pool-item-search] candidates %s ladder %s best %s" % (
                [(pr.index, "S" if pr.is_soft else "h") for _pi, pr in candidates],
                None if first_decision is None else (first_decision[1].placement.profile.index, round(ladder_score, 2)),
                None if best is None else (best[2].placement.profile.index, round(best[0], 2))), flush=True)
        if first_decision is None:
            return None
        if best[1] != first_decision[0] and best[0] > ladder_score + margin:
            self.pool_item_overrides = getattr(self, "pool_item_overrides", 0) + 1
            best[2].placement.reason = "pool item search: " + best[2].placement.reason
            return best[1], best[2]
        return first_decision

    def _decide_one(self, board, profile):
        """One item's decision on a board the way ``policy`` makes it for a
        pool of one: the ladder, then the stack option (the last resort
        left out: a decline in a trial costs nothing)."""
        decision = self._timed(layer1.choose_for_item, board, profile, self.config, selector=self.selector)
        if decision is None and self.stack_option is not None:
            decision = self._timed(self.stack_option.propose, board, profile)
        return decision

    def _pool_item_continue(self, ordered: list, pool: list, deadline: float):
        """The play-time form of the bench's item-choice ceiling
        (``bench/search.py`` ItemSearchAgent, +2.49 items a scene on the
        analytic B suite): each candidate item is placed on a scratch copy
        of the board and the rest of the visible pool is continued by the
        same policy (the ladder then the stack option, in the ladder's
        order); the candidate whose continuation places the most goes, the
        room the load keeps for the frequent footprints breaking the tie
        (``room.RoomScorer.slots``), then the volume.  A continuation cut
        by the deadline counts only when it is the ladder's own item (no
        override then); the others are dropped."""
        import copy

        from .room import RoomScorer, parse_classes

        k = int(getattr(self.config, "pool_item_search_k", 3))
        margin = float(getattr(self.config, "pool_item_search_margin", 0.5))
        if getattr(self.config, "pool_item_search_soft", False):
            candidates = list(ordered[:1]) + [(pi, pr) for pi, pr in ordered[1:] if pr.is_soft][: max(0, k - 1)]
        else:
            candidates = list(ordered[:k])
        scorer = getattr(self, "_slot_scorer", None)
        if scorer is None:
            classes = parse_classes(getattr(self.config, "room_selector_classes",
                                            "0.65x0.45x0.25:1,0.75x0.56x0.27:0.7,0.55x0.40x0.24:0.5"))
            scorer = self._slot_scorer = RoomScorer(self.config, classes, cell=0.05, tolerance=0.02)
        slot_cap = float(getattr(self.config, "pool_item_search_slot_cap", 0.5))
        results = []  # (score, pool_index, decision, complete)
        first = None
        replay = bool(getattr(self.config, "pool_item_search_replay", False))
        plan = []  # the ladder's own continuation: its item's pose, then the poses after it
        for n, (pool_index, profile) in enumerate(candidates):
            if n and time.perf_counter() > deadline:
                break
            decision = self._decide_one(self.board, profile)
            if decision is None:
                if n == 0:
                    first = (None, pool_index, None, True)
                continue
            if n == 0:
                plan.append(decision.placement)
            board = layer1.Board(copy.deepcopy(self.board.containers), self.config)
            board.soft_headroom_reserve = getattr(self.board, "soft_headroom_reserve", 0.0)
            board.soft_headroom_reserve_by_container = dict(getattr(self.board, "soft_headroom_reserve_by_container", {}))
            board.apply(decision.placement)
            placed, volume = 1, float(np.prod(decision.placement.box.size))
            remaining = [(pi, pr) for pi, pr in ordered if pi != pool_index]
            complete = True
            # the continuation's length (pool_item_search_steps; 0: the
            # whole pool): the bench's horizon-4 ceilings kept most of the
            # full one's gain (soft candidates +2.9 against +3.1 a scene)
            horizon = int(getattr(self.config, "pool_item_search_steps", 0) or 0) or len(remaining)
            if n > 0 and replay and plan:
                # the ladder's own continuation replayed pose by pose on
                # the board with the candidate in it: a pose still legal
                # is applied (a validator call), one the candidate spoiled
                # is decided again by the ladder (a decision), so the
                # candidate costs as many decisions as it spoils, not a
                # continuation of its own
                for p in plan[:horizon]:
                    if p.profile.index == profile.index:
                        continue
                    if time.perf_counter() > deadline:
                        complete = False
                        break
                    ci = p.container_idx
                    ok, _why = layer1.validate(p.box, board.model(ci), board.container(ci), self.config)
                    if ok:
                        board.apply(p)
                        placed += 1
                        volume += float(np.prod(p.box.size))
                        continue
                    d2 = self._decide_one(board, p.profile)
                    if d2 is not None:
                        board.apply(d2.placement)
                        placed += 1
                        volume += float(np.prod(d2.placement.box.size))
                remaining = []
            while remaining and placed - 1 < horizon:
                hit = None
                for pi, pr in remaining:
                    if time.perf_counter() > deadline:
                        complete = False
                        break
                    d2 = self._decide_one(board, pr)
                    if d2 is not None:
                        hit = (pi, d2)
                        break
                if hit is None:
                    break
                board.apply(hit[1].placement)
                placed += 1
                volume += float(np.prod(hit[1].placement.box.size))
                remaining = [(pi, pr) for pi, pr in remaining if pi != hit[0]]
                if n == 0:
                    plan.append(hit[1].placement)
            slots = sum(scorer.slots(board, ci) for ci in range(len(board.models))) if complete else 0.0
            score = float(placed) + min(slot_cap, slots / 40.0) + volume / 10000.0
            entry = (score, pool_index, decision, complete)
            if n == 0:
                first = entry
            results.append(entry)
        self.pool_item_searches = getattr(self, "pool_item_searches", 0) + 1
        if os.environ.get("ONLINE_DEBUG"):
            print("[pool-item-continue] %s" % [
                (r[2].placement.profile.index, "S" if r[2].placement.profile.is_soft else "h",
                 round(r[0], 2), "" if r[3] else "cut") for r in results], flush=True)
        if first is None or first[2] is None:
            return None
        if not first[3]:
            return first[1], first[2]
        best = max((r for r in results if r[3]), key=lambda r: r[0])
        if best[1] != first[1] and best[0] > first[0] + margin:
            self.pool_item_overrides = getattr(self, "pool_item_overrides", 0) + 1
            best[2].placement.reason = "pool item search: " + best[2].placement.reason
            return best[1], best[2]
        return first[1], first[2]

    def _pool_item_rolling(self, ordered: list, pool: list, deadline: float):
        """The continuation search with the ladder's continuation kept
        across steps.  The ladder is deterministic on a board, so the
        decisions it made for the next items at the last step (on the
        boards it expected) are its decisions at this step while the
        board is the one it expected: the plan's poses are revalidated
        (a validator call each), the items it found no ladder pose for
        are remembered, an item the pool order ranks before the plan's
        head (a new arrival) is decided on the board, and the plan is
        extended by one decision to the horizon.  The head is the
        ladder's own item, found the way ``policy`` finds it: the ladder
        over the pool in its order, then the stack option.  Each other
        candidate is decided on the board and the plan replayed after
        it; a pose the candidate spoiled is decided again.  A step then
        costs about one ladder decision and the candidates' own,
        whatever the horizon."""
        import copy

        from .room import RoomScorer, parse_classes

        k = int(getattr(self.config, "pool_item_search_k", 3))
        margin = float(getattr(self.config, "pool_item_search_margin", 0.5))
        horizon = int(getattr(self.config, "pool_item_search_steps", 0) or 4)
        scorer = getattr(self, "_slot_scorer", None)
        if scorer is None:
            classes = parse_classes(getattr(self.config, "room_selector_classes",
                                            "0.65x0.45x0.25:1,0.75x0.56x0.27:0.7,0.55x0.40x0.24:0.5"))
            scorer = self._slot_scorer = RoomScorer(self.config, classes, cell=0.05, tolerance=0.02)
        slot_cap = float(getattr(self.config, "pool_item_search_slot_cap", 0.5))
        in_pool = {int(pr.index): (pi, pr) for pi, pr in ordered}
        late = lambda: time.perf_counter() > deadline

        def scratch():
            board = layer1.Board(copy.deepcopy(self.board.containers), self.config)
            board.soft_headroom_reserve = getattr(self.board, "soft_headroom_reserve", 0.0)
            board.soft_headroom_reserve_by_container = dict(getattr(self.board, "soft_headroom_reserve_by_container", {}))
            return board

        def put(board, placement):
            """Apply a pose to a scratch board the way the next step's board
            has it: ``policy`` rebuilds its board from the containers each
            step, so the ladder never sees the Placement objects of the
            steps before (``Board.placements``), and a scratch board must
            not carry them either or its decisions differ."""
            board.apply(placement)
            board.placements = [[] for _ in board.containers]

        def ladder(board, profile):
            d = self._timed(layer1.choose_for_item, board, profile, self.config, selector=self.selector)
            if d is not None:
                d.via = "ladder"
            return d

        def stack(board, profile):
            if self.stack_option is None:
                return None
            d = self._timed(self.stack_option.propose, board, profile)
            if d is not None:
                d.via = "stack"
            return d

        def first_decision(board, items, known=None, fails=None, ladder_deadline=None, option_deadline=None):
            """``policy``'s own choice among ``items`` (the pool order): the
            ladder over every item, then the stack option.  ``known`` maps
            an item to a decision already made on this board; ``fails``
            is the set of items the ladder had nothing for on it, filled
            in as it goes.  The deadlines are policy's own for the head
            (the ladder's share of the budget, then the option's), the
            search's for the plan.  Returns (decision, complete)."""
            known = known or {}
            fails = fails if fails is not None else set()
            # the head is policy's own decision: its first ladder call is
            # always made (policy's loop does the same); a plan decision is
            # not started once the search's deadline has passed
            head_search = ladder_deadline is not None
            n = 0
            for pi, pr in items:
                d = known.get(pr.index)
                if d is not None:
                    if d.via == "ladder":
                        return d, True
                    continue
                if pr.index in fails:
                    continue
                if head_search:
                    if n and not self._can_start(ladder_deadline):
                        return None, False
                elif not self._can_start(deadline):
                    return None, False
                n += 1
                d = ladder(board, pr)
                if d is not None:
                    return d, True
                fails.add(pr.index)
            n = 0
            for pi, pr in items:
                d = known.get(pr.index)
                if d is not None:
                    return d, True
                if head_search:
                    if n and not self._can_start(option_deadline):
                        return None, False
                elif not self._can_start(deadline):
                    return None, False
                n += 1
                d = stack(board, pr)
                if d is not None:
                    return d, True
            return None, True

        def replay(board, decisions, skip_index=None, stale=False):
            """Apply the plan's poses to ``board`` in order, each through the
            validator, a spoiled one decided again; returns (placed, volume,
            kept decisions, complete).  ``stale``: the board is not the one
            the poses were decided on (an item went in before them), so a
            pose that still fits is kept as a pose, not as the ladder's
            decision (``via = "replay"``): it is decided again before it
            is played as the ladder's own item."""
            placed, volume, kept, complete = 0, 0.0, [], True
            for d in decisions:
                p = d.placement
                if p.profile.index == skip_index or p.profile.index not in in_pool:
                    continue
                if late():
                    complete = False
                    break
                ci = p.container_idx
                ok, _why = layer1.validate(p.box, board.model(ci), board.container(ci), self.config)
                if not ok:
                    if not self._can_start(deadline):
                        complete = False
                        break
                    d = ladder(board, p.profile) or stack(board, p.profile)
                    if d is None:
                        continue
                    p = d.placement
                elif stale:
                    d.via = "replay"
                put(board, p)
                kept.append(d)
                placed += 1
                volume += float(np.prod(p.box.size))
            return placed, volume, kept, complete

        # the ladder's branch: the head the way policy finds it, with the
        # cached decisions and failures standing in for the ladder calls
        cache = getattr(self, "_pool_cache", None) or {"plan": [], "fails": []}
        # the cached decisions were made on the board the last step
        # predicted; on physics the settled board drifts, and a decision
        # on a board that is not this one is not the ladder's decision on
        # this one.  With any item off its predicted place by more than
        # the drift allowance, the cache stands as poses only.
        drift = float(getattr(self.config, "pool_item_search_drift", 0.01))
        expect = cache.get("expect")
        if expect is not None and drift >= 0.0:
            actual = {}
            for ci, c in enumerate(self.board.containers):
                for p in c.get("packed_items", []):
                    actual[(ci, int(p.get("index", -1)))] = tuple(float(v) for v in p.get("pos", (0.0, 0.0, 0.0)))
            moved = set(expect) != set(actual) or any(
                max(abs(a - b) for a, b in zip(expect[k], actual[k])) > drift for k in expect)
            if moved:
                for d in cache["plan"]:
                    d.via = "replay"
                cache = {"plan": cache["plan"], "fails": [set() for _d in cache["plan"]]}
        plan_in = [d for d in cache["plan"] if d.placement.profile.index in in_pool]
        fails_in = [set(f) & set(in_pool) for f in cache["fails"]][:len(plan_in)] or [set()]
        # only the plan's head was decided on this board (the poses after
        # it were decided on the boards after it), and only when it is a
        # decision, not a pose kept through an insertion
        genuine = bool(plan_in) and getattr(plan_in[0], "via", "replay") != "replay"
        known = {int(plan_in[0].placement.profile.index): plan_in[0]} if genuine else {}
        fail0 = set(fails_in[0]) if (fails_in and genuine) else set()
        started = float(getattr(self, "_policy_started", time.perf_counter()))
        budget = float(self.config.policy_budget_seconds)
        head, complete = first_decision(self.board, ordered, known, fail0,
                                        ladder_deadline=started + 0.6 * budget, option_deadline=started + 0.85 * budget)
        board = scratch()
        placed, volume, plan, fails = 0, 0.0, [], []
        expect_next = None
        if head is not None:
            put(board, head.placement)
            # where every item will be if the head settles where it was put
            expect_next = {}
            for ci, c in enumerate(board.containers):
                for p in c.get("packed_items", []):
                    expect_next[(ci, int(p.get("index", -1)))] = tuple(float(v) for v in p.get("pos", (0.0, 0.0, 0.0)))
            placed, volume, plan, fails = 1, float(np.prod(head.placement.box.size)), [head], [fail0]
            rest_plan = [d for d in plan_in if d.placement.profile.index != head.placement.profile.index]
            # the plan's poses were decided on the boards after its own
            # head; with another item in front they are poses, not decisions
            stale = not (plan_in and head is plan_in[0])
            if complete:
                p2, v2, kept, complete = replay(board, rest_plan, stale=stale)
                placed += p2
                volume += v2
                plan += kept
                if stale:
                    fails += [set() for _d in kept]
                else:
                    fails += fails_in[1:1 + len(kept)] + [set()] * max(0, len(kept) - len(fails_in[1:]))
        planned = {d.placement.profile.index for d in plan}
        if complete and not self._can_start(deadline):
            # the head took the search's time (a late-episode decision):
            # the ladder's item goes, no candidate is tried
            complete = False
        if complete:
            rest = [(pi, pr) for pi, pr in ordered if pr.index not in planned]
            while rest and len(plan) < horizon + 1:
                fail_here = set()
                d, complete = first_decision(board, rest, None, fail_here)
                if d is None:
                    break
                put(board, d.placement)
                plan.append(d)
                fails.append(fail_here)
                planned.add(d.placement.profile.index)
                placed += 1
                volume += float(np.prod(d.placement.box.size))
                rest = [(pi, pr) for pi, pr in rest if pr.index != d.placement.profile.index]
        self.pool_item_searches = getattr(self, "pool_item_searches", 0) + 1
        if not plan:
            self._pool_cache = {"plan": [], "fails": []}
            # the head was looked for the way policy looks, under policy's
            # own deadlines: its loops would find the same nothing
            self._pool_exhausted = True
            return None
        first = plan[0]
        first_index = int(first.placement.profile.index)
        results = []
        if complete:
            slots = sum(scorer.slots(board, ci) for ci in range(len(board.models)))
            results.append((float(placed) + min(slot_cap, slots / 40.0) + volume / 10000.0, first_index, first, True))
            # the other candidates (the pool's soft items, or the next items
            # of the ladder's order): each decided on the board, then the
            # plan's poses, the candidate's own left out, replayed after it
            if getattr(self.config, "pool_item_search_soft", True):
                others = [(pi, pr) for pi, pr in ordered if pr.is_soft and pr.index != first_index][: max(0, k - 1)]
            else:
                others = [(pi, pr) for pi, pr in ordered if pr.index != first_index][: max(0, k - 1)]
            for pi, pr in others:
                if not self._can_start(deadline):
                    break
                d = ladder(self.board, pr)
                if d is None and self._can_start(deadline):
                    d = stack(self.board, pr)
                if d is None:
                    continue
                if pr.is_soft and not getattr(self.config, "pool_item_search_soft_floor", True) \
                        and getattr(d.placement, "surface", "") == "floor":
                    # a soft item on the floor early takes the floor from
                    # the hard rows (the soft search lost 5-7 items on four
                    # c1 scenes that way); the shelf and the tops are the
                    # places where it costs the hard cargo nothing
                    continue
                if pr.is_soft and not pr.is_prioritized \
                        and not getattr(self.config, "pool_item_search_soft_shelf_over_priority", True) \
                        and getattr(d.placement, "surface", "") == "shelf" \
                        and any(p2.is_prioritized and not p2.is_soft for _i, p2 in ordered):
                    # the shelf kept for the hard priority cargo in view
                    continue
                if pr.is_soft and not pr.is_prioritized \
                        and not getattr(self.config, "pool_item_search_soft_in_priority", True) \
                        and self.board.model(d.placement.container_idx).is_prioritized:
                    # the priority container's shelf and rows kept for the
                    # priority cargo still to come (the soft search lost
                    # 0.9-1.4 priority items a scene)
                    continue
                b2 = scratch()
                put(b2, d.placement)
                if getattr(self.config, "pool_item_search_branch", "replay") == "decide":
                    # the ceiling's own test: the ladder continues after the
                    # candidate with its own decisions (horizon of them), not
                    # the plan's poses replayed; costs horizon decisions a
                    # candidate, affordable once a decision is cheap
                    p2, v2, ok = 0, 0.0, True
                    rest = [(qi, qr) for qi, qr in ordered if qr.index != pr.index]
                    # the items the ladder had nothing for on this board are
                    # not tried again in the branch (a pose one more item
                    # opens for them is rare; the failures are what makes a
                    # late-episode decision cost seconds)
                    branch_fails = set(fail0)
                    while rest and p2 < horizon:
                        d2, ok = first_decision(b2, rest, None, branch_fails)
                        if d2 is None:
                            break
                        put(b2, d2.placement)
                        p2 += 1
                        v2 += float(np.prod(d2.placement.box.size))
                        rest = [(qi, qr) for qi, qr in rest if qr.index != d2.placement.profile.index]
                    if not ok:
                        continue
                else:
                    after = [x for x in plan if x.placement.profile.index != pr.index][:horizon]
                    p2, v2, _kept, ok = replay(b2, after, skip_index=pr.index)
                    if not ok:
                        continue
                slots = sum(scorer.slots(b2, ci) for ci in range(len(b2.models)))
                v2 += float(np.prod(d.placement.box.size))
                results.append((float(p2 + 1) + min(slot_cap, slots / 40.0) + v2 / 10000.0, int(pr.index), d, True))
        if os.environ.get("ONLINE_DEBUG"):
            print("[pool-item-rolling] plan %s %s" % (
                [int(d.placement.profile.index) for d in plan], "" if complete else "cut"),
                [(r[1], "S" if in_pool[r[1]][1].is_soft else "h", round(r[0], 2)) for r in results], flush=True)
        best = max(results, key=lambda r: r[0]) if results else None
        if best is not None and best[1] != first_index and best[0] > results[0][0] + margin:
            self.pool_item_overrides = getattr(self, "pool_item_overrides", 0) + 1
            if os.environ.get("ONLINE_DEBUG"):
                print("[pool-item-rolling] override: item %d for %d" % (best[1], first_index), flush=True)
            best[2].placement.reason = "pool item search: " + best[2].placement.reason
            # the plan stands: its poses are checked on the board with the
            # candidate in it at the next step
            keep = [d for d in plan if d.placement.profile.index != best[1]]
            for d in keep:
                d.via = "replay"
            self._pool_cache = {"plan": keep, "fails": [set() for _d in keep], "expect": None}
            return in_pool[best[1]][0], best[2]
        self._pool_cache = {"plan": list(plan[1:]), "fails": list(fails[1:]), "expect": expect_next}
        return in_pool[first_index][0], first

    def _pool_plan(self, containers: list, profiles: list, deadline: float) -> None:
        """Plan the visible pool with the row planner on a scratch copy of
        the board (``planner.pack_rows``, the row lines kept per container
        across plans), when no planned item is left in the pool."""
        import copy

        from .planner import mix_row_lines, online_row_lines, pack_rows

        in_pool = {int(pr.index) for _pi, pr in profiles}
        self.plan_by_index = {i: e for i, e in self.plan_by_index.items() if i in in_pool} \
            if self.plan_source == "pool" else {}
        if self.plan_by_index:
            return
        scratch = layer1.Board(copy.deepcopy(containers), self.config)
        rows = getattr(self, "_pool_rows", None)
        if rows is None or len(rows) != len(scratch.models):
            rows = {}
            spec = str(getattr(self.config, "pool_planner_rows", "auto"))
            for ci, model in enumerate(scratch.models):
                if spec == "mix":
                    rows[ci] = mix_row_lines(self, scratch, ci, self.config)
                elif spec == "auto":
                    rows[ci] = online_row_lines(model, self.config, [])
                else:
                    rows[ci] = []
            self._pool_rows = rows
        items = [pr for _pi, pr in profiles]
        plan, planned = [], []
        for ci in range(len(scratch.models)):
            if not items or time.perf_counter() >= deadline:
                break
            allowed = [pr for pr in items if ci in layer1.routing_order(pr, scratch, self.config)]
            if not allowed:
                continue
            pack_rows(self, scratch, ci, allowed, self.config, plan, planned, deadline, row_lines=rows[ci])
            items = [pr for pr in items if pr.index not in planned]
        self.plan_by_index = {int(e["index"]): e for e in plan}
        self.plan_source = "pool" if plan else ""
        self.pool_plans = getattr(self, "pool_plans", 0) + 1

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
                if (getattr(self.config, "soft_first_skip_priority_container", False)
                        and model.is_prioritized and not profile.is_prioritized):
                    # the priority container's shelf is the priority
                    # cargo's gallery: soft-first on the B suite took it
                    # (b-c2p-s0003 and s0006 -11 items, priority placed
                    # 0.72 -> 0.57 a share)
                    continue
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
                    action = self._emit(pool_index, placement)
                    if action is not None:
                        return action
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
                action = self._emit(pool_index, placement)
                if action is not None:
                    return action
            # "tops": no shelf gallery (it took the priority cargo's room on
            # the B suite), only a top on soft cargo or one too high for
            # any hard box
            free = placement.surface == "shelf" and mode != "tops"
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
            action = self._emit(pool_index, placement)
            if action is not None:
                return action
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

    def _pocket_guarded(self, pool: list, pool_index: int, profile, decision):
        """The ladder's placement for a soft item, or the pocket guard's
        alternative when the ladder put the box on the floor where the
        hard cargo still expected will need the room (rule_alpha/pocket.py).
        The alternative goes through the same shadow check as any pose."""
        placement = decision.placement
        soft = bool(getattr(profile, "is_soft", False))
        small_hard = (bool(getattr(self.config, "pocket_guard_hard", False)) and not soft
                      and not bool(getattr(profile, "is_prioritized", False))
                      and float(getattr(profile, "max_footprint", 1.0)) < float(getattr(self.config, "pocket_guard_min_footprint", 0.2)))
        if (self.pocket is None or not (soft or small_hard) or placement.surface != "floor"
                or pool is None):
            return placement
        if self.plan_by_index:
            # Task A with a plan: the planner has laid the rooms out, and a
            # soft box moved off its floor spot broke a-c2p-s0012's plan
            # at the second step (45 -> 37 items)
            return placement
        started = float(getattr(self, "_policy_started", time.perf_counter()))
        deadline = min(started + 0.85 * float(self.config.policy_budget_seconds),
                       time.perf_counter() + float(getattr(self.config, "pocket_guard_seconds", 0.8)))
        if time.perf_counter() >= deadline:
            return placement
        try:
            item = pool[pool_index]
            found = self.pocket.alternative(self.board, profile, float(item.get("mass", 0.0)),
                                            int(placement.container_idx), placement.box, deadline, soft=soft)
        except Exception as exc:
            print(f"[pocket] alternative failed: {exc!r}", flush=True)
            return placement
        if found is None:
            return placement
        from .planner import _placement

        cand, container_idx, chosen_score, best_score = found
        alt = _placement(cand, 1, profile, int(container_idx), self.board.model(int(container_idx)))
        alt.archetype = "pocket-soft" if soft else "pocket-hard"
        alt.reason = (f"pocket guard: {best_score:.2f} slots kept against {chosen_score:.2f} "
                      f"({'floor' if cand.on_floor else 'top'} at {cand.bottom:.2f} m); was {placement.archetype}")
        # the ladder's survivors belong to the ladder's container, not
        # necessarily the guard's: the shadow gate must not build its
        # alternatives from them (b-c2p-s0005 ended on an inclusion
        # failure from one built in the wrong container)
        self.last_decision = dataclasses.replace(decision, placement=alt, survivors=[], chosen=None)
        return alt

    def _count_threshold(self) -> int | None:
        """The count under which the platform zeroes every component but
        the fill (config.count_mode): half the items, rounded up, plus the
        margin; the manifest's count on Task A, the expected count
        otherwise."""
        if not getattr(self.config, "count_mode", False):
            return None
        containers = len(self.board.models) if self.board is not None and self.board.models else 1
        total = self._manifest_total
        if not total:
            total = float(getattr(self.config, "count_mode_items_per_container", 41.0)) * containers
        share = float(getattr(self.config, "count_mode_fraction", 0.5))
        if getattr(self.config, "count_mode_strict", False):
            # strictly more than the share: 42 of 82 where the ceiling
            # gives 41 (21 of 41 either way)
            base = int(math.floor(float(total) * share + 1e-9)) + 1
        else:
            base = int(math.ceil(float(total) * share - 1e-9))
        return base + int(getattr(self.config, "count_mode_margin", 0))

    def _under_count(self, containers: list) -> bool:
        threshold = self._count_threshold()
        if threshold is None:
            return False
        placed = sum(len(c.get("packed_items", [])) for c in containers)
        if placed < threshold:
            return True
        if not getattr(self.config, "count_mode_always", False):
            return False
        # over the threshold: the pass runs for what a decline would forfeit
        order = getattr(self, "_order", None)
        manifest = getattr(self, "_manifest", None)
        pool = getattr(self, "_pool", None) or []
        if not order or not manifest or len(pool) != 1:
            return True  # Tasks B and C: the rest of the stream is unknown and worth it
        try:
            here = order.index(int(pool[0]["index"]))
        except (ValueError, KeyError, TypeError):
            return True
        value = 0.0
        for idx in order[here + 1:]:
            item = manifest.get(int(idx))
            if item is None:
                continue
            value += 0.9 if item.get("is_soft") else (2.9 if item.get("is_prioritized") else 0.3)
        return value >= float(getattr(self.config, "count_mode_min_value", 2.0))

    def _physics_resort(self, ordered: list, pool: list, deadline: float, count: bool = False) -> dict | None:
        """Every pose the geometry allows on the floor or a packed top, in
        any container, lowest and best supported first, tried in the shadow
        world until one stands (the sweep and the settle pass, no landing
        over the hard limits away).  The analytic vetoes (tower rule,
        support shares, headroom reserve, the extra transport clearance)
        are not applied: the physics is the judge here.  The cover rule
        is kept (it is the platform's placement score, not physics),
        except under the count threshold (``count``, config.count_mode):
        then the covering poses are generated too, soft tops carry load,
        the poses that cover nothing are tried first and the pool's
        smallest item goes first."""
        sim = self._shadow_sim()
        if sim is None:
            return None
        from wedge_rl.stack import covers_other_attribute, shade_area, skyline, stack_candidates

        from .planner import _placement

        strict = self.config
        cfg = dataclasses.replace(
            strict,
            settled_clearance=min(strict.settled_clearance, strict.last_resort_settled_clearance),
            routing_any_container=True, stack_max_bottom=10.0, stack_soft_min_support=0.0,
            stack_soft_standing=True,
        )
        if count:
            cfg = dataclasses.replace(cfg, allow_cover_other_attribute=True, soft_is_structure=True,
                                      stack_soft_is_structure=True)

        def room(generating: bool = False) -> bool:
            # a candidate generation is not interruptible (0.3-0.9 s a
            # container), so one is started only when the slowest so far
            # and a check both fit: the platform's slowest v27 call ran
            # 0.6 s past the resort's deadline on a generation
            need = max(self._shadow_longest, 0.2) + (self._resort_gen_longest if generating else 0.0)
            return time.perf_counter() + need <= deadline

        limit = int(getattr(strict, "physics_resort_candidates", 300))
        tried = 0
        # a Task B pool holds several items of one size (eight soft
        # 0.65 x 0.35 x 0.23 boxes of ten at the end of b-c2-s0006): the
        # candidates are the same for all of them
        generated: dict[tuple, list] = {}
        # the soft cargo first: at the end of a Task B episode the pool is
        # mostly soft, the hard items in it have been refused by every
        # stage for a reason the physics is unlikely to overturn, and a
        # soft box fits where a hard one of its size would not stand
        if count:
            # any item counts the same towards the threshold: the smallest
            # is the likeliest to stand somewhere
            queue = sorted(ordered, key=lambda pp: (float(pool[pp[0]]["length"]) * float(pool[pp[0]]["width"])
                                                    * float(pool[pp[0]]["height"]), 0 if pp[1].is_soft else 1))
        else:
            queue = sorted(ordered, key=lambda pp: 0 if pp[1].is_soft else 1)
        covering: dict[int, bool] = {}
        for pool_index, profile in queue:
            if not room():
                break
            item = pool[pool_index]
            for container_idx in layer1.routing_order(profile, self.board, cfg):
                if not room():
                    break
                model = self.board.model(container_idx)
                container = self.board.container(container_idx)
                key = (container_idx, round(float(item["length"]), 4), round(float(item["width"]), 4),
                       round(float(item["height"]), 4), bool(profile.is_soft), bool(profile.is_prioritized))
                if key in generated:
                    cands = generated[key]
                else:
                    if not room(generating=True):
                        break
                    t0 = time.perf_counter()
                    try:
                        cands = stack_candidates(model, container, cfg, profile, max_candidates=limit,
                                                 mass=float(item.get("mass", 0.0)), tower_min=None,
                                                 extra_clearance=0.0, z_top=None,
                                                 dense=float(getattr(strict, "physics_resort_anchor_step", 0.04)))
                        # half the footprint over the support at least: the
                        # shake test comes after the settle
                        # (under the threshold the physics judges the
                        # partial supports too: on c-c2-s0009 the next
                        # box, a 0.75 x 0.56, had 6 of 22 part-supported
                        # poses standing in the shadow and none at a half)
                        min_support = float(getattr(strict, "count_mode_min_support", 0.5)) if count else 0.5
                        cands = [c for c in cands if c.on_floor or c.support_ratio >= min_support]
                    except Exception as exc:
                        print(f"[physics-resort] candidates failed: {exc!r}", flush=True)
                        cands = []
                    spent = time.perf_counter() - t0
                    self._longest_call = max(self._longest_call, spent)
                    self._resort_gen_longest = max(self._resort_gen_longest, spent)
                    # the well supported low poses first: the load's height
                    # is priced, and a pose on a whole top is the one that stands
                    if count:
                        # under the threshold: the poses that cover nothing
                        # first (a covered box costs a share of the
                        # placement or soft score), then the covering ones
                        for c in cands:
                            covering[id(c)] = bool(covers_other_attribute(
                                c.box, container, bool(profile.is_soft), bool(profile.is_prioritized)))
                    # a pose that walls off deeper slots from the sweep
                    # (shade_area: lower terrain behind it, still with
                    # headroom) goes after the ones that do not, in steps
                    # of resort_shade_step m^2: on the Task C boards under
                    # the threshold the whole-top poses that would stand
                    # are nearly all sweep-blocked
                    shade_step = float(getattr(strict, "resort_shade_step", 0.0))
                    if getattr(self, "_manifest", None) or (len(pool) > 1 and not getattr(strict, "shade_veto_with_pool", False)):
                        shade_step = 0.0  # the same tasks the gate's veto leaves alone

                    shade: dict[int, int] = {}
                    if shade_step > 0.0:
                        sky = skyline(container, model)
                        for c in cands:
                            shade[id(c)] = int(shade_area(c.box, sky, float(model.z_ceiling)) / shade_step)
                    # under the threshold the whole-top poses go before the
                    # partial ones at any height: the partial ones fail
                    # the settle far more often (c-c1-s0003: the fifteen
                    # lowest poses tried, all partial, none stood)
                    cands.sort(key=lambda c: (covering.get(id(c), False),
                                              bool(count and not c.on_floor and c.support_ratio < 0.95),
                                              shade.get(id(c), 0),
                                              round(c.bottom, 2), -round(c.support_ratio, 2),
                                              -round(float(c.box.center[1]), 3), round(float(c.box.center[0]), 3)))
                    generated[key] = cands
                if not cands:
                    continue
                # the poses come in groups (the same cover class, the same
                # level, the same support share): when three of a group in
                # a row fail the settle the rest of it is skipped, since
                # they fail alike (c-c1-s0003: the 85 lowest poses, all on
                # the same hard tops, all tipped; the 88 after them stood)
                failed: dict[tuple, int] = {}
                for cand in cands:
                    if not room():
                        break
                    cover = covering.get(id(cand), False)
                    group = (cover, round(cand.bottom, 1), round(cand.support_ratio, 1))
                    if count and failed.get(group, 0) >= 3:
                        continue
                    label = "count-mode" if cover else "physics-resort"
                    placement = _placement(cand, len(cands), profile, container_idx, model)
                    placement.archetype = label
                    placement.reason = f"{label}: {cand.bottom:.2f} m, support {cand.support_ratio:.2f}, among {len(cands)}"
                    try:
                        if not self._shadow_synced:
                            sim.sync(self._shadow_observation.get("container_list", []))
                            self._shadow_synced = True
                        action = self._action(pool_index, placement)
                        v = self._shadow_verdict(sim, action, item)
                    except Exception as exc:
                        print(f"[physics-resort] check failed: {exc!r}", flush=True)
                        return None
                    tried += 1
                    if self._shadow_hard(v):
                        failed[group] = failed.get(group, 0) + 1
                    else:
                        failed[group] = 0
                    if not self._shadow_hard(v):
                        self.last_decision = layer1.Decision(placement=placement, candidate_counts={label: len(cands)},
                                                             veto_counts={}, considered=len(cands), ladder=[])
                        self.last_shadow = {"chosen": {k: v[k] for k in ("transport_ok", "settle_ok", "shake_ok", "drift", "drift_xy", "angle_deg", "ok") if k in v},
                                            "outcome": label, "tried": tried}
                        key = "count_mode" if cover else "resort"
                        self.shadow_stats[key] = self.shadow_stats.get(key, 0) + 1
                        return action
        key = "count_mode_tried" if count else "resort_tried"
        self.shadow_stats[key] = self.shadow_stats.get(key, 0) + tried
        return None

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
                action = self._emit(pool_index, self._pocket_guarded(self._pool, pool_index, profile, decision))
                if action is not None:
                    return action
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
                    action = self._emit(pool_index, decision.placement)
                    if action is not None:
                        return action
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
