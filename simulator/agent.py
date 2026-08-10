import copy
import heapq
import json
import math
import os
import random
import sys
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np

# Geometry contract
# -----------------
# - Actions use container-local coordinates.
# - Packed item positions and container planes use world coordinates.
# - The simulator only offsets containers on the world X axis.
# - Boundary clearance includes official, physics-settle, and float32 guards.
# - Transport clearance includes the official 15 mm plus a float32 guard.
# - Settled candidates represent final support contact.
# - Release candidates represent the pose sent to the simulator before settle.
# - Shelf actions are lifted 5.1 cm to avoid the validator's direct-rest path.
OFFICIAL_INCLUSION_CLEARANCE = 0.005
PHYSICS_BOUNDARY_GUARD = 0.010
FLOAT32_CLEARANCE_GUARD = 0.001
INCLUSION_CLEARANCE = (
    OFFICIAL_INCLUSION_CLEARANCE
    + PHYSICS_BOUNDARY_GUARD
    + FLOAT32_CLEARANCE_GUARD
)
OFFICIAL_TRANSPORT_CLEARANCE = 0.015
TRANSPORT_CLEARANCE = (
    OFFICIAL_TRANSPORT_CLEARANCE + FLOAT32_CLEARANCE_GUARD
)
# Self-imposed lateral margin on top of the official transport clearance.
# This is a SETTLE-SURVIVAL margin, not merely a search restriction, and
# the 2026-08-04 measurements say so directly: on the six matrix scenes
# in shipped mode, 10 mm completes 3 of 6 episodes while 2 mm completes
# 0 and turns all three of those completions into physical settle
# failures (`is_valid` true, `is_placed_safe` false). Paired Task B CI
# agrees -- 3 of 3 pools worse, suite placed 57.33 -> 44.33.
#
# The pi_B ladder that briefly justified 0.002 (232/223/242/193 at
# 10/5/2/0 mm) was measured at POLICY_ATTEMPT_BUDGET=4000, which runs
# ~2500 attempts/step -- about 30% BELOW the shipped rate. A starved
# search loses episodes to settle failures for reasons unrelated to the
# guard (10 mm dies physically in 4 of 6 scenes there, 0 of 6 under the
# deadline), so the ladder could not rank the arms. Search breadth
# itself is NOT the harm: at a fixed guard, more attempts are
# monotonically better (budget-sweep-20260804.json). Kept as a knob, but
# re-measure any contract change at or above the shipped attempt rate.
# Also the factor varied by the joint 2mm x death-band factorial
# (joint-2mm-x-death-band-factorial): the gate's uplift survives the flip.
PHYSICS_LATERAL_GUARD = float(
    os.environ.get("PHYSICS_LATERAL_GUARD", "0.010")
)
SETTLED_ITEM_CLEARANCE = TRANSPORT_CLEARANCE + PHYSICS_LATERAL_GUARD
TRANSPORT_SAMPLE_STEP = 0.03
SIMULATOR_DROP_HEIGHT = 0.08
SIMULATOR_START_MARGIN = 0.01
SIMULATOR_CEILING_MARGIN = 0.018
SIMULATOR_CEILING_CLIP_EPS = 0.0005
SHELF_ACTION_LIFT = 0.051
RELEASE_TARGET_LIFT = 0.052
RELEASE_BOUNDARY_MARGIN = 0.002
RELEASE_RISK_GATE_MODES = frozenset({"off", "shadow", "enforce"})
RELEASE_RISK_GATE_MODE = os.environ.get(
    "RELEASE_RISK_GATE_MODE", "off"
).strip().lower()
RELEASE_RISK_DIAGNOSTIC_SAMPLE_LIMIT = int(
    os.environ.get("RELEASE_RISK_DIAGNOSTIC_SAMPLE_LIMIT", "64")
)
# Shadow reranking: run the real selection stack a second time with a
# risk-adjusted release ranking and record how the final choice would have
# differed. Instrumentation only -- the returned action never changes.
RELEASE_RISK_SHADOW_RERANK = os.environ.get(
    "RELEASE_RISK_SHADOW_RERANK", "0"
).strip().lower() in {"1", "true", "yes", "on"}
RELEASE_RISK_RERANK_LAMBDA = float(
    os.environ.get("RELEASE_RISK_RERANK_LAMBDA", "1.0")
)
# Which P(rotation) model the risk-adjusted score uses: the static-Phi
# logistic ("static") or the mechanical topple-feature logistic ("mech",
# MATHEMATICAL_MODEL 5.2.1). "mech" is the submission default since the
# 2026-07-31 final_holdout evaluation.
RELEASE_RISK_P_MODELS = frozenset({"static", "mech"})
RELEASE_RISK_P_MODEL = os.environ.get(
    "RELEASE_RISK_P_MODEL", "mech"
).strip().lower()
if RELEASE_RISK_P_MODEL not in RELEASE_RISK_P_MODELS:
    raise ValueError(
        f"unknown RELEASE_RISK_P_MODEL {RELEASE_RISK_P_MODEL!r}; "
        f"expected one of {sorted(RELEASE_RISK_P_MODELS)}"
    )
# Live rerank: apply the risk-adjusted release ranking to the REAL action.
# ON by default since the one-shot final_holdout evaluation passed
# (2026-07-31: offline frozen-model AUC 0.903 [0.761, 0.980]; online
# lambda=1 improved placed on both unseen cases). Set to 0 to recover the
# pre-risk baseline; docs/RELEASE_RISK_PROTOCOL.md section 8 records the
# switch.
RELEASE_RISK_LIVE_RERANK = os.environ.get(
    "RELEASE_RISK_LIVE_RERANK", "1"
).strip().lower() in {"1", "true", "yes", "on"}
# Slide hazard weight in the risk-adjusted score:
# Q - lambda_rot*P_rot - lambda_slide*P_slide. Default 0.5 since
# 2026-08-01: under the cached (rich) search the slide term won the
# 7-case aggregate (placed 137 -> 140, fill 149 -> 172); the earlier
# not-adopted verdict was an artifact of the starved search. Set to 0
# to recover the rotation-only policy;
# RELEASE_RISK_SLIDE_SHADOW_LAMBDA > 0 makes the shadow rerank compare
# the live policy against a different slide weight.
RELEASE_RISK_SLIDE_LAMBDA = float(
    os.environ.get("RELEASE_RISK_SLIDE_LAMBDA", "0.5")
)
RELEASE_RISK_SLIDE_SHADOW_LAMBDA = float(
    os.environ.get("RELEASE_RISK_SLIDE_SHADOW_LAMBDA", "0.0")
)
CONTACT_TOLERANCE = 0.006
MIN_SUPPORT_RATIO = 0.55
# Reject release candidates whose static settled proxy rests on a
# protected top. The 2026-08-03 scenario matrix attributed 6 of 7
# priority-cover events to release actions: release_rest_height()
# treats every packed top as a landing surface and the release path has
# no support check, so covering a priority item is a legal plan.
#
# Modes: "off" (shipped), "all" (priority AND soft tops), "priority"
# (priority tops only). The pi_B ablation priced "all" at -47 suite
# placed for covers 7 -> 2 -- but base soft covers were already rare
# (soft_clean 0.92-1.0) while soft items are 13 of 41, so most of the
# landing area "all" forfeits protects a violation that barely occurs.
# "priority" exists to keep the scored benefit at a fraction of the
# cost; it guards 4 items' tops instead of 17.
RELEASE_ATTRIBUTE_GUARD_MODES = frozenset({"off", "all", "priority"})
_release_attribute_guard_raw = os.environ.get(
    "RELEASE_ATTRIBUTE_GUARD", "0"
).strip().lower()
if _release_attribute_guard_raw in {"1", "true", "yes", "on"}:
    _release_attribute_guard_raw = "all"
elif _release_attribute_guard_raw in {"0", "false", "no", ""}:
    _release_attribute_guard_raw = "off"
if _release_attribute_guard_raw not in RELEASE_ATTRIBUTE_GUARD_MODES:
    raise ValueError(
        f"unknown RELEASE_ATTRIBUTE_GUARD "
        f"{_release_attribute_guard_raw!r}; expected one of "
        f"{sorted(RELEASE_ATTRIBUTE_GUARD_MODES)} (or a boolean alias)"
    )
RELEASE_ATTRIBUTE_GUARD = _release_attribute_guard_raw
POLICY_BUDGET_SECONDS = 6.5
# Measurement-mode work budget for the ONLINE primary search. 0 keeps the
# shipped behaviour (wall-clock only).
#
# The shipped policy stops on a deadline, so the candidate set it reaches --
# and therefore the action it picks -- is a function of machine speed at
# that instant. One different candidate at step 4 sends the episode down a
# different trajectory, which is why re-running the same forced branch from
# the same parent state does not reproduce (sigma-branch-is-the-size-of-the-
# effects) and why an identical binary returns 13/17/18 placed on b000-k40.
# ADR-002 removed exactly this dependence from the OFFLINE evaluator by
# bounding work instead of time, and the offline order became bit-identical
# across a slow and a fast machine; the online half never got the same
# treatment.
#
# Setting this makes the primary search stop after a fixed number of
# attempts, so the same state yields the same action regardless of speed.
# It does NOT remove arrival-order sensitivity -- Var_omega is a property
# of the problem, not of the instrument, and must survive.
#
# This defines a MEASUREMENT policy, not the shipped one: pi_B for finding
# structure, pi_tau (deadline) for competition performance. Never report a
# fixed-work number as shipped performance.
POLICY_ATTEMPT_BUDGET = max(
    0, int(os.environ.get("POLICY_ATTEMPT_BUDGET", "0"))
)


def effective_attempt_budget(attempt_budget):
    """An explicit budget wins; otherwise the measurement constant.

    The constant exists so the online path can be work-bounded without
    every call site threading it. The parameter exists so an offline
    probe can ask for a specific amount of work on a captured state.
    Neither should silently override the other, so explicit beats
    implicit and 0 still means off.
    """
    if attempt_budget is not None:
        return attempt_budget
    return POLICY_ATTEMPT_BUDGET or None

# How many visible items the search may consider per step. At the shipped 10
# a 40-item visible pool is searched 10 items deep, and the single largest
# measured gain on this project came from changing which 10 those are
# (class-aware coverage, placed 10.67 -> 17.00). The item dimension is the
# one axis where a breadth intervention has ever paid, so it is a knob.
MAX_POOL_ITEMS_EVALUATED = max(
    1, int(os.environ.get("MAX_POOL_ITEMS_EVALUATED", "10"))
)
RESCUE_SCAN_ENABLED = os.environ.get(
    "RESCUE_SCAN_ENABLED", "0"
).strip().lower() in {"1", "true", "yes", "on"}
RESCUE_SCAN_RESERVE_SECONDS = float(
    os.environ.get("RESCUE_SCAN_RESERVE_SECONDS", "0.2")
)
RESCUE_SCAN_ATTEMPT_BUDGET = int(
    os.environ.get("RESCUE_SCAN_ATTEMPT_BUDGET", "512")
)
RESCUE_SCAN_ATTEMPTS_PER_UNIT = int(
    os.environ.get("RESCUE_SCAN_ATTEMPTS_PER_UNIT", "32")
)
CROSS_STEP_INCUMBENT_MODES = frozenset({"off", "shadow"})
CROSS_STEP_INCUMBENT_MODE = os.environ.get(
    "CROSS_STEP_INCUMBENT_MODE", "off"
).strip().lower()
if CROSS_STEP_INCUMBENT_MODE not in CROSS_STEP_INCUMBENT_MODES:
    raise ValueError(
        f"unknown CROSS_STEP_INCUMBENT_MODE "
        f"{CROSS_STEP_INCUMBENT_MODE!r}; expected one of "
        f"{sorted(CROSS_STEP_INCUMBENT_MODES)}"
    )
CROSS_STEP_INCUMBENT_PER_ITEM = max(
    1, int(os.environ.get("CROSS_STEP_INCUMBENT_PER_ITEM", "2"))
)
TEMPORAL_CHUNK_ENSEMBLE_MODES = frozenset({"off", "shadow"})
TEMPORAL_CHUNK_ENSEMBLE_MODE = os.environ.get(
    "TEMPORAL_CHUNK_ENSEMBLE_MODE", "off"
).strip().lower()
if TEMPORAL_CHUNK_ENSEMBLE_MODE not in TEMPORAL_CHUNK_ENSEMBLE_MODES:
    raise ValueError(
        f"unknown TEMPORAL_CHUNK_ENSEMBLE_MODE "
        f"{TEMPORAL_CHUNK_ENSEMBLE_MODE!r}; expected one of "
        f"{sorted(TEMPORAL_CHUNK_ENSEMBLE_MODES)}"
    )
TEMPORAL_CHUNK_DEPTH = max(
    2, int(os.environ.get("TEMPORAL_CHUNK_DEPTH", "3"))
)
TEMPORAL_CHUNK_ATTEMPTS_PER_STEP = max(
    1, int(os.environ.get("TEMPORAL_CHUNK_ATTEMPTS_PER_STEP", "64"))
)
TEMPORAL_CHUNK_STRIDE = max(
    1, int(os.environ.get("TEMPORAL_CHUNK_STRIDE", "1"))
)
TEMPORAL_CHUNK_CELL_SIZE = max(
    0.01, float(os.environ.get("TEMPORAL_CHUNK_CELL_SIZE", "0.10"))
)
PLACEMENT_SELECTOR_MODES = frozenset(
    {"scalar", "structured_noop", "structured_retained"}
)
PLACEMENT_SELECTOR_MODE = os.environ.get(
    "PLACEMENT_SELECTOR_MODE", "scalar"
).strip().lower()
if PLACEMENT_SELECTOR_MODE not in PLACEMENT_SELECTOR_MODES:
    raise ValueError(
        f"unknown PLACEMENT_SELECTOR_MODE {PLACEMENT_SELECTOR_MODE!r}; "
        f"expected one of {sorted(PLACEMENT_SELECTOR_MODES)}"
    )
ITEM_COVERAGE_MODES = frozenset({"legacy", "class_aware"})
ITEM_COVERAGE_MODE = os.environ.get(
    "ITEM_COVERAGE_MODE", "class_aware"
).strip().lower()
OFFLINE_SEARCH_BUDGET_SECONDS = float(
    os.environ.get("OFFLINE_SEARCH_BUDGET_SECONDS", "150.0")
)
OFFLINE_MAX_EVALUATIONS = int(
    os.environ.get("OFFLINE_MAX_EVALUATIONS", "1000")
)
# Offline order search only (Agent.optimize / DryRunEvaluator), which the
# official harness calls when the case sets agent.optimize -- Task A. The
# online policy never reads these, so Task B and Task C are unaffected.
#
# Adopted 2026-08-02 from Actions run 30717998654 (ADR-002). Without a
# per-item bound one unplaceable item's scan made a single dry run cost
# ~35 s, so the search evaluated 3.0 of its allowed 1000 complete orders
# -- the seed plus two neighbours -- inside the 150 s budget. Bounding
# each item at 128 deterministic anchor attempts and capping pair-macro
# construction at 0.5 s cut a dry run to ~2.7 s, raising it to 51.3
# evaluated orders and physical placed 20 -> 25 / fill 29.298 -> 34.949.
# OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM=0 restores the legacy global-deadline
# scan; OFFLINE_PAIR_MACRO_BUDGET_SECONDS=0.0 restores the legacy
# remaining-budget macro stage.
OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM = max(
    0, int(os.environ.get("OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM", "128"))
)
OFFLINE_PAIR_MACRO_BUDGET_SECONDS = float(
    os.environ.get("OFFLINE_PAIR_MACRO_BUDGET_SECONDS", "0.5")
)
OFFLINE_RANDOM_SEED = 20260723
OFFLINE_FILL_WEIGHT = float(
    os.environ.get("OFFLINE_FILL_WEIGHT", "0.65")
)
OFFLINE_STABILITY_WEIGHT = float(
    os.environ.get("OFFLINE_STABILITY_WEIGHT", "0.35")
)
# --- Closed-loop lookahead (online policy) ---
LOOKAHEAD_TOP_K = int(os.environ.get("LOOKAHEAD_TOP_K", "3"))
LOOKAHEAD_DISCOUNT = float(os.environ.get("LOOKAHEAD_DISCOUNT", "0.5"))
LOOKAHEAD_SELECTION_MODE = os.environ.get(
    "LOOKAHEAD_SELECTION_MODE", "weighted"
).strip().lower()
LOOKAHEAD_SELECTION_MODES = frozenset(
    {"weighted", "depth2", "pool_resilience", "board"}
)
LOOKAHEAD_TIME_RESERVE_SECONDS = float(
    os.environ.get("LOOKAHEAD_TIME_RESERVE_SECONDS", "1.5")
)
LOOKAHEAD_INNER_ITEMS = int(os.environ.get("LOOKAHEAD_INNER_ITEMS", "3"))


def placement_selection_kwargs():
    """Opt into the rich pipeline without changing its selection rule."""
    if PLACEMENT_SELECTOR_MODE == "structured_noop":
        return {"structured_evaluation": True}
    if PLACEMENT_SELECTOR_MODE == "structured_retained":
        return {"retained_evaluation": True}
    return {}
# --- Board receptivity (the Tetris terms) ---
# Cell size of the 2.5D height map the board features are read off.  0.05 m
# against a container on the order of 2 m x 1.5 m gives roughly 40 x 30
# columns, which is coarse enough to scan many times per step and fine
# enough to separate a flat surface from a stepped one.
BOARD_CELL_SIZE = max(0.01, float(os.environ.get("BOARD_CELL_SIZE", "0.05")))
# How far the columns under a footprint may vary and still count as a
# landing site.  The physics tolerates a small step; a large one is a
# topple.
BOARD_FLATNESS_TOLERANCE = max(
    0.0, float(os.environ.get("BOARD_FLATNESS_TOLERANCE", "0.02"))
)
# Alternativity saturates: the difference between one site and two is the
# difference between hostage and free, the difference between forty and
# forty-one is nothing.
BOARD_SITE_CAP = max(1, int(os.environ.get("BOARD_SITE_CAP", "16")))
# Distinct footprints probed per step, largest first.  Large footprints
# lose their sites first, so they carry most of the signal.
BOARD_PROBE_SHAPES = max(1, int(os.environ.get("BOARD_PROBE_SHAPES", "8")))
VISIBLE_POOL_ROLLOUT_MODES = frozenset({"off", "shadow", "enforce"})
VISIBLE_POOL_ROLLOUT_MODE = os.environ.get(
    "VISIBLE_POOL_ROLLOUT_MODE", "off"
).strip().lower()
if VISIBLE_POOL_ROLLOUT_MODE not in VISIBLE_POOL_ROLLOUT_MODES:
    raise ValueError(
        f"unknown VISIBLE_POOL_ROLLOUT_MODE "
        f"{VISIBLE_POOL_ROLLOUT_MODE!r}; expected one of "
        f"{sorted(VISIBLE_POOL_ROLLOUT_MODES)}"
    )
VISIBLE_POOL_ROLLOUT_TOP_K = max(
    1, int(os.environ.get("VISIBLE_POOL_ROLLOUT_TOP_K", "3"))
)
VISIBLE_POOL_ROLLOUT_DEPTH = max(
    1, int(os.environ.get("VISIBLE_POOL_ROLLOUT_DEPTH", "3"))
)
VISIBLE_POOL_ROLLOUT_ATTEMPTS = max(
    1, int(os.environ.get("VISIBLE_POOL_ROLLOUT_ATTEMPTS", "64"))
)
VISIBLE_POOL_ROLLOUT_Q_BAND = max(
    0.0, float(os.environ.get("VISIBLE_POOL_ROLLOUT_Q_BAND", "0.15"))
)
# Systematic anchor-grid subsampling inside the rollout's future steps only.
# 1 reproduces the measured enforce/shadow runs exactly; a larger value
# trades resolution for reach at the same attempt budget.
VISIBLE_POOL_ROLLOUT_STRIDE = max(
    1, int(os.environ.get("VISIBLE_POOL_ROLLOUT_STRIDE", "1"))
)
# Live candidate search: reorder the anchor scan into stride-interleaved
# order so a deadline-truncated search covers the whole support plane
# coarsely instead of one band densely.  This is a permutation, not a
# subsample -- a search that runs to exhaustion sees the identical set.
# 1 is the shipped order.
LIVE_SEARCH_INTERLEAVE = max(
    1, int(os.environ.get("LIVE_SEARCH_INTERLEAVE", "1"))
)
# --- DPOR (dynamic partial-order reduction) for pair-block ordering ---
DPOR_MAX_ALTERNATE_ATTEMPTS = int(
    os.environ.get("DPOR_MAX_ALTERNATE_ATTEMPTS", "16")
)
# Candidate search is breadth-first across prioritized
# (item, orientation, container) units.  The first pass prevents one
# infeasible unit from consuming the whole policy budget; later passes keep
# improving the best validated incumbent.
#
# 64 was too shallow to reach the depth at which a unit's candidates start
# existing.  Probing the terminal states of episodes that died with zero
# candidates (reports/same-class-stacking) found placements for 6 of 23
# visible items at 256 attempts per item and none at all at 64, with 1024
# and 4096 adding nothing -- so the curve has a knee, and 64 sat below it
# while the live search reported units 1/120 completed and gave up on a
# state that still had legal moves.
#
# Measured at 64/128/256 over two paired blocks on the five development
# configs (reports/first-pass-depth): placed 9W/0L/1T for both 128 and
# 256, sign test p = 0.0039, suite totals 143 -> 172 -> 179, fill
# 176.8 -> 225.3 -> 218.3.  Total attempts per step and policy time are
# unchanged, so this redistributes work rather than spending more.
# The cost is real and shows up where it was predicted: mean items with
# a candidate in the opening falls 9.64 -> 8.28.  placed rose on every
# configuration anyway.
ANCHOR_FIRST_PASS_ATTEMPTS = int(
    os.environ.get("ANCHOR_FIRST_PASS_ATTEMPTS", "256")
)
ANCHOR_DEEP_PASS_ATTEMPTS = int(
    os.environ.get("ANCHOR_DEEP_PASS_ATTEMPTS", "256")
)
# Anchor-space fallback. The shipped support_plane generator can exhaust its
# entire anchor space inside the policy budget and accept nothing while the
# cartesian space at the same state holds physically safe placements
# (task-c-fatal-oracle-two-classes: c001-k1 step 18, support_plane 0 settled /
# 0 release after 18,419 attempts in 4.2 s, cartesian 6 settled / 54 release,
# all 60 safe under live settle). No reordering and no extra time can reach a
# solution the primary space does not contain, so the fallback changes the
# space rather than the schedule.
#
# It runs only after the primary search has completed every unit without
# accepting anything, and it replaces the redundant second scan rather than
# adding time: when the first search returns empty, today's policy repeats the
# identical scan, which at c001-k1 costs 4.2 s of a 6.5 s budget for nothing.
#
# Coarse-to-fine, not dense-truncated. A dense cartesian scan costs 19.6 s for
# settled at that state and would explore one corner deeply; the stride ladder
# covers the whole space at every level, so a bounded run still sees all of it.
# Default OFF -- every previous fallback design in this repository looked good
# on static replay and lost on physics.
# Shipped ON 2026-08-04 and REVERTED the same day. The official submission
# scored 29.959 against 35.375 for the identical build with this off, and
# all six components fell: cog -20.7%, stability -22.4%, soft -18.1%,
# placement -13.3%, fill -1.8%, placed -2.6%. Attribution is clean because
# nothing else in that build changes default behaviour.
#
# The mechanism was predictable from Ranker.score and I did not check it:
# the score this gate deliberately overrides is built from +2.0*support,
# +0.35y and -0.18*z*mass -- the only terms steering centre-of-gravity and
# stability. Systematically preferring a lower-scored placement therefore
# spends exactly the components that fell hardest. Local evaluate() returns
# only fill and placed, so the four components paying the bill are not
# computed locally at all, and the local shake proxy that could have stood
# in was never made an acceptance criterion.
DEATH_BAND_FALLBACK_ENABLED = os.environ.get(
    "DEATH_BAND_FALLBACK", "0"
).strip().lower() in {"1", "true", "yes", "on"}
# Fixed from the measured killer scores, not fitted.
# Score pre-filter, and it is load-bearing rather than decoration. Dropping
# it (DEATH_BAND_SCORE="") turns the gate into a GLOBAL risk filter that acts
# on any release the model prices at P_rot >= 0.5, which is the intervention
# class this repository already rejected once
# (visible-pool-rollout-enforce-rejected-v1). The live risk rerank is instead
# a soft score penalty and ships on; this hard replacement gate ships off.
# -1.5 came from three measured killer scores, so it IS a fitted constant --
# the unbanded form is kept as an ablation arm to price that fit rather than
# defended as principled.
# Require the replacement to dominate: no worse on support ratio as well as
# safer on P_rot. Set to 0 for the v1 behaviour that traded one for the other.
DEATH_BAND_REQUIRE_DOMINANCE = os.environ.get(
    "DEATH_BAND_REQUIRE_DOMINANCE", "1"
).strip().lower() in {"1", "true", "yes", "on"}
_death_band_score = os.environ.get("DEATH_BAND_SCORE", "-1.5").strip()
DEATH_BAND_SCORE = float(_death_band_score) if _death_band_score else None
# Skip the gate entirely when the step's budget is nearly spent: evaluating
# P_rot and re-searching both cost time, and b000-k20 measured the mean
# drifting 19.7 -> 18.0 with zero swaps -- pure evaluation overhead on a
# deadline trajectory. Half a second is the floor below which the re-search
# cannot complete anyway.
DEATH_BAND_MIN_BUDGET_SECONDS = float(
    os.environ.get("DEATH_BAND_MIN_BUDGET_SECONDS", "0.5")
)
ANCHOR_FALLBACK_ENABLED = os.environ.get(
    "ANCHOR_FALLBACK_ENABLED", "0"
).strip().lower() in {"1", "true", "yes", "on"}
ANCHOR_FALLBACK_STRIDES = tuple(
    max(1, int(value))
    for value in os.environ.get(
        "ANCHOR_FALLBACK_STRIDES", "16,4,1"
    ).split(",")
    if value.strip()
) or (16, 4, 1)
# Derive the anchor envelope from the container's own half-spaces instead of
# from a box formula. See rectangular_container_anchor_bounds.
#
# ON by default since 2026-08-02. This is a contract correction, not a
# heuristic: inside_container and container_z_interval already used the real
# half-spaces while the envelope used a box, so the low-y side was one wall
# thickness too tight on the AKE/AKN-derived containers, for every item and
# both generators. On the state previously certified as a dead end, both
# generators run exhaustively returned 0 candidates under the box bound and
# 33 under this one, all 33 physically safe.
#
# Task C, three repeats per cell, deterministic and non-overlapping:
# c000-k1 placed 19 -> 23 with fill 13.529 -> 26.099, c001-k1 placed 18 -> 21
# with fill 22.256 -> 25.366.
#
# What is NOT measured, and the honest reason it shipped anyway: the Task B
# guard has not run on CI, and the guard does not reproduce off it. The search
# space is strictly wider, so each unit spends its attempts differently inside
# the same budget. `ANCHOR_TRUE_ENVELOPE=0` and the `box_envelope` ablation arm
# recover the previous behaviour exactly.
ANCHOR_TRUE_ENVELOPE = os.environ.get(
    "ANCHOR_TRUE_ENVELOPE", "1"
).strip().lower() in {"1", "true", "yes", "on"}
# Shrink the anchor envelope inward by sin(tilt) x item height. The fill
# evaluator forfeits an item's ENTIRE volume when any settled corner ends up
# past a boundary plane beyond the inclusion margin, and wall-adjacent tall
# items lean by the measured settle tilt (local shake proxy: 2.3-3.4 deg on
# Task C), pushing the top corner several cm outside -- measured forfeit on
# c001-k1: 5 of 21 items, 23.2% of packed volume, 7.49 fill points. The
# angle is fixed from that measurement, not fitted; the margin scales with
# the placed item's height, not with any catalog of item types. 0 disables.
ANCHOR_TILT_MARGIN_DEG = float(
    os.environ.get("ANCHOR_TILT_MARGIN_DEG", "0")
)
# Allocation tie-break. Container choice is otherwise an accident of the
# per-step score maximum, which the two-container smoke measured as a 19:3
# skew that left one container nearly empty when a failed placement ended
# the episode. Within this score band, prefer the container with more
# estimated remaining volume; outside it, score wins as before. 0 disables.
L3_PREFER_EMPTY_BAND = float(
    os.environ.get("L3_PREFER_EMPTY_BAND", "0")
)
# Measured on the two-container scene: every episode-ending action was a
# bottom-tier release into the crowded container while the other stood
# near-empty, and the release risk gate never evaluated it. When ONLY
# release candidates exist for the step, route the release to the container
# with the most estimated remaining volume (lexicographic: emptiness, then
# score). Settled candidates always win as before. 0 disables.
L3_RELEASE_ROUTE = os.environ.get(
    "L3_RELEASE_ROUTE", "0"
).strip().lower() in {"1", "true", "yes", "on"}
# Loading order over zones of the container, as a score term.
#
# Transport enters at y = -width/2 and runs toward +y, so an item parked in
# front spends the whole lane behind it. Measured on the board
# dual-shelf-mixed stops on: of the poses where the space is free and the
# item fits, 62.9% are refused ONLY by transport_path_clear, and those sit
# deep (y median +0.250) while the legal ones sit by the door (-0.400).
# The loss is the corridor, not the envelope and not the cargo, so it is
# recoverable by where and when things go in.
#
# Ranker.score already leans deep for ordinary cargo (+0.35*y). What it has
# no notion of is that the deep region is SPENT first and cannot be
# revisited. This adds that as a ranking bonus by zone.
#
# "doctrine" is shelf top, then deep, then centre, then under the shelf --
# under-shelf last because it is a dead-end pocket worth using only when
# nothing else reaches. "reversed" is the same order inverted and exists so
# the arm has a control that moves the same machinery the other way; a
# doctrine arm that beats base but not reversed has measured the bonus, not
# the ordering.
#
# Default off. Nothing about the shipped policy changes until an ablation
# with base/base_null pairs says the effect clears that run's noise floor.
ZONE_ORDER_MODES = frozenset({"off", "doctrine", "reversed"})
ZONE_ORDER_MODE = os.environ.get("ZONE_ORDER", "off").strip().lower()
# The fingerprint resolves each registered knob by its ENV name, so a module
# attribute called ZONE_ORDER_MODE records as null and the knob is registered
# without its value ever being hashed. Several knobs already sit in the
# fingerprint that way; this one does not.
ZONE_ORDER = ZONE_ORDER_MODE
# One bonus unit per rank step, so the span is three. It has to clear the
# 2.0 that `2.0 * support` swings, because a release candidate scores
# support 0 -- support_ratio needs 6 mm of contact and a release pose is
# sent 16 mm clear of its surface -- while a pose resting on the shelf
# plate scores 1. At 0.5 the whole zone span was 1.5 and could not reorder
# that pair, so the knob expressed nothing where it mattered most.
ZONE_ORDER_BONUS = float(os.environ.get("ZONE_ORDER_BONUS", "1.0"))
if ZONE_ORDER_MODE not in ZONE_ORDER_MODES:
    raise ValueError(
        f"unknown ZONE_ORDER {ZONE_ORDER_MODE!r}; "
        f"expected one of {', '.join(sorted(ZONE_ORDER_MODES))}"
    )
# Rank 0 is filled last. The bonus is rank * ZONE_ORDER_BONUS, so the gap
# between adjacent zones is one bonus unit and the span is three.
ZONE_RANKS = {
    "doctrine": {"shelf_top": 3, "deep": 2, "centre": 1, "under_shelf": 0},
    "reversed": {"shelf_top": 0, "deep": 1, "centre": 2, "under_shelf": 3},
}
CONSTRUCTIVE_ORDER_MODES = frozenset({"composite", "volume"})
CONSTRUCTIVE_ORDER_MODE = os.environ.get(
    "CONSTRUCTIVE_ORDER_MODE", "composite"
).strip().lower()
ANCHOR_GENERATOR_MODES = frozenset({"cartesian", "support_plane"})
ANCHOR_GENERATOR_MODE = os.environ.get(
    "ANCHOR_GENERATOR_MODE", "support_plane"
).strip().lower()
SUPPORT_PLANE_ADJACENCY = float(
    os.environ.get("SUPPORT_PLANE_ADJACENCY", "0.016")
)
SUPPORT_PLANE_ROUND_ATTEMPTS = int(
    os.environ.get("SUPPORT_PLANE_ROUND_ATTEMPTS", "8")
)
CANDIDATE_AUDIT_ENABLED = (
    os.environ.get("NEDO_CANDIDATE_AUDIT", "0").strip().lower()
    in {"1", "true", "yes", "on"}
)
EPS = 1e-6


def get_rotated_dimensions(length, width, height, orientation):
    dimensions = (
        (length, width, height),
        (length, height, width),
        (height, width, length),
        (width, length, height),
        (width, height, length),
        (height, length, width),
    )
    if orientation not in range(6):
        raise ValueError("orientation must be between 0 and 5")
    return tuple(float(value) for value in dimensions[orientation])


def unique_orientations(item):
    seen = set()
    result = []
    for orientation in range(6):
        dims = get_rotated_dimensions(
            item["length"], item["width"], item["height"], orientation
        )
        key = tuple(round(value, 6) for value in dims)
        if key not in seen:
            seen.add(key)
            result.append(orientation)
    return result


def container_offset_x(container):
    center = container.get("center")
    return 0.0 if center is None else float(center[0])


def container_requires_shelf(container):
    return bool(container.get("shelf", container.get("require_shelf", False)))


def normalize_container(container):
    normalized = copy.deepcopy(container)
    normalized["require_shelf"] = container_requires_shelf(normalized)
    normalized.setdefault("buffer", 0.0)
    normalized.setdefault("cut_x", 0.0)
    normalized.setdefault("cut_y", 0.0)
    normalized.setdefault("is_prioritized", False)
    normalized["packed_items"] = []
    return normalized


def local_to_world(local_pos, container):
    x, y, z = (float(value) for value in local_pos)
    return np.array(
        [x + container_offset_x(container), y, z], dtype=np.float64
    )


def world_to_local(world_pos, container):
    x, y, z = (float(value) for value in world_pos)
    return np.array(
        [x - container_offset_x(container), y, z], dtype=np.float64
    )


def _compute_container_z_interval(
    x,
    y,
    dims,
    offset_x,
    points,
    normals,
):
    half_size = np.asarray(dims, dtype=np.float64) / 2.0
    center_x = float(x) + float(offset_x)
    lower = -float("inf")
    upper = float("inf")
    limit = -INCLUSION_CLEARANCE + EPS

    for point_values, normal_values in zip(points, normals):
        point = np.asarray(point_values, dtype=np.float64)
        normal = np.asarray(normal_values, dtype=np.float64)
        constant = (
            normal[0] * (center_x - point[0])
            + normal[1] * (float(y) - point[1])
            - normal[2] * point[2]
            + float(np.abs(normal) @ half_size)
        )
        coefficient = float(normal[2])
        if abs(coefficient) <= EPS:
            if constant > limit:
                return None
            continue
        boundary = (limit - constant) / coefficient
        if coefficient > 0.0:
            upper = min(upper, boundary)
        else:
            lower = max(lower, boundary)

    if lower > upper + EPS:
        return None
    return (float(lower), float(upper))


@lru_cache(maxsize=65536)
def _cached_container_z_interval(
    x,
    y,
    dims,
    offset_x,
    points,
    normals,
):
    return _compute_container_z_interval(
        x, y, dims, offset_x, points, normals
    )


_CONTAINER_Z_INTERVAL_CACHE_BYPASS = False


def container_z_interval(x, y, dims, container):
    """Exact AABB z interval allowed by the static container half-spaces."""
    points = container.get("points")
    normals = container.get("n_vecs")
    if points is None or normals is None:
        return (-float("inf"), float("inf"))
    point_key = tuple(
        tuple(float(value) for value in point) for point in points
    )
    normal_key = tuple(
        tuple(float(value) for value in normal) for normal in normals
    )
    arguments = (
        float(x),
        float(y),
        tuple(float(value) for value in dims),
        container_offset_x(container),
        point_key,
        normal_key,
    )
    if _CONTAINER_Z_INTERVAL_CACHE_BYPASS:
        return _compute_container_z_interval(*arguments)
    return _cached_container_z_interval(*arguments)


def packed_position_world(packed):
    for key in ("pos", "place_pos", "position", "center"):
        value = packed.get(key)
        if value is not None:
            return np.asarray(value, dtype=np.float64)
    raise KeyError("packed item has no position")


def packed_dimensions(packed):
    if packed.get("dims") is not None:
        return tuple(float(value) for value in packed["dims"])
    settled_orn = packed.get("orn")
    if settled_orn is not None and len(settled_orn) == 4:
        x, y, z, w = (float(value) for value in settled_orn)
        norm = math.sqrt(x * x + y * y + z * z + w * w)
        if norm > EPS:
            x, y, z, w = (value / norm for value in (x, y, z, w))
        rotation = np.array(
            [
                [
                    1.0 - 2.0 * (y * y + z * z),
                    2.0 * (x * y - z * w),
                    2.0 * (x * z + y * w),
                ],
                [
                    2.0 * (x * y + z * w),
                    1.0 - 2.0 * (x * x + z * z),
                    2.0 * (y * z - x * w),
                ],
                [
                    2.0 * (x * z - y * w),
                    2.0 * (y * z + x * w),
                    1.0 - 2.0 * (x * x + y * y),
                ],
            ],
            dtype=np.float64,
        )
        base_dimensions = np.array(
            [
                packed["length"],
                packed["width"],
                packed["height"],
            ],
            dtype=np.float64,
        )
        settled_aabb = np.abs(rotation) @ base_dimensions
        return tuple(float(value) for value in settled_aabb)
    orientation = int(packed.get("orientation", 0))
    return get_rotated_dimensions(
        packed["length"], packed["width"], packed["height"], orientation
    )


@dataclass(frozen=True)
class AABB:
    center: tuple
    size: tuple
    name: str = ""

    @property
    def minimum(self):
        return np.asarray(self.center) - np.asarray(self.size) / 2.0

    @property
    def maximum(self):
        return np.asarray(self.center) + np.asarray(self.size) / 2.0

    @property
    def top(self):
        return float(self.maximum[2])


@dataclass(frozen=True)
class SupportPlaneComponent:
    surfaces: tuple

    @property
    def top(self):
        return max(float(surface.top) for surface in self.surfaces)

    @property
    def minimum_xy(self):
        return np.min(
            np.asarray(
                [surface.minimum[:2] for surface in self.surfaces],
                dtype=np.float64,
            ),
            axis=0,
        )

    @property
    def maximum_xy(self):
        return np.max(
            np.asarray(
                [surface.maximum[:2] for surface in self.surfaces],
                dtype=np.float64,
            ),
            axis=0,
        )

    @property
    def area(self):
        rectangles = [
            (
                float(surface.minimum[0]),
                float(surface.maximum[0]),
                float(surface.minimum[1]),
                float(surface.maximum[1]),
            )
            for surface in self.surfaces
        ]
        return rectangle_union_area(rectangles)

    @property
    def contains_floor(self):
        return any(surface.name == "floor" for surface in self.surfaces)


@dataclass(frozen=True)
class SupportMetrics:
    ratio: float
    center_margin: float
    contact_count: int
    mass_support_ratio: float


@dataclass(frozen=True)
class ReleaseRiskThresholds:
    """
    Provisional deterministic thresholds for the isolated gate ablation.

    There is deliberately no initial-tilt threshold. Every orientation the
    agent can command is axis-aligned, so ``initial_tilt_deg`` is always
    0.0 and a tilt rule could never fire; see
    ``ReleaseRiskFeatures.feature_availability``.
    """

    min_support_ratio: float = float(
        os.environ.get("RELEASE_RISK_MIN_SUPPORT_RATIO", "0.25")
    )
    min_com_margin: float = float(
        os.environ.get("RELEASE_RISK_MIN_COM_MARGIN", "-0.25")
    )
    max_overhang_ratio: float = float(
        os.environ.get("RELEASE_RISK_MAX_OVERHANG_RATIO", "0.75")
    )
    max_drop_normalized: float = float(
        os.environ.get("RELEASE_RISK_MAX_DROP_NORMALIZED", "0.75")
    )
    max_support_imbalance: float = float(
        os.environ.get("RELEASE_RISK_MAX_SUPPORT_IMBALANCE", "0.90")
    )

    # These five live as dataclass fields, so `getattr(agent, ENV_NAME)`
    # finds nothing and the fingerprint stores null for all of them --
    # registered, and never actually hashed. Exposed at module level below
    # for the same reason DEATH_BAND_FALLBACK is: a knob the fingerprint
    # cannot see is a knob a merge can change without moving the hash, which
    # is the exact failure the registry exists to catch.

    def as_dict(self):
        return {
            "min_support_ratio": float(self.min_support_ratio),
            "min_com_margin": float(self.min_com_margin),
            "max_overhang_ratio": float(self.max_overhang_ratio),
            "max_drop_normalized": float(self.max_drop_normalized),
            "max_support_imbalance": float(self.max_support_imbalance),
        }


# Module-level mirrors of the five threshold fields, under their ENV names,
# so `context/knobs.json` registering them actually reaches the fingerprint.
# Values come from the dataclass rather than re-reading os.environ, so the
# two can never drift apart.
_RELEASE_RISK_DEFAULT_THRESHOLDS = ReleaseRiskThresholds()
RELEASE_RISK_MIN_SUPPORT_RATIO = _RELEASE_RISK_DEFAULT_THRESHOLDS.min_support_ratio
RELEASE_RISK_MIN_COM_MARGIN = _RELEASE_RISK_DEFAULT_THRESHOLDS.min_com_margin
RELEASE_RISK_MAX_OVERHANG_RATIO = _RELEASE_RISK_DEFAULT_THRESHOLDS.max_overhang_ratio
RELEASE_RISK_MAX_DROP_NORMALIZED = _RELEASE_RISK_DEFAULT_THRESHOLDS.max_drop_normalized
RELEASE_RISK_MAX_SUPPORT_IMBALANCE = (
    _RELEASE_RISK_DEFAULT_THRESHOLDS.max_support_imbalance
)
# Same gap, same fix: the variable is DEATH_BAND_FALLBACK_ENABLED, so the
# knob that cost 15.3% officially was registered and never hashed.
DEATH_BAND_FALLBACK = DEATH_BAND_FALLBACK_ENABLED


@dataclass(frozen=True)
class ReleaseRiskFeatures:
    support_ratio: float
    com_margin: float
    overhang_ratio: float
    drop_normalized: float
    support_imbalance: float
    left_right_imbalance: float
    front_back_imbalance: float
    initial_tilt_deg: float
    initial_orientation: int

    def as_dict(self):
        return {
            "support_ratio": float(self.support_ratio),
            "com_margin": float(self.com_margin),
            "overhang_ratio": float(self.overhang_ratio),
            "drop_normalized": float(self.drop_normalized),
            "support_imbalance": float(self.support_imbalance),
            "left_right_imbalance": float(self.left_right_imbalance),
            "front_back_imbalance": float(self.front_back_imbalance),
            "initial_tilt_deg": float(self.initial_tilt_deg),
            "initial_orientation": int(self.initial_orientation),
        }

    @staticmethod
    def feature_sources():
        """
        Provenance of every online feature.

        No field uses PyBullet settle telemetry.  That telemetry is joined
        only by the offline replay/summary tools after the action executes.
        """
        return {
            "support_ratio": "predicted_contact_state",
            "com_margin": "predicted_contact_state",
            "overhang_ratio": "predicted_contact_state",
            "drop_normalized": "command_and_predicted_contact_state",
            "support_imbalance": "predicted_contact_state",
            "left_right_imbalance": "predicted_contact_state",
            "front_back_imbalance": "predicted_contact_state",
            "initial_tilt_deg": "command_state",
            "initial_orientation": "command_state",
        }

    @staticmethod
    def unavailable_features():
        """
        Fields that are recorded but carry no information today.

        ``initial_tilt_deg`` is a placeholder: every orientation the agent
        can command is axis-aligned, so the commanded tilt is identically
        0.0.  It is kept in the record so that replays stay schema-stable
        and so a future non-axis-aligned command can populate it, but it
        must not be used as a gate rule or as a learned feature while it is
        constant.
        """
        return ("initial_tilt_deg",)

    @staticmethod
    def feature_availability():
        unavailable = set(ReleaseRiskFeatures.unavailable_features())
        return {
            name: (
                "unavailable_placeholder"
                if name in unavailable
                else "available"
            )
            for name in ReleaseRiskFeatures.feature_sources()
        }


@dataclass(frozen=True)
class ReleaseRiskAssessment:
    passed: bool
    reasons: tuple


@dataclass(frozen=True, slots=True)
class RankEvaluation:
    """Named immediate-score terms before physical-risk adjustment."""

    volume: float
    support: float
    depth: float
    lateral: float
    lift: float
    routing: float
    zone: float
    unattributed: float
    total: float

    def components(self):
        return {
            "volume": float(self.volume),
            "support": float(self.support),
            "depth": float(self.depth),
            "lateral": float(self.lateral),
            "lift": float(self.lift),
            "routing": float(self.routing),
            "zone": float(self.zone),
            "unattributed": float(self.unattributed),
        }


@dataclass(frozen=True, slots=True)
class RiskAdjustment:
    rotation_probability: float | None
    slide_probability: float | None
    rotation_penalty: float
    slide_penalty: float
    total_penalty: float


@dataclass(frozen=True, slots=True)
class PlacementCommand:
    """The command sent to the simulator, separate from predicted settle."""

    pool_index: int
    stable_item_index: int
    container_index: int
    place_pos: tuple
    orientation: int
    mode: str

    def as_action(self):
        return {
            "item_idx": int(self.pool_index),
            "container_idx": int(self.container_index),
            "place_pos": np.asarray(self.place_pos, dtype=np.float32),
            "orientation": int(self.orientation),
        }


@dataclass(frozen=True, slots=True)
class PlacementProposal:
    """Candidate facts produced by search, before ranking or selection."""

    pool_index: int
    stable_item_index: int
    item: dict
    container_index: int
    container: dict
    orientation: int
    candidate: AABB
    source: str = "placement_core"

    def command(self):
        center = simulator_action_center(self.candidate, self.container)
        return PlacementCommand(
            pool_index=int(self.pool_index),
            stable_item_index=int(self.stable_item_index),
            container_index=int(self.container_index),
            place_pos=tuple(float(value) for value in center),
            orientation=int(self.orientation),
            mode=(
                "release"
                if self.candidate.name == "release_candidate"
                else "settled"
            ),
        )


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    """The complete scalar evaluation retained for later selectors."""

    immediate: RankEvaluation
    risk: RiskAdjustment
    adjusted_score: float
    provenance: str


@dataclass(frozen=True)
class PlacementDecision:
    action: dict
    candidate: AABB
    score: float
    proposal: PlacementProposal | None = None
    command: PlacementCommand | None = None
    evaluation: CandidateEvaluation | None = None


@dataclass(frozen=True)
class CrossStepCandidate:
    """A validated candidate retained under a stable item identity."""

    item_index: int
    previous_pool_index: int
    container_index: int
    orientation: int
    candidate: AABB
    previous_score: float


@dataclass(frozen=True)
class TemporalChunkProposal:
    """One future action predicted by a rollout rooted at an older step."""

    origin_step: int
    target_step: int
    item_index: int
    previous_pool_index: int
    container_index: int
    orientation: int
    candidate: AABB
    previous_score: float


class CrossStepCandidateCollector:
    """Keep a bounded top-N per (item, settled/release) group."""

    def __init__(self, per_item):
        self.per_item = max(1, int(per_item))
        self._groups = {}
        self._seen = set()
        self._sequence = 0

    def observe(self, item_idx, item, container_idx, orientation, decision):
        candidate = decision.candidate
        item_index = int(item.get("index", item_idx))
        kind = (
            "release"
            if candidate.name == "release_candidate"
            else "settled"
        )
        candidate_key = (
            item_index,
            int(container_idx),
            int(orientation),
            kind,
            tuple(round(float(value), 6) for value in candidate.center),
            tuple(round(float(value), 6) for value in candidate.size),
        )
        if candidate_key in self._seen:
            return
        self._seen.add(candidate_key)
        retained = CrossStepCandidate(
            item_index=item_index,
            previous_pool_index=int(item_idx),
            container_index=int(container_idx),
            orientation=int(orientation),
            candidate=candidate,
            previous_score=float(decision.score),
        )
        self._sequence += 1
        entry = (float(decision.score), self._sequence, retained)
        group = self._groups.setdefault((item_index, kind), [])
        if len(group) < self.per_item:
            heapq.heappush(group, entry)
        elif entry[0] > group[0][0]:
            heapq.heapreplace(group, entry)

    def snapshot(self, excluded_item_index=None):
        retained = []
        for (item_index, _kind), group in sorted(self._groups.items()):
            if (
                excluded_item_index is not None
                and item_index == int(excluded_item_index)
            ):
                continue
            retained.extend(
                candidate
                for _score, _sequence, candidate in sorted(
                    group,
                    key=lambda entry: (entry[0], entry[1]),
                    reverse=True,
                )
            )
        return retained


class VisiblePoolRolloutCollector:
    """Best accepted live-search candidate for each stable item."""

    def __init__(self):
        self._best_by_item = {}
        self._class_by_item = {}

    def observe(
        self,
        item_idx,
        item,
        _container_idx,
        _orientation,
        decision,
    ):
        item_index = int(item.get("index", item_idx))
        current = self._best_by_item.get(item_index)
        if current is None or float(decision.score) > float(current.score):
            self._best_by_item[item_index] = decision
            self._class_by_item[item_index] = (
                tuple(
                    sorted(
                        round(float(item[name]), 6)
                        for name in ("length", "width", "height")
                    )
                ),
                round(float(item.get("mass", 1.0)), 6),
                bool(item.get("is_soft", False)),
                bool(item.get("is_prioritized", False)),
            )

    def snapshot(self, limit=None):
        ordered = sorted(
            self._best_by_item.values(),
            key=lambda decision: float(decision.score),
            reverse=True,
        )
        if limit is None:
            return ordered
        limit = max(0, int(limit))
        item_for_decision = {
            id(decision): item_index
            for item_index, decision in self._best_by_item.items()
        }
        diverse = []
        seen_classes = set()
        for decision in ordered:
            item_index = item_for_decision[id(decision)]
            item_class = self._class_by_item[item_index]
            if item_class in seen_classes:
                continue
            seen_classes.add(item_class)
            diverse.append(decision)
            if len(diverse) >= limit:
                return diverse
        selected_ids = {id(decision) for decision in diverse}
        for decision in ordered:
            if id(decision) in selected_ids:
                continue
            diverse.append(decision)
            if len(diverse) >= limit:
                break
        return diverse


@dataclass(frozen=True)
class VisiblePoolFeasibility:
    feasible_items: int
    evaluated_items: int
    best_score: float


@dataclass(frozen=True)
class LookaheadEvaluation:
    decision: PlacementDecision
    feasible_next_items: int
    total_next_items: int
    best_next_score: float


@dataclass(frozen=True)
class VisiblePoolRolloutValue:
    """Deterministic static-proxy value after one candidate action."""

    placed_count: int
    added_volume: float
    cumulative_rotation_risk: float
    cumulative_slide_risk: float
    attempts_used: int
    accepted_candidates: int
    initial_release_proxy: bool
    release_truncated: bool
    terminal_reason: str
    trace: tuple


@dataclass(frozen=True)
class PlacementTrace:
    item_index: int
    container_idx: int
    orientation: int
    candidate: AABB
    support: SupportMetrics
    mass: float


@dataclass(frozen=True)
class BlockSignature:
    fill_ratio: float
    top_profile: tuple
    min_support_ratio: float
    total_mass: float
    center_of_mass: tuple


@dataclass(frozen=True)
class BlockTemplate:
    item_indices: tuple
    internal_order: tuple
    relative_placements: tuple
    dimensions: tuple
    signature: BlockSignature


@dataclass(frozen=True)
class DryRunResult:
    placed_count: int
    failed_index: object
    placed_volume: float
    fill_ratio: float
    stability_proxy: float
    center_of_mass_z: float
    normalized_center_of_mass_z: float
    mean_support_ratio: float
    min_support_ratio: float
    min_support_margin: float
    mean_support_count: float
    runtime_seconds: float

    def rank_key(self):
        return (
            int(self.placed_count),
            float(self.placed_volume),
            float(self.fill_ratio),
            float(self.stability_proxy),
            -float(self.normalized_center_of_mass_z),
        )

    def weighted_score(
        self,
        fill_weight=OFFLINE_FILL_WEIGHT,
        stability_weight=OFFLINE_STABILITY_WEIGHT,
    ):
        return (
            float(fill_weight) * float(self.fill_ratio)
            + float(stability_weight) * float(self.stability_proxy)
        )


def shelf_aabbs(container):
    length = float(container["length"])
    width = float(container["width"])
    height = float(container["height"])
    thickness = float(container["thickness"])
    buffer = float(container.get("buffer", 0.0))
    cut_x = float(container.get("cut_x", 0.0))
    shelf_z = height / 2.0 + thickness / 2.0 + buffer

    shelves = []
    if cut_x > 0.0:
        shelves.append(
            AABB(
                center=(
                    -length / 2.0 + cut_x / 2.0 + thickness,
                    0.0,
                    shelf_z,
                ),
                size=(cut_x, width - 2.0 * thickness, thickness),
                name="small_shelf",
            )
        )

    if container_requires_shelf(container):
        shelves.append(
            AABB(
                center=(0.0, width / 4.0, shelf_z),
                size=(
                    length - thickness,
                    width / 2.0 - 2.0 * thickness,
                    thickness,
                ),
                name="main_shelf",
            )
        )
    return shelves


# Rebuilding every packed AABB from dicts dominated the transport check
# (measured: 8163 rebuild calls / 2.7 s inside one 5 s policy call --
# 78% of the search budget), starving the candidate scan to ~190
# attempts against populations in the tens of thousands. The packed
# list is immutable during a search, so cache per list identity;
# lookahead simulations deep-copy the container (new list object) and
# placements append (length change), both of which invalidate.
_PACKED_AABBS_CACHE: dict[int, tuple] = {}


def packed_aabbs_local(container):
    packed_list = container.get("packed_items", [])
    key = id(packed_list)
    hit = _PACKED_AABBS_CACHE.get(key)
    if (
        hit is not None
        and hit[0] is packed_list
        and hit[1] == len(packed_list)
    ):
        return hit[2]
    boxes = []
    for packed in packed_list:
        try:
            center = world_to_local(packed_position_world(packed), container)
            dims = packed_dimensions(packed)
        except (KeyError, TypeError, ValueError):
            continue
        boxes.append(
            (
                AABB(tuple(center), dims, "packed_item"),
                bool(packed.get("is_soft", False)),
                bool(packed.get("is_prioritized", False)),
            )
        )
    if len(_PACKED_AABBS_CACHE) > 256:
        _PACKED_AABBS_CACHE.clear()
    _PACKED_AABBS_CACHE[key] = (packed_list, len(packed_list), boxes)
    return boxes


def xy_overlap_area(first, second):
    overlap = np.maximum(
        0.0,
        np.minimum(first.maximum[:2], second.maximum[:2])
        - np.maximum(first.minimum[:2], second.minimum[:2]),
    )
    return float(overlap[0] * overlap[1])


def rectangle_union_area(rectangles):
    """Exact union area for a small collection of axis-aligned rectangles."""
    normalized = [
        (float(x0), float(x1), float(y0), float(y1))
        for x0, x1, y0, y1 in rectangles
        if float(x1) > float(x0) + EPS and float(y1) > float(y0) + EPS
    ]
    if not normalized:
        return 0.0
    xs = sorted({value for rect in normalized for value in rect[:2]})
    area = 0.0
    for x0, x1 in zip(xs, xs[1:]):
        if x1 <= x0 + EPS:
            continue
        intervals = sorted(
            (y0, y1)
            for rx0, rx1, y0, y1 in normalized
            if rx0 < x1 - EPS and rx1 > x0 + EPS
        )
        if not intervals:
            continue
        covered = 0.0
        current_start, current_end = intervals[0]
        for start, end in intervals[1:]:
            if start <= current_end + EPS:
                current_end = max(current_end, end)
            else:
                covered += current_end - current_start
                current_start, current_end = start, end
        covered += current_end - current_start
        area += (x1 - x0) * covered
    return float(area)


def _axis_gap(first_min, first_max, second_min, second_max):
    return max(
        0.0,
        float(second_min) - float(first_max),
        float(first_min) - float(second_max),
    )


def _axis_overlap(first_min, first_max, second_min, second_max):
    return min(float(first_max), float(second_max)) - max(
        float(first_min), float(second_min)
    )


def support_surfaces_are_adjacent(
    first,
    second,
    adjacency=SUPPORT_PLANE_ADJACENCY,
):
    if abs(float(first.top) - float(second.top)) > CONTACT_TOLERANCE:
        return False
    x_gap = _axis_gap(
        first.minimum[0],
        first.maximum[0],
        second.minimum[0],
        second.maximum[0],
    )
    y_gap = _axis_gap(
        first.minimum[1],
        first.maximum[1],
        second.minimum[1],
        second.maximum[1],
    )
    x_overlap = _axis_overlap(
        first.minimum[0],
        first.maximum[0],
        second.minimum[0],
        second.maximum[0],
    )
    y_overlap = _axis_overlap(
        first.minimum[1],
        first.maximum[1],
        second.minimum[1],
        second.maximum[1],
    )
    return bool(
        (x_gap <= adjacency + EPS and y_overlap > EPS)
        or (y_gap <= adjacency + EPS and x_overlap > EPS)
    )


def support_plane_components(
    surfaces,
    adjacency=SUPPORT_PLANE_ADJACENCY,
):
    surfaces = list(surfaces)
    parents = list(range(len(surfaces)))

    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first_index, second_index):
        first_root = find(first_index)
        second_root = find(second_index)
        if first_root != second_root:
            parents[second_root] = first_root

    for first_index, first in enumerate(surfaces):
        for second_index in range(first_index + 1, len(surfaces)):
            if support_surfaces_are_adjacent(
                first,
                surfaces[second_index],
                adjacency=adjacency,
            ):
                union(first_index, second_index)

    groups = {}
    for index, surface in enumerate(surfaces):
        groups.setdefault(find(index), []).append(surface)
    return [
        SupportPlaneComponent(tuple(group))
        for group in groups.values()
    ]


def order_support_plane_components(components):
    """Floor, area, depth, then low height preserve future accessibility."""
    return sorted(
        components,
        key=lambda component: (
            0 if component.contains_floor else 1,
            -float(component.area),
            -float(component.maximum_xy[1]),
            float(component.top),
            float(component.minimum_xy[0]),
            float(component.minimum_xy[1]),
        ),
    )


def support_component_overlap_area(candidate, component):
    rectangles = []
    for surface in component.surfaces:
        overlap_min = np.maximum(
            candidate.minimum[:2], surface.minimum[:2]
        )
        overlap_max = np.minimum(
            candidate.maximum[:2], surface.maximum[:2]
        )
        rectangles.append(
            (
                float(overlap_min[0]),
                float(overlap_max[0]),
                float(overlap_min[1]),
                float(overlap_max[1]),
            )
        )
    return rectangle_union_area(rectangles)


def penetrates_with_lateral_clearance(candidate, obstacle, clearance):
    vertical_gap = max(
        obstacle.minimum[2] - candidate.maximum[2],
        candidate.minimum[2] - obstacle.maximum[2],
    )
    if vertical_gap >= -CONTACT_TOLERANCE:
        return False

    x_gap = max(
        obstacle.minimum[0] - candidate.maximum[0],
        candidate.minimum[0] - obstacle.maximum[0],
    )
    y_gap = max(
        obstacle.minimum[1] - candidate.maximum[1],
        candidate.minimum[1] - obstacle.maximum[1],
    )
    return x_gap < clearance - EPS and y_gap < clearance - EPS


def within_euclidean_clearance(candidate, obstacle, clearance):
    gaps = np.maximum(
        0.0,
        np.maximum(
            obstacle.minimum - candidate.maximum,
            candidate.minimum - obstacle.maximum,
        ),
    )
    return float(np.linalg.norm(gaps)) < float(clearance) - EPS


def transport_sweeps(candidate, container):
    length = float(container["length"])
    width = float(container["width"])
    thickness = float(container["thickness"])
    cut_x = float(container.get("cut_x", 0.0))
    half_x = float(candidate.size[0]) / 2.0
    x_min = (
        -length / 2.0
        + thickness
        + cut_x
        + half_x
        + SIMULATOR_START_MARGIN
    )
    x_max = (
        length / 2.0
        - thickness
        - half_x
        - SIMULATOR_START_MARGIN
    )
    target_x = float(candidate.center[0])
    target_y = float(candidate.center[1])
    start_x = min(max(target_x, x_min), x_max)
    entry_y = -width / 2.0
    action_center = simulator_action_center(candidate, container)
    height = float(container["height"])
    buffer = float(container.get("buffer", 0.0))
    half_z = float(candidate.size[2]) / 2.0
    effective_start_z = SIMULATOR_DROP_HEIGHT
    bottom_z = float(action_center[2]) - half_z
    resting_surfaces = (
        thickness,
        height / 2.0 + thickness + buffer,
    )
    for resting_z in resting_surfaces:
        if 0.0 <= bottom_z - resting_z <= 0.05:
            effective_start_z = 0.0
            break

    top_z = float(action_center[2]) + half_z
    if effective_start_z > 0.0:
        ceiling_surfaces = (
            height / 2.0 + buffer,
            height + buffer - thickness,
        )
        for ceiling_z in ceiling_surfaces:
            clearance = ceiling_z - top_z
            if (
                0.0
                <= clearance
                < effective_start_z + SIMULATOR_CEILING_MARGIN
            ):
                effective_start_z = max(
                    0.0,
                    clearance
                    - SIMULATOR_CEILING_MARGIN
                    - SIMULATOR_CEILING_CLIP_EPS,
                )
                break

    maximum_start_z = (
        height
        + buffer
        - thickness
        - half_z
        - SIMULATOR_START_MARGIN
    )
    transport_z = min(
        maximum_start_z,
        float(action_center[2]) + effective_start_z,
    )
    y_leg = AABB(
        center=(start_x, (entry_y + target_y) / 2.0, transport_z),
        size=(
            float(candidate.size[0]),
            abs(target_y - entry_y) + float(candidate.size[1]),
            float(candidate.size[2]),
        ),
        name="transport_y_sweep",
    )
    x_leg = AABB(
        center=((start_x + target_x) / 2.0, target_y, transport_z),
        size=(
            abs(target_x - start_x) + float(candidate.size[0]),
            float(candidate.size[1]),
            float(candidate.size[2]),
        ),
        name="transport_x_sweep",
    )
    return (y_leg, x_leg)


def transport_sweep(candidate, container):
    sweeps = transport_sweeps(candidate, container)
    minimum = np.minimum(sweeps[0].minimum, sweeps[1].minimum)
    maximum = np.maximum(sweeps[0].maximum, sweeps[1].maximum)
    return AABB(
        center=tuple(float(value) for value in (minimum + maximum) / 2.0),
        size=tuple(float(value) for value in maximum - minimum),
        name="transport_sweep",
    )


def transport_samples(candidate, container, step: float = TRANSPORT_SAMPLE_STEP):
    length = float(container["length"])
    width = float(container["width"])
    thickness = float(container["thickness"])
    cut_x = float(container.get("cut_x", 0.0))
    half_x = float(candidate.size[0]) / 2.0
    x_min = (
        -length / 2.0
        + thickness
        + cut_x
        + half_x
        + SIMULATOR_START_MARGIN
    )
    x_max = (
        length / 2.0
        - thickness
        - half_x
        - SIMULATOR_START_MARGIN
    )
    target_x = float(candidate.center[0])
    target_y = float(candidate.center[1])
    start_x = min(max(target_x, x_min), x_max)
    entry_y = -width / 2.0
    action_center = simulator_action_center(candidate, container)
    height = float(container["height"])
    buffer = float(container.get("buffer", 0.0))
    half_z = float(candidate.size[2]) / 2.0
    effective_start_z = SIMULATOR_DROP_HEIGHT
    bottom_z = float(action_center[2]) - half_z
    resting_surfaces = (
        thickness,
        height / 2.0 + thickness + buffer,
    )
    for resting_z in resting_surfaces:
        if 0.0 <= bottom_z - resting_z <= 0.05:
            effective_start_z = 0.0
            break

    top_z = float(action_center[2]) + half_z
    if effective_start_z > 0.0:
        ceiling_surfaces = (
            height / 2.0 + buffer,
            height + buffer - thickness,
        )
        for ceiling_z in ceiling_surfaces:
            clearance = ceiling_z - top_z
            if (
                0.0
                <= clearance
                < effective_start_z + SIMULATOR_CEILING_MARGIN
            ):
                effective_start_z = max(
                    0.0,
                    clearance
                    - SIMULATOR_CEILING_MARGIN
                    - SIMULATOR_CEILING_CLIP_EPS,
                )
                break

    maximum_start_z = (
        height
        + buffer
        - thickness
        - half_z
        - SIMULATOR_START_MARGIN
    )
    transport_z = min(
        maximum_start_z,
        float(action_center[2]) + effective_start_z,
    )

    samples = []
    dist_y = abs(target_y - entry_y)
    steps_y = max(int(math.ceil(dist_y / step)), 1)
    for i in range(steps_y + 1):
        frac = i / steps_y
        y = entry_y + (target_y - entry_y) * frac
        samples.append(
            AABB((start_x, y, transport_z), candidate.size, "transport_sample_y")
        )

    dist_x = abs(target_x - start_x)
    steps_x = max(int(math.ceil(dist_x / step)), 1)
    for i in range(steps_x + 1):
        frac = i / steps_x
        x = start_x + (target_x - start_x) * frac
        samples.append(
            AABB((x, target_y, transport_z), candidate.size, "transport_sample_x")
        )

    return samples


def simulator_action_center(candidate, container):
    action_center = np.asarray(candidate.center, dtype=np.float64).copy()
    if candidate.name == "release_candidate":
        return action_center
    for shelf in shelf_aabbs(container):
        if (
            abs(float(candidate.minimum[2]) - shelf.top)
            <= CONTACT_TOLERANCE
            and xy_overlap_area(candidate, shelf) > EPS
        ):
            action_center[2] += SHELF_ACTION_LIFT
            break
    return action_center


def support_surfaces(container):
    thickness = float(container["thickness"])
    buffer = float(container.get("buffer", 0.0))
    length = float(container["length"])
    width = float(container["width"])

    surfaces = [
        AABB(
            center=(0.0, 0.0, thickness + buffer),
            size=(length, width, 0.0),
            name="floor",
        )
    ]
    surfaces.extend(shelf_aabbs(container))
    for box, is_soft, is_prioritized in packed_aabbs_local(container):
        if not is_soft and not is_prioritized:
            surfaces.append(box)
    return surfaces


class Geometry:
    @staticmethod
    def inside_container(candidate, container):
        points = container.get("points")
        normals = container.get("n_vecs")
        if points is None or normals is None:
            return True

        center_world = local_to_world(candidate.center, container)
        half_size = np.asarray(candidate.size, dtype=np.float64) / 2.0
        points = np.asarray(points, dtype=np.float64)
        normals = np.asarray(normals, dtype=np.float64)
        signed_extents = (
            np.sum(normals * (center_world - points), axis=1)
            + np.abs(normals) @ half_size
        )
        return bool(np.all(signed_extents <= -INCLUSION_CLEARANCE + EPS))

    @staticmethod
    def clears_static_geometry(candidate, container):
        for shelf in shelf_aabbs(container):
            if penetrates_with_lateral_clearance(
                candidate, shelf, SETTLED_ITEM_CLEARANCE
            ):
                return False
        for packed, _is_soft, _is_prioritized in packed_aabbs_local(container):
            if penetrates_with_lateral_clearance(
                candidate, packed, SETTLED_ITEM_CLEARANCE
            ):
                return False
        return True

    @staticmethod
    def support_ratio(candidate, container):
        item_area = float(candidate.size[0] * candidate.size[1])
        if item_area <= EPS:
            return 0.0

        bottom = float(candidate.minimum[2])
        contact_surfaces = [
            surface
            for surface in support_surfaces(container)
            if abs(bottom - surface.top) <= CONTACT_TOLERANCE
            and xy_overlap_area(candidate, surface) > EPS
        ]
        supported_area = max(
            (
                support_component_overlap_area(candidate, component)
                for component in support_plane_components(contact_surfaces)
            ),
            default=0.0,
        )
        return min(1.0, supported_area / item_area)

    @staticmethod
    def support_metrics(candidate, container, item=None):
        item_area = float(candidate.size[0] * candidate.size[1])
        if item_area <= EPS:
            return SupportMetrics(0.0, -1.0, 0, 0.0)

        contacts = []
        thickness = float(container["thickness"])
        buffer = float(container.get("buffer", 0.0))
        static_surfaces = [
            AABB(
                center=(0.0, 0.0, thickness + buffer),
                size=(
                    float(container["length"]),
                    float(container["width"]),
                    0.0,
                ),
                name="floor",
            )
        ]
        static_surfaces.extend(shelf_aabbs(container))
        for surface in static_surfaces:
            contacts.append((surface, 1.0))

        item_mass = max(EPS, float((item or {}).get("mass", 1.0)))
        for packed in container.get("packed_items", []):
            if bool(packed.get("is_soft", False)):
                continue
            if bool(packed.get("is_prioritized", False)):
                continue
            try:
                box = AABB(
                    tuple(
                        world_to_local(
                            packed_position_world(packed), container
                        )
                    ),
                    packed_dimensions(packed),
                    "packed_item",
                )
            except (KeyError, TypeError, ValueError):
                continue
            support_mass = max(EPS, float(packed.get("mass", 1.0)))
            contacts.append((box, min(1.0, support_mass / item_mass)))

        bottom = float(candidate.minimum[2])
        margins = []
        mass_weighted = 0.0
        area_weight = 0.0
        contact_count = 0
        center_xy = np.asarray(candidate.center[:2], dtype=np.float64)
        normalizer = max(
            EPS, 0.5 * min(float(candidate.size[0]), float(candidate.size[1]))
        )

        for surface, mass_ratio in contacts:
            if abs(bottom - surface.top) > CONTACT_TOLERANCE:
                continue
            overlap_min = np.maximum(
                candidate.minimum[:2], surface.minimum[:2]
            )
            overlap_max = np.minimum(
                candidate.maximum[:2], surface.maximum[:2]
            )
            span = np.maximum(0.0, overlap_max - overlap_min)
            area = float(span[0] * span[1])
            if area <= EPS:
                continue

            contact_count += 1
            signed_margin = min(
                float(center_xy[0] - overlap_min[0]),
                float(overlap_max[0] - center_xy[0]),
                float(center_xy[1] - overlap_min[1]),
                float(overlap_max[1] - center_xy[1]),
            )
            margins.append(max(-1.0, min(1.0, signed_margin / normalizer)))
            mass_weighted += area * mass_ratio
            area_weight += area

        ratio = Geometry.support_ratio(candidate, container)
        center_margin = max(margins) if margins else -1.0
        mass_support = (
            min(1.0, mass_weighted / area_weight)
            if area_weight > EPS
            else 0.0
        )
        return SupportMetrics(
            ratio=ratio,
            center_margin=center_margin,
            contact_count=contact_count,
            mass_support_ratio=mass_support,
        )

    @staticmethod
    def has_stable_support(candidate, container):
        return Geometry.support_ratio(candidate, container) >= MIN_SUPPORT_RATIO

    @staticmethod
    def transport_path_clear(candidate, container):
        for sample in transport_samples(candidate, container):
            for obstacle in shelf_aabbs(container):
                if within_euclidean_clearance(
                    sample, obstacle, SETTLED_ITEM_CLEARANCE
                ):
                    return False
            for obstacle, _is_soft, _is_prioritized in packed_aabbs_local(
                container
            ):
                if within_euclidean_clearance(
                    sample, obstacle, SETTLED_ITEM_CLEARANCE
                ):
                    return False
        return True

    @classmethod
    def rejection_reason(cls, candidate, container):
        if not cls.inside_container(candidate, container):
            return "containment"
        if not cls.clears_static_geometry(candidate, container):
            return "static_geometry"
        if not cls.has_stable_support(candidate, container):
            return "support"
        if not cls.transport_path_clear(candidate, container):
            return "corridor"
        return None

    @staticmethod
    def release_rests_on_protected_item(candidate, container, item=None):
        """True when the settled proxy rests on a top the item may not cover.

        Same-attribute stacking stays allowed, mirroring the official
        violation definition (an upper item LACKING the attribute on a
        lower item having it). With no item context the check is
        conservative and treats the mover as plain cargo.
        """
        guard_soft = RELEASE_ATTRIBUTE_GUARD == "all"
        item_is_priority = bool((item or {}).get("is_prioritized", False))
        item_is_soft = bool((item or {}).get("is_soft", False))
        proxy = settled_proxy_candidate(candidate, container)
        bottom = float(proxy.minimum[2])
        for box, is_soft, is_prioritized in packed_aabbs_local(container):
            if is_prioritized and not item_is_priority:
                pass
            elif guard_soft and is_soft and not item_is_soft:
                pass
            else:
                continue
            if (
                abs(bottom - float(box.top)) <= CONTACT_TOLERANCE
                and xy_overlap_area(proxy, box) > EPS
            ):
                return True
        return False

    @classmethod
    def release_rejection_reason(cls, candidate, container, item=None):
        if not cls.inside_container(candidate, container):
            return "containment"
        if not cls.clears_static_geometry(candidate, container):
            return "static_geometry"
        if not cls.transport_path_clear(candidate, container):
            return "corridor"
        if RELEASE_ATTRIBUTE_GUARD != "off" and cls.release_rests_on_protected_item(
            candidate, container, item
        ):
            return "attribute_rest"
        return None

    @classmethod
    def valid(cls, candidate, container):
        if candidate.name == "release_candidate":
            return cls.release_rejection_reason(candidate, container) is None
        return cls.rejection_reason(candidate, container) is None


REJECTION_REASONS = (
    "containment",
    "headroom",
    "static_geometry",
    "support",
    "corridor",
    "attribute_rest",
)


def _new_candidate_counter():
    return {
        "attempted": 0,
        "accepted": 0,
        "envelope_pruned": 0,
        "rejected": {reason: 0 for reason in REJECTION_REASONS},
    }


def _diagnostic_counters(diagnostics, item_idx, kind):
    total = diagnostics.setdefault("total", _new_candidate_counter())
    by_item = diagnostics.setdefault("by_item", {})
    item_counter = by_item.setdefault(str(item_idx), _new_candidate_counter())
    by_kind = diagnostics.setdefault("by_kind", {})
    kind_counter = by_kind.setdefault(str(kind), _new_candidate_counter())
    return total, item_counter, kind_counter


def _record_candidate_diagnostic(
    diagnostics,
    item_idx,
    reason,
    kind="settled",
):
    if diagnostics is None:
        return
    for counter in _diagnostic_counters(diagnostics, item_idx, kind):
        counter["attempted"] += 1
        if reason is None:
            counter["accepted"] += 1
        else:
            counter["rejected"][reason] += 1


def _record_envelope_prune(diagnostics, item_idx, kind="settled"):
    if diagnostics is None:
        return
    for counter in _diagnostic_counters(diagnostics, item_idx, kind):
        counter["envelope_pruned"] += 1


def release_rest_height(x, y, dims, container):
    footprint = AABB(
        center=(float(x), float(y), 0.0),
        size=(float(dims[0]), float(dims[1]), 0.0),
        name="release_footprint",
    )
    height = float(container["thickness"]) + float(
        container.get("buffer", 0.0)
    )
    obstacles = list(shelf_aabbs(container))
    obstacles.extend(
        box for box, _is_soft, _is_priority in packed_aabbs_local(container)
    )
    for obstacle in obstacles:
        if xy_overlap_area(footprint, obstacle) > EPS:
            height = max(height, obstacle.top)
    return height


def settled_proxy_candidate(candidate, container):
    if candidate.name != "release_candidate":
        return candidate
    interval = container_z_interval(
        candidate.center[0],
        candidate.center[1],
        candidate.size,
        container,
    )
    if interval is None:
        return candidate
    rest_height = release_rest_height(
        candidate.center[0],
        candidate.center[1],
        candidate.size,
        container,
    )
    proxy_z = max(
        interval[0],
        rest_height + float(candidate.size[2]) / 2.0,
    )
    return AABB(
        center=(
            float(candidate.center[0]),
            float(candidate.center[1]),
            float(proxy_z),
        ),
        size=candidate.size,
        name="release_settled_proxy",
    )


def _release_support_rectangles(candidate, container):
    rectangles = []
    bottom = float(candidate.minimum[2])
    for surface in support_surfaces(container):
        if abs(bottom - float(surface.top)) > CONTACT_TOLERANCE:
            continue
        overlap_min = np.maximum(
            candidate.minimum[:2],
            surface.minimum[:2],
        )
        overlap_max = np.minimum(
            candidate.maximum[:2],
            surface.maximum[:2],
        )
        rectangles.append(
            (
                float(overlap_min[0]),
                float(overlap_max[0]),
                float(overlap_min[1]),
                float(overlap_max[1]),
            )
        )
    return rectangles


def _split_rectangle_area(rectangles, axis, split, positive):
    clipped = []
    for x0, x1, y0, y1 in rectangles:
        if axis == 0:
            if positive:
                x0 = max(float(x0), float(split))
            else:
                x1 = min(float(x1), float(split))
        else:
            if positive:
                y0 = max(float(y0), float(split))
            else:
                y1 = min(float(y1), float(split))
        clipped.append((x0, x1, y0, y1))
    return rectangle_union_area(clipped)


def release_risk_features(
    candidate,
    item,
    container,
    orientation,
):
    """
    Calculate deterministic pre-ranking proxies for one release command.

    The returned drop compares the commanded center with the static settled
    proxy.  All discrete orientations currently sent by the agent are
    axis-aligned, so their commanded tilt is zero; the orientation code is
    retained explicitly for replay and future non-axis-aligned commands.
    """
    proxy = settled_proxy_candidate(candidate, container)
    support = Geometry.support_metrics(proxy, container, item)
    rectangles = _release_support_rectangles(proxy, container)
    supported_area = rectangle_union_area(rectangles)
    center_x = float(proxy.center[0])
    center_y = float(proxy.center[1])
    left = _split_rectangle_area(
        rectangles, axis=0, split=center_x, positive=False
    )
    right = _split_rectangle_area(
        rectangles, axis=0, split=center_x, positive=True
    )
    back = _split_rectangle_area(
        rectangles, axis=1, split=center_y, positive=False
    )
    front = _split_rectangle_area(
        rectangles, axis=1, split=center_y, positive=True
    )
    if supported_area > EPS:
        left_right = (right - left) / supported_area
        front_back = (front - back) / supported_area
    else:
        left_right = 0.0
        front_back = 0.0
    drop = max(
        0.0,
        float(candidate.center[2]) - float(proxy.center[2]),
    )
    height = max(EPS, float(candidate.size[2]))
    return ReleaseRiskFeatures(
        support_ratio=float(support.ratio),
        com_margin=float(support.center_margin),
        overhang_ratio=max(0.0, 1.0 - float(support.ratio)),
        drop_normalized=float(drop / height),
        support_imbalance=max(abs(left_right), abs(front_back)),
        left_right_imbalance=float(left_right),
        front_back_imbalance=float(front_back),
        initial_tilt_deg=0.0,
        initial_orientation=int(orientation),
    )


def evaluate_release_risk(features, thresholds=None):
    thresholds = thresholds or ReleaseRiskThresholds()
    reasons = []
    if features.support_ratio < thresholds.min_support_ratio - EPS:
        reasons.append("support")
    if features.com_margin < thresholds.min_com_margin - EPS:
        reasons.append("com_margin")
    if features.overhang_ratio > thresholds.max_overhang_ratio + EPS:
        reasons.append("overhang")
    if features.drop_normalized > thresholds.max_drop_normalized + EPS:
        reasons.append("drop")
    if (
        features.support_imbalance
        > thresholds.max_support_imbalance + EPS
    ):
        reasons.append("support_imbalance")
    # No initial-pose rule: initial_tilt_deg is an unavailable placeholder
    # that is always 0.0 for the axis-aligned orientations the agent can
    # command, so such a rule could never reject a candidate. Reinstate it
    # only together with non-axis-aligned commands that actually populate
    # the field.
    return ReleaseRiskAssessment(
        passed=not reasons,
        reasons=tuple(reasons),
    )


def normalized_release_risk_gate_mode(mode):
    normalized = str(mode).strip().lower()
    if normalized not in RELEASE_RISK_GATE_MODES:
        available = ", ".join(sorted(RELEASE_RISK_GATE_MODES))
        raise ValueError(
            f"unknown release risk gate mode {mode!r}; expected {available}"
        )
    return normalized


# Provisional v1 rotation-risk logistic, fit on the first stratified replay
# dataset (462 release rows / 13 snapshots, standardized batch-GD logistic,
# target rotated_over_30). The coefficients are NOT final -- snapshot-level
# extrapolation is unstable (LOSO AUC 0.699 [0.581, 0.804]) -- and exist
# only so shadow reranking can be instrumented; the refit/refreeze procedure
# lives in docs/RELEASE_RISK_PROTOCOL.md. Feature order matters and the
# imbalance features enter as absolute values.
RELEASE_RISK_LOGISTIC_V1 = {
    "version": "provisional-v1-20260731",
    "target": "rotated_over_30",
    "features": (
        "support_ratio",
        "com_margin",
        "drop_normalized",
        "abs_support_imbalance",
        "abs_left_right_imbalance",
        "abs_front_back_imbalance",
    ),
    "mean": (0.30744, -0.336992, 0.173174, 0.281372, 0.139214, 0.177689),
    "scale": (0.369019, 0.804913, 0.052053, 0.401402, 0.296668, 0.34478),
    # Intercept first, then one weight per standardized feature.
    "weights": (
        -1.873689,
        -3.391304,
        1.842337,
        -0.19114,
        0.682616,
        -0.047121,
        0.202496,
    ),
}


# Mechanical topple features (MATHEMATICAL_MODEL 5.2.1) computed from the
# predicted contact state only. This is the live port of
# scripts/evaluate_mechanics_features.py::mechanics_features; a parity
# unit test keeps the two implementations from drifting.
MECH_ETA_CAP = 1e6
MECH_ETA_EPSILON = 1e-6


def _convex_hull_2d(points):
    """Monotone chain; returns CCW hull without the repeated last point."""
    unique = sorted(set(points))
    if len(unique) <= 2:
        return unique

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _release_contact_patches(container, x, y, dims, z_rest):
    """Footprint-intersected predicted contact patches at the rest height.

    The surface universe matches release_rest_height exactly: floor,
    shelves, and every packed AABB (soft and priority included -- they
    physically support even though they are excluded as planning surfaces
    elsewhere).
    """
    dx, dy, _dz = dims
    fx0, fx1 = x - dx / 2.0, x + dx / 2.0
    fy0, fy1 = y - dy / 2.0, y + dy / 2.0

    floor_top = float(container["thickness"]) + float(
        container.get("buffer", 0.0)
    )
    length = float(container["length"])
    width = float(container["width"])
    surfaces = [
        (-length / 2.0, length / 2.0, -width / 2.0, width / 2.0, floor_top)
    ]
    for box in shelf_aabbs(container):
        surfaces.append(
            (
                float(box.minimum[0]),
                float(box.maximum[0]),
                float(box.minimum[1]),
                float(box.maximum[1]),
                float(box.top),
            )
        )
    for box, _soft, _prio in packed_aabbs_local(container):
        surfaces.append(
            (
                float(box.minimum[0]),
                float(box.maximum[0]),
                float(box.minimum[1]),
                float(box.maximum[1]),
                float(box.top),
            )
        )

    patches = []
    for sx0, sx1, sy0, sy1, top in surfaces:
        if abs(top - z_rest) > CONTACT_TOLERANCE:
            continue
        ox0, ox1 = max(fx0, sx0), min(fx1, sx1)
        oy0, oy1 = max(fy0, sy0), min(fy1, sy1)
        if ox1 - ox0 <= 1e-9 or oy1 - oy0 <= 1e-9:
            continue
        patches.append(
            {
                "corners": [
                    (ox0, oy0),
                    (ox0, oy1),
                    (ox1, oy0),
                    (ox1, oy1),
                ],
                "top": top,
            }
        )
    return patches


def release_mechanics_features(x, y, z_command, dims, container):
    """Phi_mech for one release command from predicted contact state."""
    _dx, _dy, dz = dims
    z_rest = float(release_rest_height(x, y, dims, container))
    z_com = z_rest + dz / 2.0
    drop = max(0.0, (float(z_command) - dz / 2.0) - z_rest)

    patches = _release_contact_patches(container, x, y, dims, z_rest)
    degenerate = not patches
    if degenerate:
        # By construction of release_rest_height at least one surface
        # matched; an empty set means numeric-tolerance starvation, which
        # we score as the worst case rather than dropping the candidate.
        d_min = 0.0
        h_at_min = dz / 2.0
        b_min = 0.0
    else:
        corner_tops = {}
        for patch in patches:
            for corner in patch["corners"]:
                previous = corner_tops.get(corner)
                if previous is None or patch["top"] > previous:
                    corner_tops[corner] = patch["top"]
        hull = _convex_hull_2d(list(corner_tops))
        d_min = math.inf
        h_at_min = dz / 2.0
        b_min = math.inf
        if len(hull) < 3:
            # Line or point contact: no interior, zero margin about the
            # contact line itself.
            d_min = 0.0
            z_e = max(patch["top"] for patch in patches)
            h_at_min = max(1e-6, z_com - z_e)
            b_min = 0.0
        else:
            for index, start in enumerate(hull):
                end = hull[(index + 1) % len(hull)]
                ex, ey = end[0] - start[0], end[1] - start[1]
                norm = math.hypot(ex, ey)
                if norm <= 1e-12:
                    continue
                # CCW hull: interior lies left of each edge.
                signed = (
                    (x - start[0]) * ey - (y - start[1]) * ex
                ) / norm * -1.0
                z_e = max(
                    corner_tops.get(start, z_rest),
                    corner_tops.get(end, z_rest),
                )
                h_e = max(1e-6, z_com - z_e)
                b_e = (
                    math.sqrt(signed * signed + h_e * h_e) - h_e
                    if signed > 0.0
                    else 0.0
                )
                if signed < d_min:
                    d_min = signed
                    h_at_min = h_e
                if b_e < b_min:
                    b_min = b_e
            if not math.isfinite(d_min):
                d_min, b_min = 0.0, 0.0

    theta_c = math.atan2(d_min, h_at_min)
    eta = min(MECH_ETA_CAP, drop / max(b_min, MECH_ETA_EPSILON))
    return {
        "d_min": float(d_min),
        "theta_c_min": float(theta_c),
        "B_min": float(b_min),
        "log1p_eta_max": float(math.log1p(eta)),
        "drop_meters": float(drop),
        "z_rest": float(z_rest),
        "degenerate_contact": bool(degenerate),
    }


# Mechanics rotation-risk logistic, fit on the development split only
# (33-snapshot round: 1106 release rows, 267 positives, in-sample AUC
# 0.824 vs LOSO 0.819 -- no overfit gap). Frozen as the EXPERIMENTAL
# model for the online ablation; the confirmatory feature-set/lambda
# selection still runs on the validation split per
# docs/RELEASE_RISK_PROTOCOL.md, and the submission default stays off
# until the final_holdout evaluation.
RELEASE_RISK_MECH_LOGISTIC_V1 = {
    "version": "mech-dev-v1-20260731",
    "target": "rotated_over_30",
    "features": ("d_min", "theta_c_min", "B_min", "log1p_eta_max"),
    "mean": (0.037038, 0.205288, 0.032355, 4.394738),
    "scale": (0.140667, 0.671682, 0.03931, 4.553431),
    # Intercept first, then one weight per standardized feature.
    "weights": (-1.749795, 0.05247, 1.422137, -1.963219, 1.249267),
}


def release_rotation_risk_probability_mech(x, y, z_command, dims, container):
    """P(rotated_over_30 | Phi_mech) from the dev-fit mechanics logistic."""
    mech = release_mechanics_features(x, y, z_command, dims, container)
    model = RELEASE_RISK_MECH_LOGISTIC_V1
    z = model["weights"][0]
    for name, mean, scale, weight in zip(
        model["features"],
        model["mean"],
        model["scale"],
        model["weights"][1:],
    ):
        z += weight * (mech[name] - mean) / scale
    z = max(-30.0, min(30.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def _support_centroid_2d(patches):
    """Area-weighted centroid of predicted contact patches."""
    total = sx = sy = 0.0
    for patch in patches:
        xs = [c[0] for c in patch["corners"]]
        ys = [c[1] for c in patch["corners"]]
        area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        if area <= 0.0:
            continue
        total += area
        sx += area * (min(xs) + max(xs)) / 2.0
        sy += area * (min(ys) + max(ys)) / 2.0
    if total <= 0.0:
        return None
    return sx / total, sy / total


def _ray_hull_margin_2d(hull, point, direction):
    """Distance from point to hull boundary along +direction (0 if none)."""
    if len(hull) < 3:
        return 0.0
    px, py = point
    ux, uy = direction
    best = None
    for index, start in enumerate(hull):
        end = hull[(index + 1) % len(hull)]
        ex, ey = end[0] - start[0], end[1] - start[1]
        denominator = ux * ey - uy * ex
        if abs(denominator) < 1e-12:
            continue
        t = ((start[0] - px) * ey - (start[1] - py) * ex) / denominator
        s = ((start[0] - px) * uy - (start[1] - py) * ux) / denominator
        if t >= 0.0 and -1e-9 <= s <= 1.0 + 1e-9:
            if best is None or t < best:
                best = t
    return float(best) if best is not None else 0.0


def release_slide_features(candidate, item, container, orientation):
    """
    Equivariant local-frame slide features (S0 set). Live port of
    scripts/evaluate_slide_equivariant.py::frame_row; a parity unit
    test keeps the geometric parts from drifting.
    """
    x = float(candidate.center[0])
    y = float(candidate.center[1])
    z_command = float(candidate.center[2])
    dims = tuple(float(v) for v in candidate.size)
    z_rest = float(release_rest_height(x, y, dims, container))
    patches = _release_contact_patches(container, x, y, dims, z_rest)
    centroid = _support_centroid_2d(patches)
    if centroid is None:
        offset = 0.0
        ux, uy = 1.0, 0.0
        hull = []
    else:
        ex, ey = x - centroid[0], y - centroid[1]
        offset = math.hypot(ex, ey)
        if offset < 1e-9:
            ux, uy = 1.0, 0.0
        else:
            ux, uy = ex / offset, ey / offset
        corner_tops = {}
        for patch in patches:
            for corner in patch["corners"]:
                previous = corner_tops.get(corner)
                if previous is None or patch["top"] > previous:
                    corner_tops[corner] = patch["top"]
        hull = _convex_hull_2d(list(corner_tops))

    mech = release_mechanics_features(x, y, z_command, dims, container)
    static = release_risk_features(candidate, item, container, orientation)
    mass = float(item.get("mass", 1.0)) if isinstance(item, dict) else 1.0
    friction = (
        float(item.get("lateralFriction", 0.5))
        if isinstance(item, dict)
        else 0.5
    )
    is_soft = (
        1.0 if isinstance(item, dict) and item.get("is_soft") else 0.0
    )
    volume = max(1e-9, dims[0] * dims[1] * dims[2])
    return {
        "com_offset": offset,
        "downhill_margin": _ray_hull_margin_2d(hull, (x, y), (ux, uy)),
        "uphill_margin": _ray_hull_margin_2d(hull, (x, y), (-ux, -uy)),
        "d_min": float(mech["d_min"]),
        "B_min": float(mech["B_min"]),
        "log1p_eta_max": float(mech["log1p_eta_max"]),
        "drop_meters": float(mech["drop_meters"]),
        "support_ratio": float(static.support_ratio),
        "mass": mass,
        "lateral_friction": friction,
        "density": mass / volume,
        "is_soft": is_soft,
    }


# Large-slide (|d_xy| > 0.30 m) logistic on the S0 equivariant features,
# fit on the development split only (1106 rows, 166 positives, in-sample
# AUC 0.817, validation AUC 0.884). Frozen for the slide shadow line;
# the live action stays rotation-only until the slide protocol steps
# (shadow pairs -> validation -> ablation) complete.
RELEASE_RISK_SLIDE_LOGISTIC_V1 = {
    "version": "slide-dev-v1-20260731",
    "target": "large_slide_over_030",
    "features": (
        "com_offset",
        "downhill_margin",
        "uphill_margin",
        "d_min",
        "B_min",
        "log1p_eta_max",
        "drop_meters",
        "support_ratio",
        "mass",
        "lateral_friction",
        "density",
        "is_soft",
    ),
    # drop_meters is constant (0.052) on the development rows -- the
    # official release height is fixed -- so its scale collapses to the
    # fit's 1.0 placeholder and its weight is exactly 0.
    "mean": (
        0.09432, 0.107568, 0.218246, 0.037038, 0.032355, 4.394738,
        0.052, 0.3358, 10.84991, 0.487703, 173.17924, 0.23689,
    ),
    "scale": (
        0.088616, 0.104093, 0.094631, 0.140667, 0.03931, 4.553431,
        1.0, 0.374496, 2.761313, 0.16118, 27.947355, 0.425174,
    ),
    # Intercept first, then one weight per standardized feature.
    "weights": (
        -2.707567, -1.14305, -0.65272, 0.607355, -0.320216, -1.964321,
        0.412931, 0.0, 0.113542, 0.025405, -3.026743, 0.16793, 2.499778,
    ),
}


def release_large_slide_probability(candidate, item, container, orientation):
    """P(|d_xy| > 0.30 | equivariant frame features), dev-fit logistic."""
    features = release_slide_features(candidate, item, container, orientation)
    model = RELEASE_RISK_SLIDE_LOGISTIC_V1
    z = model["weights"][0]
    for name, mean, scale, weight in zip(
        model["features"],
        model["mean"],
        model["scale"],
        model["weights"][1:],
    ):
        z += weight * (features[name] - mean) / scale
    z = max(-30.0, min(30.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def active_release_risk_model_version():
    if RELEASE_RISK_P_MODEL == "mech":
        return RELEASE_RISK_MECH_LOGISTIC_V1["version"]
    return RELEASE_RISK_LOGISTIC_V1["version"]


def release_rotation_risk_probability(features):
    """P(rotated_over_30 | Phi) from the provisional v1 logistic."""
    phi = features.as_dict() if hasattr(features, "as_dict") else dict(features)
    values = (
        float(phi["support_ratio"]),
        float(phi["com_margin"]),
        float(phi["drop_normalized"]),
        abs(float(phi["support_imbalance"])),
        abs(float(phi["left_right_imbalance"])),
        abs(float(phi["front_back_imbalance"])),
    )
    model = RELEASE_RISK_LOGISTIC_V1
    z = model["weights"][0]
    for value, mean, scale, weight in zip(
        values, model["mean"], model["scale"], model["weights"][1:]
    ):
        z += weight * (value - mean) / scale
    z = max(-30.0, min(30.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def release_risk_adjustment(
    candidate,
    item,
    container,
    orientation,
    risk_lambda,
):
    """Return named physical-risk terms without changing rank order here."""
    if risk_lambda is None or candidate.name != "release_candidate":
        return RiskAdjustment(None, None, 0.0, 0.0, 0.0)
    if RELEASE_RISK_P_MODEL == "mech":
        rotation_probability = release_rotation_risk_probability_mech(
            float(candidate.center[0]),
            float(candidate.center[1]),
            float(candidate.center[2]),
            tuple(float(v) for v in candidate.size),
            container,
        )
    else:
        features = release_risk_features(
            candidate, item, container, orientation
        )
        rotation_probability = release_rotation_risk_probability(features)
    rotation_penalty = float(risk_lambda) * float(rotation_probability)
    slide_probability = None
    slide_penalty = 0.0
    if RELEASE_RISK_SLIDE_LAMBDA > 0.0:
        slide_probability = float(
            release_large_slide_probability(
                candidate, item, container, orientation
            )
        )
        slide_penalty = (
            float(RELEASE_RISK_SLIDE_LAMBDA) * slide_probability
        )
    return RiskAdjustment(
        rotation_probability=float(rotation_probability),
        slide_probability=slide_probability,
        rotation_penalty=float(rotation_penalty),
        slide_penalty=float(slide_penalty),
        total_penalty=float(rotation_penalty + slide_penalty),
    )


def risk_adjusted_score(
    score,
    candidate,
    item,
    container,
    orientation,
    risk_lambda,
):
    """
    Q_lambda = Q_old - lambda * P_rot - lambda_slide * P_slide for
    release candidates; settled candidates are returned unchanged.

    Kept as the scalar compatibility API.  New selection code should retain
    ``RiskAdjustment`` through ``evaluate_placement_proposal``.
    """
    if risk_lambda is None or candidate.name != "release_candidate":
        return float(score), None
    if RELEASE_RISK_P_MODEL == "mech":
        probability = release_rotation_risk_probability_mech(
            float(candidate.center[0]),
            float(candidate.center[1]),
            float(candidate.center[2]),
            tuple(float(v) for v in candidate.size),
            container,
        )
    else:
        features = release_risk_features(
            candidate, item, container, orientation
        )
        probability = release_rotation_risk_probability(features)
    adjusted = float(score) - float(risk_lambda) * float(probability)
    if RELEASE_RISK_SLIDE_LAMBDA > 0.0:
        adjusted -= RELEASE_RISK_SLIDE_LAMBDA * float(
            release_large_slide_probability(
                candidate, item, container, orientation
            )
        )
    return adjusted, float(probability)


def _record_release_risk_diagnostic(
    diagnostics,
    item_idx,
    candidate,
    container,
    features,
    assessment,
    mode,
    thresholds,
):
    if diagnostics is None:
        return
    event = diagnostics.setdefault(
        "release_risk_gate",
        {
            "mode": mode,
            "thresholds": thresholds.as_dict(),
            "feature_sources": ReleaseRiskFeatures.feature_sources(),
            "feature_availability": (
                ReleaseRiskFeatures.feature_availability()
            ),
            "unavailable_features": list(
                ReleaseRiskFeatures.unavailable_features()
            ),
            "offline_settled_telemetry_used": False,
            "evaluated": 0,
            "passed": 0,
            "would_reject": 0,
            "enforced_rejections": 0,
            "reasons": {},
            "samples": [],
        },
    )
    event["evaluated"] += 1
    if assessment.passed:
        event["passed"] += 1
    else:
        event["would_reject"] += 1
        if mode == "enforce":
            event["enforced_rejections"] += 1
        for reason in assessment.reasons:
            event["reasons"][reason] = event["reasons"].get(reason, 0) + 1
    if len(event["samples"]) < max(0, RELEASE_RISK_DIAGNOSTIC_SAMPLE_LIMIT):
        event["samples"].append(
            {
                "item_index": int(item_idx),
                "command_center": [
                    float(value) for value in candidate.center
                ],
                "predicted_contact_center": [
                    float(value)
                    for value in settled_proxy_candidate(
                        candidate, container
                    ).center
                ],
                "features": features.as_dict(),
                "passed": bool(assessment.passed),
                "reasons": list(assessment.reasons),
            }
        )


def finalize_release_flow_diagnostics(diagnostics):
    """
    Expose the static -> gated boundary independently of final action choice.

    ``by_kind.release.accepted`` counts candidates that passed static
    geometry before the risk gate.  In ``off`` mode the gate is deliberately
    not evaluated, preserving the legacy policy cost and candidate order.
    """
    if diagnostics is None:
        return
    by_kind = diagnostics.get("by_kind")
    release_counter = (
        by_kind.get("release")
        if isinstance(by_kind, dict)
        else None
    )
    static_count = (
        int(release_counter.get("accepted", 0))
        if isinstance(release_counter, dict)
        else 0
    )
    gate = diagnostics.get("release_risk_gate")
    gate_mode = (
        str(gate.get("mode"))
        if isinstance(gate, dict) and gate.get("mode")
        else normalized_release_risk_gate_mode(RELEASE_RISK_GATE_MODE)
    )
    gate_pass_count = (
        int(gate.get("passed", 0)) if isinstance(gate, dict) else 0
    )
    gate_reject_count = (
        int(gate.get("would_reject", 0))
        if isinstance(gate, dict)
        else 0
    )
    diagnostics["release_static_count"] = static_count
    diagnostics["release_gate_pass_count"] = gate_pass_count
    diagnostics["release_gate_reject_count"] = gate_reject_count
    diagnostics["release_all_rejected"] = bool(
        gate_mode == "enforce"
        and static_count > 0
        and gate_pass_count == 0
        and gate_reject_count == static_count
    )


def record_selected_release_risk(
    diagnostics,
    decision,
    pool_list,
    containers,
):
    """Attach the chosen release's online assessment for later telemetry join."""
    if (
        diagnostics is None
        or decision is None
        or decision.candidate.name != "release_candidate"
        or RELEASE_RISK_GATE_MODE == "off"
    ):
        return
    item_idx = int(decision.action["item_idx"])
    container_idx = int(decision.action["container_idx"])
    if not (
        0 <= item_idx < len(pool_list)
        and 0 <= container_idx < len(containers)
    ):
        return
    item = pool_list[item_idx]
    container = containers[container_idx]
    features = release_risk_features(
        decision.candidate,
        item,
        container,
        int(decision.action["orientation"]),
    )
    assessment = evaluate_release_risk(features)
    diagnostics["selected_release_risk"] = {
        "mode": RELEASE_RISK_GATE_MODE,
        "features": features.as_dict(),
        "feature_sources": features.feature_sources(),
        "feature_availability": features.feature_availability(),
        "unavailable_features": list(features.unavailable_features()),
        "offline_settled_telemetry_used": False,
        "passed": bool(assessment.passed),
        "reasons": list(assessment.reasons),
    }


def release_candidate_passes_risk_gate(
    candidate,
    item,
    container,
    orientation,
    *,
    mode=None,
    thresholds=None,
    diagnostics=None,
    item_idx=None,
):
    mode = normalized_release_risk_gate_mode(
        RELEASE_RISK_GATE_MODE if mode is None else mode
    )
    if mode == "off":
        return True
    features = release_risk_features(
        candidate,
        item,
        container,
        orientation,
    )
    thresholds = thresholds or ReleaseRiskThresholds()
    assessment = evaluate_release_risk(features, thresholds=thresholds)
    _record_release_risk_diagnostic(
        diagnostics,
        item.get("index", -1) if item_idx is None else item_idx,
        candidate,
        container,
        features,
        assessment,
        mode,
        thresholds,
    )
    return bool(assessment.passed or mode == "shadow")


def rectangular_container_anchor_bounds(dims, container):
    """
    Where an anchor may sit in x and y.

    The box formula below is not the container. These are AKE/AKN-derived
    shapes whose y planes are ASYMMETRIC -- measured at [-W/2, +W/2 - t] on
    both Task C cases -- while this subtracts a thickness from each side, so
    the low-y side is one thickness too tight for every item, orientation and
    generator. At c001-k1 step 20 that band held sixteen physically safe
    placements and both generators, run exhaustively, returned nothing.

    ``ANCHOR_TRUE_ENVELOPE`` derives the bounds from the container's own
    half-spaces instead. Only axis-aligned planes contribute: a slanted plane
    (the bottom chamfer) has no single x or y bound, and it needs none here
    because container_z_interval already applies every half-space exactly at
    each (x, y). This widens where the search LOOKS; what it finds is still
    validated by inside_container, so the fix cannot admit an illegal
    placement.

    Default off. It changes the shipped search space, so adoption needs the
    Task B guard, which does not reproduce off CI.
    """
    dx, dy, dz = dims
    length = float(container["length"])
    width = float(container["width"])
    thickness = float(container["thickness"])
    # Tilt margin: a settled item leans, and its top corner moves laterally
    # by about sin(tilt) * height. The fill evaluator forfeits the whole
    # item when that corner crosses a boundary plane, so the envelope
    # retreats from every wall by exactly that predicted drift. Scales with
    # the placed item's height; independent of any item-type catalog.
    tilt_margin = (
        math.sin(math.radians(ANCHOR_TILT_MARGIN_DEG)) * dz
        if ANCHOR_TILT_MARGIN_DEG > 0.0
        else 0.0
    )

    def shrunk(bounds):
        if tilt_margin <= 0.0:
            return bounds
        return (
            bounds[0] + tilt_margin,
            bounds[1] - tilt_margin,
            bounds[2] + tilt_margin,
            bounds[3] - tilt_margin,
        )

    box = (
        -length / 2.0 + thickness + dx / 2.0 + INCLUSION_CLEARANCE,
        length / 2.0 - thickness - dx / 2.0 - INCLUSION_CLEARANCE,
        -width / 2.0 + thickness + dy / 2.0 + INCLUSION_CLEARANCE,
        width / 2.0 - thickness - dy / 2.0 - INCLUSION_CLEARANCE,
    )
    if not ANCHOR_TRUE_ENVELOPE:
        return shrunk(box)
    points = container.get("points")
    normals = container.get("n_vecs")
    if points is None or normals is None:
        return shrunk(box)
    offset_x = container_offset_x(container)
    half = (dx / 2.0, dy / 2.0)
    limit = -INCLUSION_CLEARANCE
    low = [-float("inf"), -float("inf")]
    high = [float("inf"), float("inf")]
    for point_values, normal_values in zip(points, normals):
        normal = np.asarray(normal_values, dtype=np.float64)
        point = np.asarray(point_values, dtype=np.float64)
        for axis in (0, 1):
            if abs(normal[axis]) <= EPS:
                continue
            if np.count_nonzero(np.abs(normal) > EPS) != 1:
                continue
            # normal[axis] * (centre - point[axis]) + |normal| . half <= limit
            slack = (limit - abs(normal[axis]) * half[axis]) / abs(
                normal[axis]
            )
            if normal[axis] > 0.0:
                high[axis] = min(high[axis], float(point[axis]) + slack)
            else:
                low[axis] = max(low[axis], float(point[axis]) - slack)
    if not all(map(math.isfinite, low + high)):
        return shrunk(box)
    return shrunk(
        (
            low[0] - offset_x,
            high[0] - offset_x,
            low[1],
            high[1],
        )
    )


def _component_near_obstacle(component, obstacle, dims):
    dx, dy, _dz = dims
    x_gap = _axis_gap(
        component.minimum_xy[0],
        component.maximum_xy[0],
        obstacle.minimum[0],
        obstacle.maximum[0],
    )
    y_gap = _axis_gap(
        component.minimum_xy[1],
        component.maximum_xy[1],
        obstacle.minimum[1],
        obstacle.maximum[1],
    )
    return bool(
        x_gap <= dx + SETTLED_ITEM_CLEARANCE + EPS
        and y_gap <= dy + SETTLED_ITEM_CLEARANCE + EPS
    )


def support_plane_anchor_positions(component, dims, container):
    """Generate anchors coupled to one connected horizontal support plane."""
    dx, dy, dz = dims
    x_low, x_high, y_low, y_high = rectangular_container_anchor_bounds(
        dims, container
    )
    if x_low > x_high + EPS or y_low > y_high + EPS:
        return []

    xs = {
        float(x_low),
        0.0,
        float(x_high),
        float((component.minimum_xy[0] + component.maximum_xy[0]) / 2.0),
        float(component.minimum_xy[0] + dx / 2.0),
        float(component.maximum_xy[0] - dx / 2.0),
    }
    ys = {
        float(y_low),
        0.0,
        float(y_high),
        float((component.minimum_xy[1] + component.maximum_xy[1]) / 2.0),
        float(component.minimum_xy[1] + dy / 2.0),
        float(component.maximum_xy[1] - dy / 2.0),
    }
    for surface in component.surfaces:
        xs.update(
            (
                float(surface.center[0]),
                float(surface.minimum[0] + dx / 2.0),
                float(surface.maximum[0] - dx / 2.0),
            )
        )
        ys.update(
            (
                float(surface.center[1]),
                float(surface.minimum[1] + dy / 2.0),
                float(surface.maximum[1] - dy / 2.0),
            )
        )

    candidate_bottom = float(component.top)
    candidate_top = candidate_bottom + float(dz)
    obstacles = list(shelf_aabbs(container))
    obstacles.extend(
        box for box, _is_soft, _is_priority in packed_aabbs_local(container)
    )
    for obstacle in obstacles:
        vertical_gap = max(
            float(obstacle.minimum[2]) - candidate_top,
            candidate_bottom - float(obstacle.maximum[2]),
        )
        if (
            vertical_gap >= -CONTACT_TOLERANCE
            or not _component_near_obstacle(component, obstacle, dims)
        ):
            continue
        xs.update(
            (
                float(
                    obstacle.minimum[0]
                    - dx / 2.0
                    - TRANSPORT_CLEARANCE
                ),
                float(
                    obstacle.maximum[0]
                    + dx / 2.0
                    + TRANSPORT_CLEARANCE
                ),
            )
        )
        ys.update(
            (
                float(
                    obstacle.minimum[1]
                    - dy / 2.0
                    - TRANSPORT_CLEARANCE
                ),
                float(
                    obstacle.maximum[1]
                    + dy / 2.0
                    + TRANSPORT_CLEARANCE
                ),
            )
        )

    xs = sorted(
        (
            value
            for value in xs
            if x_low - EPS <= value <= x_high + EPS
        ),
        key=abs,
    )
    ys = sorted(
        (
            value
            for value in ys
            if y_low - EPS <= value <= y_high + EPS
        ),
        reverse=True,
    )
    z = float(component.top + dz / 2.0)
    return [
        (float(x), float(y), z)
        for y in ys
        for x in xs
    ]


def interleaved_scan_order(positions, interleave):
    """
    Reorder an anchor list into stride-interleaved order.

    This is a **permutation**, not a subsample: every anchor is still
    yielded, exactly once, and with ``interleave <= 1`` the order is
    unchanged.  That distinction is the whole point.  The rollout's future
    search is capped by an attempt count it can never exhaust, so there a
    stride that *drops* anchors is a pure win.  The live search is capped by
    a deadline it often does exhaust, so dropping anchors there would lose
    candidates the current search finds.  Permuting costs nothing at
    exhaustion and changes only which anchors a deadline-truncated search
    reaches first.

    ``support_plane_anchor_positions`` emits ``for y descending, for x by
    |x|``, so the natural prefix is one deep y band near the centre line -
    which is the shape of the observed live coverage hole.  Interleaving by
    N makes the first pass step through every N-th anchor, so a truncated
    search sees the whole plane coarsely instead of one band densely.
    """
    interleave = max(1, int(interleave))
    if interleave == 1 or len(positions) <= interleave:
        return list(positions)
    return [
        positions[index]
        for phase in range(interleave)
        for index in range(phase, len(positions), interleave)
    ]


def support_plane_anchor_count(components, dims, container):
    return len(
        {
            tuple(round(value, 6) for value in position)
            for component in components
            for position in support_plane_anchor_positions(
                component, dims, container
            )
        }
    )


class CandidateGenerator:
    @staticmethod
    def iter_cartesian_attempts(
        observation,
        item,
        container_idx,
        orientation,
        limit=400,
        deadline=None,
        diagnostics=None,
        item_idx=None,
        attempt_kind="both",
        stride=1,
        stride_offset=0,
    ):
        """
        Yield every validated candidate attempt lazily.

        A rejected or envelope-pruned anchor yields ``None`` so the caller
        can time-slice work by attempted anchors rather than by accepted
        candidates.  This is important late in an episode, where a unit may
        inspect tens of thousands of invalid anchors before finding nothing.

        ``stride``/``stride_offset`` perform systematic sampling of the
        anchor grid for offline measurement: only every stride-th deduped
        grid position (starting at the offset phase) is validated and
        yielded, the rest are skipped without paying validation cost. With
        the default stride 1 behaviour is unchanged. Because the scan order
        is deterministic, a caller can treat ``count * stride`` as a
        Horvitz-Thompson estimate of the full-grid count and vary the
        offset to measure sampling variance.
        """
        if attempt_kind not in {"both", "settled", "release"}:
            raise ValueError(
                "attempt_kind must be 'both', 'settled', or 'release'"
            )
        stride = max(1, int(stride))
        stride_offset = int(stride_offset) % stride
        container = observation["container_list"][container_idx]
        if item_idx is None:
            item_idx = item.get("index", -1)
        dims = get_rotated_dimensions(
            item["length"], item["width"], item["height"], orientation
        )
        dx, dy, dz = dims
        length = float(container["length"])
        width = float(container["width"])
        thickness = float(container["thickness"])
        cut_x = float(container.get("cut_x", 0.0))

        # Shared with the support-plane path so one envelope defect cannot
        # hide in only one generator -- which is what happened: both carried
        # the same box formula, so an exhaustive run of both still missed the
        # band along the low-y wall.
        x_low, x_high, y_low, y_high = (
            rectangular_container_anchor_bounds(dims, container)
        )
        if x_low > x_high + EPS or y_low > y_high + EPS:
            _record_envelope_prune(diagnostics, item_idx)
            yield None
            return

        xs = {x_low, 0.0, x_high}
        ys = {y_low, 0.0, y_high}
        zs = set()

        if cut_x > 0.0:
            xs.add(
                -length / 2.0
                + thickness
                + cut_x
                + dx / 2.0
                + TRANSPORT_CLEARANCE
            )

        for surface in support_surfaces(container):
            zs.add(surface.top + dz / 2.0)
            xs.update(
                (
                    surface.minimum[0] + dx / 2.0,
                    surface.maximum[0] - dx / 2.0,
                )
            )
            ys.update(
                (
                    surface.minimum[1] + dy / 2.0,
                    surface.maximum[1] - dy / 2.0,
                )
            )

        for packed, _is_soft, _is_prioritized in packed_aabbs_local(container):
            xs.update(
                (
                    packed.minimum[0] - dx / 2.0 - TRANSPORT_CLEARANCE,
                    packed.maximum[0] + dx / 2.0 + TRANSPORT_CLEARANCE,
                )
            )
            ys.update(
                (
                    packed.minimum[1] - dy / 2.0 - TRANSPORT_CLEARANCE,
                    packed.maximum[1] + dy / 2.0 + TRANSPORT_CLEARANCE,
                )
            )

        accepted = 0
        seen = set()
        intervals = {}
        grid_index = -1

        def interval_at(x, y):
            key = (float(x), float(y))
            if key not in intervals:
                intervals[key] = container_z_interval(
                    x,
                    y,
                    dims,
                    container,
                )
            return intervals[key]

        if attempt_kind in {"both", "settled"}:
            for z in sorted(zs):
                for y in sorted(ys, reverse=True):
                    for x in sorted(xs, key=abs):
                        if (
                            deadline is not None
                            and time.perf_counter() >= deadline
                        ):
                            return
                        position = (float(x), float(y), float(z))
                        key = tuple(round(value, 4) for value in position)
                        if key in seen:
                            continue
                        seen.add(key)
                        grid_index += 1
                        if (
                            stride > 1
                            and (grid_index - stride_offset) % stride != 0
                        ):
                            continue
                        interval = interval_at(x, y)
                        if (
                            interval is None
                            or float(z) < interval[0] - EPS
                            or float(z) > interval[1] + EPS
                        ):
                            _record_envelope_prune(
                                diagnostics,
                                item_idx,
                            )
                            yield None
                            continue
                        candidate = AABB(position, dims, "candidate")
                        reason = Geometry.rejection_reason(
                            candidate,
                            container,
                        )
                        _record_candidate_diagnostic(
                            diagnostics,
                            item_idx,
                            reason,
                        )
                        if reason is None:
                            accepted += 1
                            yield candidate
                            if accepted >= limit:
                                return
                        else:
                            yield None
        if accepted and attempt_kind == "both":
            return

        if attempt_kind in {"both", "release"}:
            release_index = -1
            for y in sorted(ys, reverse=True):
                for x in sorted(xs, key=abs):
                    if (
                        deadline is not None
                        and time.perf_counter() >= deadline
                    ):
                        return
                    release_index += 1
                    if (
                        stride > 1
                        and (release_index - stride_offset) % stride != 0
                    ):
                        continue
                    interval = interval_at(x, y)
                    if interval is None:
                        _record_envelope_prune(
                            diagnostics,
                            item_idx,
                            kind="release",
                        )
                        yield None
                        continue
                    rest_height = release_rest_height(
                        x,
                        y,
                        dims,
                        container,
                    )
                    z = max(
                        interval[0] + RELEASE_BOUNDARY_MARGIN,
                        rest_height + dz / 2.0 + RELEASE_TARGET_LIFT,
                    )
                    if z > interval[1] + EPS:
                        _record_envelope_prune(
                            diagnostics,
                            item_idx,
                            kind="release",
                        )
                        yield None
                        continue
                    position = (float(x), float(y), float(z))
                    key = tuple(round(value, 4) for value in position)
                    if key in seen:
                        continue
                    seen.add(key)
                    candidate = AABB(
                        position,
                        dims,
                        "release_candidate",
                    )
                    reason = Geometry.release_rejection_reason(
                        candidate,
                        container,
                        item=item,
                    )
                    _record_candidate_diagnostic(
                        diagnostics,
                        item_idx,
                        reason,
                        kind="release",
                    )
                    if reason is None:
                        if not release_candidate_passes_risk_gate(
                            candidate,
                            item,
                            container,
                            orientation,
                            diagnostics=diagnostics,
                            item_idx=item_idx,
                        ):
                            yield None
                            continue
                        accepted += 1
                        yield candidate
                        if accepted >= limit:
                            return
                    else:
                        yield None

    @staticmethod
    def iter_release_plane_attempts(
        observation,
        item,
        container_idx,
        orientation,
        limit=400,
        deadline=None,
        diagnostics=None,
        item_idx=None,
        stride=1,
        stride_offset=0,
        interleave=1,
    ):
        """
        Generate release targets directly from local support-plane anchors.

        Release z is solved analytically for each coupled (x, y) pair.  This
        avoids the Cartesian prefix formed by crossing every observed x edge
        with every observed y edge before reaching a feasible release point.

        ``stride``/``stride_offset`` systematically subsample the deduped
        anchor sequence exactly as ``iter_cartesian_attempts`` does: only
        every stride-th anchor (starting at the offset phase) is validated
        and yielded.  A skipped anchor costs no validation and consumes no
        round slot, so a fixed attempt budget spreads further into each
        plane component instead of exhausting on its prefix.  Stride 1 is
        the unchanged default.
        """
        stride = max(1, int(stride))
        stride_offset = int(stride_offset) % stride
        container = observation["container_list"][container_idx]
        if item_idx is None:
            item_idx = item.get("index", -1)
        dims = get_rotated_dimensions(
            item["length"], item["width"], item["height"], orientation
        )
        _dx, _dy, dz = dims
        x_low, x_high, y_low, y_high = rectangular_container_anchor_bounds(
            dims, container
        )
        if x_low > x_high + EPS or y_low > y_high + EPS:
            _record_envelope_prune(
                diagnostics,
                item_idx,
                kind="release",
            )
            yield None
            return

        components = order_support_plane_components(
            support_plane_components(support_surfaces(container))
        )
        position_groups = [
            (
                component,
                interleaved_scan_order(
                    support_plane_anchor_positions(
                        component,
                        dims,
                        container,
                    ),
                    interleave,
                ),
            )
            for component in components
        ]
        if diagnostics is not None:
            unique_positions = {
                (
                    round(float(position[0]), 6),
                    round(float(position[1]), 6),
                )
                for _component, positions in position_groups
                for position in positions
            }
            diagnostics.setdefault("release_plane_searches", []).append(
                {
                    "item_index": int(item_idx),
                    "container_index": int(container_idx),
                    "orientation": int(orientation),
                    "surface_count": sum(
                        len(component.surfaces)
                        for component in components
                    ),
                    "component_count": len(components),
                    "anchor_count": len(unique_positions),
                    "round_attempts": max(
                        1, ANCHOR_FIRST_PASS_ATTEMPTS
                    ),
                    "component_order": [
                        {
                            "contains_floor": component.contains_floor,
                            "area": float(component.area),
                            "depth": float(component.maximum_xy[1]),
                            "top": float(component.top),
                            "surface_count": len(component.surfaces),
                        }
                        for component in components
                    ],
                }
            )

        states = [
            {
                "iterator": iter(positions),
            }
            for _component, positions in position_groups
            if positions
        ]
        accepted = 0
        seen = set()
        anchor_index = -1
        attempts_per_plane = max(1, ANCHOR_FIRST_PASS_ATTEMPTS)
        while states:
            next_states = []
            for state in states:
                exhausted = False
                produced = 0
                while produced < attempts_per_plane:
                    if (
                        deadline is not None
                        and time.perf_counter() >= deadline
                    ):
                        return
                    try:
                        x, y, _support_z = next(state["iterator"])
                    except StopIteration:
                        exhausted = True
                        break
                    key = (
                        round(float(x), 4),
                        round(float(y), 4),
                    )
                    if key in seen:
                        produced += 1
                        continue
                    seen.add(key)
                    anchor_index += 1
                    if (
                        stride > 1
                        and (anchor_index - stride_offset) % stride != 0
                    ):
                        continue
                    produced += 1
                    interval = container_z_interval(
                        x,
                        y,
                        dims,
                        container,
                    )
                    if interval is None:
                        _record_envelope_prune(
                            diagnostics,
                            item_idx,
                            kind="release",
                        )
                        yield None
                        continue
                    rest_height = release_rest_height(
                        x,
                        y,
                        dims,
                        container,
                    )
                    z = max(
                        interval[0] + RELEASE_BOUNDARY_MARGIN,
                        rest_height + dz / 2.0 + RELEASE_TARGET_LIFT,
                    )
                    if z > interval[1] + EPS:
                        _record_envelope_prune(
                            diagnostics,
                            item_idx,
                            kind="release",
                        )
                        yield None
                        continue
                    candidate = AABB(
                        (float(x), float(y), float(z)),
                        dims,
                        "release_candidate",
                    )
                    reason = Geometry.release_rejection_reason(
                        candidate,
                        container,
                        item=item,
                    )
                    _record_candidate_diagnostic(
                        diagnostics,
                        item_idx,
                        reason,
                        kind="release",
                    )
                    if reason is None:
                        if not release_candidate_passes_risk_gate(
                            candidate,
                            item,
                            container,
                            orientation,
                            diagnostics=diagnostics,
                            item_idx=item_idx,
                        ):
                            yield None
                            continue
                        accepted += 1
                        yield candidate
                        if accepted >= limit:
                            return
                    else:
                        yield None
                if not exhausted:
                    next_states.append(state)
            states = next_states

    @staticmethod
    def iter_support_plane_attempts(
        observation,
        item,
        container_idx,
        orientation,
        limit=400,
        deadline=None,
        diagnostics=None,
        item_idx=None,
        attempt_kind="both",
        stride=1,
        stride_offset=0,
        interleave=1,
    ):
        """
        Yield validated attempts anchored on connected support planes.

        ``stride``/``stride_offset`` systematically subsample the deduped
        anchor sequence with the same semantics as
        ``iter_cartesian_attempts``.  This is the default generator mode, so
        it is the path a strided rollout measurement actually exercises.
        Stride 1 is the unchanged default.
        """
        if attempt_kind not in {"both", "settled", "release"}:
            raise ValueError(
                "attempt_kind must be 'both', 'settled', or 'release'"
            )
        stride = max(1, int(stride))
        stride_offset = int(stride_offset) % stride
        if attempt_kind == "release":
            yield from CandidateGenerator.iter_release_plane_attempts(
                observation,
                item,
                container_idx,
                orientation,
                limit=limit,
                deadline=deadline,
                diagnostics=diagnostics,
                item_idx=item_idx,
                stride=stride,
                stride_offset=stride_offset,
                interleave=interleave,
            )
            return

        container = observation["container_list"][container_idx]
        if item_idx is None:
            item_idx = item.get("index", -1)
        dims = get_rotated_dimensions(
            item["length"], item["width"], item["height"], orientation
        )
        x_low, x_high, y_low, y_high = rectangular_container_anchor_bounds(
            dims, container
        )
        if x_low > x_high + EPS or y_low > y_high + EPS:
            _record_envelope_prune(diagnostics, item_idx)
            yield None
            return

        surfaces = support_surfaces(container)
        components = order_support_plane_components(
            support_plane_components(surfaces)
        )
        position_groups = [
            (
                component,
                interleaved_scan_order(
                    support_plane_anchor_positions(
                        component, dims, container
                    ),
                    interleave,
                ),
            )
            for component in components
        ]
        if diagnostics is not None:
            connected_keys = {
                tuple(round(value, 6) for value in position)
                for _component, positions in position_groups
                for position in positions
            }
            separate_components = [
                SupportPlaneComponent((surface,)) for surface in surfaces
            ]
            diagnostics.setdefault("support_plane_searches", []).append(
                {
                    "item_index": int(item_idx),
                    "container_index": int(container_idx),
                    "orientation": int(orientation),
                    "adjacency_threshold": float(
                        SUPPORT_PLANE_ADJACENCY
                    ),
                    "surface_count": len(surfaces),
                    "component_count": len(components),
                    "connected_anchor_count": len(connected_keys),
                    "unconnected_anchor_count": (
                        support_plane_anchor_count(
                            separate_components,
                            dims,
                            container,
                        )
                    ),
                    "round_attempts": max(
                        1, SUPPORT_PLANE_ROUND_ATTEMPTS
                    ),
                    "component_order": [
                        {
                            "contains_floor": component.contains_floor,
                            "area": float(component.area),
                            "depth": float(component.maximum_xy[1]),
                            "top": float(component.top),
                            "surface_count": len(component.surfaces),
                        }
                        for component in components
                    ],
                }
            )

        states = [
            {
                "iterator": iter(positions),
            }
            for _component, positions in position_groups
            if positions
        ]
        accepted = 0
        seen = set()
        anchor_index = -1
        attempts_per_plane = max(1, SUPPORT_PLANE_ROUND_ATTEMPTS)
        while states:
            next_states = []
            for state in states:
                exhausted = False
                produced = 0
                while produced < attempts_per_plane:
                    if (
                        deadline is not None
                        and time.perf_counter() >= deadline
                    ):
                        return
                    try:
                        position = next(state["iterator"])
                    except StopIteration:
                        exhausted = True
                        break
                    key = tuple(round(value, 4) for value in position)
                    if key in seen:
                        produced += 1
                        continue
                    seen.add(key)
                    anchor_index += 1
                    if (
                        stride > 1
                        and (anchor_index - stride_offset) % stride != 0
                    ):
                        continue
                    produced += 1
                    interval = container_z_interval(
                        position[0],
                        position[1],
                        dims,
                        container,
                    )
                    if (
                        interval is None
                        or position[2] < interval[0] - EPS
                        or position[2] > interval[1] + EPS
                    ):
                        _record_envelope_prune(
                            diagnostics,
                            item_idx,
                        )
                        yield None
                        continue
                    candidate = AABB(position, dims, "candidate")
                    reason = Geometry.rejection_reason(
                        candidate,
                        container,
                    )
                    _record_candidate_diagnostic(
                        diagnostics,
                        item_idx,
                        reason,
                    )
                    if reason is None:
                        accepted += 1
                        yield candidate
                        if accepted >= limit:
                            return
                    else:
                        yield None
                if not exhausted:
                    next_states.append(state)
            states = next_states

        if accepted or attempt_kind == "settled":
            return
        yield from CandidateGenerator.iter_release_plane_attempts(
            observation,
            item,
            container_idx,
            orientation,
            limit=limit,
            deadline=deadline,
            diagnostics=diagnostics,
            item_idx=item_idx,
            stride=stride,
            stride_offset=stride_offset,
            interleave=interleave,
        )

    @staticmethod
    def iter_attempts(
        observation,
        item,
        container_idx,
        orientation,
        limit=400,
        deadline=None,
        diagnostics=None,
        item_idx=None,
        attempt_kind="both",
        generator_mode=None,
        stride=1,
        stride_offset=0,
        interleave=1,
    ):
        mode = (
            ANCHOR_GENERATOR_MODE
            if generator_mode is None
            else str(generator_mode).strip().lower()
        )
        if mode not in ANCHOR_GENERATOR_MODES:
            available = ", ".join(sorted(ANCHOR_GENERATOR_MODES))
            raise ValueError(
                f"unknown anchor generator mode '{mode}'; "
                f"available: {available}"
            )
        if mode == "cartesian" and int(interleave) > 1:
            # The Cartesian generator streams a nested product rather than a
            # materialised anchor list, so it cannot honour a permutation.
            # Fail rather than silently run the shipped order under a name
            # that says otherwise.
            raise ValueError(
                "interleave is implemented for the support_plane generator "
                "only; ANCHOR_GENERATOR_MODE=cartesian cannot honour it"
            )
        if mode == "cartesian":
            yield from CandidateGenerator.iter_cartesian_attempts(
                observation,
                item,
                container_idx,
                orientation,
                limit=limit,
                deadline=deadline,
                diagnostics=diagnostics,
                item_idx=item_idx,
                attempt_kind=attempt_kind,
                stride=stride,
                stride_offset=stride_offset,
            )
            return
        yield from CandidateGenerator.iter_support_plane_attempts(
            observation,
            item,
            container_idx,
            orientation,
            limit=limit,
            deadline=deadline,
            diagnostics=diagnostics,
            item_idx=item_idx,
            attempt_kind=attempt_kind,
            stride=stride,
            stride_offset=stride_offset,
            interleave=interleave,
        )

    @staticmethod
    def generate(
        observation,
        item,
        container_idx,
        orientation,
        limit=400,
        deadline=None,
        diagnostics=None,
        item_idx=None,
        generator_mode=None,
    ):
        """Compatibility wrapper returning only accepted candidates."""
        return [
            candidate
            for candidate in CandidateGenerator.iter_attempts(
                observation,
                item,
                container_idx,
                orientation,
                limit=limit,
                deadline=deadline,
                diagnostics=diagnostics,
                item_idx=item_idx,
                generator_mode=generator_mode,
            )
            if candidate is not None
        ]


@lru_cache(maxsize=256)
def _zone_geometry(length, width, height, thickness, buffer, cut_x, shelf):
    """
    (shelf_top_z, shelf_y_lo, shelf_y_hi, deep_y) for zone classification.

    Cached on the container's dimensions because `Ranker.score` runs on the
    hot path -- rebuilding the shelf AABBs per candidate would cost search
    breadth, and a knob that shrinks the search is not measuring its own
    hypothesis.
    """
    container = {
        "length": length,
        "width": width,
        "height": height,
        "thickness": thickness,
        "buffer": buffer,
        "cut_x": cut_x,
        "shelf": shelf,
    }
    plates = [a for a in shelf_aabbs(container) if a.name == "main_shelf"]
    deep_y = width / 4.0
    if not plates:
        return (None, None, None, deep_y)
    plate = plates[0]
    return (
        float(plate.maximum[2]),
        float(plate.minimum[1]),
        float(plate.maximum[1]),
        deep_y,
    )


def candidate_zone(candidate, container):
    """
    Which loading zone a pose rests in.

    Classified on the pose's BOTTOM, not its top: a tall item standing on
    the floor by the door is not on the shelf, and reading it as such
    inverts the very ordering this is here to express.
    """
    top_z, y_lo, y_hi, deep_y = _zone_geometry(
        float(container["length"]),
        float(container["width"]),
        float(container["height"]),
        float(container["thickness"]),
        float(container.get("buffer", 0.0) or 0.0),
        float(container.get("cut_x", 0.0) or 0.0),
        bool(container_requires_shelf(container)),
    )
    y = float(candidate.center[1])
    bottom = float(candidate.minimum[2])
    if top_z is not None:
        if bottom >= top_z - CONTACT_TOLERANCE:
            return "shelf_top"
        if y_lo <= y <= y_hi:
            return "under_shelf"
    return "deep" if y >= deep_y else "centre"


class Ranker:
    @staticmethod
    def evaluate(candidate, item, container, has_priority_container):
        support = Geometry.support_ratio(candidate, container)
        volume = math.prod(candidate.size)
        mass = float(item.get("mass", 1.0))
        x, y, z = candidate.center
        is_priority_item = bool(item.get("is_prioritized", False))
        is_priority_container = bool(container.get("is_prioritized", False))
        if is_priority_item:
            depth_score = -0.55 * y
        else:
            depth_score = 0.35 * y

        routing_score = 0.0
        if has_priority_container:
            if is_priority_item and is_priority_container:
                routing_score = 8.0
            elif not is_priority_item and is_priority_container:
                routing_score = -2.5

        zone_score = 0.0
        if ZONE_ORDER_MODE != "off":
            zone_score = ZONE_ORDER_BONUS * ZONE_RANKS[ZONE_ORDER_MODE][
                candidate_zone(candidate, container)
            ]

        components = {
            "volume": 12.0 * volume,
            "support": 2.0 * support,
            "depth": depth_score,
            "lateral": -0.12 * abs(x),
            "lift": -0.18 * z * mass,
            "routing": routing_score,
            "zone": zone_score,
        }
        # Keep the shipped scalar expression's left-to-right arithmetic.
        # Python 3.12's built-in sum uses compensated summation, which can
        # differ by one ULP and flip a near-tied selector despite identical
        # named terms.
        total = (
            components["volume"]
            + components["support"]
            + components["depth"]
            + components["lateral"]
            + components["lift"]
            + components["routing"]
            + components["zone"]
        )
        return RankEvaluation(
            **components,
            unattributed=0.0,
            total=float(total),
        )

    @staticmethod
    def score(candidate, item, container, has_priority_container):
        """Allocation-light live scalar path."""
        support = Geometry.support_ratio(candidate, container)
        volume = math.prod(candidate.size)
        mass = float(item.get("mass", 1.0))
        x, y, z = candidate.center
        is_priority_item = bool(item.get("is_prioritized", False))
        is_priority_container = bool(
            container.get("is_prioritized", False)
        )
        depth_score = -0.55 * y if is_priority_item else 0.35 * y
        routing_score = 0.0
        if has_priority_container:
            if is_priority_item and is_priority_container:
                routing_score = 8.0
            elif not is_priority_item and is_priority_container:
                routing_score = -2.5
        zone_score = 0.0
        if ZONE_ORDER_MODE != "off":
            zone_score = ZONE_ORDER_BONUS * ZONE_RANKS[ZONE_ORDER_MODE][
                candidate_zone(candidate, container)
            ]
        return (
            12.0 * volume
            + 2.0 * support
            + depth_score
            - 0.12 * abs(x)
            - 0.18 * z * mass
            + routing_score
            + zone_score
        )


def evaluate_placement_proposal(
    proposal,
    has_priority_container,
    risk_lambda=None,
):
    """
    Turn search facts into one scored command without selecting it.

    This is the stable seam for future-value, chunk and learned selectors:
    candidate generation owns ``PlacementProposal``; this function owns the
    current immediate/risk model; selectors consume ``PlacementDecision``;
    the simulator receives only ``PlacementCommand.as_action()``.
    """
    immediate = Ranker.evaluate(
        proposal.candidate,
        proposal.item,
        proposal.container,
        has_priority_container,
    )
    if not isinstance(immediate, RankEvaluation):
        # Compatibility for small experiment/test evaluators that return a
        # scalar.  Production Ranker.evaluate always returns named terms.
        scalar = float(immediate)
        immediate = RankEvaluation(
            volume=0.0,
            support=0.0,
            depth=0.0,
            lateral=0.0,
            lift=0.0,
            routing=0.0,
            zone=0.0,
            unattributed=scalar,
            total=scalar,
        )
    risk = release_risk_adjustment(
        proposal.candidate,
        proposal.item,
        proposal.container,
        proposal.orientation,
        risk_lambda,
    )
    adjusted = float(immediate.total) - float(risk.total_penalty)
    command = proposal.command()
    evaluation = CandidateEvaluation(
        immediate=immediate,
        risk=risk,
        adjusted_score=adjusted,
        provenance=str(proposal.source),
    )
    return PlacementDecision(
        action=command.as_action(),
        candidate=proposal.candidate,
        score=adjusted,
        proposal=proposal,
        command=command,
        evaluation=evaluation,
    )


def make_placement_decision(
    item_idx,
    item,
    container_idx,
    container,
    orientation,
    candidate,
    has_priority_container,
    risk_lambda=None,
    source="placement_core",
    structured=False,
):
    """Create either the shipped light decision or an opt-in rich one."""
    if structured:
        return evaluate_placement_proposal(
            PlacementProposal(
                pool_index=int(item_idx),
                stable_item_index=int(item.get("index", item_idx)),
                item=item,
                container_index=int(container_idx),
                container=container,
                orientation=int(orientation),
                candidate=candidate,
                source=str(source),
            ),
            has_priority_container=has_priority_container,
            risk_lambda=risk_lambda,
        )
    score = Ranker.score(
        candidate,
        item,
        container,
        has_priority_container,
    )
    score, _risk_probability = risk_adjusted_score(
        score,
        candidate,
        item,
        container,
        orientation,
        risk_lambda,
    )
    return PlacementDecision(
        action={
            "item_idx": int(item_idx),
            "container_idx": int(container_idx),
            "place_pos": np.asarray(
                simulator_action_center(candidate, container),
                dtype=np.float32,
            ),
            "orientation": int(orientation),
        },
        candidate=candidate,
        score=float(score),
    )


def enrich_retained_decision(
    decision,
    observation,
    has_priority_container,
    risk_lambda=None,
    source="placement_core_retained",
):
    """Materialize named terms only after scalar selection has finished."""
    if decision is None:
        return None
    item_idx = int(decision.action["item_idx"])
    container_idx = int(decision.action["container_idx"])
    item = observation["pool_list"][item_idx]
    container = observation["container_list"][container_idx]
    return make_placement_decision(
        item_idx,
        item,
        container_idx,
        container,
        int(decision.action["orientation"]),
        decision.candidate,
        has_priority_container=has_priority_container,
        risk_lambda=risk_lambda,
        source=source,
        structured=True,
    )


def placement_evaluation_record(decision):
    """JSON-safe explanation of a structured candidate evaluation."""
    evaluation = getattr(decision, "evaluation", None)
    command = getattr(decision, "command", None)
    if evaluation is None:
        return None
    risk = evaluation.risk
    return {
        "schema_version": 1,
        "provenance": str(evaluation.provenance),
        "immediate_components": evaluation.immediate.components(),
        "immediate_total": float(evaluation.immediate.total),
        "risk": {
            "rotation_probability": risk.rotation_probability,
            "slide_probability": risk.slide_probability,
            "rotation_penalty": float(risk.rotation_penalty),
            "slide_penalty": float(risk.slide_penalty),
            "total_penalty": float(risk.total_penalty),
        },
        "adjusted_score": float(evaluation.adjusted_score),
        "command_mode": None if command is None else str(command.mode),
        "stable_item_index": (
            None if command is None else int(command.stable_item_index)
        ),
    }


def action_for_execution(decision):
    """Convert the selected decision to the external simulator contract."""
    command = getattr(decision, "command", None)
    if command is not None:
        return command.as_action()
    return decision.action


def eligible_container_indices(item, containers):
    indices = list(range(len(containers)))
    if not bool(item.get("is_prioritized", False)):
        return indices
    priority_indices = [
        index
        for index, container in enumerate(containers)
        if bool(container.get("is_prioritized", False))
    ]
    return priority_indices or indices


def online_item_order(pool_list):
    def key(index_and_item):
        index, item = index_and_item
        volume = (
            float(item["length"])
            * float(item["width"])
            * float(item["height"])
        )
        if bool(item.get("is_prioritized", False)):
            group = 2
        elif bool(item.get("is_soft", False)):
            group = 1
        else:
            group = 0
        return (
            group,
            -float(item.get("mass", 1.0)),
            -volume,
            index,
        )

    return sorted(enumerate(pool_list), key=key)


def capped_online_items(pool_list, limit, mode=ITEM_COVERAGE_MODE):
    """
    Apply the online item cap without silently dropping an entire class.

    ``legacy`` preserves the original prefix. ``class_aware`` reserves one
    slot for each present class, in the existing normal -> soft -> priority
    strategy order, then fills the remaining slots from the legacy order.
    Candidate ranking remains unchanged.
    """
    normalized_mode = str(mode).strip().lower()
    if normalized_mode not in ITEM_COVERAGE_MODES:
        available = ", ".join(sorted(ITEM_COVERAGE_MODES))
        raise ValueError(
            f"unknown item coverage mode '{mode}'; available: {available}"
        )
    if limit <= 0:
        return []
    ordered = online_item_order(pool_list)
    if normalized_mode == "legacy" or len(ordered) <= limit:
        return ordered[:limit]

    representatives = []
    represented_pool_indices = set()
    for class_id in (0, 1, 2):
        representative = next(
            (
                indexed_item
                for indexed_item in ordered
                if item_group(indexed_item[1]) == class_id
            ),
            None,
        )
        if representative is None:
            continue
        representatives.append(representative)
        represented_pool_indices.add(int(representative[0]))
        if len(representatives) >= limit:
            return representatives

    selected = list(representatives)
    for indexed_item in ordered:
        if int(indexed_item[0]) in represented_pool_indices:
            continue
        selected.append(indexed_item)
        if len(selected) >= limit:
            break
    return selected


def rescue_online_items(pool_list):
    """Return every visible item in deterministic class round-robin order."""
    grouped = {class_id: [] for class_id in (0, 1, 2)}
    for indexed_item in online_item_order(pool_list):
        grouped[item_group(indexed_item[1])].append(indexed_item)
    ordered = []
    depth = 0
    while any(depth < len(grouped[class_id]) for class_id in grouped):
        for class_id in (0, 1, 2):
            if depth < len(grouped[class_id]):
                ordered.append(grouped[class_id][depth])
        depth += 1
    return ordered


def item_group(item):
    if bool(item.get("is_prioritized", False)):
        return 2
    if bool(item.get("is_soft", False)):
        return 1
    return 0


def item_class_name(item):
    if bool(item.get("is_prioritized", False)):
        return "priority"
    if bool(item.get("is_soft", False)):
        return "soft"
    return "normal"


def selection_stage_coverage(pool_list, stages):
    """Measure item coverage at each narrowing stage, overall and by class."""
    visible_by_class = {
        class_name: set()
        for class_name in ("normal", "soft", "priority")
    }
    for pool_index, item in enumerate(pool_list):
        item_index = int(item.get("index", pool_index))
        visible_by_class[item_class_name(item)].add(item_index)

    visible = set().union(*visible_by_class.values())
    included = set(stages.get("item_cap_item_indices", [])) & visible
    started = (
        set(stages.get("search_started_item_indices", []))
        & included
    )
    generated = (
        set(stages.get("candidate_generated_item_indices", []))
        & started
    )

    def ratio(numerator, denominator):
        if denominator == 0:
            return None
        return float(numerator) / float(denominator)

    def metrics(visible_items):
        class_included = included & visible_items
        class_started = started & class_included
        class_generated = generated & class_started
        return {
            "visible": len(visible_items),
            "included": len(class_included),
            "search_started": len(class_started),
            "candidate_generated": len(class_generated),
            "included_over_visible": ratio(
                len(class_included), len(visible_items)
            ),
            "started_over_included": ratio(
                len(class_started), len(class_included)
            ),
            "generated_over_started": ratio(
                len(class_generated), len(class_started)
            ),
        }

    return {
        "overall": metrics(visible),
        "by_class": {
            class_name: metrics(visible_by_class[class_name])
            for class_name in ("normal", "soft", "priority")
        },
    }


def constructive_order(item_list):
    if not item_list:
        return []

    volumes = [
        float(item["length"])
        * float(item["width"])
        * float(item["height"])
        for item in item_list
    ]
    base_areas = [
        max(
            float(item["length"]) * float(item["width"]),
            float(item["length"]) * float(item["height"]),
            float(item["width"]) * float(item["height"]),
        )
        for item in item_list
    ]
    masses = [float(item.get("mass", 1.0)) for item in item_list]
    volume_scale = max(max(volumes), EPS)
    area_scale = max(max(base_areas), EPS)
    mass_scale = max(max(masses), EPS)

    scored = []
    for stable_position, item in enumerate(item_list):
        length = float(item["length"])
        width = float(item["width"])
        height = float(item["height"])
        volume = length * width * height
        base_area = max(length * width, length * height, width * height)
        mass = float(item.get("mass", 1.0))
        cutout_filler = (
            min(length, width, height) <= 0.30
            and sorted((length, width, height))[1] <= 0.44
            and mass <= 10.0
        )
        if CONSTRUCTIVE_ORDER_MODE == "volume":
            # Lexicographic: no coefficients. The composite's three terms
            # are one axis in disguise (base_area/mass correlate 0.94 on
            # the sample catalog) and its weights are recorded nowhere;
            # volume-only beat it on 2 of 3 seeds when measured.
            composite = volume / volume_scale
        else:
            composite = (
                0.45 * volume / volume_scale
                + 0.30 * base_area / area_scale
                + 0.25 * mass / mass_scale
                - (0.05 if cutout_filler else 0.0)
            )
        scored.append(
            (
                item_group(item),
                -composite,
                -mass,
                -volume,
                stable_position,
                item,
            )
        )
    scored.sort(key=lambda row: row[:-1])
    return [row[-1] for row in scored]


def estimated_remaining_container_volume(container):
    remaining = effective_container_volume(container)
    for packed in container.get("packed_items", []):
        try:
            remaining -= math.prod(packed_dimensions(packed))
        except (KeyError, TypeError, ValueError):
            continue
    return max(0.0, float(remaining))


def prioritized_search_units(
    observation,
    indexed_items,
    class_aware_first_pass=False,
):
    """
    Build a deterministic item -> stable-pose -> roomy-container order.

    ``indexed_items`` already carries the strategy order (hard normal,
    soft, then priority for the online policy).  Within an item, poses with
    a larger base are visited first, followed by eligible containers with
    more estimated remaining volume.
    """
    containers = observation.get("container_list", [])
    units = []
    for item_rank, (item_idx, item) in enumerate(indexed_items):
        orientations = sorted(
            unique_orientations(item),
            key=lambda orientation: (
                -math.prod(
                    get_rotated_dimensions(
                        item["length"],
                        item["width"],
                        item["height"],
                        orientation,
                    )[:2]
                ),
                orientation,
            ),
        )
        container_indices = sorted(
            eligible_container_indices(item, containers),
            key=lambda container_idx: (
                -estimated_remaining_container_volume(
                    containers[container_idx]
                ),
                container_idx,
            ),
        )
        for pose_rank, orientation in enumerate(orientations):
            for container_rank, container_idx in enumerate(container_indices):
                for kind_rank, attempt_kind in enumerate(
                    ("settled", "release")
                ):
                    units.append(
                        (
                            item_rank,
                            pose_rank,
                            container_rank,
                            kind_rank,
                            int(item_idx),
                            item,
                            int(container_idx),
                            int(orientation),
                            attempt_kind,
                        )
                    )
    units.sort(key=lambda unit: unit[:4])
    if class_aware_first_pass:
        first_units = []
        remaining_units = []
        seen_item_ranks = set()
        for unit in units:
            item_rank = int(unit[0])
            if item_rank not in seen_item_ranks:
                seen_item_ranks.add(item_rank)
                first_units.append(unit)
            else:
                remaining_units.append(unit)
        return first_units + remaining_units
    return units


def rescue_search_units(observation, indexed_items):
    """
    Put one release and one settled unit for every item before deepening.

    The ordinary anytime stream prioritizes quality.  Rescue instead
    prioritizes breadth: every visible item and both candidate modes get a
    shallow chance before another pose/container unit is expanded.
    """
    units = prioritized_search_units(observation, indexed_items)
    first_units = []
    remaining_units = []
    seen_item_kinds = set()
    for unit in units:
        key = (int(unit[0]), str(unit[8]))
        if key in seen_item_kinds:
            remaining_units.append(unit)
        else:
            seen_item_kinds.add(key)
            first_units.append(unit)
    first_units.sort(key=lambda unit: (-int(unit[3]), int(unit[0])))
    return first_units + remaining_units


def candidate_audit_record(
    item_idx,
    item,
    container_idx,
    orientation,
    candidate,
    container,
    elapsed_seconds=None,
):
    action_center = simulator_action_center(candidate, container)
    record = {
        "pool_index": int(item_idx),
        "item_index": int(item.get("index", item_idx)),
        "container_index": int(container_idx),
        "orientation": int(orientation),
        "kind": candidate.name or "candidate",
        "center": [float(value) for value in candidate.center],
        "size": [float(value) for value in candidate.size],
        "action_center": [float(value) for value in action_center],
    }
    if elapsed_seconds is not None:
        record["elapsed_seconds"] = float(elapsed_seconds)
    return record


def revalidate_cross_step_candidates(
    observation,
    retained_candidates,
    *,
    deadline=None,
    risk_lambda=None,
):
    """Revalidate retained commands against the next observed state.

    This is shadow telemetry only.  It deliberately uses the complete
    current static contract instead of assuming that a candidate survives
    merely because it does not overlap the newest packed item.
    """
    started = time.perf_counter()
    pool_list = observation.get("pool_list", [])
    containers = observation.get("container_list", [])
    pool_by_item_index = {}
    for pool_index, item in enumerate(pool_list):
        item_index = int(item.get("index", pool_index))
        pool_by_item_index.setdefault(item_index, (pool_index, item))

    failure_counts = {}
    valid = []
    pool_survivor_items = set()
    valid_items = set()
    valid_kinds = {"settled": 0, "release": 0}
    records = []
    for retained in retained_candidates:
        pool_entry = pool_by_item_index.get(retained.item_index)
        if pool_entry is None:
            reason = "item_not_visible"
        elif not 0 <= retained.container_index < len(containers):
            reason = "container_not_visible"
        else:
            pool_index, item = pool_entry
            pool_survivor_items.add(retained.item_index)
            container = containers[retained.container_index]
            candidate = retained.candidate
            if candidate.name == "release_candidate":
                reason = Geometry.release_rejection_reason(
                    candidate, container, item=item
                )
                if reason is None and not release_candidate_passes_risk_gate(
                    candidate,
                    item,
                    container,
                    retained.orientation,
                    mode=RELEASE_RISK_GATE_MODE,
                    diagnostics=None,
                    item_idx=pool_index,
                ):
                    reason = "risk_gate"
            else:
                reason = Geometry.rejection_reason(candidate, container)

        record = {
            "item_index": int(retained.item_index),
            "previous_pool_index": int(retained.previous_pool_index),
            "container_index": int(retained.container_index),
            "orientation": int(retained.orientation),
            "kind": retained.candidate.name or "candidate",
            "previous_score": float(retained.previous_score),
            "valid": reason is None,
            "rejection_reason": reason,
        }
        if pool_entry is not None:
            record["current_pool_index"] = int(pool_entry[0])
        records.append(record)
        if reason is not None:
            failure_counts[reason] = failure_counts.get(reason, 0) + 1
            continue

        pool_index, item = pool_entry
        container = containers[retained.container_index]
        decision = make_placement_decision(
            pool_index,
            item,
            retained.container_index,
            container,
            retained.orientation,
            retained.candidate,
            has_priority_container=any(
                bool(candidate_container.get("is_prioritized", False))
                for candidate_container in containers
            ),
            risk_lambda=risk_lambda,
            source="cross_step_revalidation",
        )
        valid.append(decision)
        valid_items.add(retained.item_index)
        kind = (
            "release"
            if retained.candidate.name == "release_candidate"
            else "settled"
        )
        valid_kinds[kind] += 1
        record["current_score"] = float(decision.score)

    finished = time.perf_counter()
    return {
        "mode": "shadow",
        "previous_count": len(retained_candidates),
        "previous_item_count": len(
            {candidate.item_index for candidate in retained_candidates}
        ),
        "pool_survivor_count": sum(
            1
            for candidate in retained_candidates
            if candidate.item_index in pool_by_item_index
        ),
        "pool_survivor_item_count": len(pool_survivor_items),
        "static_valid_count": len(valid),
        "static_valid_item_count": len(valid_items),
        "valid_settled_count": valid_kinds["settled"],
        "valid_release_count": valid_kinds["release"],
        "failure_counts": failure_counts,
        "validation_seconds": float(finished - started),
        "deadline_remaining_before_validation": (
            None if deadline is None else float(deadline - started)
        ),
        "deadline_remaining_after_validation": (
            None if deadline is None else float(deadline - finished)
        ),
        "candidates": records,
    }, valid


def iter_stride_fallback_candidates(
    observation,
    indexed_items,
    deadline=None,
    diagnostics=None,
):
    """
    Coarse-to-fine cartesian rescan of the same units, for the case where the
    primary anchor space is exhausted and empty.

    Each stride level covers the WHOLE anchor grid, sampling every stride-th
    deduped position, so a level cut short by the deadline has still looked
    everywhere at that resolution. This is the opposite of truncating a dense
    scan, which spends the budget on one corner. Yields accepted candidates in
    the same shape as the primary stream, so the caller's incumbent logic is
    unchanged.
    """
    # Release units first, against the canonical order. Measured on the
    # c001-k1 fatal state: the cartesian settled space costs 399,975 attempts
    # for 6 candidates while the release space costs 31,953 for 54, so the
    # canonical settled-first order spends the whole remaining budget in the
    # expensive, sparse half and finds nothing (0 accepted in 2.3 s), while
    # release-first finds one in 0.38 s.
    #
    # This is a real trade, not free: if the release sweep consumes the
    # budget, the caller may return a release candidate where a settled one
    # existed, and release placements are the topple channel. It is taken
    # because the alternative this path replaces is the fixed-coordinate
    # action that ends the episode outright, and the risk terms still rank
    # whatever is found.
    units = sorted(
        prioritized_search_units(observation, indexed_items),
        key=lambda unit: (0 if unit[8] == "release" else 1, unit[:4]),
    )
    stats = None
    if diagnostics is not None:
        stats = diagnostics.setdefault("search", {}).setdefault(
            "anchor_fallback",
            {
                "strides": list(ANCHOR_FALLBACK_STRIDES),
                "levels_started": 0,
                "levels_completed": 0,
                "attempts": 0,
                "accepted": 0,
                "deadline_reached": False,
                "first_accepted_seconds": None,
            },
        )
    started = time.perf_counter()
    for stride in ANCHOR_FALLBACK_STRIDES:
        if stats is not None:
            stats["levels_started"] += 1
        level_complete = True
        for unit in units:
            (
                _item_rank,
                _pose_rank,
                _container_rank,
                _kind_rank,
                item_idx,
                item,
                container_idx,
                orientation,
                attempt_kind,
            ) = unit
            for candidate in CandidateGenerator.iter_cartesian_attempts(
                observation,
                item,
                container_idx,
                orientation,
                limit=sys.maxsize,
                deadline=deadline,
                diagnostics=diagnostics,
                item_idx=item_idx,
                attempt_kind=attempt_kind,
                stride=stride,
            ):
                if stats is not None:
                    stats["attempts"] += 1
                if candidate is not None:
                    if stats is not None:
                        stats["accepted"] += 1
                        if stats["first_accepted_seconds"] is None:
                            stats["first_accepted_seconds"] = (
                                time.perf_counter() - started
                            )
                    yield (
                        item_idx,
                        item,
                        container_idx,
                        orientation,
                        candidate,
                    )
                if (
                    deadline is not None
                    and time.perf_counter() >= deadline
                ):
                    if stats is not None:
                        stats["deadline_reached"] = True
                    return
            if deadline is not None and time.perf_counter() >= deadline:
                if stats is not None:
                    stats["deadline_reached"] = True
                    level_complete = False
                return
        if stats is not None and level_complete:
            stats["levels_completed"] += 1


def iter_prioritized_candidates(
    observation,
    indexed_items,
    deadline=None,
    diagnostics=None,
    attempt_budget=None,
    anchor_fallback=False,
    stride=1,
    stride_offset=0,
    interleave=1,
):
    """
    Time-sliced candidate stream.

    Every prioritized (item, pose, container) unit receives a shallow first
    pass before any unit is deeply expanded.  Subsequent rounds continue in
    the same priority order, so the caller can retain and improve a safe
    incumbent without starving later items or poses.

    ``anchor_fallback`` replaces the primary anchor space with the coarse-to-
    fine cartesian rescan. The caller sets it only after a primary search has
    completed every unit and accepted nothing, where repeating the primary
    scan is known to be pure waste.

    ``stride``/``stride_offset`` are forwarded to the anchor generator.  The
    budget in ``attempt_budget`` counts yielded attempts, and a strided skip
    yields nothing, so raising the stride buys anchor-grid coverage at a
    fixed budget rather than at extra cost.  Stride 1 is the unchanged
    default.

    ``interleave`` is the deadline-limited counterpart and is *not* the same
    knob: it permutes the anchor order instead of subsampling it, so a
    search that exhausts a unit still sees every anchor.  Use ``stride`` when
    the cap is an attempt count that will never be exhausted, ``interleave``
    when the cap is a deadline that might be.
    """
    if anchor_fallback:
        yield from iter_stride_fallback_candidates(
            observation,
            indexed_items,
            deadline=deadline,
            diagnostics=diagnostics,
        )
        return
    class_aware_first_pass = bool(
        diagnostics is not None
        and diagnostics.get("_class_aware_first_pass", False)
    )
    units = prioritized_search_units(
        observation,
        indexed_items,
        class_aware_first_pass=class_aware_first_pass,
    )
    search_started = time.perf_counter()
    audit = None
    if diagnostics is not None and CANDIDATE_AUDIT_ENABLED:
        searches = diagnostics.setdefault("candidate_audit", [])
        audit = {
            "search_index": len(searches),
            "accepted_settled": [],
            "accepted_release": [],
            # Per-unit progress at the moment the search stops. The accepted
            # lists alone cannot tell an unvisited unit from a visited one
            # whose candidates lie deeper than the attempts spent, and those
            # two call for opposite fixes (reorder units versus keep an
            # anytime incumbent). Audit-only; the shipped policy never
            # enables this.
            "units": [],
        }
        searches.append(audit)
    states = [
        {
            "unit": unit,
            "iterator": None,
            "unit_rank": unit_rank,
        }
        for unit_rank, unit in enumerate(units)
    ]
    unit_audit = None
    if audit is not None:
        unit_audit = [
            {
                "unit_rank": unit_rank,
                "pool_index": int(unit[4]),
                "item_index": int(unit[5].get("index", unit[4])),
                "container_index": int(unit[6]),
                "orientation": int(unit[7]),
                "attempt_kind": unit[8],
                "started": False,
                "exhausted": False,
                "attempts": 0,
                "accepted": 0,
                "first_seen_seconds": None,
            }
            for unit_rank, unit in enumerate(units)
        ]
        audit["units"] = unit_audit
    search_stats = None
    record_item_lifecycle = bool(
        diagnostics is not None
        and diagnostics.get("_record_item_lifecycle", False)
    )
    if diagnostics is not None:
        search_stats = diagnostics.setdefault(
            "search",
            {
                "units_total": len(units),
                "units_started": 0,
                "units_completed": 0,
                "rounds_started": 0,
                "deadline_reached": False,
                "incumbent_updates": 0,
                # Depth-vs-breadth telemetry. attempts_used is the whole
                # scan's cost; attempts_to_first_candidate is how deep the
                # scan had to go before anything at all was placeable, and
                # is None when nothing ever was. Together they say whether
                # a first-pass cap is starving units or wasting them.
                "attempts_to_first_candidate": None,
            },
        )
        # A diagnostics dict can outlive one scan, so the new fields are
        # defaulted rather than assumed present.
        search_stats.setdefault("attempts_to_first_candidate", None)
        if record_item_lifecycle:
            search_stats.setdefault("item_indices_started", [])
            search_stats.setdefault("item_indices_with_candidates", [])

    attempts_used = 0
    attempts_per_unit = max(1, ANCHOR_FIRST_PASS_ATTEMPTS)
    while states:
        if search_stats is not None:
            search_stats["rounds_started"] += 1
        next_states = []
        for state in states:
            if (
                deadline is not None
                and time.perf_counter() >= deadline
            ):
                if search_stats is not None:
                    search_stats["deadline_reached"] = True
                return

            (
                _item_rank,
                _pose_rank,
                _container_rank,
                _kind_rank,
                item_idx,
                item,
                container_idx,
                orientation,
                attempt_kind,
            ) = state["unit"]
            if state["iterator"] is None:
                state["iterator"] = CandidateGenerator.iter_attempts(
                    observation,
                    item,
                    container_idx,
                    orientation,
                    deadline=deadline,
                    diagnostics=diagnostics,
                    item_idx=item_idx,
                    attempt_kind=attempt_kind,
                    stride=stride,
                    stride_offset=stride_offset,
                    interleave=interleave,
                )
                if search_stats is not None:
                    search_stats["units_started"] += 1
                if unit_audit is not None:
                    entry = unit_audit[state["unit_rank"]]
                    entry["started"] = True
                    entry["first_seen_seconds"] = (
                        time.perf_counter() - search_started
                    )
                if record_item_lifecycle:
                    item_index = int(item.get("index", item_idx))
                    if (
                        item_index
                        not in search_stats["item_indices_started"]
                    ):
                        search_stats["item_indices_started"].append(
                            item_index
                        )

            exhausted = False
            for _ in range(attempts_per_unit):
                if (
                    attempt_budget is not None
                    and attempts_used >= int(attempt_budget)
                ):
                    return
                if (
                    deadline is not None
                    and time.perf_counter() >= deadline
                ):
                    if search_stats is not None:
                        search_stats["deadline_reached"] = True
                    return
                try:
                    candidate = next(state["iterator"])
                except StopIteration:
                    exhausted = True
                    if search_stats is not None:
                        search_stats["units_completed"] += 1
                    if unit_audit is not None:
                        unit_audit[state["unit_rank"]]["exhausted"] = True
                    break
                attempts_used += 1
                if unit_audit is not None:
                    unit_audit[state["unit_rank"]]["attempts"] += 1
                if search_stats is not None:
                    # Recorded unconditionally. It used to be written only
                    # when a budget was set, which meant the SHIPPED
                    # deadline path -- the one whose irreproducibility is
                    # the problem -- reported no work quantity at all, so
                    # the budget could not be calibrated from it.
                    search_stats["attempts_consumed"] = attempts_used
                    if (
                        candidate is not None
                        and search_stats["attempts_to_first_candidate"]
                        is None
                    ):
                        search_stats["attempts_to_first_candidate"] = (
                            attempts_used
                        )
                if candidate is not None:
                    if record_item_lifecycle:
                        item_index = int(item.get("index", item_idx))
                        if (
                            item_index
                            not in search_stats[
                                "item_indices_with_candidates"
                            ]
                        ):
                            search_stats[
                                "item_indices_with_candidates"
                            ].append(item_index)
                    if audit is not None:
                        unit_audit[state["unit_rank"]]["accepted"] += 1
                        audit_key = (
                            "accepted_release"
                            if candidate.name == "release_candidate"
                            else "accepted_settled"
                        )
                        audit[audit_key].append(
                            candidate_audit_record(
                                item_idx,
                                item,
                                container_idx,
                                orientation,
                                candidate,
                                observation["container_list"][
                                    container_idx
                                ],
                                elapsed_seconds=(
                                    time.perf_counter() - search_started
                                ),
                            )
                        )
                    yield (
                        item_idx,
                        item,
                        container_idx,
                        orientation,
                        candidate,
                    )
            if not exhausted:
                next_states.append(state)
        states = next_states
        attempts_per_unit = max(1, ANCHOR_DEEP_PASS_ATTEMPTS)


# --- Board receptivity -----------------------------------------------------
#
# The ranker scores a placement by what it gains: volume, support, depth,
# priority routing, minus a release-risk penalty.  Nothing in it prices
# what the placement costs the *board*.  Two placements that gain the same
# volume can leave surfaces that differ by everything.
#
# A strong Tetris player does not merely avoid holes.  They keep a board
# that accepts whatever arrives next and that can still be repaired when it
# does not.  Three quantities carry that, and all three are readable off a
# height map -- which is what a Tetris board is:
#
#   A  acceptance breadth  how many of the shapes still in play have at
#                          least one landing site left.  A board that has
#                          stopped accepting a shape has lost it whether or
#                          not that shape has arrived yet.
#   R  alternativity       how many distinct sites each shape has.  One
#                          site is not the same as two: with one site the
#                          board is hostage to arrival order, because any
#                          intervening placement can take it.
#   H  repairability       the void sealed under the surface, which no
#                          later placement can reclaim, and the roughness
#                          that makes large footprints unplaceable.  A is
#                          about now; H is about whether a bad now can be
#                          undone.
#
# Two approximations, both deliberate and both conservative:
#
# * A height map is 2.5D, so the space under a shelf cannot be represented.
#   Shelf columns are charged as solid from the floor up, which means items
#   placed beneath a shelf are invisible to these features rather than
#   counted as damage.
# * Columns are sampled at their centres, so a ledge narrower than a cell
#   does not exist.  Under-counting sites is safer than inventing them.
#
# These features rank; they do not gate.  Every candidate they see has
# already passed inclusion, transport-path and support validation.


@dataclass(frozen=True)
class BoardGrid:
    cell_x: float
    cell_y: float
    xs: Any
    ys: Any
    floor: Any
    ceiling: Any
    usable: Any

    @property
    def cell_area(self):
        return self.cell_x * self.cell_y


@dataclass(frozen=True)
class BoardFeatures:
    accepted_shapes: int
    total_shapes: int
    alternativity: int
    sealed_volume: float
    roughness: float

    def rank_key(self):
        """A first, then R, then H. Breadth lost is not bought back by
        tidiness; a tidy board that accepts nothing is finished."""
        return (
            self.accepted_shapes,
            self.alternativity,
            -self.sealed_volume,
            -self.roughness,
        )

    def as_dict(self):
        return {
            "accepted_shapes": int(self.accepted_shapes),
            "total_shapes": int(self.total_shapes),
            "alternativity": int(self.alternativity),
            "sealed_volume": float(self.sealed_volume),
            "roughness": float(self.roughness),
        }


_BOARD_GRID_CACHE: dict[tuple, BoardGrid] = {}
_BOARD_OCCUPANCY_CACHE: dict[int, tuple] = {}


def _board_grid_key(container):
    return (
        round(float(container["length"]), 6),
        round(float(container["width"]), 6),
        round(float(container["height"]), 6),
        round(float(container["thickness"]), 6),
        round(float(container.get("buffer", 0.0)), 6),
        round(float(container.get("cut_x", 0.0)), 6),
        round(float(container.get("cut_y", 0.0)), 6),
        round(float(container_offset_x(container)), 6),
        bool(container_requires_shelf(container)),
        round(BOARD_CELL_SIZE, 6),
    )


def board_grid(container):
    """Column centres with the z interval the container allows at each."""
    key = _board_grid_key(container)
    hit = _BOARD_GRID_CACHE.get(key)
    if hit is not None:
        return hit

    length = float(container["length"])
    width = float(container["width"])
    height = float(container["height"])
    thickness = float(container["thickness"])
    buffer = float(container.get("buffer", 0.0))

    x_span = max(length - 2.0 * thickness, BOARD_CELL_SIZE)
    y_span = max(width - 2.0 * thickness, BOARD_CELL_SIZE)
    nx = max(1, int(round(x_span / BOARD_CELL_SIZE)))
    ny = max(1, int(round(y_span / BOARD_CELL_SIZE)))
    cell_x = x_span / nx
    cell_y = y_span / ny
    x0 = -length / 2.0 + thickness
    y0 = -width / 2.0 + thickness
    xs = np.array(
        [x0 + (index + 0.5) * cell_x for index in range(nx)], dtype=np.float64
    )
    ys = np.array(
        [y0 + (index + 0.5) * cell_y for index in range(ny)], dtype=np.float64
    )

    # Fallback when the container carries no half-space description: the
    # nominal interior box.  Used by unit tests and by any observation that
    # omits points/n_vecs.
    fallback_floor = thickness + buffer
    fallback_ceiling = height - thickness

    floor = np.zeros((nx, ny), dtype=np.float64)
    ceiling = np.zeros((nx, ny), dtype=np.float64)
    usable = np.zeros((nx, ny), dtype=bool)
    for i in range(nx):
        for j in range(ny):
            interval = container_z_interval(
                float(xs[i]), float(ys[j]), (0.0, 0.0, 0.0), container
            )
            if interval is None:
                continue
            lower, upper = interval
            if not math.isfinite(lower) or not math.isfinite(upper):
                lower, upper = fallback_floor, fallback_ceiling
            if upper <= lower:
                continue
            floor[i, j] = lower
            ceiling[i, j] = upper
            usable[i, j] = True

    grid = BoardGrid(cell_x, cell_y, xs, ys, floor, ceiling, usable)
    if len(_BOARD_GRID_CACHE) > 32:
        _BOARD_GRID_CACHE.clear()
    _BOARD_GRID_CACHE[key] = grid
    return grid


def _board_stamp(grid, top, filled, box, from_floor=False):
    """Raise the surface over one box and charge its column volume."""
    minimum = box.minimum
    maximum = box.maximum
    i0 = int(np.searchsorted(grid.xs, minimum[0], side="left"))
    i1 = int(np.searchsorted(grid.xs, maximum[0], side="right"))
    j0 = int(np.searchsorted(grid.ys, minimum[1], side="left"))
    j1 = int(np.searchsorted(grid.ys, maximum[1], side="right"))
    if i1 <= i0 or j1 <= j0:
        return
    window = (slice(i0, i1), slice(j0, j1))
    z_top = float(maximum[2])
    z_bottom = float(minimum[2])
    np.maximum(top[window], z_top, out=top[window])
    if from_floor:
        filled[window] += np.maximum(z_top - grid.floor[window], 0.0)
    else:
        filled[window] += max(z_top - z_bottom, 0.0)


def board_occupancy(container, grid=None):
    """Surface height and filled column volume for the settled board."""
    grid = grid if grid is not None else board_grid(container)
    packed_list = container.get("packed_items", [])
    key = id(packed_list)
    hit = _BOARD_OCCUPANCY_CACHE.get(key)
    if (
        hit is not None
        and hit[0] is packed_list
        and hit[1] == len(packed_list)
        and hit[2] is grid
    ):
        return hit[3], hit[4]

    top = grid.floor.copy()
    filled = np.zeros_like(top)
    # A shelf is charged solid from the floor up. See the module note: this
    # hides the space beneath rather than reporting it as damage.
    for shelf in shelf_aabbs(container):
        _board_stamp(grid, top, filled, shelf, from_floor=True)
    for box, _is_soft, _is_prioritized in packed_aabbs_local(container):
        _board_stamp(grid, top, filled, box)

    if len(_BOARD_OCCUPANCY_CACHE) > 256:
        _BOARD_OCCUPANCY_CACHE.clear()
    _BOARD_OCCUPANCY_CACHE[key] = (packed_list, len(packed_list), grid, top, filled)
    return top, filled


def board_probe_shapes(items, limit=None):
    """Distinct footprints still in play, largest first.

    Every orientation of every visible item contributes a footprint; the
    required headroom for a footprint is the smallest height among the
    orientations that produce it, because that is the easiest way for the
    board to accept that shape.
    """
    limit = BOARD_PROBE_SHAPES if limit is None else limit
    shapes: dict[tuple, float] = {}
    for item in items:
        try:
            length = float(item["length"])
            width = float(item["width"])
            height = float(item["height"])
        except (KeyError, TypeError, ValueError):
            continue
        for orientation in unique_orientations(item):
            dx, dy, dz = get_rotated_dimensions(
                length, width, height, orientation
            )
            key = (round(float(dx), 4), round(float(dy), 4))
            previous = shapes.get(key)
            if previous is None or float(dz) < previous:
                shapes[key] = float(dz)
    ordered = sorted(
        shapes.items(), key=lambda entry: -(entry[0][0] * entry[0][1])
    )
    return [(dx, dy, dz) for (dx, dy), dz in ordered[:limit]]


def _board_site_count(grid, top, headroom, shape):
    """Landing sites for one footprint: flat enough, with headroom."""
    dx, dy, dz = shape
    wx = min(max(1, int(math.ceil(dx / grid.cell_x - EPS))), top.shape[0])
    wy = min(max(1, int(math.ceil(dy / grid.cell_y - EPS))), top.shape[1])
    if top.shape[0] < wx or top.shape[1] < wy:
        return 0
    windows_top = np.lib.stride_tricks.sliding_window_view(top, (wx, wy))
    windows_room = np.lib.stride_tricks.sliding_window_view(
        headroom, (wx, wy)
    )
    windows_usable = np.lib.stride_tricks.sliding_window_view(
        grid.usable, (wx, wy)
    )
    axes = (-2, -1)
    flat = (
        windows_top.max(axis=axes) - windows_top.min(axis=axes)
        <= BOARD_FLATNESS_TOLERANCE + EPS
    )
    room = windows_room.min(axis=axes) >= dz - EPS
    whole = windows_usable.all(axis=axes)
    return int(np.count_nonzero(flat & room & whole))


def board_features(grid, top, filled, shapes):
    """A, R and H for one board state."""
    headroom = grid.ceiling - top
    accepted = 0
    alternativity = 0
    for shape in shapes:
        sites = _board_site_count(grid, top, headroom, shape)
        if sites > 0:
            accepted += 1
        alternativity += min(sites, BOARD_SITE_CAP)

    void = np.where(grid.usable, top - grid.floor - filled, 0.0)
    sealed_volume = float(np.maximum(void, 0.0).sum() * grid.cell_area)

    surface = np.where(grid.usable, top, np.nan)
    roughness = 0.0
    for axis in (0, 1):
        step = np.abs(np.diff(surface, axis=axis))
        roughness += float(np.nansum(step))

    return BoardFeatures(
        accepted_shapes=accepted,
        total_shapes=len(shapes),
        alternativity=alternativity,
        sealed_volume=sealed_volume,
        roughness=roughness,
    )


def board_features_after(container, candidate, shapes):
    """Board features for the state one candidate placement would leave.

    A release candidate is commanded above its resting height and falls.
    Stamping it where it was commanded evaluates a board that never
    exists: it invents a sealed void under a box that is going to land,
    and it eats headroom that will still be there. The settled proxy is
    the same one the release risk model already uses, so the board and
    the risk gate agree about where the item ends up.
    """
    grid = board_grid(container)
    base_top, base_filled = board_occupancy(container, grid)
    top = base_top.copy()
    filled = base_filled.copy()
    _board_stamp(
        grid, top, filled, settled_proxy_candidate(candidate, container)
    )
    return board_features(grid, top, filled, shapes)


def board_rank_key(decision, containers, shapes):
    """Rank one immediate candidate by the board it would leave behind.

    The incumbent score breaks ties last, so within a set of candidates the
    board cannot distinguish, behaviour is the shipped behaviour.
    """
    container_index = int(decision.action["container_idx"])
    if not (0 <= container_index < len(containers)):
        return None
    features = board_features_after(
        containers[container_index], decision.candidate, shapes
    )
    return features, features.rank_key() + (float(decision.score),)


class SettledFirstSelector:
    """Current live selection doctrine, isolated from candidate search."""

    def __init__(self, containers):
        self.containers = containers
        self.best_settled = None
        self.best_settled_score = -float("inf")
        self.best_release = None
        self.best_release_score = -float("inf")
        self.release_by_container = {}

    def _beats(self, challenger, incumbent_score, incumbent):
        challenger_score = float(challenger.score)
        if incumbent is None:
            return True
        if L3_PREFER_EMPTY_BAND <= 0.0:
            return challenger_score > incumbent_score
        if challenger_score > incumbent_score + L3_PREFER_EMPTY_BAND:
            return True
        if challenger_score < incumbent_score - L3_PREFER_EMPTY_BAND:
            return False
        remaining_new = estimated_remaining_container_volume(
            self.containers[int(challenger.action["container_idx"])]
        )
        remaining_old = estimated_remaining_container_volume(
            self.containers[int(incumbent.action["container_idx"])]
        )
        if abs(remaining_new - remaining_old) > EPS:
            return remaining_new > remaining_old
        return challenger_score > incumbent_score

    def observe(self, decision):
        score = float(decision.score)
        updated = False
        if decision.candidate.name == "release_candidate":
            if self._beats(
                decision, self.best_release_score, self.best_release
            ):
                self.best_release_score = score
                self.best_release = decision
                updated = True
            if L3_RELEASE_ROUTE:
                container_index = int(decision.action["container_idx"])
                incumbent = self.release_by_container.get(container_index)
                if incumbent is None or score > incumbent[0]:
                    self.release_by_container[container_index] = (
                        score,
                        decision,
                    )
        elif self._beats(
            decision, self.best_settled_score, self.best_settled
        ):
            self.best_settled_score = score
            self.best_settled = decision
            updated = True
        return updated

    def select(self):
        if self.best_settled is not None:
            return self.best_settled
        if L3_RELEASE_ROUTE and len(self.release_by_container) > 1:
            emptiest = max(
                self.release_by_container,
                key=lambda container_index: (
                    estimated_remaining_container_volume(
                        self.containers[container_index]
                    ),
                    self.release_by_container[container_index][0],
                ),
            )
            return self.release_by_container[emptiest][1]
        return self.best_release


class TopKSettledFirstSelector:
    """Bounded portfolio with the same settled-before-release doctrine."""

    def __init__(self, k):
        self.k = max(0, int(k))
        self.settled_heap = []
        self.release_heap = []
        self.counter = 0

    def observe(self, decision):
        self.counter += 1
        score = float(decision.score)
        entry = (score, self.counter, decision)
        heap = (
            self.release_heap
            if decision.candidate.name == "release_candidate"
            else self.settled_heap
        )
        if len(heap) < self.k:
            heapq.heappush(heap, entry)
            return True
        if heap and score > heap[0][0]:
            heapq.heapreplace(heap, entry)
            return True
        return False

    def select(self):
        return [
            decision
            for _, _, decision in sorted(
                self.settled_heap or self.release_heap,
                key=lambda entry: entry[0],
                reverse=True,
            )
        ]


class PlacementCore:
    """Single source of truth used by online policy and offline dry-runs."""

    @staticmethod
    def choose(
        observation,
        indexed_items,
        deadline=None,
        diagnostics=None,
        risk_lambda=None,
        candidate_observer=None,
        anchor_fallback=False,
        attempt_budget=None,
        selector=None,
        structured_evaluation=False,
        retained_evaluation=False,
    ):
        containers = observation.get("container_list", [])
        if not containers:
            return None

        has_priority_container = any(
            bool(container.get("is_prioritized", False))
            for container in containers
        )
        if selector is None and not structured_evaluation:
            best_settled = None
            best_settled_score = -float("inf")
            best_release = None
            best_release_score = -float("inf")
            release_by_container = {}

            for (
                item_idx,
                item,
                container_idx,
                orientation,
                candidate,
            ) in iter_prioritized_candidates(
                observation,
                indexed_items,
                deadline=deadline,
                diagnostics=diagnostics,
                anchor_fallback=anchor_fallback,
                interleave=LIVE_SEARCH_INTERLEAVE,
                attempt_budget=effective_attempt_budget(attempt_budget),
            ):
                container = containers[container_idx]
                score = Ranker.score(
                    candidate,
                    item,
                    container,
                    has_priority_container,
                )
                score, _risk_probability = risk_adjusted_score(
                    score,
                    candidate,
                    item,
                    container,
                    orientation,
                    risk_lambda,
                )
                decision = PlacementDecision(
                    action={
                        "item_idx": int(item_idx),
                        "container_idx": int(container_idx),
                        "place_pos": np.asarray(
                            simulator_action_center(candidate, container),
                            dtype=np.float32,
                        ),
                        "orientation": int(orientation),
                    },
                    candidate=candidate,
                    score=float(score),
                )
                if candidate_observer is not None:
                    candidate_observer(
                        item_idx,
                        item,
                        container_idx,
                        orientation,
                        decision,
                    )

                def beats(challenger_score, incumbent_score, incumbent):
                    if incumbent is None:
                        return True
                    if L3_PREFER_EMPTY_BAND <= 0.0:
                        return challenger_score > incumbent_score
                    if (
                        challenger_score
                        > incumbent_score + L3_PREFER_EMPTY_BAND
                    ):
                        return True
                    if (
                        challenger_score
                        < incumbent_score - L3_PREFER_EMPTY_BAND
                    ):
                        return False
                    remaining_new = estimated_remaining_container_volume(
                        containers[int(decision.action["container_idx"])]
                    )
                    remaining_old = estimated_remaining_container_volume(
                        containers[int(incumbent.action["container_idx"])]
                    )
                    if abs(remaining_new - remaining_old) > EPS:
                        return remaining_new > remaining_old
                    return challenger_score > incumbent_score

                updated = False
                if candidate.name == "release_candidate":
                    if beats(score, best_release_score, best_release):
                        best_release_score = score
                        best_release = decision
                        updated = True
                    if L3_RELEASE_ROUTE:
                        container_key = int(
                            decision.action["container_idx"]
                        )
                        incumbent = release_by_container.get(container_key)
                        if incumbent is None or score > incumbent[0]:
                            release_by_container[container_key] = (
                                score,
                                decision,
                            )
                elif beats(score, best_settled_score, best_settled):
                    best_settled_score = score
                    best_settled = decision
                    updated = True
                if updated and diagnostics is not None:
                    diagnostics["search"]["incumbent_updates"] += 1
            if best_settled is not None:
                selected = best_settled
            elif L3_RELEASE_ROUTE and len(release_by_container) > 1:
                emptiest = max(
                    release_by_container,
                    key=lambda container_index: (
                        estimated_remaining_container_volume(
                            containers[container_index]
                        ),
                        release_by_container[container_index][0],
                    ),
                )
                selected = release_by_container[emptiest][1]
            else:
                selected = best_release
            if retained_evaluation:
                return enrich_retained_decision(
                    selected,
                    observation,
                    has_priority_container,
                    risk_lambda=risk_lambda,
                    source="placement_core_retained",
                )
            return selected

        active_selector = selector or SettledFirstSelector(containers)
        use_structured_evaluation = bool(
            structured_evaluation or selector is not None
        )

        for (
            item_idx,
            item,
            container_idx,
            orientation,
            candidate,
        ) in iter_prioritized_candidates(
            observation,
            indexed_items,
            deadline=deadline,
            diagnostics=diagnostics,
            anchor_fallback=anchor_fallback,
            interleave=LIVE_SEARCH_INTERLEAVE,
            attempt_budget=effective_attempt_budget(attempt_budget),
        ):
            container = containers[container_idx]
            decision = make_placement_decision(
                item_idx,
                item,
                container_idx,
                container,
                orientation,
                candidate,
                has_priority_container=has_priority_container,
                risk_lambda=risk_lambda,
                source="placement_core",
                structured=use_structured_evaluation,
            )
            score = float(decision.score)
            if candidate_observer is not None:
                candidate_observer(
                    item_idx,
                    item,
                    container_idx,
                    orientation,
                    decision,
                )
            updated = bool(active_selector.observe(decision))
            if updated and diagnostics is not None:
                diagnostics["search"]["incumbent_updates"] += 1
        selected = active_selector.select()
        if retained_evaluation:
            return enrich_retained_decision(
                selected,
                observation,
                has_priority_container,
                risk_lambda=risk_lambda,
                source="placement_core_retained",
            )
        return selected

    @staticmethod
    def rescue_choose(
        observation,
        indexed_items,
        deadline,
        attempt_budget=RESCUE_SCAN_ATTEMPT_BUDGET,
        diagnostics=None,
        risk_lambda=None,
    ):
        """Breadth-first emergency scan with a deterministic work budget."""
        containers = observation.get("container_list", [])
        budget = max(0, int(attempt_budget))
        stats = {
            "enabled": True,
            "triggered": True,
            "reserve_seconds": float(RESCUE_SCAN_RESERVE_SECONDS),
            "attempt_budget": budget,
            "attempts": 0,
            "units_total": 0,
            "units_started": 0,
            "units_completed": 0,
            "deadline_reached": False,
            "accepted_settled": 0,
            "accepted_release": 0,
            "incumbent_updates": 0,
            "item_indices_started": [],
            "item_indices_with_candidates": [],
            "selected_kind": None,
            "selected_item_index": None,
        }
        if diagnostics is not None:
            diagnostics["rescue_scan"] = stats
        if not containers or not indexed_items or budget == 0:
            return None

        units = rescue_search_units(observation, indexed_items)
        stats["units_total"] = len(units)
        states = [{"unit": unit, "iterator": None} for unit in units]
        has_priority_container = any(
            bool(container.get("is_prioritized", False))
            for container in containers
        )
        best_settled = None
        best_settled_score = -float("inf")
        best_release = None
        best_release_score = -float("inf")
        release_by_container = {}

        deadline_reached = False
        while (
            states
            and stats["attempts"] < budget
            and not deadline_reached
        ):
            next_states = []
            for state in states:
                if stats["attempts"] >= budget:
                    break
                if time.perf_counter() >= deadline:
                    stats["deadline_reached"] = True
                    deadline_reached = True
                    break
                (
                    _item_rank,
                    _pose_rank,
                    _container_rank,
                    _kind_rank,
                    item_idx,
                    item,
                    container_idx,
                    orientation,
                    attempt_kind,
                ) = state["unit"]
                if state["iterator"] is None:
                    state["iterator"] = CandidateGenerator.iter_attempts(
                        observation,
                        item,
                        container_idx,
                        orientation,
                        deadline=deadline,
                        diagnostics=diagnostics,
                        item_idx=item_idx,
                        attempt_kind=attempt_kind,
                    )
                    stats["units_started"] += 1
                    item_index = int(item.get("index", item_idx))
                    if item_index not in stats["item_indices_started"]:
                        stats["item_indices_started"].append(item_index)
                exhausted = False
                for _ in range(
                    max(1, int(RESCUE_SCAN_ATTEMPTS_PER_UNIT))
                ):
                    if stats["attempts"] >= budget:
                        break
                    if time.perf_counter() >= deadline:
                        stats["deadline_reached"] = True
                        deadline_reached = True
                        break
                    try:
                        candidate = next(state["iterator"])
                        stats["attempts"] += 1
                    except StopIteration:
                        stats["units_completed"] += 1
                        exhausted = True
                        break
                    if candidate is None:
                        continue

                    item_index = int(item.get("index", item_idx))
                    if (
                        item_index
                        not in stats["item_indices_with_candidates"]
                    ):
                        stats["item_indices_with_candidates"].append(
                            item_index
                        )
                    container = containers[container_idx]
                    decision = make_placement_decision(
                        item_idx,
                        item,
                        container_idx,
                        container,
                        orientation,
                        candidate,
                        has_priority_container=has_priority_container,
                        risk_lambda=risk_lambda,
                        source="rescue_scan",
                    )
                    score = float(decision.score)
                    if candidate.name == "release_candidate":
                        stats["accepted_release"] += 1
                        if score > best_release_score:
                            best_release_score = score
                            best_release = decision
                            stats["incumbent_updates"] += 1
                    else:
                        stats["accepted_settled"] += 1
                        if score > best_settled_score:
                            best_settled_score = score
                            best_settled = decision
                            stats["incumbent_updates"] += 1
                if not exhausted:
                    next_states.append(state)
            states = next_states

        decision = best_settled or best_release
        if decision is not None:
            stats["selected_kind"] = decision.candidate.name
            selected_pool_index = int(decision.action["item_idx"])
            if 0 <= selected_pool_index < len(
                observation.get("pool_list", [])
            ):
                stats["selected_item_index"] = int(
                    observation["pool_list"][selected_pool_index].get(
                        "index", selected_pool_index
                    )
                )
        if diagnostics is not None:
            search = diagnostics.setdefault("search", {})
            for key in (
                "item_indices_started",
                "item_indices_with_candidates",
            ):
                merged = search.setdefault(key, [])
                for item_index in stats[key]:
                    if item_index not in merged:
                        merged.append(item_index)
        return decision

    @staticmethod
    def top_candidates(
        observation,
        indexed_items,
        k,
        deadline=None,
        diagnostics=None,
        risk_lambda=None,
        candidate_observer=None,
        attempt_budget=None,
        selector=None,
        structured_evaluation=False,
        retained_evaluation=False,
    ):
        """
        Same search as choose(), but keeps the best k decisions (a bounded
        min-heap) instead of only the single best. Used by the closed-loop
        lookahead in Agent.policy() to consider more than one immediate
        action before committing.
        """
        containers = observation.get("container_list", [])
        if not containers or k <= 0:
            return []

        has_priority_container = any(
            bool(container.get("is_prioritized", False))
            for container in containers
        )
        if selector is None and not structured_evaluation:
            settled_heap = []
            release_heap = []
            counter = 0
            for (
                item_idx,
                item,
                container_idx,
                orientation,
                candidate,
            ) in iter_prioritized_candidates(
                observation,
                indexed_items,
                deadline=deadline,
                diagnostics=diagnostics,
                interleave=LIVE_SEARCH_INTERLEAVE,
                attempt_budget=effective_attempt_budget(attempt_budget),
            ):
                container = containers[container_idx]
                score = Ranker.score(
                    candidate,
                    item,
                    container,
                    has_priority_container,
                )
                score, _risk_probability = risk_adjusted_score(
                    score,
                    candidate,
                    item,
                    container,
                    orientation,
                    risk_lambda,
                )
                decision = PlacementDecision(
                    action={
                        "item_idx": int(item_idx),
                        "container_idx": int(container_idx),
                        "place_pos": np.asarray(
                            simulator_action_center(candidate, container),
                            dtype=np.float32,
                        ),
                        "orientation": int(orientation),
                    },
                    candidate=candidate,
                    score=float(score),
                )
                if candidate_observer is not None:
                    candidate_observer(
                        item_idx,
                        item,
                        container_idx,
                        orientation,
                        decision,
                    )
                counter += 1
                entry = (score, counter, decision)
                heap = (
                    release_heap
                    if candidate.name == "release_candidate"
                    else settled_heap
                )
                updated = False
                if len(heap) < k:
                    heapq.heappush(heap, entry)
                    updated = True
                elif score > heap[0][0]:
                    heapq.heapreplace(heap, entry)
                    updated = True
                if updated and diagnostics is not None:
                    diagnostics["search"]["incumbent_updates"] += 1
            selected = [
                decision
                for _, _, decision in sorted(
                    settled_heap or release_heap,
                    key=lambda entry: entry[0],
                    reverse=True,
                )
            ]
            if retained_evaluation:
                return [
                    enrich_retained_decision(
                        decision,
                        observation,
                        has_priority_container,
                        risk_lambda=risk_lambda,
                        source="placement_core_top_k_retained",
                    )
                    for decision in selected
                ]
            return selected

        active_selector = selector or TopKSettledFirstSelector(k)
        use_structured_evaluation = bool(
            structured_evaluation or selector is not None
        )

        for (
            item_idx,
            item,
            container_idx,
            orientation,
            candidate,
        ) in iter_prioritized_candidates(
            observation,
            indexed_items,
            deadline=deadline,
            diagnostics=diagnostics,
            interleave=LIVE_SEARCH_INTERLEAVE,
            attempt_budget=effective_attempt_budget(attempt_budget),
        ):
            container = containers[container_idx]
            decision = make_placement_decision(
                item_idx,
                item,
                container_idx,
                container,
                orientation,
                candidate,
                has_priority_container=has_priority_container,
                risk_lambda=risk_lambda,
                source="placement_core_top_k",
                structured=use_structured_evaluation,
            )
            score = float(decision.score)
            if candidate_observer is not None:
                candidate_observer(
                    item_idx,
                    item,
                    container_idx,
                    orientation,
                    decision,
                )
            updated = bool(active_selector.observe(decision))
            if updated and diagnostics is not None:
                diagnostics["search"]["incumbent_updates"] += 1
        selected = active_selector.select()
        if retained_evaluation:
            return [
                enrich_retained_decision(
                    decision,
                    observation,
                    has_priority_container,
                    risk_lambda=risk_lambda,
                    source="placement_core_top_k_retained",
                )
                for decision in selected
            ]
        return selected


def normalized_lookahead_mode(mode):
    normalized = str(mode).strip().lower()
    if normalized not in LOOKAHEAD_SELECTION_MODES:
        available = ", ".join(sorted(LOOKAHEAD_SELECTION_MODES))
        raise ValueError(
            f"unknown lookahead selection mode '{mode}'; available: {available}"
        )
    return normalized


def lookahead_rank_key(
    evaluation,
    mode=LOOKAHEAD_SELECTION_MODE,
    discount=LOOKAHEAD_DISCOUNT,
):
    mode = normalized_lookahead_mode(mode)
    immediate_score = float(evaluation.decision.score)
    best_next_score = float(evaluation.best_next_score)
    has_feasible_next = (
        evaluation.total_next_items == 0
        or evaluation.feasible_next_items > 0
    )

    if mode == "weighted":
        return (immediate_score + float(discount) * best_next_score,)
    if mode == "depth2":
        return (
            int(has_feasible_next),
            best_next_score,
            immediate_score,
        )
    return (
        int(evaluation.feasible_next_items),
        best_next_score,
        immediate_score,
    )


def evaluate_visible_pool_feasibility(
    observation,
    indexed_items,
    deadline=None,
):
    feasible_items = 0
    best_score = -float("inf")
    evaluated_items = 0
    for indexed_item in indexed_items:
        if deadline is not None and time.perf_counter() >= deadline:
            return None
        next_decision = PlacementCore.choose(
            observation,
            [indexed_item],
            deadline=deadline,
        )
        evaluated_items += 1
        if next_decision is None:
            continue
        feasible_items += 1
        best_score = max(best_score, float(next_decision.score))

    if feasible_items == 0:
        best_score = 0.0
    return VisiblePoolFeasibility(
        feasible_items=feasible_items,
        evaluated_items=evaluated_items,
        best_score=best_score,
    )


def effective_container_volume(container):
    if container.get("volume") is not None:
        return max(EPS, float(container["volume"]))

    length = float(container["length"])
    width = float(container["width"])
    height = float(container["height"])
    thickness = float(container["thickness"])
    buffer = float(container.get("buffer", 0.0))
    cut_x = float(container.get("cut_x", 0.0))
    cut_y = float(container.get("cut_y", 0.0))
    inner_length = length - 2.0 * thickness
    inner_width = width - 2.0 * thickness
    inner_height = height - thickness - buffer
    base_volume = inner_length * inner_width * inner_height
    cut_volume = (
        0.5
        * max(0.0, cut_x - thickness)
        * max(0.0, cut_y - thickness)
        * inner_width
    )
    small_shelf_volume = cut_x * thickness * inner_width
    shelf_volume = 0.0
    if container_requires_shelf(container):
        shelf_width = width / 2.0 - 2.0 * thickness
        shelf_volume = inner_length * thickness * max(0.0, shelf_width)
    return max(
        EPS,
        base_volume - cut_volume - small_shelf_volume - shelf_volume,
    )


def apply_placement_decision(item, decision, containers):
    action = decision.action
    container_idx = int(action["container_idx"])
    container = containers[container_idx]
    predicted_settled = settled_proxy_candidate(
        decision.candidate,
        container,
    )
    metrics = Geometry.support_metrics(predicted_settled, container, item)

    packed = copy.deepcopy(item)
    packed["pos"] = local_to_world(
        predicted_settled.center, container
    ).tolist()
    packed["orientation"] = int(action["orientation"])
    packed["belongs_to"] = container_idx
    container.setdefault("packed_items", []).append(packed)

    return PlacementTrace(
        item_index=int(item["index"]),
        container_idx=container_idx,
        orientation=int(action["orientation"]),
        candidate=predicted_settled,
        support=metrics,
        mass=max(EPS, float(item.get("mass", 1.0))),
    )


def _rollout_candidate_key(candidate, item, container, score):
    """Proxy-policy key deliberately independent of the live Ranker."""
    predicted = settled_proxy_candidate(candidate, container)
    support = Geometry.support_metrics(predicted, container, item)
    volume = math.prod(float(value) for value in candidate.size)
    return (
        int(candidate.name != "release_candidate"),
        float(support.ratio),
        -float(predicted.center[2]),
        float(volume),
        float(score),
    )


def bounded_rollout_decision(
    observation,
    indexed_items,
    attempt_budget,
    risk_lambda=None,
    stride=1,
    stride_offset=0,
    structured_evaluation=False,
):
    """
    Select one proxy-rollout transition under an anchor-attempt budget.

    Unlike the live Ranker, the proxy policy first prefers settled support,
    then support quality and low height.  Q_live is only the final stable
    tie-break, so the rollout does not recursively reproduce the utility it
    is intended to diagnose.

    ``stride`` spreads the same ``attempt_budget`` across the whole anchor
    grid instead of its prefix.  Late in an episode the prefix is dense with
    anchors the packed geometry already rejects, so the budget can be spent
    without reaching the region where a future placement still fits.
    """
    best = None
    best_key = None
    diagnostics = {}
    accepted = 0
    containers = observation.get("container_list", [])
    has_priority_container = any(
        bool(container.get("is_prioritized", False))
        for container in containers
    )
    for item_idx, item, container_idx, orientation, candidate in (
        iter_prioritized_candidates(
            observation,
            indexed_items,
            diagnostics=diagnostics,
            attempt_budget=max(0, int(attempt_budget)),
            stride=stride,
            stride_offset=stride_offset,
        )
    ):
        accepted += 1
        container = containers[container_idx]
        decision = make_placement_decision(
            item_idx,
            item,
            container_idx,
            container,
            orientation,
            candidate,
            has_priority_container=has_priority_container,
            risk_lambda=risk_lambda,
            source="bounded_rollout",
            structured=structured_evaluation,
        )
        score = float(decision.score)
        key = _rollout_candidate_key(candidate, item, container, score)
        if best_key is None or key > best_key:
            best_key = key
            best = decision
    search = diagnostics.get("search", {})
    attempts_before = int(search.get("attempts_consumed", 0))
    return best, attempts_before, accepted


def visible_pool_rollout_value(
    observation,
    indexed_items,
    initial_decision,
    depth=3,
    attempts_per_step=512,
    risk_lambda=None,
    stride=1,
    stride_offset=0,
):
    """
    Evaluate a candidate with a bounded visible-pool static rollout.

    The commanded initial release is converted through the existing settled
    proxy and explicitly marked.  A later release transition is not applied:
    without PyBullet its next state is uncertain, so the branch terminates.

    ``stride`` applies to the future transitions only.  The immediate
    candidate is supplied by the caller and is never resampled, so the
    stride cannot change which action is being evaluated - only how widely
    its consequences are searched.
    """
    pool_list = observation.get("pool_list", [])
    initial_pool_idx = int(initial_decision.action["item_idx"])
    if not (0 <= initial_pool_idx < len(pool_list)):
        raise IndexError("initial decision item_idx is outside the pool")

    containers = copy.deepcopy(observation.get("container_list", []))
    initial_item = pool_list[initial_pool_idx]
    initial_release_proxy = (
        initial_decision.candidate.name == "release_candidate"
    )
    apply_placement_decision(initial_item, initial_decision, containers)
    remaining = [
        (idx, item)
        for idx, item in indexed_items
        if int(idx) != initial_pool_idx
    ]
    placed_count = 0
    added_volume = 0.0
    cumulative_rotation_risk = 0.0
    cumulative_slide_risk = 0.0
    attempts_used = 0
    accepted_candidates = 0
    release_truncated = False
    terminal_reason = "depth_reached"
    trace = []

    for rollout_step in range(max(0, int(depth) - 1)):
        if not remaining:
            terminal_reason = "pool_exhausted"
            break
        sim_observation = {
            "pool_list": pool_list,
            "container_list": containers,
        }
        decision, step_attempts, step_accepted = bounded_rollout_decision(
            sim_observation,
            remaining,
            attempts_per_step,
            risk_lambda=risk_lambda,
            stride=stride,
            stride_offset=stride_offset,
        )
        attempts_used += int(step_attempts)
        accepted_candidates += int(step_accepted)
        if decision is None:
            terminal_reason = "no_candidate"
            break
        item_idx = int(decision.action["item_idx"])
        item = pool_list[item_idx]
        if decision.candidate.name == "release_candidate":
            container = containers[int(decision.action["container_idx"])]
            rotation_probability = release_rotation_risk_probability_mech(
                float(decision.candidate.center[0]),
                float(decision.candidate.center[1]),
                float(decision.candidate.center[2]),
                tuple(float(v) for v in decision.candidate.size),
                container,
            )
            slide_probability = release_large_slide_probability(
                decision.candidate,
                item,
                container,
                int(decision.action["orientation"]),
            )
            cumulative_rotation_risk += float(rotation_probability)
            cumulative_slide_risk += float(slide_probability)
            release_truncated = True
            terminal_reason = "release_transition_uncertain"
            trace.append(
                {
                    "step": int(rollout_step + 1),
                    "item_index": int(item.get("index", item_idx)),
                    "kind": "release_candidate",
                    "applied": False,
                    "rotation_risk": float(rotation_probability),
                    "slide_risk": float(slide_probability),
                }
            )
            break
        apply_placement_decision(item, decision, containers)
        placed_count += 1
        volume = float(
            item["length"] * item["width"] * item["height"]
        )
        added_volume += volume
        trace.append(
            {
                "step": int(rollout_step + 1),
                "item_index": int(item.get("index", item_idx)),
                "kind": str(decision.candidate.name),
                "applied": True,
                "volume": volume,
            }
        )
        remaining = [
            (idx, remaining_item)
            for idx, remaining_item in remaining
            if int(idx) != item_idx
        ]

    return VisiblePoolRolloutValue(
        placed_count=int(placed_count),
        added_volume=float(added_volume),
        cumulative_rotation_risk=float(cumulative_rotation_risk),
        cumulative_slide_risk=float(cumulative_slide_risk),
        attempts_used=int(attempts_used),
        accepted_candidates=int(accepted_candidates),
        initial_release_proxy=bool(initial_release_proxy),
        release_truncated=bool(release_truncated),
        terminal_reason=str(terminal_reason),
        trace=tuple(trace),
    )


def build_temporal_chunk_proposals(
    observation,
    indexed_items,
    initial_decision,
    *,
    origin_step,
    depth=TEMPORAL_CHUNK_DEPTH,
    attempts_per_step=TEMPORAL_CHUNK_ATTEMPTS_PER_STEP,
    risk_lambda=None,
    stride=TEMPORAL_CHUNK_STRIDE,
    stride_offset=0,
):
    """Predict future commands without executing them on the live state.

    The selected live action is applied only to a deep-copied static state.
    Each later settled transition extends that proxy state.  A release
    transition is retained as a future proposal but terminates the chunk,
    because its post-settle state is not known without physics.
    """
    started = time.perf_counter()
    pool_list = observation.get("pool_list", [])
    initial_pool_idx = int(initial_decision.action["item_idx"])
    if not (0 <= initial_pool_idx < len(pool_list)):
        raise IndexError("initial decision item_idx is outside the pool")

    containers = copy.deepcopy(observation.get("container_list", []))
    initial_item = pool_list[initial_pool_idx]
    apply_placement_decision(initial_item, initial_decision, containers)
    remaining = [
        (idx, item)
        for idx, item in indexed_items
        if int(idx) != initial_pool_idx
    ]
    proposals = []
    attempts_used = 0
    accepted_candidates = 0
    terminal_reason = "depth_reached"

    for offset in range(1, max(1, int(depth))):
        if not remaining:
            terminal_reason = "pool_exhausted"
            break
        sim_observation = {
            "pool_list": pool_list,
            "container_list": containers,
        }
        decision, step_attempts, step_accepted = bounded_rollout_decision(
            sim_observation,
            remaining,
            attempts_per_step,
            risk_lambda=risk_lambda,
            stride=stride,
            stride_offset=stride_offset,
        )
        attempts_used += int(step_attempts)
        accepted_candidates += int(step_accepted)
        if decision is None:
            terminal_reason = "no_candidate"
            break

        item_idx = int(decision.action["item_idx"])
        item = pool_list[item_idx]
        proposals.append(
            TemporalChunkProposal(
                origin_step=int(origin_step),
                target_step=int(origin_step) + int(offset),
                item_index=int(item.get("index", item_idx)),
                previous_pool_index=item_idx,
                container_index=int(decision.action["container_idx"]),
                orientation=int(decision.action["orientation"]),
                candidate=decision.candidate,
                previous_score=float(decision.score),
            )
        )
        if decision.candidate.name == "release_candidate":
            terminal_reason = "release_transition_uncertain"
            break

        apply_placement_decision(item, decision, containers)
        remaining = [
            (idx, remaining_item)
            for idx, remaining_item in remaining
            if int(idx) != item_idx
        ]

    return {
        "origin_step": int(origin_step),
        "depth": int(depth),
        "attempts_per_step": int(attempts_per_step),
        "stride": int(stride),
        "generated_count": len(proposals),
        "attempts_used": int(attempts_used),
        "accepted_candidates": int(accepted_candidates),
        "terminal_reason": str(terminal_reason),
        "elapsed_seconds": float(time.perf_counter() - started),
    }, proposals


def temporal_chunk_action_key(
    *, item_index, container_index, orientation, candidate, cell_size=None
):
    """Coarse action class used to ensemble nearby delayed predictions."""
    cell_size = float(cell_size or TEMPORAL_CHUNK_CELL_SIZE)
    kind = (
        "release"
        if candidate.name == "release_candidate"
        else "settled"
    )
    return (
        int(item_index),
        int(container_index),
        int(orientation),
        kind,
        int(round(float(candidate.center[0]) / cell_size)),
        int(round(float(candidate.center[1]) / cell_size)),
    )


def temporal_chunk_ensemble_evaluation(
    observation,
    proposals,
    selected_decision,
    *,
    current_step,
    deadline=None,
    risk_lambda=None,
    cell_size=TEMPORAL_CHUNK_CELL_SIZE,
):
    """Revalidate due delayed proposals and measure temporal agreement."""
    due = [
        proposal
        for proposal in proposals
        if int(proposal.target_step) == int(current_step)
    ]
    base, valid_decisions = revalidate_cross_step_candidates(
        observation,
        due,
        deadline=deadline,
        risk_lambda=risk_lambda,
    )
    candidate_records = base.get("candidates", [])
    scheduled_by_delay = {}
    for proposal in due:
        delay_key = str(int(current_step) - int(proposal.origin_step))
        scheduled_by_delay[delay_key] = (
            scheduled_by_delay.get(delay_key, 0) + 1
        )
    valid_pairs = [
        (proposal, record)
        for proposal, record in zip(due, candidate_records)
        if record.get("valid") is True
    ]

    groups = {}
    valid_by_delay = {}
    for proposal, record in valid_pairs:
        delay = int(current_step) - int(proposal.origin_step)
        valid_by_delay[str(delay)] = valid_by_delay.get(str(delay), 0) + 1
        key = temporal_chunk_action_key(
            item_index=proposal.item_index,
            container_index=proposal.container_index,
            orientation=proposal.orientation,
            candidate=proposal.candidate,
            cell_size=cell_size,
        )
        group = groups.setdefault(
            key,
            {
                "key": list(key),
                "vote_count": 0,
                "origin_steps": [],
                "delays": [],
                "best_previous_score": -float("inf"),
            },
        )
        group["vote_count"] += 1
        group["origin_steps"].append(int(proposal.origin_step))
        group["delays"].append(delay)
        group["best_previous_score"] = max(
            float(group["best_previous_score"]),
            float(proposal.previous_score),
        )
        record["origin_step"] = int(proposal.origin_step)
        record["target_step"] = int(proposal.target_step)
        record["delay"] = delay
        record["action_group"] = list(key)

    ordered_groups = sorted(
        groups.values(),
        key=lambda group: (
            int(group["vote_count"]),
            float(group["best_previous_score"]),
            tuple(group["key"]),
        ),
        reverse=True,
    )
    consensus = ordered_groups[0] if ordered_groups else None

    item_groups = {}
    for proposal, _record in valid_pairs:
        item_group = item_groups.setdefault(
            int(proposal.item_index),
            {
                "item_index": int(proposal.item_index),
                "vote_count": 0,
                "origin_steps": [],
                "delays": [],
                "best_previous_score": -float("inf"),
            },
        )
        item_group["vote_count"] += 1
        item_group["origin_steps"].append(int(proposal.origin_step))
        item_group["delays"].append(
            int(current_step) - int(proposal.origin_step)
        )
        item_group["best_previous_score"] = max(
            float(item_group["best_previous_score"]),
            float(proposal.previous_score),
        )
    ordered_item_groups = sorted(
        item_groups.values(),
        key=lambda group: (
            int(group["vote_count"]),
            float(group["best_previous_score"]),
            int(group["item_index"]),
        ),
        reverse=True,
    )
    item_consensus = ordered_item_groups[0] if ordered_item_groups else None

    selected_key = None
    selected_item_index = None
    pool_list = observation.get("pool_list", [])
    if selected_decision is not None:
        selected_pool_index = int(selected_decision.action["item_idx"])
        if 0 <= selected_pool_index < len(pool_list):
            selected_item_index = int(
                pool_list[selected_pool_index].get(
                    "index", selected_pool_index
                )
            )
            selected_key = temporal_chunk_action_key(
                item_index=selected_item_index,
                container_index=int(
                    selected_decision.action["container_idx"]
                ),
                orientation=int(selected_decision.action["orientation"]),
                candidate=selected_decision.candidate,
                cell_size=cell_size,
            )

    base.update(
        {
            "mode": "shadow",
            "current_step": int(current_step),
            "scheduled_count": len(due),
            "origin_count": len(
                {proposal.origin_step for proposal in due}
            ),
            "valid_origin_count": len(
                {proposal.origin_step for proposal, _record in valid_pairs}
            ),
            "scheduled_by_delay": scheduled_by_delay,
            "valid_by_delay": valid_by_delay,
            "action_group_count": len(ordered_groups),
            "max_vote_count": (
                0 if consensus is None else int(consensus["vote_count"])
            ),
            "consensus": consensus,
            "selected_action_group": (
                None if selected_key is None else list(selected_key)
            ),
            "selected_matches_consensus": bool(
                selected_key is not None
                and consensus is not None
                and tuple(consensus["key"]) == tuple(selected_key)
            ),
            "selected_matches_any_valid_action": bool(
                selected_key is not None and selected_key in groups
            ),
            "selected_matches_any_valid_item": bool(
                selected_item_index is not None
                and selected_item_index in item_groups
            ),
            "item_group_count": len(ordered_item_groups),
            "max_item_vote_count": (
                0
                if item_consensus is None
                else int(item_consensus["vote_count"])
            ),
            "item_consensus": item_consensus,
            "selected_matches_item_consensus": bool(
                selected_item_index is not None
                and item_consensus is not None
                and int(item_consensus["item_index"])
                == int(selected_item_index)
            ),
            "would_prevent_protocol_fallback": bool(
                selected_decision is None and valid_decisions
            ),
            "action_groups": ordered_groups,
            "item_groups": ordered_item_groups,
        }
    )
    return base, valid_decisions


def visible_pool_rollout_rank_key(value):
    return (
        int(value.placed_count),
        float(value.added_volume),
        -float(value.cumulative_rotation_risk),
        -float(value.cumulative_slide_risk),
    )


def _rollout_action_record(decision, pool_list, value):
    pool_index = int(decision.action["item_idx"])
    item_index = None
    if 0 <= pool_index < len(pool_list):
        item_index = int(pool_list[pool_index].get("index", pool_index))
    return {
        "pool_index": pool_index,
        "item_index": item_index,
        "container_index": int(decision.action["container_idx"]),
        "orientation": int(decision.action["orientation"]),
        "kind": str(decision.candidate.name or "candidate"),
        "q_live": float(decision.score),
        "rollout_key": list(visible_pool_rollout_rank_key(value)),
        "value": {
            **dataclass_to_dict(value),
            "trace": list(value.trace),
        },
    }


def dataclass_to_dict(value):
    """Small local serializer that keeps submission dependencies minimal."""
    return {
        field_name: getattr(value, field_name)
        for field_name in value.__dataclass_fields__
        if field_name != "trace"
    }


def visible_pool_rollout_evaluation(
    observation,
    indexed_items,
    candidates,
    selected_decision,
    *,
    depth=VISIBLE_POOL_ROLLOUT_DEPTH,
    attempts_per_step=VISIBLE_POOL_ROLLOUT_ATTEMPTS,
    q_band=VISIBLE_POOL_ROLLOUT_Q_BAND,
    risk_lambda=None,
    stride=VISIBLE_POOL_ROLLOUT_STRIDE,
    stride_offset=0,
):
    """Evaluate a class-diverse live Top-K and return record + proposal."""
    global _CONTAINER_Z_INTERVAL_CACHE_BYPASS
    started = time.perf_counter()
    pool_list = observation.get("pool_list", [])
    unique = []
    seen = set()
    selected_key = (
        int(selected_decision.action["item_idx"]),
        int(selected_decision.action["container_idx"]),
        int(selected_decision.action["orientation"]),
        tuple(
            round(float(v), 6)
            for v in selected_decision.candidate.center
        ),
        tuple(
            round(float(v), 6)
            for v in selected_decision.candidate.size
        ),
    )
    for decision in candidates:
        if decision is None:
            continue
        key = (
            int(decision.action["item_idx"]),
            int(decision.action["container_idx"]),
            int(decision.action["orientation"]),
            tuple(round(float(v), 6) for v in decision.candidate.center),
            tuple(round(float(v), 6) for v in decision.candidate.size),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(decision)
        if len(unique) >= int(VISIBLE_POOL_ROLLOUT_TOP_K):
            break
    if selected_key not in seen:
        if len(unique) >= int(VISIBLE_POOL_ROLLOUT_TOP_K):
            unique[-1] = selected_decision
        else:
            unique.append(selected_decision)

    evaluated = []
    previous_cache_bypass = _CONTAINER_Z_INTERVAL_CACHE_BYPASS
    _CONTAINER_Z_INTERVAL_CACHE_BYPASS = True
    try:
        for decision in unique:
            value = visible_pool_rollout_value(
                observation,
                indexed_items,
                decision,
                depth=depth,
                attempts_per_step=attempts_per_step,
                risk_lambda=risk_lambda,
                stride=stride,
                stride_offset=stride_offset,
            )
            evaluated.append(
                (
                    decision,
                    _rollout_action_record(decision, pool_list, value),
                )
            )
    finally:
        _CONTAINER_Z_INTERVAL_CACHE_BYPASS = previous_cache_bypass

    selected_score = float(selected_decision.score)
    for _decision, record in evaluated:
        record["q_delta_from_selected"] = float(
            record["q_live"] - selected_score
        )
        record["q_loss_from_selected"] = float(
            selected_score - record["q_live"]
        )
        record["within_q_band"] = bool(
            record["q_live"] >= selected_score - float(q_band)
        )
    eligible = [pair for pair in evaluated if pair[1]["within_q_band"]]
    unrestricted = max(
        evaluated,
        key=lambda pair: (
            tuple(pair[1]["rollout_key"]), pair[1]["q_live"]
        ),
        default=None,
    )
    proposed_pair = max(
        eligible,
        key=lambda pair: (
            tuple(pair[1]["rollout_key"]), pair[1]["q_live"]
        ),
        default=None,
    )
    proposed_decision = None if proposed_pair is None else proposed_pair[0]
    proposed = None if proposed_pair is None else proposed_pair[1]
    unrestricted_record = None if unrestricted is None else unrestricted[1]
    selected_pool_index = int(selected_decision.action["item_idx"])
    selected_pair = next(
        (
            pair
            for pair in evaluated
            if (
                int(pair[0].action["item_idx"]),
                int(pair[0].action["container_idx"]),
                int(pair[0].action["orientation"]),
                tuple(round(float(v), 6) for v in pair[0].candidate.center),
                tuple(round(float(v), 6) for v in pair[0].candidate.size),
            )
            == selected_key
        ),
        None,
    )
    selected_record = None if selected_pair is None else selected_pair[1]
    rollout_keys = {
        tuple(candidate_record["rollout_key"])
        for _decision, candidate_record in evaluated
    }
    record = {
        "mode": str(VISIBLE_POOL_ROLLOUT_MODE),
        "depth": int(depth),
        "attempts_per_step": int(attempts_per_step),
        "stride": int(stride),
        "q_band": float(q_band),
        "risk_scope": "future_transitions_only",
        "candidate_count": len(evaluated),
        "eligible_count": len(eligible),
        "non_degenerate": len(rollout_keys) > 1,
        "proposal_improves_rollout": bool(
            proposed is not None
            and selected_record is not None
            and tuple(proposed["rollout_key"])
            > tuple(selected_record["rollout_key"])
        ),
        "selected_pool_index": selected_pool_index,
        "proposed_pool_index": (
            None if proposed is None else int(proposed["pool_index"])
        ),
        "would_change_item": bool(
            proposed is not None
            and int(proposed["pool_index"]) != selected_pool_index
        ),
        "would_change_action": bool(
            proposed_decision is not None
            and proposed_decision is not selected_decision
        ),
        "unrestricted_proposed_pool_index": (
            None
            if unrestricted_record is None
            else int(unrestricted_record["pool_index"])
        ),
        "unrestricted_proposed_q_delta": (
            None
            if unrestricted_record is None
            else float(unrestricted_record["q_delta_from_selected"])
        ),
        "unrestricted_proposed_q_loss": (
            None
            if unrestricted_record is None
            else float(unrestricted_record["q_loss_from_selected"])
        ),
        "unrestricted_proposal_within_q_band": bool(
            unrestricted_record is not None
            and unrestricted_record["within_q_band"]
        ),
        "unrestricted_would_change_item": bool(
            unrestricted_record is not None
            and int(unrestricted_record["pool_index"])
            != selected_pool_index
        ),
        "elapsed_seconds": float(time.perf_counter() - started),
        "candidates": [record for _decision, record in evaluated],
    }
    return record, proposed_decision


def visible_pool_rollout_shadow_record(*args, **kwargs):
    """Compatibility seam for telemetry-only callers and unit tests."""
    record, _proposed = visible_pool_rollout_evaluation(*args, **kwargs)
    return record


def replay_placement_trace(ordered_items, container_templates, deadline=None):
    containers = [
        normalize_container(container) for container in container_templates
    ]
    trace = []
    for item in ordered_items:
        if deadline is not None and time.perf_counter() >= deadline:
            break
        observation = {
            "pool_list": [item],
            "container_list": containers,
        }
        decision = PlacementCore.choose(
            observation,
            [(0, item)],
            deadline=deadline,
        )
        if decision is None:
            break
        trace.append(apply_placement_decision(item, decision, containers))
    return trace


def _pair_template_from_records(first, second, first_item, second_item):
    """
    Shared math for turning two adjacent PlacementTrace records (in the
    order they were actually executed) into a BlockTemplate. Used both for
    the trace's natural order and for a DPOR-generated alternate order.
    """
    boxes = (first.candidate, second.candidate)
    minimum = np.minimum(boxes[0].minimum, boxes[1].minimum)
    maximum = np.maximum(boxes[0].maximum, boxes[1].maximum)
    dimensions = tuple(float(value) for value in maximum - minimum)
    envelope_volume = max(EPS, math.prod(dimensions))
    item_volume = sum(
        float(item["length"])
        * float(item["width"])
        * float(item["height"])
        for item in (first_item, second_item)
    )
    total_mass = first.mass + second.mass
    center_of_mass = (
        first.mass * np.asarray(first.candidate.center, dtype=np.float64)
        + second.mass
        * np.asarray(second.candidate.center, dtype=np.float64)
    ) / max(EPS, total_mass)

    relative_placements = tuple(
        (
            record.item_index,
            record.container_idx,
            tuple(
                float(value)
                for value in (
                    np.asarray(record.candidate.center)
                    - minimum
                )
            ),
            record.orientation,
        )
        for record in (first, second)
    )
    top_profile = tuple(
        (
            float(box.minimum[0] - minimum[0]),
            float(box.maximum[0] - minimum[0]),
            float(box.minimum[1] - minimum[1]),
            float(box.maximum[1] - minimum[1]),
            float(box.top - minimum[2]),
        )
        for box in boxes
    )
    signature = BlockSignature(
        fill_ratio=min(1.0, item_volume / envelope_volume),
        top_profile=top_profile,
        min_support_ratio=min(
            first.support.ratio, second.support.ratio
        ),
        total_mass=total_mass,
        center_of_mass=tuple(
            float(value) for value in center_of_mass - minimum
        ),
    )
    return BlockTemplate(
        item_indices=(first.item_index, second.item_index),
        internal_order=(first.item_index, second.item_index),
        relative_placements=relative_placements,
        dimensions=dimensions,
        signature=signature,
    )


def records_are_support_independent(first, second):
    """
    Sufficient (not necessary) DPOR condition: neither placed box rests on
    top of the other. If that holds, neither placement used the other as a
    support surface, so swapping which one was placed first cannot remove a
    support relationship either order depends on -- the two actions
    commute in the sense of dynamic partial-order reduction (Flanagan &
    Godefroid). When it does NOT hold (one is stacked on the other), the
    original execution order is kept as the only candidate, since trying
    the reverse would place the top item into empty space with no support.
    """
    first_box = first.candidate
    second_box = second.candidate
    second_rests_on_first = (
        abs(float(second_box.minimum[2]) - first_box.top) <= CONTACT_TOLERANCE
    )
    first_rests_on_second = (
        abs(float(first_box.minimum[2]) - second_box.top) <= CONTACT_TOLERANCE
    )
    return not second_rests_on_first and not first_rests_on_second


def containers_after_prefix(container_templates, trace_prefix, items_by_index):
    """
    Cheaply reconstruct container state after replaying a known prefix of a
    trace, without re-running PlacementCore (positions are already known).
    """
    containers = [
        normalize_container(container) for container in container_templates
    ]
    for record in trace_prefix:
        item = items_by_index.get(record.item_index)
        if item is None:
            continue
        container = containers[record.container_idx]
        packed = copy.deepcopy(item)
        packed["pos"] = local_to_world(
            record.candidate.center, container
        ).tolist()
        packed["orientation"] = int(record.orientation)
        packed["belongs_to"] = record.container_idx
        container.setdefault("packed_items", []).append(packed)
    return containers


def alternate_order_records(
    items_by_index,
    container_templates,
    trace,
    index,
    deadline=None,
):
    """
    DPOR pricing step: actually replay the reverse order (second_item then
    first_item) from the true pre-pair state, using the same PlacementCore
    used everywhere else, instead of guessing at swapped coordinates. Returns
    None if either placement is infeasible in the reversed order.
    """
    first = trace[index]
    second = trace[index + 1]
    first_item = items_by_index.get(first.item_index)
    second_item = items_by_index.get(second.item_index)
    if first_item is None or second_item is None:
        return None

    containers = containers_after_prefix(
        container_templates, trace[:index], items_by_index
    )

    observation_1 = {"pool_list": [second_item], "container_list": containers}
    decision_1 = PlacementCore.choose(
        observation_1, [(0, second_item)], deadline=deadline
    )
    if decision_1 is None:
        return None
    record_1 = apply_placement_decision(second_item, decision_1, containers)

    observation_2 = {"pool_list": [first_item], "container_list": containers}
    decision_2 = PlacementCore.choose(
        observation_2, [(0, first_item)], deadline=deadline
    )
    if decision_2 is None:
        return None
    record_2 = apply_placement_decision(first_item, decision_2, containers)

    return record_1, record_2


def block_templates_from_trace(
    ordered_items,
    trace,
    container_templates=None,
    max_templates=8,
    deadline=None,
):
    items_by_index = {
        int(item["index"]): item for item in ordered_items
    }
    templates = []
    dpor_attempts = 0
    for index, (first, second) in enumerate(zip(trace, trace[1:])):
        if first.container_idx != second.container_idx:
            continue
        first_item = items_by_index.get(first.item_index)
        second_item = items_by_index.get(second.item_index)
        if first_item is None or second_item is None:
            continue
        if item_group(first_item) != item_group(second_item):
            continue

        templates.append(
            _pair_template_from_records(first, second, first_item, second_item)
        )

        # DPOR: only pay for an alternate-order dry run when the pair is
        # provably order-independent, and only while there is search budget
        # and an attempt allowance left. Dependent pairs (one physically
        # supports the other) keep the single witnessed order, matching the
        # theory's "static sufficient condition, else keep fixed order".
        if (
            container_templates is not None
            and dpor_attempts < DPOR_MAX_ALTERNATE_ATTEMPTS
            and (deadline is None or time.perf_counter() < deadline)
            and records_are_support_independent(first, second)
        ):
            dpor_attempts += 1
            alternate = alternate_order_records(
                items_by_index,
                container_templates,
                trace,
                index,
                deadline=deadline,
            )
            if alternate is not None:
                alt_first, alt_second = alternate
                templates.append(
                    _pair_template_from_records(
                        alt_first, alt_second, second_item, first_item
                    )
                )

    templates.sort(
        key=lambda template: (
            template.signature.min_support_ratio,
            template.signature.fill_ratio,
            -template.dimensions[2],
            tuple(-index for index in template.item_indices),
        ),
        reverse=True,
    )
    return templates[:max(0, int(max_templates))]


def generate_pair_block_templates(
    ordered_items,
    container_templates,
    max_templates=8,
    deadline=None,
):
    trace = replay_placement_trace(
        ordered_items,
        container_templates,
        deadline=deadline,
    )
    return block_templates_from_trace(
        ordered_items,
        trace,
        container_templates=container_templates,
        max_templates=max_templates,
        deadline=deadline,
    )


def apply_block_template_neighbor(items, template, target_position):
    positions = {
        int(item["index"]): position
        for position, item in enumerate(items)
    }
    if any(index not in positions for index in template.internal_order):
        return list(items)

    target_position = max(0, min(int(target_position), len(items)))
    selected = set(template.item_indices)
    removed_before_target = sum(
        1
        for index in selected
        if positions.get(index, len(items)) < target_position
    )
    insertion = max(
        0,
        min(
            target_position - removed_before_target,
            len(items) - len(selected),
        ),
    )
    remaining = [
        item for item in items if int(item["index"]) not in selected
    ]
    by_index = {int(item["index"]): item for item in items}
    block_items = [
        by_index[index] for index in template.internal_order
    ]
    return remaining[:insertion] + block_items + remaining[insertion:]


class DryRunEvaluator:
    """Evaluate an offline order by replaying the online placement core."""

    def __init__(
        self,
        container_templates,
        attempts_per_item=OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM,
    ):
        self.container_templates = [
            normalize_container(container) for container in container_templates
        ]
        self._cache = {}
        self.cache_hits = 0
        self.evaluations = 0
        self.last_trace = []
        self.attempts_per_item = max(0, int(attempts_per_item))

    def evaluate(self, ordered_items, deadline=None):
        key = tuple(int(item["index"]) for item in ordered_items)
        cached = self._cache.get(key)
        if cached is not None:
            self.cache_hits += 1
            self.last_trace = []
            return cached

        started = time.perf_counter()
        containers = copy.deepcopy(self.container_templates)
        total_capacity = sum(
            effective_container_volume(container) for container in containers
        )
        placed_volume = 0.0
        weighted_z = 0.0
        weighted_normalized_z = 0.0
        total_mass = 0.0
        support_ratios = []
        support_margins = []
        support_counts = []
        mass_support_ratios = []
        failed_index = None
        timed_out = False
        trace = []

        for item in ordered_items:
            if deadline is not None and time.perf_counter() >= deadline:
                failed_index = int(item["index"])
                timed_out = True
                break

            observation = {
                "pool_list": [item],
                "container_list": containers,
            }
            if self.attempts_per_item > 0:
                decision = PlacementCore.rescue_choose(
                    observation,
                    [(0, item)],
                    deadline=(
                        deadline
                        if deadline is not None
                        else float("inf")
                    ),
                    attempt_budget=self.attempts_per_item,
                )
            else:
                decision = PlacementCore.choose(
                    observation,
                    [(0, item)],
                    deadline=deadline,
                )
            if decision is None:
                failed_index = int(item["index"])
                timed_out = (
                    deadline is not None
                    and time.perf_counter() >= deadline
                )
                break

            record = apply_placement_decision(
                item, decision, containers
            )
            trace.append(record)
            container = containers[record.container_idx]
            support_ratios.append(record.support.ratio)
            support_margins.append(record.support.center_margin)
            support_counts.append(float(record.support.contact_count))
            mass_support_ratios.append(
                record.support.mass_support_ratio
            )

            item_volume = (
                float(item["length"])
                * float(item["width"])
                * float(item["height"])
            )
            mass = record.mass
            z = float(record.candidate.center[2])
            height = max(EPS, float(container["height"]))
            placed_volume += item_volume
            weighted_z += mass * z
            weighted_normalized_z += mass * (z / height)
            total_mass += mass

        placed_count = len(support_ratios)
        mean_support = (
            float(np.mean(support_ratios)) if support_ratios else 0.0
        )
        min_support = min(support_ratios) if support_ratios else 0.0
        min_margin = min(support_margins) if support_margins else -1.0
        mean_margin = (
            float(np.mean(support_margins)) if support_margins else -1.0
        )
        mean_count = (
            float(np.mean(support_counts)) if support_counts else 0.0
        )
        mean_mass_support = (
            float(np.mean(mass_support_ratios))
            if mass_support_ratios
            else 0.0
        )
        stability = (
            0.45 * mean_support
            + 0.20 * min_support
            + 0.20 * ((mean_margin + 1.0) / 2.0)
            + 0.10 * mean_mass_support
            + 0.05 * min(1.0, mean_count / 2.0)
        )
        result = DryRunResult(
            placed_count=placed_count,
            failed_index=failed_index,
            placed_volume=placed_volume,
            fill_ratio=min(1.0, placed_volume / total_capacity),
            stability_proxy=max(0.0, min(1.0, stability)),
            center_of_mass_z=(
                weighted_z / total_mass if total_mass > EPS else 0.0
            ),
            normalized_center_of_mass_z=(
                weighted_normalized_z / total_mass
                if total_mass > EPS
                else 0.0
            ),
            mean_support_ratio=mean_support,
            min_support_ratio=min_support,
            min_support_margin=min_margin,
            mean_support_count=mean_count,
            runtime_seconds=time.perf_counter() - started,
        )
        self.evaluations += 1
        self.last_trace = trace
        if not timed_out:
            self._cache[key] = result
        return result


class Agent:
    def __init__(self, module_path: str):
        self.module_path = module_path
        self._container_templates = []
        self._offline_search_budget_seconds = OFFLINE_SEARCH_BUDGET_SECONDS
        self._offline_max_evaluations = OFFLINE_MAX_EVALUATIONS
        self.last_offline_result = None
        self.last_offline_initial_result = None
        self.last_offline_evaluations = 0
        self.last_offline_cache_hits = 0
        self.last_pair_macro_candidates = 0
        self.last_pair_macro_adoptions = 0
        self.last_lookahead_evaluation = None
        self.last_top_candidate_count = 0
        self.last_top_candidates = []
        self.last_board_features = None
        self.last_candidate_diagnostics = {}
        self.last_action_source = None
        self.last_candidate_kind = None
        self.last_top_candidate_item_indices = []
        self.last_future_probe_item_indices = []
        self._item_lifecycle = {}
        self._policy_step = 0
        self._optimize_enabled = False
        self._lookahead_k = 0
        self._policy_trace_path = os.environ.get("NEDO_POLICY_TRACE_PATH")
        self._cross_step_candidates = []
        self.last_cross_step_valid_decisions = []
        self._temporal_chunk_proposals = []
        self.last_temporal_chunk_valid_decisions = []

    def _append_policy_trace(self, payload):
        if not self._policy_trace_path:
            return
        trace_dir = os.path.dirname(self._policy_trace_path)
        if trace_dir:
            os.makedirs(trace_dir, exist_ok=True)
        with open(self._policy_trace_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    @staticmethod
    def _append_lifecycle_step(record, field, step):
        steps = record[field]
        if not steps or steps[-1] != step:
            steps.append(step)

    def _selection_trace(
        self,
        pool_list,
        ordered_items,
        selected_pool_index,
        action_source,
    ):
        if not self._policy_trace_path:
            return {}, [], {}
        visible_item_indices = [
            int(item.get("index", pool_index))
            for pool_index, item in enumerate(pool_list)
        ]
        item_cap_item_indices = [
            int(item.get("index", pool_index))
            for pool_index, item in ordered_items
        ]
        search = self.last_candidate_diagnostics.get("search", {})
        search_started_item_indices = [
            int(item_index)
            for item_index in search.get("item_indices_started", [])
        ]
        candidate_generated_item_indices = [
            int(item_index)
            for item_index in search.get(
                "item_indices_with_candidates", []
            )
        ]
        candidate_topk_item_indices = list(
            self.last_top_candidate_item_indices
        )
        future_probe_item_indices = list(
            self.last_future_probe_item_indices
        )
        selected_item_index = None
        if (
            selected_pool_index is not None
            and 0 <= selected_pool_index < len(pool_list)
        ):
            selected_item_index = int(
                pool_list[selected_pool_index].get(
                    "index", selected_pool_index
                )
            )

        stages = {
            "visible_item_indices": visible_item_indices,
            "item_cap_item_indices": item_cap_item_indices,
            "search_started_item_indices": search_started_item_indices,
            "candidate_generated_item_indices": (
                candidate_generated_item_indices
            ),
            "candidate_topk_item_indices": candidate_topk_item_indices,
            "future_probe_item_indices": future_probe_item_indices,
        }
        coverage = selection_stage_coverage(pool_list, stages)
        stage_sets = {
            key: set(values)
            for key, values in stages.items()
            if key != "visible_item_indices"
        }

        for pool_index, item in enumerate(pool_list):
            item_index = int(item.get("index", pool_index))
            record = self._item_lifecycle.setdefault(
                item_index,
                {
                    "item_index": item_index,
                    "item_class": item_class_name(item),
                    "first_visible_step": self._policy_step,
                    "visible_steps": [],
                    "search_included_steps": [],
                    "search_started_steps": [],
                    "candidate_generated_steps": [],
                    "candidate_topk_steps": [],
                    "future_probe_steps": [],
                    "selected_step": None,
                    "selected_action_source": None,
                },
            )
            self._append_lifecycle_step(
                record, "visible_steps", self._policy_step
            )
            stage_fields = (
                ("item_cap_item_indices", "search_included_steps"),
                ("search_started_item_indices", "search_started_steps"),
                (
                    "candidate_generated_item_indices",
                    "candidate_generated_steps",
                ),
                (
                    "candidate_topk_item_indices",
                    "candidate_topk_steps",
                ),
                (
                    "future_probe_item_indices",
                    "future_probe_steps",
                ),
            )
            for stage_name, field_name in stage_fields:
                if item_index in stage_sets[stage_name]:
                    self._append_lifecycle_step(
                        record, field_name, self._policy_step
                    )
            if (
                action_source in {"placement_core", "rescue_scan"}
                and item_index == selected_item_index
                and record["selected_step"] is None
            ):
                record["selected_step"] = self._policy_step
                record["selected_action_source"] = action_source

        lifecycle = []
        visible_set = set(visible_item_indices)
        for item_index in sorted(self._item_lifecycle):
            record = dict(self._item_lifecycle[item_index])
            if record["selected_step"] is not None:
                observation = "selected"
            elif item_index not in visible_set:
                observation = "not_visible"
            elif (
                action_source == "unsafe_protocol_fallback"
                and item_index == selected_item_index
            ):
                observation = "unsafe_protocol_fallback_target"
            elif item_index not in stage_sets["item_cap_item_indices"]:
                observation = "excluded_by_item_cap"
            elif item_index not in stage_sets["search_started_item_indices"]:
                observation = "search_not_started"
            elif (
                item_index
                not in stage_sets["candidate_generated_item_indices"]
            ):
                observation = "no_candidate_observed"
            elif item_index not in stage_sets["candidate_topk_item_indices"]:
                observation = "generated_but_low_rank"
            else:
                observation = "topk_not_selected"
            record["starvation_observation"] = observation
            lifecycle.append(record)
        return stages, lifecycle, coverage

    def get_init_states(self, init_states: dict):
        containers = init_states.get("container_list", [])
        self._container_templates = [
            normalize_container(container) for container in containers
        ]
        self._policy_step = 0
        self._item_lifecycle = {}
        self.last_top_candidate_item_indices = []
        self.last_future_probe_item_indices = []
        self._cross_step_candidates = []
        self.last_cross_step_valid_decisions = []
        self._temporal_chunk_proposals = []
        self.last_temporal_chunk_valid_decisions = []
        self._optimize_enabled = bool(init_states.get("optimize", False))
        self._lookahead_k = int(init_states.get("lookahead_k", 0))
        self._append_policy_trace(
            {
                "event": "init",
                "optimize": self._optimize_enabled,
                "lookahead_k": self._lookahead_k,
                "item_coverage_mode": ITEM_COVERAGE_MODE,
                "release_risk_gate_mode": RELEASE_RISK_GATE_MODE,
                "release_risk_p_model": RELEASE_RISK_P_MODEL,
                "release_risk_live_rerank": RELEASE_RISK_LIVE_RERANK,
                "cross_step_incumbent_mode": CROSS_STEP_INCUMBENT_MODE,
                "cross_step_incumbent_per_item": (
                    CROSS_STEP_INCUMBENT_PER_ITEM
                ),
                "temporal_chunk_ensemble_mode": (
                    TEMPORAL_CHUNK_ENSEMBLE_MODE
                ),
                "temporal_chunk_depth": TEMPORAL_CHUNK_DEPTH,
                "temporal_chunk_attempts_per_step": (
                    TEMPORAL_CHUNK_ATTEMPTS_PER_STEP
                ),
                "temporal_chunk_stride": TEMPORAL_CHUNK_STRIDE,
                "temporal_chunk_cell_size": TEMPORAL_CHUNK_CELL_SIZE,
                "release_risk_thresholds": (
                    ReleaseRiskThresholds().as_dict()
                ),
            }
        )
        return True

    def optimize(self, item_list: list):
        initial = constructive_order(item_list)
        initial_indices = [int(item["index"]) for item in initial]
        if len(initial) < 2 or not self._container_templates:
            return initial_indices

        evaluator = DryRunEvaluator(
            self._container_templates,
            attempts_per_item=OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM,
        )
        started = time.perf_counter()
        deadline = started + max(0.0, self._offline_search_budget_seconds)
        best_items = list(initial)
        best_result = evaluator.evaluate(best_items, deadline=deadline)
        self.last_offline_initial_result = best_result
        self.last_offline_result = best_result
        if OFFLINE_PAIR_MACRO_BUDGET_SECONDS < 0.0:
            pair_macros = []
        else:
            pair_macro_deadline = deadline
            if OFFLINE_PAIR_MACRO_BUDGET_SECONDS > 0.0:
                pair_macro_deadline = min(
                    deadline,
                    time.perf_counter()
                    + OFFLINE_PAIR_MACRO_BUDGET_SECONDS,
                )
            pair_macros = block_templates_from_trace(
                initial,
                evaluator.last_trace,
                container_templates=self._container_templates,
                deadline=pair_macro_deadline,
            )
        self.last_pair_macro_candidates = len(pair_macros)
        self.last_pair_macro_adoptions = 0

        if self._offline_search_budget_seconds <= 0.0:
            self.last_offline_evaluations = evaluator.evaluations
            self._append_offline_optimization_trace(initial_indices)
            return initial_indices

        seed = OFFLINE_RANDOM_SEED
        for position, item in enumerate(initial):
            seed = (
                seed * 1000003
                + (position + 1) * int(item["index"] + 1)
            ) & 0xFFFFFFFF
        rng = random.Random(seed)
        current_items = list(best_items)
        moving_runtime = max(0.001, best_result.runtime_seconds)

        for iteration in range(max(0, self._offline_max_evaluations - 1)):
            remaining = deadline - time.perf_counter()
            if remaining <= max(0.01, 1.5 * moving_runtime):
                break

            group_positions = {}
            for position, item in enumerate(current_items):
                group_positions.setdefault(item_group(item), []).append(position)
            movable_groups = [
                group
                for group, positions in sorted(group_positions.items())
                if len(positions) >= 2
            ]
            if not movable_groups:
                break

            used_pair_macro = False
            if pair_macros and iteration % 3 == 0:
                template = pair_macros[
                    iteration % len(pair_macros)
                ]
                first_item = next(
                    (
                        item
                        for item in current_items
                        if int(item["index"])
                        == template.item_indices[0]
                    ),
                    None,
                )
                if first_item is not None:
                    group = item_group(first_item)
                    target_positions = list(
                        group_positions.get(group, [])
                    )
                    if target_positions:
                        target_positions.append(
                            target_positions[-1] + 1
                        )
                        target = rng.choice(target_positions)
                        neighbor = apply_block_template_neighbor(
                            current_items,
                            template,
                            target,
                        )
                        used_pair_macro = neighbor != current_items
                    else:
                        neighbor = list(current_items)
                else:
                    neighbor = list(current_items)
            else:
                neighbor = list(current_items)

            if not used_pair_macro:
                group = movable_groups[iteration % len(movable_groups)]
                positions = group_positions[group]
                first, second = rng.sample(positions, 2)
                neighbor = list(current_items)
                if iteration % 2 == 0:
                    neighbor[first], neighbor[second] = (
                        neighbor[second],
                        neighbor[first],
                    )
                else:
                    moved = neighbor.pop(first)
                    neighbor.insert(second, moved)

            result = evaluator.evaluate(neighbor, deadline=deadline)
            moving_runtime = (
                0.8 * moving_runtime
                + 0.2 * max(0.001, result.runtime_seconds)
            )
            if result.rank_key() > best_result.rank_key():
                best_result = result
                best_items = list(neighbor)
            current_items = list(neighbor)
            if used_pair_macro:
                self.last_pair_macro_adoptions += 1

        self.last_offline_result = best_result
        self.last_offline_evaluations = evaluator.evaluations
        self.last_offline_cache_hits = evaluator.cache_hits
        optimized_indices = [int(item["index"]) for item in best_items]
        self._append_offline_optimization_trace(optimized_indices)
        return optimized_indices

    def _append_offline_optimization_trace(self, optimized_indices):
        def result_payload(result):
            if result is None:
                return None
            return dataclass_to_dict(result)

        self._append_policy_trace(
            {
                "event": "offline_optimization",
                "dry_run_attempts_per_item": int(
                    OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM
                ),
                "pair_macro_budget_seconds": float(
                    OFFLINE_PAIR_MACRO_BUDGET_SECONDS
                ),
                "evaluations": int(self.last_offline_evaluations),
                "cache_hits": int(self.last_offline_cache_hits),
                "pair_macro_candidates": int(
                    self.last_pair_macro_candidates
                ),
                "pair_macro_adoptions": int(
                    self.last_pair_macro_adoptions
                ),
                "initial_result": result_payload(
                    self.last_offline_initial_result
                ),
                "best_result": result_payload(self.last_offline_result),
                "optimized_order": [
                    int(index) for index in optimized_indices
                ],
            }
        )

    def _board_choice(self, top, observation, ordered_items):
        """Pick among the ranker's top-K by the board each one leaves.

        The ranker proposes and the board disposes: every candidate here
        already passed validation and risk gating, so this only reorders a
        set the shipped agent was already willing to place. K = 1 is the
        shipped decision exactly.
        """
        containers = observation.get("container_list", [])
        shapes = board_probe_shapes(item for _index, item in ordered_items)
        self.last_board_features = None
        if not shapes or not containers:
            return top[0]
        best_decision = top[0]
        best_key = None
        best_features = None
        for decision in top:
            ranked = board_rank_key(decision, containers, shapes)
            if ranked is None:
                continue
            features, key = ranked
            if best_key is None or key > best_key:
                best_key = key
                best_decision = decision
                best_features = features
        self.last_board_features = best_features
        return best_decision

    def _closed_loop_choice(
        self,
        observation,
        pool_list,
        ordered_items,
        deadline,
        risk_lambda=None,
        diagnostics=...,
        candidate_observer=None,
        attempt_budget=None,
    ):
        """
        Closed-loop 1-ply lookahead. Keep the top-K immediate candidates
        (not just the single best), hypothetically settle each one against
        a deep-copied container state using the exact same PlacementCore
        used for every other decision, then rank the resulting pool-aware
        evaluation with the configured selection mode.

        weighted preserves the original discounted sum. depth2 avoids mixing
        immediate and future scales by comparing next-step feasibility,
        best-next score, and immediate score lexicographically.
        pool_resilience first preserves the number of visible items that
        remain individually placeable.

        ``risk_lambda`` switches the release ranking to the risk-adjusted
        score; the shadow rerank passes ``diagnostics=None`` so its second
        search never pollutes the audit trail of the real one.
        """
        if diagnostics is ...:
            diagnostics = self.last_candidate_diagnostics
        self.last_top_candidate_item_indices = []
        self.last_future_probe_item_indices = []
        if not ordered_items:
            self.last_lookahead_evaluation = None
            self.last_top_candidate_count = 0
            return None

        selection_mode = normalized_lookahead_mode(
            LOOKAHEAD_SELECTION_MODE
        )
        lookahead_deadline = deadline - LOOKAHEAD_TIME_RESERVE_SECONDS
        search_deadline = (
            lookahead_deadline
            if lookahead_deadline > time.perf_counter()
            else deadline
        )
        top_candidate_kwargs = {
            "deadline": search_deadline,
            "diagnostics": diagnostics,
            "risk_lambda": risk_lambda,
            **placement_selection_kwargs(),
        }
        if attempt_budget:
            top_candidate_kwargs["attempt_budget"] = attempt_budget
        if candidate_observer is not None:
            top_candidate_kwargs["candidate_observer"] = candidate_observer
        top = PlacementCore.top_candidates(
            observation,
            ordered_items,
            LOOKAHEAD_TOP_K,
            **top_candidate_kwargs,
        )
        self.last_top_candidate_count = len(top)
        self.last_top_candidates = list(top)
        seen_top_items = set()
        for decision in top:
            pool_index = int(decision.action["item_idx"])
            if 0 <= pool_index < len(pool_list):
                item_index = int(
                    pool_list[pool_index].get("index", pool_index)
                )
                if item_index not in seen_top_items:
                    seen_top_items.add(item_index)
                    self.last_top_candidate_item_indices.append(item_index)
        if not top:
            self.last_lookahead_evaluation = None
            return None
        if (
            len(top) == 1
            or len(ordered_items) <= 1
            or time.perf_counter() >= lookahead_deadline
        ):
            self.last_lookahead_evaluation = LookaheadEvaluation(
                decision=top[0],
                feasible_next_items=0,
                total_next_items=0,
                best_next_score=0.0,
            )
            return top[0]

        if selection_mode == "board":
            decision = self._board_choice(top, observation, ordered_items)
            self.last_lookahead_evaluation = LookaheadEvaluation(
                decision=decision,
                feasible_next_items=0,
                total_next_items=0,
                best_next_score=0.0,
            )
            return decision

        inner_pool = ordered_items[:LOOKAHEAD_INNER_ITEMS]
        self.last_future_probe_item_indices = [
            int(item.get("index", pool_index))
            for pool_index, item in inner_pool
        ]
        best_decision = top[0]
        best_key = None
        best_evaluation = None
        for decision in top:
            if time.perf_counter() >= deadline - 0.2:
                break
            item_idx = decision.action["item_idx"]
            placed_item = pool_list[item_idx]
            sim_containers = copy.deepcopy(
                observation.get("container_list", [])
            )
            apply_placement_decision(placed_item, decision, sim_containers)
            remaining = [
                (idx, item) for idx, item in inner_pool if idx != item_idx
            ]
            pool_feasibility = VisiblePoolFeasibility(
                feasible_items=0,
                evaluated_items=0,
                best_score=0.0,
            )
            if remaining:
                sim_observation = {
                    "pool_list": pool_list,
                    "container_list": sim_containers,
                }
                pool_feasibility = evaluate_visible_pool_feasibility(
                    sim_observation,
                    remaining,
                    deadline=deadline - 0.2,
                )
                if pool_feasibility is None:
                    break
            evaluation = LookaheadEvaluation(
                decision=decision,
                feasible_next_items=pool_feasibility.feasible_items,
                total_next_items=len(remaining),
                best_next_score=pool_feasibility.best_score,
            )
            rank_key = lookahead_rank_key(
                evaluation,
                mode=selection_mode,
            )
            if best_key is None or rank_key > best_key:
                best_key = rank_key
                best_decision = decision
                best_evaluation = evaluation
        if best_evaluation is None:
            best_evaluation = LookaheadEvaluation(
                decision=best_decision,
                feasible_next_items=0,
                total_next_items=0,
                best_next_score=0.0,
            )
        self.last_lookahead_evaluation = best_evaluation
        return best_decision

    def _decision_summary(self, decision, pool_list, containers):
        """Compact, JSON-safe description of one decision for telemetry."""
        pool_index = int(decision.action["item_idx"])
        container_index = int(decision.action["container_idx"])
        entry = {
            "kind": decision.candidate.name or "candidate",
            "pool_index": pool_index,
            "item_index": (
                int(pool_list[pool_index].get("index", pool_index))
                if 0 <= pool_index < len(pool_list)
                else None
            ),
            "container_index": container_index,
            "orientation": int(decision.action["orientation"]),
            "score": float(decision.score),
            "center": [float(value) for value in decision.candidate.center],
            "size": [float(value) for value in decision.candidate.size],
            "action_command": {
                "item_idx": pool_index,
                "container_idx": container_index,
                "place_pos": [
                    float(value)
                    for value in decision.action["place_pos"]
                ],
                "orientation": int(decision.action["orientation"]),
            },
        }
        if (
            decision.candidate.name == "release_candidate"
            and 0 <= pool_index < len(pool_list)
            and 0 <= container_index < len(containers)
        ):
            features = release_risk_features(
                decision.candidate,
                pool_list[pool_index],
                containers[container_index],
                int(decision.action["orientation"]),
            )
            entry["p_rot"] = release_rotation_risk_probability(features)
        return entry

    def _shadow_rerank_record(
        self,
        observation,
        pool_list,
        containers,
        ordered_items,
        decision,
    ):
        """
        Re-run the real selection stack with the risk-adjusted release
        ranking and report how the final choice would differ. The returned
        action is never changed; this only annotates diagnostics. When the
        baseline chose a settled candidate the risk term cannot alter the
        outcome (it only reweights release candidates below the settled
        preference), so the second search is skipped.
        """
        if not RELEASE_RISK_SHADOW_RERANK or decision is None:
            return None
        slide_shadow = RELEASE_RISK_SLIDE_SHADOW_LAMBDA > 0.0
        if RELEASE_RISK_LIVE_RERANK and not slide_shadow:
            # The real action already used the risk-adjusted ranking; a
            # shadow pass with the same lambdas would compare it with
            # itself. With a slide shadow lambda the shadow differs
            # (rot+slide vs the live rot-only), so it still runs.
            return None
        baseline = self._decision_summary(decision, pool_list, containers)
        record = {
            "enabled": True,
            "lambda": float(RELEASE_RISK_RERANK_LAMBDA),
            "slide_lambda": (
                float(RELEASE_RISK_SLIDE_SHADOW_LAMBDA)
                if slide_shadow
                else None
            ),
            "model": active_release_risk_model_version(),
            "slide_model": (
                RELEASE_RISK_SLIDE_LOGISTIC_V1["version"]
                if slide_shadow
                else None
            ),
            "baseline": baseline,
        }
        if decision.candidate.name != "release_candidate":
            record["applies"] = False
            record["risk_selection"] = baseline
            record["changed"] = False
            return record

        saved_state = (
            self.last_top_candidate_item_indices,
            self.last_future_probe_item_indices,
            self.last_lookahead_evaluation,
            self.last_top_candidate_count,
        )
        shadow_deadline = time.perf_counter() + POLICY_BUDGET_SECONDS
        global RELEASE_RISK_SLIDE_LAMBDA
        saved_slide_lambda = RELEASE_RISK_SLIDE_LAMBDA
        if slide_shadow:
            RELEASE_RISK_SLIDE_LAMBDA = RELEASE_RISK_SLIDE_SHADOW_LAMBDA
        try:
            shadow_decision = self._closed_loop_choice(
                observation,
                pool_list,
                ordered_items,
                shadow_deadline,
                risk_lambda=RELEASE_RISK_RERANK_LAMBDA,
                diagnostics=None,
            )
            if shadow_decision is None:
                shadow_decision = PlacementCore.choose(
                    observation,
                    ordered_items,
                    deadline=shadow_deadline,
                    diagnostics=None,
                    risk_lambda=RELEASE_RISK_RERANK_LAMBDA,
                )
        finally:
            RELEASE_RISK_SLIDE_LAMBDA = saved_slide_lambda
            (
                self.last_top_candidate_item_indices,
                self.last_future_probe_item_indices,
                self.last_lookahead_evaluation,
                self.last_top_candidate_count,
            ) = saved_state
        record["applies"] = True
        if shadow_decision is None:
            record["risk_selection"] = None
            record["changed"] = None
            return record
        risk_selection = self._decision_summary(
            shadow_decision, pool_list, containers
        )
        record["risk_selection"] = risk_selection
        record["changed"] = (
            risk_selection["action_command"] != baseline["action_command"]
        )
        return record

    def policy(self, observation: dict):
        # The work bound lives in POLICY_ATTEMPT_BUDGET and is applied inside
        # PlacementCore, so nothing is threaded from here and the deadline
        # arithmetic is the shipped arithmetic. A budget larger than the
        # deadline affords is simply deadline-bound again, which is why that
        # constant is calibrated from the recorded attempts_consumed rather
        # than guessed.
        deadline = time.perf_counter() + POLICY_BUDGET_SECONDS
        primary_deadline = deadline
        if RESCUE_SCAN_ENABLED:
            primary_deadline = max(
                time.perf_counter(),
                deadline - max(0.0, RESCUE_SCAN_RESERVE_SECONDS),
            )
        class_aware_coverage = ITEM_COVERAGE_MODE == "class_aware"
        self.last_candidate_diagnostics = {
            "_record_item_lifecycle": bool(self._policy_trace_path),
            "_class_aware_first_pass": class_aware_coverage,
        }
        if RESCUE_SCAN_ENABLED:
            self.last_candidate_diagnostics["rescue_scan"] = {
                "enabled": True,
                "triggered": False,
                "attempt_budget": int(RESCUE_SCAN_ATTEMPT_BUDGET),
                "reserve_seconds": float(RESCUE_SCAN_RESERVE_SECONDS),
            }
        self.last_action_source = None
        self.last_candidate_kind = None
        pool_list = observation.get("pool_list", [])
        containers = observation.get("container_list", [])
        ordered_items = capped_online_items(
            pool_list,
            MAX_POOL_ITEMS_EVALUATED,
            mode=ITEM_COVERAGE_MODE,
        )
        cross_step_collector = None
        if CROSS_STEP_INCUMBENT_MODE == "shadow":
            cross_step_collector = CrossStepCandidateCollector(
                CROSS_STEP_INCUMBENT_PER_ITEM
            )
        rollout_collector = None
        if VISIBLE_POOL_ROLLOUT_MODE in {"shadow", "enforce"}:
            rollout_collector = VisiblePoolRolloutCollector()

        live_lambda = (
            RELEASE_RISK_RERANK_LAMBDA if RELEASE_RISK_LIVE_RERANK else None
        )
        if live_lambda is not None:
            self.last_candidate_diagnostics["release_risk_live_rerank"] = {
                "lambda": float(live_lambda),
                "model": active_release_risk_model_version(),
            }
        closed_loop_kwargs = {"risk_lambda": live_lambda}
        candidate_observers = []
        if cross_step_collector is not None:
            candidate_observers.append(cross_step_collector.observe)
        if rollout_collector is not None:
            candidate_observers.append(rollout_collector.observe)
        if candidate_observers:
            def observe_candidate(*args):
                for observer in candidate_observers:
                    observer(*args)

            closed_loop_kwargs["candidate_observer"] = observe_candidate
        decision = self._closed_loop_choice(
            observation,
            pool_list,
            ordered_items,
            primary_deadline,
            **closed_loop_kwargs,
        )
        action_source = "placement_core"
        if decision is None:
            # The closed-loop pass has already searched the primary anchor
            # space. If it completed every unit and accepted nothing, running
            # the identical scan again cannot find anything and costs most of
            # the remaining budget -- measured at 4.2 s of 6.5 s on
            # c001-k1 step 18. Spend that time on a different anchor space
            # instead, where the oracle showed 60 physically safe placements
            # the primary space does not contain.
            search_stats = self.last_candidate_diagnostics.get("search", {})
            units_total = int(search_stats.get("units_total", 0))
            primary_exhausted = units_total > 0 and (
                int(search_stats.get("units_completed", 0)) >= units_total
            )
            use_anchor_fallback = bool(
                ANCHOR_FALLBACK_ENABLED and primary_exhausted
            )
            choose_kwargs = {
                "deadline": primary_deadline,
                "diagnostics": self.last_candidate_diagnostics,
                "risk_lambda": live_lambda,
                "anchor_fallback": use_anchor_fallback,
                **placement_selection_kwargs(),
            }
            if candidate_observers:
                choose_kwargs["candidate_observer"] = observe_candidate
            decision = PlacementCore.choose(
                observation,
                ordered_items,
                **choose_kwargs,
            )
            if decision is not None and use_anchor_fallback:
                action_source = "anchor_fallback"
        if (
            DEATH_BAND_FALLBACK_ENABLED
            and decision is not None
            and action_source == "placement_core"
            and decision.candidate.name == "release_candidate"
            and (
                DEATH_BAND_SCORE is None
                or float(decision.score) <= DEATH_BAND_SCORE
            )
        ):
            # Gamble detection. Every measured episode death executed a
            # release the ranker itself scored at or below the death band
            # (-1.545, -1.545, -2.384 on the two-container scene), wagering
            # the whole remaining stream on one placement. Before executing
            # such a release, spend the remaining budget on the alternate
            # coarse-to-fine anchor space; take its answer only if it is
            # settled or strictly better.
            def rotation_probability(dec, dec_item):
                _adj, prob = risk_adjusted_score(
                    float(dec.score),
                    dec.candidate,
                    dec_item,
                    observation["container_list"][
                        int(dec.action["container_idx"])
                    ],
                    int(dec.action["orientation"]),
                    1.0,
                )
                return float(prob) if prob is not None else 0.0

            pool_by_idx = {
                int(idx): itm for idx, itm in ordered_items
            }
            chosen_item = pool_by_idx.get(
                int(decision.action["item_idx"]),
                observation["pool_list"][0],
            )
            budget_left = (
                float("inf")
                if primary_deadline is None
                else primary_deadline - time.perf_counter()
            )
            if budget_left < DEATH_BAND_MIN_BUDGET_SECONDS:
                pass  # not enough time to evaluate, let alone re-search
            elif rotation_probability(decision, chosen_item) >= 0.5:
                # The model itself calls the chosen release likelier to
                # topple than not. Additive reranking cannot save this
                # turn -- the measured score valley between the toppling
                # pose (-1.44) and the physically safe ones (-2.8) exceeds
                # the whole penalty range -- so the selection becomes
                # lexicographic for this one turn: any settled or
                # P_rot < 0.5 candidate, best score among them, beats
                # every likely-toppler.
                caught = []

                def catch(item_idx, item, container_idx, orientation, dec):
                    caught.append((int(item_idx), item, dec))

                retry = PlacementCore.choose(
                    observation,
                    ordered_items,
                    deadline=primary_deadline,
                    diagnostics=self.last_candidate_diagnostics,
                    risk_lambda=live_lambda,
                    anchor_fallback=True,
                    candidate_observer=catch,
                    **placement_selection_kwargs(),
                )
                if retry is not None:
                    caught.append(
                        (int(retry.action["item_idx"]), None, retry)
                    )
                # Dominance, not preference. v1 took the best-scored
                # candidate with P_rot < 0.5, which bought safety with
                # whatever the replacement gave up -- and what it gave up
                # was support ratio, the physical quantity Ranker.score
                # spends on centre of gravity and stability. The official
                # submission charged 20.7% of cog and 22.4% of stability
                # for that trade. The local proxies cannot police it: the
                # shake metrics' repeat-to-repeat spread (23-75%) swamps
                # the effect size (2-15%).
                #
                # So the trade is removed by construction. A replacement
                # must be no worse on BOTH axes -- lower toppling risk AND
                # support ratio not below the action it replaces. Nothing
                # is weighted; if no candidate dominates, the original
                # action stands and the gamble is taken knowingly.
                incumbent_container = observation["container_list"][
                    int(decision.action["container_idx"])
                ]
                incumbent_support = Geometry.support_ratio(
                    decision.candidate, incumbent_container
                )
                incumbent_lift = float(decision.candidate.center[2]) * float(
                    chosen_item.get("mass", 1.0)
                )
                best_safe = None
                for item_idx, item, dec in caught:
                    dec_item = item or pool_by_idx.get(item_idx)
                    if dec_item is None:
                        continue
                    if dec.candidate.name == "release_candidate" and (
                        rotation_probability(dec, dec_item) >= 0.5
                    ):
                        continue
                    if DEATH_BAND_REQUIRE_DOMINANCE:
                        # Both stability-bearing terms of Ranker.score, not
                        # one: +2.0*support carries stability and
                        # -0.18*z*mass carries centre of gravity. Guarding
                        # support alone still lets the gate swap a heavy
                        # item upward, which is the cog half of the same
                        # bill. (The remaining +0.35y term is door-side
                        # depth, which the placement rules score, not cog.)
                        support = Geometry.support_ratio(
                            dec.candidate,
                            observation["container_list"][
                                int(dec.action["container_idx"])
                            ],
                        )
                        if support < incumbent_support - EPS:
                            continue
                        lift = float(dec.candidate.center[2]) * float(
                            dec_item.get("mass", 1.0)
                        )
                        if lift > incumbent_lift + EPS:
                            continue
                    if best_safe is None or float(dec.score) > float(
                        best_safe.score
                    ):
                        best_safe = dec
                if best_safe is not None:
                    decision = best_safe
                    action_source = "death_band_fallback"
        if decision is None and RESCUE_SCAN_ENABLED:
            rescue_items = rescue_online_items(pool_list)
            decision = PlacementCore.rescue_choose(
                observation,
                rescue_items,
                deadline=deadline,
                attempt_budget=RESCUE_SCAN_ATTEMPT_BUDGET,
                diagnostics=self.last_candidate_diagnostics,
                risk_lambda=live_lambda,
            )
            if decision is not None:
                action_source = "rescue_scan"
        rollout_record = None
        if (
            decision is not None
            and rollout_collector is not None
            and action_source != "rescue_scan"
        ):
            rollout_record, rollout_proposal = (
                visible_pool_rollout_evaluation(
                    observation,
                    ordered_items,
                    rollout_collector.snapshot(
                        VISIBLE_POOL_ROLLOUT_TOP_K
                    ),
                    decision,
                    risk_lambda=live_lambda,
                )
            )
            rollout_record["enforced"] = bool(
                VISIBLE_POOL_ROLLOUT_MODE == "enforce"
                and rollout_record.get("proposal_improves_rollout") is True
                and rollout_proposal is not None
                and rollout_proposal is not decision
            )
            if rollout_record["enforced"]:
                rollout_record["original_pool_index"] = int(
                    decision.action["item_idx"]
                )
                decision = rollout_proposal
                action_source = "rollout_enforce"
            self.last_candidate_diagnostics[
                "visible_pool_rollout"
            ] = rollout_record
        if cross_step_collector is not None:
            selected_item_index_for_buffer = None
            if decision is not None:
                selected_pool_index_for_buffer = int(
                    decision.action["item_idx"]
                )
                if 0 <= selected_pool_index_for_buffer < len(pool_list):
                    selected_item_index_for_buffer = int(
                        pool_list[selected_pool_index_for_buffer].get(
                            "index", selected_pool_index_for_buffer
                        )
                    )
            cross_step_summary, cross_step_valid = (
                revalidate_cross_step_candidates(
                    observation,
                    self._cross_step_candidates,
                    deadline=deadline,
                    risk_lambda=live_lambda,
                )
            )
            cross_step_summary["would_prevent_protocol_fallback"] = bool(
                decision is None and cross_step_valid
            )
            next_cross_step_candidates = cross_step_collector.snapshot(
                excluded_item_index=selected_item_index_for_buffer
            )
            cross_step_summary["collected_for_next_step_count"] = len(
                next_cross_step_candidates
            )
            cross_step_summary["collected_for_next_step_item_count"] = len(
                {
                    candidate.item_index
                    for candidate in next_cross_step_candidates
                }
            )
            self.last_candidate_diagnostics["cross_step_incumbent"] = (
                cross_step_summary
            )
            self.last_cross_step_valid_decisions = cross_step_valid
            self._cross_step_candidates = next_cross_step_candidates
        if TEMPORAL_CHUNK_ENSEMBLE_MODE == "shadow":
            temporal_summary, temporal_valid = (
                temporal_chunk_ensemble_evaluation(
                    observation,
                    self._temporal_chunk_proposals,
                    decision,
                    current_step=self._policy_step,
                    deadline=deadline,
                    risk_lambda=live_lambda,
                )
            )
            pending = [
                proposal
                for proposal in self._temporal_chunk_proposals
                if int(proposal.target_step) > int(self._policy_step)
            ]
            generated = []
            generation = None
            if decision is not None:
                generation, generated = build_temporal_chunk_proposals(
                    observation,
                    ordered_items,
                    decision,
                    origin_step=self._policy_step,
                    risk_lambda=live_lambda,
                )
            self._temporal_chunk_proposals = pending + generated
            self.last_temporal_chunk_valid_decisions = temporal_valid
            temporal_summary["generation"] = generation
            temporal_summary["generated_for_future_count"] = len(generated)
            temporal_summary["pending_future_count"] = len(
                self._temporal_chunk_proposals
            )
            temporal_summary["pending_target_steps"] = sorted(
                {
                    int(proposal.target_step)
                    for proposal in self._temporal_chunk_proposals
                }
            )
            self.last_candidate_diagnostics[
                "temporal_chunk_ensemble"
            ] = temporal_summary
        if decision is not None:
            self.last_action_source = action_source
            self.last_candidate_kind = (
                decision.candidate.name or "candidate"
            )
            evaluation = self.last_lookahead_evaluation
            if evaluation is None or evaluation.decision is not decision:
                evaluation = LookaheadEvaluation(
                    decision=decision,
                    feasible_next_items=0,
                    total_next_items=0,
                    best_next_score=0.0,
                )
            selected_pool_index = int(decision.action["item_idx"])
            selected_item_index = None
            if 0 <= selected_pool_index < len(pool_list):
                selected_item_index = int(
                    pool_list[selected_pool_index]["index"]
                )
            feasible_ratio = (
                evaluation.feasible_next_items / evaluation.total_next_items
                if evaluation.total_next_items > 0
                else None
            )
            (
                selection_stages,
                item_lifecycle,
                coverage,
            ) = self._selection_trace(
                pool_list,
                (
                    rescue_online_items(pool_list)
                    if action_source == "rescue_scan"
                    else ordered_items
                ),
                selected_pool_index,
                action_source,
            )
            record_selected_release_risk(
                self.last_candidate_diagnostics,
                decision,
                pool_list,
                containers,
            )
            evaluation_record = placement_evaluation_record(decision)
            if evaluation_record is not None:
                self.last_candidate_diagnostics[
                    "selected_candidate_evaluation"
                ] = evaluation_record
            shadow_record = None
            if action_source != "rescue_scan":
                shadow_record = self._shadow_rerank_record(
                    observation,
                    pool_list,
                    containers,
                    ordered_items,
                    decision,
                )
            if shadow_record is not None:
                self.last_candidate_diagnostics["shadow_rerank"] = (
                    shadow_record
                )
            finalize_release_flow_diagnostics(
                self.last_candidate_diagnostics
            )
            self.last_candidate_diagnostics.pop(
                "_record_item_lifecycle", None
            )
            self.last_candidate_diagnostics.pop(
                "_class_aware_first_pass", None
            )
            self._append_policy_trace(
                {
                    "event": "decision",
                    "step": self._policy_step,
                    "mode": LOOKAHEAD_SELECTION_MODE,
                    "placement_selector_mode": PLACEMENT_SELECTOR_MODE,
                    "item_coverage_mode": ITEM_COVERAGE_MODE,
                    "optimize": self._optimize_enabled,
                    "lookahead_k": self._lookahead_k,
                    "pool_size": len(pool_list),
                    "selected_pool_index": selected_pool_index,
                    "selected_item_index": selected_item_index,
                    "top_candidate_count": self.last_top_candidate_count,
                    "immediate_score": float(decision.score),
                    "evaluated_remaining_items": (
                        evaluation.total_next_items
                    ),
                    "feasible_remaining_items": (
                        evaluation.feasible_next_items
                    ),
                    "feasible_remaining_ratio": feasible_ratio,
                    "best_next_score": float(
                        evaluation.best_next_score
                    ),
                    "action_source": action_source,
                    "candidate_kind": (
                        decision.candidate.name or "candidate"
                    ),
                    "action_command": {
                        "item_idx": selected_pool_index,
                        "container_idx": int(
                            decision.action["container_idx"]
                        ),
                        "place_pos": [
                            float(value)
                            for value in decision.action["place_pos"]
                        ],
                        "orientation": int(
                            decision.action["orientation"]
                        ),
                    },
                    "candidate_diagnostics": self.last_candidate_diagnostics,
                    "selection_stages": selection_stages,
                    "coverage": coverage,
                    "item_lifecycle": item_lifecycle,
                }
            )
            self._policy_step += 1
            return action_for_execution(decision)

        fallback_container = 0
        if pool_list and containers:
            eligible = eligible_container_indices(pool_list[0], containers)
            if eligible:
                fallback_container = eligible[0]
        selected_item_index = (
            int(pool_list[0]["index"]) if pool_list else None
        )
        self.last_action_source = "unsafe_protocol_fallback"
        self.last_candidate_kind = "unsafe_protocol_fallback"
        (
            selection_stages,
            item_lifecycle,
            coverage,
        ) = self._selection_trace(
            pool_list,
            ordered_items,
            0 if pool_list else None,
            "unsafe_protocol_fallback",
        )
        finalize_release_flow_diagnostics(
            self.last_candidate_diagnostics
        )
        self.last_candidate_diagnostics.pop(
            "_record_item_lifecycle", None
        )
        self.last_candidate_diagnostics.pop(
            "_class_aware_first_pass", None
        )
        self._append_policy_trace(
            {
                "event": "decision",
                "step": self._policy_step,
                "mode": LOOKAHEAD_SELECTION_MODE,
                "placement_selector_mode": PLACEMENT_SELECTOR_MODE,
                "item_coverage_mode": ITEM_COVERAGE_MODE,
                "optimize": self._optimize_enabled,
                "lookahead_k": self._lookahead_k,
                "pool_size": len(pool_list),
                "selected_pool_index": 0 if pool_list else None,
                "selected_item_index": selected_item_index,
                "top_candidate_count": self.last_top_candidate_count,
                "immediate_score": None,
                "evaluated_remaining_items": 0,
                "feasible_remaining_items": 0,
                "feasible_remaining_ratio": None,
                "best_next_score": 0.0,
                "action_source": "unsafe_protocol_fallback",
                "candidate_kind": "unsafe_protocol_fallback",
                "internal_outcome": "no_safe_action",
                "no_safe_action": True,
                "protocol_fallback": "fixed",
                "protocol_fallback_kind": "fixed_coordinate",
                "action_command": {
                    "item_idx": 0,
                    "container_idx": fallback_container,
                    "place_pos": [0.0, 0.0, 0.25],
                    "orientation": 0,
                },
                "candidate_diagnostics": self.last_candidate_diagnostics,
                "selection_stages": selection_stages,
                "coverage": coverage,
                "item_lifecycle": item_lifecycle,
            }
        )
        self._policy_step += 1
        return {
            "item_idx": 0,
            "container_idx": fallback_container,
            "place_pos": np.array([0.0, 0.0, 0.25], dtype=np.float32),
            "orientation": 0,
        }
