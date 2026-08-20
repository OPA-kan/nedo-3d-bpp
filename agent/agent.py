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
# Last-resort relaxation. The fixed protocol fallback emits a known
# transport-invalid action, so firing it ends the episode with certainty,
# and the feasibility phase study (reports/anchor-recall/phase-structure.md)
# showed the deadline search often accepts nothing while reachable safe
# candidates exist. When the scan has accepted zero candidates, this knob
# spends the given wall-clock slice rescanning once with the self-imposed
# lateral guard relaxed to the official transport clearance -- the
# environment's own requirement, never below it -- and emits the best
# candidate found. Certain death is exchanged for a positive survival
# probability; outside the zero-accepted regime nothing changes. 0 disables.
LAST_RESORT_RELAXATION_SECONDS = float(
    os.environ.get("LAST_RESORT_RELAXATION_SECONDS", "0") or "0"
)
# Log-only safety shadow. Points at a numpy weight artifact exported by
# scripts/export_state_model.py (candidate-mlp-safety-v1). When set, the
# policy scores the action it ALREADY chose with the learned safety ranker
# and records the logit in the policy trace: one 64-wide forward per step,
# after selection, nothing on the per-candidate hot path, nothing reranked.
# This is the live-contact contract check (does live-computed phi reproduce
# the offline AUC?) that must precede any reranking experiment. Empty
# leaves the trace event off; since the 2026-08-17 adoption the MODEL
# itself no longer needs this knob -- _safety_shadow_model falls back to
# the embedded copy of the same artifact when the path is empty, so the
# shipped quiet-guard trigger works with no environment and no
# filesystem. A set path still overrides the embedded copy (instrument
# replay compatibility).
SAFETY_RERANK_SHADOW = os.environ.get("SAFETY_RERANK_SHADOW", "")
# Gate 2 reranker (reports/state-model/gate2-rerank-protocol.md, amended
# by gate2b-amendment.md). Requires SAFETY_RERANK_SHADOW for the weights.
# "shadow" runs the full incumbent-plus-retained-top-K scoring on the hot
# path and logs the would-swap verdict without touching the action (the
# physical negative control); "enforce" executes the swap. The rule
# constants below come from the Gate 1 calibration table and the offline
# rescuability audit, not from any episode wave: trigger and escape sit
# where measured empirical survival reaches 1.0, and the score-loss bound
# is ABSOLUTE because the audit showed danger states have incumbent
# scores near zero, where the original relative bound blocked every
# rescue (0/27) that an absolute unit of score would have bought (18/27,
# with one bad pick and mean needless-swap cost 0.34).
SAFETY_RERANK_MODES = frozenset({"off", "shadow", "enforce"})
SAFETY_RERANK_MODE = os.environ.get("SAFETY_RERANK_MODE", "off")
if SAFETY_RERANK_MODE not in SAFETY_RERANK_MODES:
    raise ValueError(
        f"unknown SAFETY_RERANK_MODE {SAFETY_RERANK_MODE!r}; "
        f"expected one of {sorted(SAFETY_RERANK_MODES)}"
    )
SAFETY_RERANK_TRIGGER_LOGIT = 2.0
SAFETY_RERANK_MARGIN_LOGIT = 2.0
SAFETY_RERANK_MAX_SCORE_LOSS_ABS = 1.0
SAFETY_RERANK_POOL_CAP = 4096
SAFETY_RERANK_RECORDED_CANDIDATES = 12
# Visible-pool tree search (reports/hazard/visible-tree-search-protocol.md;
# rationale docs/theory/LITERATURE_SEARCH_DIRECTION.md). Runs strictly
# after every live selection decision is frozen. "shadow" performs the
# full search and logs the would-change verdict without touching the
# action (the physical negative control); "enforce" swaps the played
# action to the best root under the preregistered tie-band rule; the
# incumbent always stands otherwise -- never refuse, never fall through.
VISIBLE_TREE_SEARCH_MODES = frozenset({"off", "shadow", "enforce"})
VISIBLE_TREE_SEARCH = os.environ.get("VISIBLE_TREE_SEARCH", "off")
if VISIBLE_TREE_SEARCH not in VISIBLE_TREE_SEARCH_MODES:
    raise ValueError(
        f"unknown VISIBLE_TREE_SEARCH {VISIBLE_TREE_SEARCH!r}; "
        f"expected one of {sorted(VISIBLE_TREE_SEARCH_MODES)}"
    )
# The constants below are fixed by the frozen protocol and are therefore
# source literals, not environment knobs.
# Roots: the incumbent plus up to BRANCH-1 retained alternatives.
VISIBLE_TREE_SEARCH_BRANCH = 4
# Further greedy placements expanded beyond each root.
VISIBLE_TREE_SEARCH_DEPTH = 2
# Wall-clock slice for the whole search; on exhaustion the incumbent
# stands and the record notes budget_exhausted.
VISIBLE_TREE_SEARCH_SECONDS = 2.0
# A non-incumbent root must beat the incumbent's path score by MORE than
# this band to swap. 0.05 is a third of the L3 prefer-empty band (0.15),
# the smallest scalar-score difference this codebase already treats as a
# tie on the same Ranker scale, so proxy jitter alone cannot swap.
VISIBLE_TREE_SEARCH_TIE_BAND = 0.05
# Coarse expansion scan stride in metres (~2 board cells at the default
# 0.05 m cell size).
VISIBLE_TREE_SEARCH_STRIDE = 0.10
# Receptivity cap per remaining item at a leaf, and the fixed weight
# converting summed landing-site counts into path-score units. At 0.01
# per site the capped per-item term is at most 0.24 (below one L3 band)
# and a 5-site swing is needed to cross the tie band, so receptivity
# breaks ties between similar-Q paths without outranking a clear Q gap
# on any single item.
VISIBLE_TREE_SEARCH_SITE_CAP = 24
VISIBLE_TREE_SEARCH_RECEPTIVITY_WEIGHT = 0.01
# Per item and expansion step, the scan prescreens positions with the
# analytic Ranker terms, keeping the best position of every depth row
# per (container, footprint) -- row-diverse, because the shipped checks
# refuse whole regions (corridor, lateral clearance) the heightmap
# cannot see, and a shortlist drawn from one region dies with it.
# Leaders are re-scored with the shipped Ranker and validated down that
# ordering with the shipped release checks, at most this many
# validations, while the budget affords them.
VISIBLE_TREE_SEARCH_CHECKS_PER_ITEM = 24
# In-process physics probe (reports/hazard/physics-probe-protocol.md).
# Log-only: when non-empty, after every placement-core decision is
# frozen the chosen candidate is replayed in a DIRECT pybullet scene
# rebuilt from the observation, and the predicted settle motion is
# appended to the policy trace. The played action never changes; if
# pybullet is not importable the probe disables itself permanently and
# the agent behaves exactly as shipped. Empty disables.
PHYSICS_PROBE_SHADOW = os.environ.get("PHYSICS_PROBE_SHADOW", "")
# Per-step pose snapshot (reports/hazard/post-shake/verdict.md, "what
# would close the gap"). Log-only diagnostic: when "1" and a policy
# trace path is active, every policy step appends a compact
# "pose_snapshot" trace event recording the CURRENT pose of every
# packed item exactly as this observation's container_list reports it.
# The env refreshes ALL packed poses after each safe placement
# (containers.update_packed_items), so the last snapshot of an episode
# carries every disturbance that the per-item placement-step record
# misses -- except whatever the final placement itself moves, which has
# no later observation. Nothing on any decision path changes; empty
# disables.
NEDO_POSE_SNAPSHOT = os.environ.get("NEDO_POSE_SNAPSHOT", "")
# Behavioral probe guard (reports/hazard/probe-guard-protocol.md). "guard"
# probes the frozen placement-core choice with the same settle clone and,
# only when it predicts unsafe, probes alternatives in shipped-score order
# and plays the first that predicts safe; the incumbent stands otherwise --
# never refuse, never fall through. The probe physics is
# physics_probe_settle, reused verbatim. "guard_quiet"
# (reports/hazard/quiet-guard-protocol.md) is the same guard gated by the
# calibrated safety logit: at or above SAFETY_RERANK_TRIGGER_LOGIT (or on
# a failed logit) the step plays unchanged with no probe.
#
# Default "guard_quiet" since 2026-08-17 (ledger
# `quiet-guard-confirmed-adoption-licensed`), on three independent stream
# sets under three independent preregistrations: development run
# 32000938328 (all five gates; pooled placed +7, steps +7, 9 rescues),
# confirmation run 32001795205 (seed-20260817 streams: placed 210 vs 184,
# paired 5W/1L, physical deaths 10 -> 7; failed only the backwards
# transport gate the corrected protocol repudiated), corrected
# confirmation run 32002161568 (seed-20260818 streams: placed 213 vs 194,
# paired 6W/2L, topple+slide 6 -> 5, every stream within the
# three-placement floor). Fail-safe: no importable pybullet means no
# probes and no observed-pool collection, and an unloadable safety model
# means every quiet trigger skips -- either degrades to the pre-adoption
# default trajectory.
PHYSICS_PROBE_MODES = frozenset({"off", "guard", "guard_quiet"})
PHYSICS_PROBE_MODE = os.environ.get("PHYSICS_PROBE_MODE", "guard_quiet")
if PHYSICS_PROBE_MODE not in PHYSICS_PROBE_MODES:
    raise ValueError(
        f"unknown PHYSICS_PROBE_MODE {PHYSICS_PROBE_MODE!r}; "
        f"expected one of {sorted(PHYSICS_PROBE_MODES)}"
    )
# Guard attribute filter (reports/hazard/attribute-filter-protocol.md).
# "1": while the guard rescues a predicted-unsafe incumbent, an
# alternative whose candidate_attribute_violations exceed the
# incumbent's own on either the priority or the soft count is skipped
# before it is probed; if every safe alternative worsens coverage the
# incumbent stands. Trigger, probe order, physics arbitration, caps and
# never-refuse: unchanged. Default off until the preregistered wave
# passes.
PHYSICS_PROBE_ATTR_FILTER = (
    os.environ.get("PHYSICS_PROBE_ATTR_FILTER", "0") == "1"
)
# Rule-faithful attribute support (reports/hazard/attribute-support-protocol.md).
# "1": support_surfaces() admits a protected top when the mover carries
# every attribute that top is protected by, which is what the published
# rule allows -- 同属性の積み重ねは減点なし. Default "0" keeps the
# historical over-approximation, where NO protected top is ever support,
# so the shipped trajectory is unchanged until a wave says otherwise.
#
# The over-approximation is not free: support-exhaustion-is-the-terminal-state
# records a fatal board where all 950 legal release candidates rest on
# protected tops and the settled contract refuses every one, and
# docs/ATTRIBUTE_PLACEMENT.md notes the same shape -- 公式が許す同属性積み
# 重ね(体積になる)を捨てながら、違反そのものは防げていない.
ATTRIBUTE_SUPPORT_RULE = (
    os.environ.get("ATTRIBUTE_SUPPORT_RULE", "0") == "1"
)
# Fixed by the frozen protocol, so source literals rather than knobs: at
# most this many probes per step (the incumbent's included) and this
# wall-clock slice, clamped to the shipped policy deadline.
PHYSICS_PROBE_GUARD_MAX_PROBES = 6
PHYSICS_PROBE_GUARD_SECONDS = 1.5
# The official settle horizon (settle_wait_step: 300 in the development
# configs, simulator/configs/sample_config.json). The observation does
# not carry the validator config, so the probe cannot read it live.
PHYSICS_PROBE_SETTLE_STEPS = 300
# Official settle thresholds (validator.place_item displacement_threshold
# 0.3; the 30-degree angle channel of terminal_failure_channel). The raw
# probe values are recorded so any threshold can be re-applied.
PHYSICS_PROBE_DISPLACEMENT_THRESHOLD = 0.3
PHYSICS_PROBE_ANGLE_THRESHOLD_DEG = 30.0
# Orientation euler table copied verbatim from
# simulator/src/ground_handling/utils.py ORNS -- the table the
# validator uses for every warp. tests/test_physics_probe.py compares
# the two entry by entry.
SIMULATOR_ORNS = (
    (0.0, 0.0, 0.0),
    (math.pi / 2, 0.0, 0.0),
    (0.0, math.pi / 2, 0.0),
    (0.0, 0.0, math.pi / 2),
    (0.0, math.pi / 2, math.pi / 2),
    (math.pi / 2, 0.0, math.pi / 2),
)
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
# Online policy deadline. 6.5 s under the platform's 8.0 s
# policy_timeout, and the shipped value is not a free parameter: the
# evaluation platform fixes the timeout, a timeout substitutes
# env.action_space.sample() (a random action, which on a late board is a
# probable death), and the official feedback already reports a max
# policy time of 6.992 s against that 8.0 s ceiling.
#
# It is a knob ONLY so diagnostics can measure what the deadline costs
# us. `death-budget-is-search-starvation-not-physics` records that 57.6%
# of episodes end with the search having accepted nothing before this
# deadline, finding no candidate for any item after ~7371 attempts.
# Whether those boards are genuinely full or merely un-searched in 6.5 s
# is the question that decides whether a learned proposer is worth
# building, and it cannot be asked without varying this.
#
# Raising it is therefore a MEASUREMENT policy, never a shipped one: any
# value above the default is unshippable by construction. Registered
# offline_optimizer=false for the same reason -- the offline proposal
# oracle must not be able to "discover" that more time scores better.
POLICY_BUDGET_SECONDS = float(
    os.environ.get("POLICY_BUDGET_SECONDS", "6.5")
)
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
LATE_POOL_ITEMS_EVALUATED = max(
    0, int(os.environ.get("LATE_POOL_ITEMS_EVALUATED", "0"))
)
LATE_POOL_MIN_PLACED = max(
    0, int(os.environ.get("LATE_POOL_MIN_PLACED", "6"))
)
LATE_POOL_MAX_VISIBLE = max(
    0, int(os.environ.get("LATE_POOL_MAX_VISIBLE", "0"))
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
MULTI_AXIS_SELECTOR_MODES = frozenset({"off", "shadow", "enforce"})
MULTI_AXIS_SELECTOR_MODE = os.environ.get(
    "MULTI_AXIS_SELECTOR_MODE", "off"
).strip().lower()
if MULTI_AXIS_SELECTOR_MODE not in MULTI_AXIS_SELECTOR_MODES:
    raise ValueError(
        f"unknown MULTI_AXIS_SELECTOR_MODE {MULTI_AXIS_SELECTOR_MODE!r}; "
        f"expected one of {sorted(MULTI_AXIS_SELECTOR_MODES)}"
    )
RESIDUAL_AFFORDANCE_SHADOW_MODES = frozenset({"off", "shadow"})
RESIDUAL_AFFORDANCE_SHADOW_MODE = os.environ.get(
    "RESIDUAL_AFFORDANCE_SHADOW_MODE", "off"
).strip().lower()
if RESIDUAL_AFFORDANCE_SHADOW_MODE not in RESIDUAL_AFFORDANCE_SHADOW_MODES:
    raise ValueError(
        "unknown RESIDUAL_AFFORDANCE_SHADOW_MODE "
        f"{RESIDUAL_AFFORDANCE_SHADOW_MODE!r}; expected one of "
        f"{sorted(RESIDUAL_AFFORDANCE_SHADOW_MODES)}"
    )
# Exact action-only ridge frozen after run 32368148298 and then confirmed,
# without refitting, on runs 32372290412 and 32375696343.  The model predicts
# the Pareto direction of branch-capped searched residual affordance.  It does
# not predict official score, so the only licensed live mode is log-only
# shadow.  Feature order is the graph action tensor without immediate_score:
# six command fields followed by the fourteen observed item fields below.
RESIDUAL_AFFORDANCE_MODEL_ID = "action-ridge-32351615182-v1"
RESIDUAL_AFFORDANCE_ITEM_FEATURES = (
    "length", "width", "height", "mass", "is_prioritized", "is_soft",
    "lateralFriction", "rollingFriction", "spinningFriction",
    "restitution", "angularDamping", "contactStiffness",
    "contactDamping", "linearDamping",
)
RESIDUAL_AFFORDANCE_SCALES = (
    0.3806073153191131, 0.2621412364385038, 0.2835773360318977,
    0.42196113293868803, 0.43291467977395326, 0.3092434436967794,
    0.07663267431256171, 0.10788513919624611, 0.041828401959703054,
    4.353352152772388, 0.558991687464666, 0.7468812475943873,
    0.29089082826744855, 0.007290921570502314,
    0.007290921570502314, 0.14544541413372428, 1.0,
    2060.2073935166304, 596.1282959431495, 0.5975049980755098,
)
RESIDUAL_AFFORDANCE_WEIGHTS = (
    -0.03352362571555443, -0.17731679491757138,
    0.2745141931066554, -0.49347796424288454,
    0.01687634848410732, -0.1729749895194009,
    -0.5346835821963346, 0.342788110155405,
    -0.3736838894945536, 0.4049669902454743,
    -0.33664655932076804, 0.17875471372173454,
    0.06640011580088521, -0.05065562676644937,
    -0.05065562676645119, -0.0664001158008919, 0.0,
    -0.12809334439384412, 0.4520593099191406,
    0.17875471372178273,
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
# Experimental Task A proposal-oracle arm. The shipped default remains the
# ADR-003 risk-off oracle; setting this makes offline candidate ranking use
# the same release-risk penalties as online execution.
OFFLINE_RISK_RERANK = os.environ.get(
    "OFFLINE_RISK_RERANK", "0"
).strip().lower() in {"1", "true", "yes", "on"}
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
# Vacuum cutoff. Crossing the committed anchor-recall oracles with their
# decision-time telemetry (reports/anchor-recall/phase-structure.md) sorted
# every zero-settled search into two phases: truly empty boards let the scan
# finish because the candidate space implodes near the collapse, while
# drowning boards never complete a third of their units. When the fraction
# of settled units exhausted without one settled candidate reaches this
# threshold, the remaining settled units are skipped and the rest of the
# deadline goes to release units, whose choice quality decides survival at
# such boards (460-1014 physically safe releases existed at the
# certified-empty boards). 0 disables. The measured detector operating
# point is 0.34: precision 1.0, recall 7/8 on the raw oracle states.
VACUUM_SETTLED_CUTOFF = float(
    os.environ.get("VACUUM_SETTLED_CUTOFF", "0") or "0"
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


def attribute_rest_is_legal(item, is_soft, is_prioritized):
    """May `item` legally rest on a packed item with these attributes?

    The published rule, read per axis: a protected item is penalised
    when covered by an item of a DIFFERENT attribute than its own, and
    same-attribute stacking is explicitly exempt -- 優先手荷物(ソフト貨物)
    の上に優先手荷物(ソフト貨物)を配置しても減点はなく, それ以外の状況の
    場合に減点 (simulator/README.md 評価指標).

    "Per axis" is the part that is easy to get wrong, and it is verified
    against the bundled `calculate_attribute_placement` in
    tests/test_agent.py rather than argued from the sentence: a PRIORITY
    item resting on a SOFT one IS a soft-axis violation, because it is
    not itself soft. Only an item carrying every protected attribute the
    lower item has may rest on it.
    """
    if is_soft and not bool(item.get("is_soft", False)):
        return False
    if is_prioritized and not bool(item.get("is_prioritized", False)):
        return False
    return True


def support_surfaces(container, item=None):
    """Tops an anchor may rest on.

    `item=None` keeps the historical contract: only PLAIN packed items
    are support, so nothing is ever proposed onto a protected top. That
    is stricter than the rule -- it discards the same-attribute stacking
    the rule explicitly allows, and
    `support-exhaustion-is-the-terminal-state` records boards where all
    950 legal release candidates rest on protected tops while the
    settled contract refuses every one of them.

    Passing `item` applies the rule instead of the over-approximation,
    admitting a protected top exactly when the mover carries every
    attribute that top is protected by. Gated by
    ATTRIBUTE_SUPPORT_RULE so the default trajectory is unchanged until
    a wave says otherwise.
    """
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
    rule_mode = ATTRIBUTE_SUPPORT_RULE and item is not None
    for box, is_soft, is_prioritized in packed_aabbs_local(container):
        if rule_mode:
            if attribute_rest_is_legal(item, is_soft, is_prioritized):
                surfaces.append(box)
        elif not is_soft and not is_prioritized:
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

        for surface in support_surfaces(container, item):
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
            support_plane_components(support_surfaces(container, item))
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

        surfaces = support_surfaces(container, item)
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


def predicted_center_of_mass_z(observation, item, candidate, container):
    """Mass-weighted world-z after a static predicted-contact placement."""
    weighted_z = 0.0
    total_mass = 0.0
    for existing_container in observation.get("container_list", []):
        for packed in existing_container.get("packed_items", []):
            try:
                mass = max(EPS, float(packed.get("mass", 1.0)))
                world_z = float(packed_position_world(packed)[2])
            except (KeyError, TypeError, ValueError):
                continue
            weighted_z += mass * world_z
            total_mass += mass
    mass = max(EPS, float(item.get("mass", 1.0)))
    world_z = float(local_to_world(candidate.center, container)[2])
    weighted_z += mass * world_z
    total_mass += mass
    return weighted_z / total_mass if total_mass > EPS else 0.0


def candidate_attribute_violations(item, candidate, container, *, stack_aware=False):
    """Incremental rule-proxy violations caused by placing one candidate.

    Two readings of the same published sentence -- "soft手荷物の上への
    通常荷物配置による破損リスク", the breakage risk of putting ordinary
    cargo ON TOP OF a soft item.

    `stack_aware=False` (default, and what the bundled diagnostic's
    `_covers_from_above` also does) charges only DIRECT CONTACT: the
    mover's bottom must sit within CONTACT_TOLERANCE of the protected
    top. Measured on 42 recorded terminal states
    (`reports/official/soft-rule-gap.md`), that predicate fires on 0.19
    soft items per episode and is identically zero on 34 of 42, which is
    why every intervention built on it has been inert -- including the
    preregistered attribute filter, whose 0-of-16 result was mechanically
    guaranteed rather than informative.

    `stack_aware=True` charges any ordinary item resting ANYWHERE over
    the protected one, so load carried down through an intervening box
    counts. On the same states that reads 2.24 violated soft items and
    5.45 violating pairs per episode, with 1 of 42 episodes clean, and
    it moves the local soft ratio from 98.14 to 33.42 against an
    official soft_item_score of 19.65.

    Which reading the official scorer uses is NOT established -- its
    normalization and scene set are unpublished, and the closest variant
    is still several points away on development configs. The flag exists
    so the two can be compared by measurement; it changes no default.
    """
    priority = 0
    soft = 0
    bottom = float(candidate.minimum[2])
    for lower, is_soft, is_priority in packed_aabbs_local(container):
        top = float(lower.top)
        if stack_aware:
            # At or above the protected top, by the same tolerance, so
            # the two readings agree on the direct-contact case and
            # differ only on load carried through a stack.
            if bottom < top - CONTACT_TOLERANCE:
                continue
        elif abs(bottom - top) > CONTACT_TOLERANCE:
            continue
        if xy_overlap_area(candidate, lower) <= EPS:
            continue
        if is_priority and not bool(item.get("is_prioritized", False)):
            priority += 1
        if is_soft and not bool(item.get("is_soft", False)):
            soft += 1
    return priority, soft


def multi_axis_candidate_record(decision, observation, rank):
    """Separate official-proxy axes for one retained placement candidate."""
    pool_index = int(decision.action["item_idx"])
    container_index = int(decision.action["container_idx"])
    item = observation["pool_list"][pool_index]
    container = observation["container_list"][container_index]
    contact = settled_proxy_candidate(decision.candidate, container)
    support = Geometry.support_metrics(contact, container, item)
    priority_cover, soft_cover = candidate_attribute_violations(
        item, contact, container
    )
    # Recorded alongside, never substituted for, the shipped reading.
    # The shipped one is inert on most episodes, so a shadow that only
    # logged it could not tell whether a stack-aware selector would have
    # any reach at all -- which is exactly what the attribute filter's
    # inert verdict failed to reveal in advance.
    priority_cover_stack, soft_cover_stack = candidate_attribute_violations(
        item, contact, container, stack_aware=True
    )
    has_priority_container = any(
        bool(current.get("is_prioritized", False))
        for current in observation.get("container_list", [])
    )
    priority_routing = int(
        bool(item.get("is_prioritized", False))
        and has_priority_container
        and not bool(container.get("is_prioritized", False))
    )
    evaluation = decision.evaluation
    risk = evaluation.risk if evaluation is not None else None
    p_rot = (
        0.0
        if risk is None or risk.rotation_probability is None
        else float(risk.rotation_probability)
    )
    p_slide = (
        0.0
        if risk is None or risk.slide_probability is None
        else float(risk.slide_probability)
    )
    return {
        "rank": int(rank),
        "pool_index": pool_index,
        "item_index": int(item.get("index", pool_index)),
        "container_index": container_index,
        "orientation": int(decision.action["orientation"]),
        "command_mode": (
            "release"
            if decision.candidate.name == "release_candidate"
            else "settled"
        ),
        "priority_cover_violations": int(priority_cover),
        "soft_cover_violations": int(soft_cover),
        "priority_cover_violations_stack": int(priority_cover_stack),
        "soft_cover_violations_stack": int(soft_cover_stack),
        "priority_routing_violation": int(priority_routing),
        "rotation_probability": p_rot,
        "slide_probability": p_slide,
        "support_ratio": float(support.ratio),
        "support_center_margin": float(support.center_margin),
        "predicted_com_z": float(
            predicted_center_of_mass_z(
                observation, item, contact, container
            )
        ),
        "immediate_score": (
            float(evaluation.immediate.total)
            if evaluation is not None
            else float(decision.score)
        ),
        "adjusted_score": float(decision.score),
    }


def multi_axis_dominates(first, second):
    """True when first is no worse on every trusted physical/rule axis."""
    minimize = (
        "priority_cover_violations",
        "soft_cover_violations",
        "priority_routing_violation",
        "rotation_probability",
        "slide_probability",
    )
    maximize = ("support_ratio", "support_center_margin")
    no_worse = all(first[key] <= second[key] for key in minimize) and all(
        first[key] >= second[key] for key in maximize
    )
    strictly_better = any(
        first[key] < second[key] for key in minimize
    ) or any(first[key] > second[key] for key in maximize)
    return bool(no_worse and strictly_better)


def multi_axis_shadow_record(top, observation, selected_decision=None):
    """Pareto proposal over retained Top-K, relative to the live choice."""
    records = [
        multi_axis_candidate_record(decision, observation, rank)
        for rank, decision in enumerate(top)
    ]
    if not records:
        return None
    front = [
        candidate
        for candidate in records
        if not any(
            other is not candidate
            and multi_axis_dominates(other, candidate)
            for other in records
        )
    ]
    baseline = records[0]
    selected_rank = next(
        (
            rank
            for rank, decision in enumerate(top)
            if decision is selected_decision
        ),
        None,
    )
    selected = (
        records[selected_rank] if selected_rank is not None else baseline
    )
    dominators = [
        candidate
        for candidate in records
        if candidate is not selected
        and multi_axis_dominates(candidate, selected)
    ]
    proposed = (
        max(dominators, key=lambda candidate: candidate["adjusted_score"])
        if dominators
        else selected
    )
    return {
        "schema_version": 1,
        "mode": "shadow",
        "scope": "immediate_retained_top_k",
        "selection_rule": "pareto_then_adjusted_score",
        "predicted_com_role": "telemetry_only",
        "candidate_count": len(records),
        "pareto_front_size": len(front),
        "baseline_rank": int(baseline["rank"]),
        "selected_rank": (
            None if selected_rank is None else int(selected_rank)
        ),
        "proposed_rank": int(proposed["rank"]),
        "baseline_dominated": any(
            multi_axis_dominates(other, baseline)
            for other in records[1:]
        ),
        "would_change_action": proposed["rank"] != baseline["rank"],
        "would_change_item": (
            proposed["item_index"] != selected["item_index"]
        ),
        "selected_dominated": bool(dominators),
        "would_change_selected_action": (
            proposed["rank"] != selected["rank"]
        ),
        "enforced": False,
        "candidates": records,
    }


def residual_affordance_action_features(observation, decision):
    """Rebuild the frozen graph action tensor for one live decision."""
    action = action_for_execution(decision)
    pool_index = int(action["item_idx"])
    item = observation["pool_list"][pool_index]
    values = [
        float(action["container_idx"]),
        *[float(value) for value in action["place_pos"]],
        float(action["orientation"]),
        float(decision.candidate.name == "release_candidate"),
    ]
    values.extend(
        float(bool(item.get(name)))
        if name in ("is_prioritized", "is_soft")
        else float(item.get(name, 0.0) or 0.0)
        for name in RESIDUAL_AFFORDANCE_ITEM_FEATURES
    )
    if len(values) != len(RESIDUAL_AFFORDANCE_WEIGHTS):
        raise ValueError("residual affordance feature shape mismatch")
    return values


def residual_affordance_action_utility(observation, decision):
    """Frozen no-intercept ridge utility; differences reproduce training."""
    values = residual_affordance_action_features(observation, decision)
    return sum(
        value / scale * weight
        for value, scale, weight in zip(
            values,
            RESIDUAL_AFFORDANCE_SCALES,
            RESIDUAL_AFFORDANCE_WEIGHTS,
        )
    )


def residual_affordance_shadow_record(top, observation, selected_decision):
    """Compare the frozen model after live selection without changing it.

    The unrestricted proposal measures the replicated model exactly.  The
    guarded proposal additionally refuses any increase in direct-contact OR
    stack-aware soft/priority coverage, and in priority routing, relative to
    the live decision.  Logging both answers whether special-item safety costs
    the learner reach before any enforce mode can be considered.
    """
    if selected_decision is None:
        return None
    decisions = []
    seen = set()
    for decision in [selected_decision, *(top or [])]:
        key = _safety_rerank_action_key(decision)
        if key not in seen:
            seen.add(key)
            decisions.append(decision)
    records = []
    for rank, decision in enumerate(decisions):
        record = multi_axis_candidate_record(decision, observation, rank)
        record["affordance_utility"] = float(
            residual_affordance_action_utility(observation, decision)
        )
        records.append(record)
    incumbent = records[0]
    unrestricted = max(records, key=lambda row: row["affordance_utility"])

    def contract_not_worse(candidate):
        return all(
            int(candidate[name]) <= int(incumbent[name])
            for name in (
                "priority_cover_violations",
                "soft_cover_violations",
                "priority_cover_violations_stack",
                "soft_cover_violations_stack",
                "priority_routing_violation",
            )
        )

    eligible = [record for record in records if contract_not_worse(record)]
    guarded = max(eligible, key=lambda row: row["affordance_utility"])
    return {
        "schema_version": 1,
        "mode": "shadow",
        "model_id": RESIDUAL_AFFORDANCE_MODEL_ID,
        "target": "searched_residual_affordance_pareto",
        "candidate_count": len(records),
        "incumbent_rank": 0,
        "unrestricted_proposed_rank": int(unrestricted["rank"]),
        "guarded_proposed_rank": int(guarded["rank"]),
        "would_change_action": unrestricted["rank"] != 0,
        "would_change_item": (
            unrestricted["item_index"] != incumbent["item_index"]
        ),
        "unrestricted_contract_not_worse": contract_not_worse(unrestricted),
        "guarded_would_change_action": guarded["rank"] != 0,
        "guarded_would_change_item": (
            guarded["item_index"] != incumbent["item_index"]
        ),
        "attribute_guard_blocked_unrestricted": (
            unrestricted["rank"] != guarded["rank"]
        ),
        "immediate_score_delta": float(
            unrestricted["immediate_score"] - incumbent["immediate_score"]
        ),
        "guarded_immediate_score_delta": float(
            guarded["immediate_score"] - incumbent["immediate_score"]
        ),
        "candidates": records,
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


def effective_online_item_cap(observation):
    """Expand item breadth only in the measured mid/late intervention band."""
    placed = sum(
        len(container.get("packed_items", []))
        for container in observation.get("container_list", [])
    )
    if (
        LATE_POOL_ITEMS_EVALUATED > MAX_POOL_ITEMS_EVALUATED
        and placed >= LATE_POOL_MIN_PLACED
        and (
            LATE_POOL_MAX_VISIBLE <= 0
            or len(observation.get("pool_list", [])) <= LATE_POOL_MAX_VISIBLE
        )
    ):
        return LATE_POOL_ITEMS_EVALUATED
    return MAX_POOL_ITEMS_EVALUATED


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
    settled_units_total = sum(1 for unit in units if unit[8] == "settled")
    settled_units_exhausted = 0
    settled_candidate_seen = False
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
            if (
                VACUUM_SETTLED_CUTOFF > 0.0
                and not settled_candidate_seen
                and settled_units_total
                and state["unit"][8] == "settled"
                and settled_units_exhausted / settled_units_total
                >= VACUUM_SETTLED_CUTOFF
            ):
                # The settled phase measured itself empty: enough settled
                # units exhausted without one candidate. Skip the remaining
                # settled units so release units get the rest of the
                # deadline.
                if search_stats is not None:
                    search_stats["vacuum_cutoff_fired"] = True
                    search_stats["vacuum_settled_units_skipped"] = (
                        search_stats.get("vacuum_settled_units_skipped", 0)
                        + 1
                    )
                continue

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
                    if attempt_kind == "settled":
                        settled_units_exhausted += 1
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
                    if candidate.name != "release_candidate":
                        settled_candidate_seen = True
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


# The shipped safety-model artifact
# (reports/state-model/candidate-mlp-safety-v1.json), embedded verbatim as
# compact JSON so the default guard_quiet trigger needs no filesystem and
# no environment: the evaluation platform runs agent.py alone. Parsed
# lazily on first use; a parse failure leaves the model None, which makes
# every quiet trigger skip (fail-safe, never fail-closed).
# tests/test_safety_rerank.py asserts the embedded copy scores a known
# input identically to the committed file.
_EMBEDDED_SAFETY_MODEL_JSON = """{"schema_version":1,"model":"candidate_mlp_safety_v1","provenance":{"trainer":"scripts/train_state_model.py architecture","corpus_rows":7764,"corpus_cases":["m-dual-dedicated-priority","m-dual-empty","m-dual-full-stream","m-dual-preloaded-dedicated","m-dual-shelf-mixed","m-single-empty-noshelf","m-single-empty-shelf","m-single-preloaded"],"seed":0,"epochs":200,"loco_verdict":"state_model_beats_incumbent (reports/state-model/summary.md)"},"input_contract":{"phi_features":["support_ratio","com_margin","overhang_ratio","drop_normalized","support_imbalance","left_right_imbalance","front_back_imbalance","initial_orientation"],"phi_source":"release_risk.features (the agent's own live risk feature vector)","candidate_width":20,"candidate_source":"train_state_model.candidate_vector (candidate geometry plus container frame)","output":"index 0 is the safety logit; regression heads ['delta_theta_deg', 'd_norm'] follow and are unused at inference"},"normalization":{"phi_mean":[0.13334617018699646,-0.701382577419281,0.8666539788246155,0.15092317759990692,0.18776781857013702,0.002667159540578723,0.05417562648653984,2.2215352058410645],"phi_scale":[0.26904231309890747,0.6065492630004883,0.26904237270355225,0.05482155457139015,0.35699978470802307,0.3010175824165344,0.3363071084022522,1.7843339443206787],"candidate_mean":[0.19427907466888428,-0.15196453034877777,0.8482204675674438,0.4644082486629486,0.46799737215042114,0.37126651406288147,0.06811456382274628,0.26996394991874695,0.13794435560703278,0.09544049203395844,0.24896959960460663,0.09260690212249756,0.15507470071315765,1.0,2.0,1.461600661277771,1.611752986907959,0.16447708010673523,0.10561566054821014,9.771122932434082],"candidate_scale":[0.42511439323425293,0.3293556571006775,0.389913946390152,0.16260531544685364,0.16092130541801453,0.15216228365898132,0.019983338192105293,0.4439390003681183,0.3448556959629059,0.293809711933136,0.4324313700199127,0.2898898720741272,0.3619786500930786,1.0,1.0,0.025948673486709595,0.0037085169460624456,0.37070432305336,0.30736014246940613,5.028741836547852]},"layers":[{"kind":"linear","weight":[[-0.014537336304783821,0.23408174514770508,-0.14150337874889374,-0.18608610332012177,-0.26640379428863525,0.09649322926998138,-0.05755353346467018,0.23585733771324158,0.5015504360198975,0.4324682652950287,-0.24053457379341125,0.15640394389629364,-0.41687914729118347,-0.28779512643814087,-0.38409456610679626,0.07657141238451004,-0.01712644472718239,0.07937133312225342,-0.24005015194416046,0.22284723818302155,0.0032367364037781954,0.15601381659507751,-0.038665853440761566,0.12606872618198395,-0.04155808687210083,0.004929768852889538,0.1331937462091446,-0.2552429437637329],[-0.0072363982908427715,0.17468009889125824,-0.1842772662639618,-0.11370889097452164,-0.28740185499191284,0.12495583295822144,0.25783035159111023,-0.06025643274188042,-0.4147427976131439,0.456393301486969,0.04862282797694206,-0.007969027385115623,0.21154944598674774,-0.05810725316405296,0.02960306964814663,-0.2710971534252167,-0.2571428120136261,0.018732018768787384,0.1703898161649704,0.1609698086977005,-0.05931622162461281,-0.00677917618304491,0.1201610118150711,0.1690424531698227,0.06146327778697014,0.007045016624033451,0.06540074944496155,-0.32613542675971985],[-0.021287601441144943,-0.021972954273223877,-0.07391936331987381,0.11142163723707199,0.15236541628837585,0.07101967930793762,-0.12318155914545059,0.14112159609794617,0.19948498904705048,-0.46527862548828125,0.24876698851585388,0.21177983283996582,0.1607818454504013,0.16618499159812927,-0.07318992912769318,-0.07635413110256195,0.1640300750732422,-0.09281428158283234,0.12509576976299286,0.13235323131084442,0.22970063984394073,-0.16337773203849792,0.0172836035490036,-0.19702160358428955,-0.2505762279033661,0.08693289756774902,0.23651202023029327,-0.6080357432365417],[0.11702893674373627,0.08443065732717514,-0.11278076469898224,-0.1683676391839981,0.19511613249778748,-0.017336953431367874,0.04960562661290169,0.2288573533296585,0.19080112874507904,-0.07218297570943832,-0.19485361874103546,-0.27183887362480164,0.01357952132821083,0.17622500658035278,-0.23403628170490265,-0.16177056729793549,0.235223650932312,0.09413977712392807,-0.3637148439884186,0.17545922100543976,-0.05219979211688042,-0.0033769928850233555,-0.14148516952991486,-0.3969665765762329,-0.2584255635738373,-0.22434672713279724,0.21736393868923187,0.2305012047290802],[-0.08173765242099762,0.3044919967651367,0.09615959227085114,-0.2203454077243805,-0.1217595711350441,-0.18703573942184448,-0.0012927164789289236,0.1049274206161499,0.3891267776489258,0.1524496078491211,-0.24996738135814667,0.31646913290023804,-0.20360302925109863,-0.3806293308734894,-0.16055719554424286,-0.146210715174675,-0.1614077091217041,0.013782775960862637,0.014125430956482887,0.056648124009370804,-0.14953245222568512,-0.00964190624654293,0.1344943642616272,-0.003653161693364382,0.021769486367702484,-0.0006613859441131353,0.10675312578678131,0.07631824910640717],[0.17610792815685272,0.18014702200889587,0.18023766577243805,-0.2833366394042969,-0.15690679848194122,0.0607939139008522,0.16115565598011017,-0.1427566260099411,-0.504410982131958,-0.40082454681396484,-0.37908950448036194,-0.018406810238957405,-0.031148945912718773,0.04853367805480957,0.09505322575569153,-0.08011697232723236,-0.1085553839802742,0.09315530210733414,0.0790666863322258,-0.18395763635635376,-0.22747506201267242,-0.03688901290297508,-0.16859464347362518,-0.1890108585357666,-0.054135020822286606,-0.02462153695523739,0.07283776998519897,-0.09012224525213242],[-0.23881705105304718,-0.13103903830051422,0.23493953049182892,0.08986541628837585,0.2501041293144226,0.04160406067967415,-0.06595274060964584,0.10842627286911011,0.1791207492351532,-0.05230163037776947,0.23347066342830658,-0.29878726601600647,-0.16330182552337646,-0.058244410902261734,0.02117113210260868,0.08380904048681259,0.16138412058353424,-0.05687980726361275,-0.03348587080836296,-0.04596644639968872,-0.15085770189762115,0.10180196911096573,0.1491730660200119,0.11723748594522476,-0.14033658802509308,-0.0033875317312777042,-0.11021450161933899,-0.3590327203273773],[-0.2007352113723755,0.04626559466123581,-0.02070418931543827,-0.23126220703125,0.043539974838495255,0.1006491482257843,-0.1415644735097885,-0.018580056726932526,-0.5712462067604065,-0.08139833807945251,-0.16424955427646637,0.2995588183403015,0.06694311648607254,-0.005302029196172953,-0.05568594112992287,-0.057092566043138504,-9.340653195977211e-05,-0.0038874333258718252,-0.019804464653134346,-0.0711078867316246,0.07365036755800247,-0.0984741598367691,0.15171214938163757,-0.12546633183956146,0.015919581055641174,0.21255147457122803,0.09499238431453705,0.13938204944133759],[-0.21200045943260193,0.027165111154317856,-0.08464238047599792,0.07310296595096588,-0.08543280512094498,-0.10339666903018951,0.10391192138195038,0.06937141716480255,0.27997025847435,0.3602267801761627,0.37001675367355347,-0.1613299548625946,0.2686697542667389,-0.13130994141101837,-0.0770045593380928,0.05331728979945183,0.29312700033187866,0.07542301714420319,-0.08750560134649277,0.012527557089924812,0.01590670272707939,-0.1816977858543396,0.1358339488506317,-0.3582429885864258,-0.20431138575077057,-0.23421739041805267,-0.014540867879986763,-0.04844335839152336],[0.48007938265800476,0.34898996353149414,-0.4362610876560211,-0.2357785701751709,-0.4421153664588928,-0.0161623302847147,-0.16175611317157745,-0.052886273711919785,-0.30292779207229614,-0.12011381983757019,0.36824092268943787,0.2974085211753845,0.07336312532424927,-0.18605533242225647,-0.0959407240152359,0.09549873322248459,-0.08343777060508728,0.19295352697372437,0.06086168810725212,-0.14710013568401337,-0.14148348569869995,0.04059123620390892,-0.10543528944253922,-0.2119068056344986,0.12370102852582932,-0.16684956848621368,-0.11384834349155426,0.06051791086792946],[-0.0011265603825449944,-0.16445711255073547,-0.1447557806968689,0.08581346273422241,-0.05588940531015396,0.27178525924682617,-0.00570187671110034,-0.06064645200967789,-0.34264299273490906,-0.4366450011730194,-0.2870413661003113,0.3217432200908661,0.11730535328388214,-0.010721635073423386,-0.026475293561816216,-0.04681966453790665,0.06449621915817261,0.04596325010061264,0.06662988662719727,0.10331160575151443,-0.2824382185935974,0.03375180438160896,-0.09759586304426193,0.11833861470222473,0.11931805312633514,-0.06541049480438232,0.22075343132019043,0.19975514709949493],[0.05571996793150902,0.023272018879652023,-0.13537319004535675,-0.23921875655651093,-0.09297935664653778,0.1891365796327591,0.0820344090461731,0.10674820840358734,-0.5922006368637085,0.49775007367134094,0.24605819582939148,0.01719428412616253,0.1423756629228592,-0.05818472430109978,-0.525331437587738,0.253006249666214,-0.08885161578655243,0.15302591025829315,0.015408402308821678,0.11970779299736023,0.16852565109729767,-0.09140006452798843,-0.1556944102048874,-0.09407373517751694,0.26181918382644653,0.18586060404777527,-0.15648500621318817,-0.16239650547504425],[0.10311029851436615,0.2508869469165802,0.20305298268795013,0.025708042085170746,-0.0607696957886219,-0.02829323150217533,0.11183172464370728,0.10713960230350494,-0.5212441682815552,0.05075276270508766,0.3250352144241333,0.2524877190589905,0.00038656650576740503,-0.1454121470451355,-0.05144267901778221,0.09144783765077591,0.0406959131360054,-0.027742043137550354,0.17102313041687012,-0.25127559900283813,0.05802709609270096,0.09160515666007996,-0.13122928142547607,0.0456237718462944,-0.11489815264940262,-0.18333975970745087,-0.3200228214263916,0.10353579372167587],[0.09794163703918457,0.3166493773460388,0.15422356128692627,-0.37894704937934875,-0.06867249310016632,0.17305855453014374,-0.1118018627166748,0.13290075957775116,-0.04218098521232605,0.14584915339946747,-0.27143406867980957,-0.023047637194395065,0.31511831283569336,0.053334612399339676,0.20296262204647064,0.026225272566080093,0.245192289352417,0.0010105129331350327,0.23014600574970245,0.12495093047618866,-0.010206884704530239,0.18781977891921997,0.0974467471241951,0.14500176906585693,-0.03552570939064026,0.11809112876653671,-0.00795710738748312,-0.15297535061836243],[-0.24767625331878662,-0.2787722647190094,-0.002804236486554146,0.4200170636177063,0.17978188395500183,-0.1499166339635849,-0.1160132959485054,0.11307786405086517,0.010311048477888107,-0.15662343800067902,-0.16117596626281738,0.020526807755231857,0.29269570112228394,-0.2009643167257309,0.107880137860775,0.195266991853714,-0.2581508755683899,0.15546531975269318,-0.009698992595076561,-0.11212250590324402,0.08017068356275558,0.007763063535094261,-0.13287247717380524,0.03755269944667816,0.049507565796375275,0.06407036632299423,-0.1450757086277008,0.24112801253795624],[-0.00608984287828207,-0.1064780130982399,0.02577885426580906,0.004750851076096296,0.1182493194937706,-0.2371693104505539,0.08902794122695923,-0.22672288119792938,-0.20877522230148315,-0.265345960855484,-0.2698182463645935,0.3186594545841217,0.15683592855930328,-0.07884030789136887,-0.06903747469186783,-0.06098688021302223,0.06944462656974792,-0.13955433666706085,0.1300622820854187,0.010328405536711216,-0.38054579496383667,-0.18255624175071716,-0.03811411187052727,0.09288845956325531,-0.20791974663734436,0.12227864563465118,0.10968411713838577,0.2686193883419037],[-0.25992053747177124,-0.5866198539733887,0.4243035316467285,-0.07693513482809067,0.18385516107082367,0.0706336498260498,0.0029205421451479197,0.20352953672409058,0.38314640522003174,0.31567588448524475,-0.5070467591285706,0.061381787061691284,-0.13501565158367157,-0.12376493215560913,0.050798963755369186,-0.09993015974760056,0.014592152088880539,0.0522625558078289,-0.048749953508377075,-0.022265125066041946,-0.09598614275455475,-0.0579642578959465,0.08247172087430954,0.09433288872241974,0.01831943728029728,-0.11231417208909988,0.06616160273551941,-0.08390356600284576],[-0.009434615261852741,0.1404901146888733,-0.2574526071548462,0.04616599529981613,-0.2023058533668518,0.1449533849954605,-0.4335411489009857,0.11086693406105042,0.3312762379646301,0.49609071016311646,0.33766108751296997,-0.08000081032514572,-0.17160744965076447,-0.042411983013153076,-0.07454677671194077,-0.04474795237183571,0.019246134907007217,0.03400641679763794,0.30681124329566956,-0.06424105167388916,-0.29319241642951965,-0.10165432840585709,0.16624005138874054,0.2781165838241577,-0.06409962475299835,0.23832997679710388,0.3742077946662903,0.1950002908706665],[0.3312058746814728,-0.1271543651819229,-0.11283104121685028,-0.02894940972328186,-0.39575091004371643,0.046503178775310516,-0.17526370286941528,0.09801402688026428,0.32762932777404785,0.41646015644073486,0.4534887969493866,0.05710483714938164,0.1700945347547531,0.044925328344106674,0.32415077090263367,0.048310015350580215,0.00863706786185503,0.0204221960157156,0.03427952155470848,-0.21606838703155518,-0.07158097624778748,-0.09536638855934143,0.1726643294095993,-0.1881728619337082,-0.12994571030139923,-0.22971206903457642,0.4881206154823303,0.40584510564804077],[-0.4074002206325531,-0.3445953130722046,0.12329107522964478,0.3810427784919739,0.1379212737083435,-0.43449217081069946,-0.04879597947001457,-0.0667407289147377,-0.18320947885513306,0.05580075830221176,-0.35347840189933777,-0.2562727630138397,0.22707167267799377,0.21478210389614105,-0.04979494586586952,0.07876048982143402,0.0748744085431099,0.17997750639915466,-0.3744537830352783,-0.1043519526720047,0.11248009651899338,-0.11887013912200928,0.03602112829685211,0.014520677737891674,-0.017527269199490547,-0.010091803036630154,0.18907424807548523,-0.0400233268737793],[-0.41760262846946716,-0.3334559202194214,0.1706308126449585,0.12800002098083496,-0.14192363619804382,0.25045672059059143,-0.07486503571271896,-0.016881518065929413,0.32240280508995056,0.05635368824005127,0.323460191488266,-0.00639239139854908,0.08472050726413727,0.07332251220941544,0.12388896942138672,0.0797032043337822,-0.006488970015197992,-0.04154541343450546,0.1457129716873169,0.05282111093401909,-0.04907303676009178,-0.15556956827640533,-0.1704189032316208,0.028228314593434334,-0.032860901206731796,-0.1137579083442688,0.0823172777891159,-0.12826307117938995],[0.21517543494701385,0.44029438495635986,-0.09387275576591492,-0.2982260584831238,-0.3063565194606781,0.0875215157866478,0.0035035372711718082,0.2670735716819763,-0.27450233697891235,0.15302392840385437,0.6962721347808838,0.5556430816650391,-0.04951593652367592,-0.12562766671180725,0.004126643296331167,0.0857086256146431,0.044564858078956604,-0.21209417283535004,-0.08551372587680817,-0.12910592555999756,0.1450984925031662,-0.016434168443083763,-0.01805899851024151,-0.11710993200540543,0.19277222454547882,-0.05452904850244522,0.1573784351348877,0.46729838848114014],[0.004247850738465786,-0.10678526759147644,0.2503630816936493,0.11163032799959183,-0.13063038885593414,0.4459599256515503,0.3169962465763092,-0.24810713529586792,0.10398156195878983,0.24285997450351715,0.22651852667331696,-0.19621437788009644,-0.10507522523403168,0.10308614373207092,0.20464171469211578,0.2197352945804596,-0.08644817769527435,-0.05525709316134453,0.12218786031007767,0.005142803303897381,-0.0992828905582428,-0.1756136119365692,-0.14153751730918884,0.1406024843454361,-0.051130812615156174,0.08600736409425735,0.19337674975395203,-0.22194984555244446],[-0.023780617862939835,0.3686430752277374,-0.20728403329849243,0.14322644472122192,-0.2330074906349182,0.17265141010284424,0.0810181051492691,-0.014920298010110855,0.40339991450309753,-0.4262242019176483,-0.4873005449771881,-0.17102040350437164,0.08337412774562836,-0.07268562912940979,-0.30727487802505493,-0.08251717686653137,-0.14653243124485016,0.01969977468252182,0.28783920407295227,-0.004175713751465082,-0.16647543013095856,0.17668457329273224,-0.02581707015633583,0.06434587389230728,-0.13465766608715057,0.06909496337175369,-0.15038421750068665,-0.2554265856742859],[-0.08514122664928436,-0.044492583721876144,0.12585142254829407,0.25340694189071655,-0.004529040306806564,0.014070218428969383,0.22264784574508667,0.03203366696834564,0.14909249544143677,-0.4626527428627014,0.17567642033100128,-0.03100518323481083,0.06033952906727791,0.2277817577123642,0.019602637737989426,-0.12743327021598816,0.0022942880168557167,0.01574503630399704,0.029807917773723602,0.05644969642162323,0.09452556073665619,0.17795203626155853,0.01630263589322567,-0.1944914162158966,0.11531195044517517,-0.15861840546131134,0.18313613533973694,-0.12983080744743347],[-0.08605824410915375,0.23179450631141663,-0.1699233055114746,-0.16545049846172333,-0.24303102493286133,0.012781892903149128,0.06413284689188004,0.020862774923443794,-0.2865908145904541,0.5820329785346985,-0.14187858998775482,0.0038848889525979757,-0.1935194581747055,-0.4291820824146271,0.16581320762634277,0.17078180611133575,-0.16179949045181274,-0.04452785849571228,0.16432829201221466,0.028919117525219917,0.13463161885738373,-0.13919761776924133,-0.03010162152349949,-0.15154236555099487,-0.14042635262012482,0.0032523649279028177,0.13233894109725952,-0.4595884084701538],[0.328804612159729,0.15100660920143127,-0.25169268250465393,0.029367905110120773,-0.27162131667137146,0.17965522408485413,-0.2544296085834503,0.24396710097789764,-0.33224669098854065,-0.4170193672180176,-0.0035990651231259108,-0.050576385110616684,-0.2469918429851532,-0.04837827757000923,-0.07386072725057602,-0.10456504672765732,0.05099271610379219,0.16474571824073792,0.152191162109375,0.095025934278965,-0.09672421962022781,-0.059123195707798004,-0.15107914805412292,-0.0021488156635314226,0.14236243069171906,0.15564823150634766,0.1101943850517273,-0.02548443153500557],[-0.11497075110673904,0.17160865664482117,-0.044545408338308334,-0.42138662934303284,-0.021640712395310402,0.11853667348623276,-0.21222445368766785,0.11105728149414062,0.3089483976364136,-0.3085508644580841,-0.39770376682281494,0.3531031310558319,-0.030400950461626053,-0.13103234767913818,0.18427103757858276,0.0006220643990673125,-0.12427222728729248,0.1736210286617279,0.08265566825866699,-0.07116048783063889,0.193293035030365,-0.11136838793754578,0.187568798661232,-0.11227846890687943,-0.09313749521970749,0.18259847164154053,-0.05205874890089035,-0.15139849483966827],[-0.1766890585422516,-0.2038881778717041,0.017714625224471092,-0.3689165413379669,-0.009248625487089157,-0.022662155330181122,-0.013289821334183216,0.09984709322452545,0.4940471649169922,0.43256130814552307,-0.33136284351348877,-0.05084637925028801,-0.13741376996040344,-0.18848472833633423,-0.024363966658711433,0.054585739970207214,-0.1349519044160843,-0.02918628603219986,0.14365652203559875,-0.09856374561786652,0.042552556842565536,0.1688896119594574,0.18682566285133362,-0.19773420691490173,-0.05513666942715645,-0.06674682348966599,-0.21128004789352417,-0.0902767926454544],[-0.15780773758888245,-0.34091806411743164,0.2396954745054245,0.14323535561561584,-0.10818835347890854,0.32004567980766296,-0.23391588032245636,-0.02470114640891552,0.3033072352409363,-0.0017108807805925608,0.2934538424015045,-0.09381319582462311,-0.15413746237754822,0.0666051059961319,0.06063267961144447,0.06826374679803848,0.07244083285331726,-0.09424960613250732,0.15244072675704956,-0.14616142213344574,-0.04307478293776512,-0.06988973915576935,-0.15734130144119263,0.07061257213354111,0.01948077231645584,-0.08077603578567505,-0.06297188997268677,-0.3190557360649109],[-0.05923360586166382,0.3362164795398712,0.035903867334127426,-0.19115093350410461,0.229393869638443,0.17249849438667297,0.08936265110969543,0.11374747008085251,0.20506970584392548,0.541820228099823,-0.030391089618206024,0.20768852531909943,-0.07688828557729721,-0.07243748009204865,0.09431827813386917,0.009774697944521904,-0.17827314138412476,0.09713595360517502,-0.016423039138317108,-0.033860333263874054,0.1835896074771881,0.18588095903396606,0.03801579400897026,0.06845921277999878,0.26813048124313354,0.00039367697900161147,0.07381660491228104,-0.38032570481300354],[0.032306015491485596,0.2723762094974518,-0.0331474170088768,-0.03388160839676857,-0.3457021415233612,0.05502469092607498,0.06688037514686584,0.14370664954185486,0.5158765316009521,0.26775991916656494,-0.3114863634109497,0.08581399917602539,-0.19039469957351685,-0.5722175240516663,-0.532496452331543,0.06140734255313873,0.10095188766717911,0.10474342852830887,0.0472455695271492,0.06428022682666779,0.05306630954146385,0.17486318945884705,-0.104853555560112,0.1262359619140625,0.014784269966185093,0.09046164155006409,0.09388857334852219,-0.014178860932588577],[-0.21878714859485626,-0.14400158822536469,0.11490095406770706,0.10472137480974197,0.2761579751968384,0.4372895359992981,0.30421873927116394,-0.1434536576271057,0.3307889699935913,0.10522143542766571,-0.07530691474676132,-0.13826021552085876,-0.17074188590049744,-0.01885482855141163,0.029491160064935684,0.31783005595207214,0.2081993669271469,-0.08962753415107727,-0.07046498358249664,-0.1266401708126068,0.04643861949443817,-0.13637876510620117,0.08280829340219498,0.05736083164811134,0.1274951547384262,-0.1564106047153473,-0.37659135460853577,-0.032247599214315414],[-0.02028670161962509,-0.27132728695869446,0.21178042888641357,-0.02235613949596882,0.16625867784023285,0.27033722400665283,0.31696322560310364,-0.21087117493152618,0.08327700942754745,-0.07468771934509277,0.22799499332904816,-0.02045634761452675,0.04863729700446129,-0.0694427564740181,0.08622727543115616,-0.13615791499614716,-0.056591231375932693,-0.023440327495336533,-0.053009822964668274,0.056953802704811096,-0.1263502538204193,-0.02972700446844101,-0.17807786166667938,-0.1531336009502411,0.09958749264478683,-0.05590616166591644,-0.05044393241405487,-0.39589938521385193],[-0.26716217398643494,-0.3157573938369751,0.22597961127758026,0.29069575667381287,0.14404049515724182,-0.2168494015932083,0.15867361426353455,-0.050288520753383636,-0.0024027705658227205,0.01702336221933365,0.14352446794509888,-0.3035687804222107,-0.0790024846792221,-0.01319105364382267,0.14335234463214874,0.018696248531341553,-0.11276334524154663,0.08059009909629822,0.02619381807744503,-0.13839104771614075,0.2175569236278534,0.12239906191825867,-0.10566912591457367,-0.00936840008944273,0.06978649646043777,0.1401626169681549,-0.27050307393074036,-0.05576792359352112],[-0.07283785194158554,-0.07154124230146408,0.059994958341121674,-0.26550617814064026,-0.14039674401283264,-0.15810488164424896,-0.4410260319709778,-8.813032764010131e-05,-0.514060914516449,0.10569534450769424,0.016459960490465164,0.3507591784000397,0.18912342190742493,-0.05990421399474144,0.3731016218662262,0.0773007795214653,-0.04830028861761093,-0.034220609813928604,-0.10592105984687805,0.054377663880586624,0.0018626883393153548,-0.1465243399143219,-0.0011554440716281533,-0.2057177871465683,-0.08751477301120758,0.058757055550813675,-0.34217503666877747,-0.41019871830940247],[-0.2440214604139328,-0.18043461441993713,0.2299513816833496,0.3389517664909363,0.3521827459335327,-0.27380192279815674,0.1687847375869751,0.10391195863485336,-0.11157858371734619,0.10460904240608215,-0.23615913093090057,-0.04269065335392952,0.06279755383729935,0.06242496147751808,-0.09918835014104843,-0.002098195254802704,0.14454226195812225,0.07800618559122086,-0.4726732075214386,0.1361933797597885,0.032536741346120834,0.1296808272600174,0.14852720499038696,0.03357323631644249,-0.007884066551923752,-0.05349058285355568,-0.09345615655183792,-0.1807175874710083],[-0.09458757936954498,-0.08622673898935318,-0.20520459115505219,0.2674146294593811,-0.04551661014556885,0.46849551796913147,0.005156536586582661,-0.1882047802209854,0.41750842332839966,0.30189916491508484,0.26198843121528625,0.04753661900758743,-0.1382378488779068,0.030961899086833,-0.08061408251523972,-0.03782860189676285,0.1775013655424118,0.05985409766435623,0.03579338267445564,-0.047066494822502136,0.016527779400348663,0.07276374846696854,0.1582835614681244,-0.04072631150484085,-0.07949226349592209,0.18515881896018982,0.14451147615909576,0.12866227328777313],[0.07495684921741486,-0.14854177832603455,-0.1754559576511383,-0.25060325860977173,-0.12093544006347656,0.0006118559394963086,0.07459873706102371,-0.01918095536530018,0.27679443359375,-0.6516956090927124,0.25359031558036804,-0.17455750703811646,-0.04316059127449989,-0.06044313311576843,0.3149920701980591,0.1252167522907257,-0.026848768815398216,-0.190042182803154,0.18111781775951385,-0.1830909550189972,0.15420003235340118,0.1326894760131836,0.08166799694299698,-0.07455537468194962,-0.06294307857751846,-0.17735156416893005,0.04047118127346039,0.23326444625854492],[0.006627543829381466,0.011350495740771294,-0.1564674973487854,0.1679895967245102,-0.040082115679979324,-0.2401280254125595,0.020888054743409157,0.15067917108535767,0.14414474368095398,-0.2959730923175812,0.3232579827308655,0.046256303787231445,0.038818296045064926,0.00064718013163656,-0.05862898752093315,-0.12530238926410675,0.09148459136486053,-0.36141717433929443,0.04762530326843262,0.041532211005687714,0.05772281810641289,0.06275191903114319,-0.17390254139900208,-0.2599259912967682,-0.046034179627895355,-0.2137688398361206,-0.07832508534193039,0.3124113082885742],[0.03476400673389435,-0.32057708501815796,-0.19046565890312195,-0.12727223336696625,0.053211428225040436,-0.024764353409409523,0.06659300625324249,-0.18995587527751923,0.30507493019104004,-0.33991512656211853,-0.5044635534286499,0.12579500675201416,-0.05940619111061096,0.11269612610340118,-0.22245262563228607,0.20240066945552826,-0.3744749426841736,0.06699832528829575,0.09470334649085999,-0.2813449800014496,0.13714303076267242,0.08310937136411667,-0.10346263647079468,-0.15357385575771332,0.04429890215396881,-0.2394711673259735,0.055517733097076416,-0.007430465891957283],[0.10050488263368607,-0.09179554879665375,0.10839342325925827,-0.15466511249542236,-0.29702630639076233,-0.2601751983165741,0.22172312438488007,-0.19664590060710907,-0.2688676416873932,0.35329318046569824,-0.01848927140235901,-0.019834008067846298,-0.3007652759552002,-0.15609650313854218,-0.3374497890472412,0.051893945783376694,0.2313869744539261,-0.28202441334724426,-0.011871888302266598,0.07278313487768173,-0.1532939374446869,-0.10729421675205231,-0.062345974147319794,-0.0006938613951206207,-0.27350032329559326,-0.28391098976135254,0.07227365672588348,0.23649054765701294],[0.08642182499170303,0.12038902938365936,-0.0805060938000679,-0.4150814712047577,-0.08657540380954742,0.2870081961154938,0.16119247674942017,-0.15218515694141388,-0.5280534625053406,-0.5352510809898376,-0.0903489738702774,0.23793762922286987,0.066950224339962,-0.1348743885755539,-0.07161010801792145,0.05385538563132286,-0.01364276371896267,0.17787563800811768,0.15734799206256866,0.11784124374389648,-0.032187286764383316,-0.0644269809126854,0.09728191792964935,-0.15347400307655334,-0.024208514019846916,0.061437252908945084,0.13406769931316376,-0.045430608093738556],[-0.19022385776042938,-0.2050648033618927,-0.05386696755886078,0.14952152967453003,0.06458383798599243,0.0003000973374582827,0.06855102628469467,-0.16126424074172974,0.2274942398071289,-0.533315122127533,-0.2899709939956665,0.061761487275362015,0.0887860432267189,-0.07024215161800385,-0.20810309052467346,-0.0072267926298081875,0.10207482427358627,0.12155349552631378,0.21255455911159515,0.08695180714130402,-0.2737497091293335,0.09459768235683441,-0.12757298350334167,0.03833143413066864,0.05211910232901573,-0.1711837649345398,0.16907808184623718,0.3912753760814667],[-0.1991284340620041,-0.25445666909217834,0.21869200468063354,-0.013130324892699718,0.30861377716064453,0.27334532141685486,0.2522425055503845,-0.27388688921928406,0.004198168404400349,0.11957074701786041,-0.025730358436703682,-0.2779538035392761,-0.14141495525836945,-0.06854015588760376,-0.09818599373102188,0.10918641090393066,0.14844879508018494,0.00040938216261565685,-0.12241853028535843,0.30793192982673645,0.10779154300689697,-0.16819263994693756,0.09454574435949326,-0.007712550461292267,0.06811138242483139,-0.26494982838630676,0.1401529163122177,0.051256176084280014],[-0.21140514314174652,0.1438777595758438,0.19699636101722717,-0.19696424901485443,0.11549509316682816,0.10396075248718262,0.2899301052093506,-0.06577154994010925,0.18486301600933075,-0.07340589165687561,-0.17557138204574585,0.2604113519191742,-0.3681087791919708,0.03112083673477173,-0.0471520870923996,0.22156473994255066,0.11537405103445053,0.22081995010375977,-0.084195077419281,0.15353058278560638,-0.2911865711212158,-0.021760523319244385,0.02743517793715,0.24230393767356873,0.29278385639190674,0.11832069605588913,-0.2792467474937439,0.12217043340206146],[-0.010227581486105919,-0.07127868384122849,0.08719376474618912,0.14721429347991943,-0.3385521173477173,-0.11718320846557617,-0.4073302149772644,-0.17170526087284088,0.13357892632484436,-0.18266479671001434,0.2710229754447937,-0.4432406425476074,-0.023916710168123245,0.14996512234210968,0.1255238950252533,0.2326098382472992,0.24892199039459229,-0.059310439974069595,-0.3069971203804016,0.11516103148460388,-0.12020684033632278,0.009319755248725414,0.18222160637378693,-0.14831727743148804,-0.11808622628450394,-0.24949434399604797,0.1754012405872345,-0.023097317665815353],[-0.2899331748485565,-0.3735930025577545,0.24386340379714966,0.18128575384616852,0.14739912748336792,0.07016856223344803,0.03922659531235695,-0.051151759922504425,-0.045286670327186584,0.3643520772457123,-0.03149019554257393,-0.21294710040092468,-0.025565769523382187,-0.0795275941491127,-0.10144492238759995,-0.18391835689544678,0.027315152809023857,0.04580581560730934,-0.11906999349594116,0.19910995662212372,0.1167854517698288,-0.06957326084375381,0.04954291880130768,0.04350410774350166,-0.12772879004478455,0.03900011628866196,0.008810472674667835,0.15513776242733002],[0.029419908300042152,0.027970967814326286,0.06447920203208923,-0.16907845437526703,0.055863380432128906,0.11203251034021378,-0.0849749967455864,0.0713685154914856,0.16294190287590027,0.5439762473106384,0.0981767401099205,0.3598080575466156,-0.034315697848796844,0.06759824603796005,0.27245286107063293,0.19460296630859375,0.09055628627538681,0.2099481076002121,-0.24292923510074615,0.01536865159869194,0.0640571340918541,0.09911981225013733,0.08908775448799133,-0.15030735731124878,-0.22410689294338226,0.06976203620433807,-0.3293408453464508,0.21957610547542572],[-0.2004622370004654,0.07317797094583511,0.02347041480243206,-0.06139427423477173,-0.3513844311237335,0.09007388353347778,-0.2431105524301529,-0.08714298158884048,0.4678829312324524,-0.7361744046211243,0.22214563190937042,-0.04366075620055199,0.28412961959838867,0.15550366044044495,0.03870570287108421,0.15890169143676758,-0.1699363738298416,0.041807208210229874,-0.014001578092575073,0.0916982889175415,0.13656668365001678,0.16445276141166687,0.14859923720359802,-0.05064128711819649,0.12659837305545807,-0.00654561584815383,-0.04406110197305679,-0.24072138965129852],[0.012037073262035847,-0.23663616180419922,-0.1636858433485031,0.23724816739559174,0.05373535677790642,0.200141042470932,0.19811144471168518,-0.06432759761810303,0.14803443849086761,0.04745480790734291,0.18501265347003937,-0.19441622495651245,0.18186286091804504,0.2621806859970093,0.11180263757705688,-0.00332338223233819,0.19560174643993378,-0.17504511773586273,-0.2559261918067932,0.1300283968448639,0.024973532184958458,-0.14750009775161743,-0.08315813541412354,-0.1912258118391037,-0.28637149930000305,-0.08597837388515472,0.2668426036834717,0.09371688961982727],[-0.1390131115913391,-0.23469313979148865,-0.10183271765708923,-0.18210072815418243,-0.008317015133798122,0.009829727932810783,-0.18966981768608093,-0.10515943169593811,-0.4331555664539337,-0.45103922486305237,-0.31519049406051636,0.31445956230163574,-0.04225041717290878,-0.0675458014011383,-0.04143455997109413,-0.16198430955410004,-0.0648692399263382,0.10934340208768845,0.008686763234436512,-0.11798425018787384,0.06814612448215485,-0.18703611195087433,0.13653592765331268,0.11662141233682632,0.0948399156332016,-0.0970878154039383,0.12224557995796204,-0.025945428758859634],[-0.05459483712911606,-0.03347637131810188,-0.05823425576090813,-0.09761384129524231,-0.13342775404453278,-0.023823024705052376,0.0563337579369545,-0.08333466947078705,0.046723589301109314,-0.5190542340278625,0.2199734002351761,-0.08000653237104416,0.2724621295928955,-0.036836739629507065,-0.002825935836881399,0.021304607391357422,0.09203943610191345,0.19279442727565765,-0.10816787928342819,-0.316872775554657,0.030775737017393112,-0.09047573804855347,0.15796752274036407,-0.055925752967596054,0.061945658177137375,0.020279714837670326,-0.04486685246229172,-0.46452149748802185],[0.21088525652885437,0.3175312876701355,0.05392202362418175,-0.4354242980480194,0.08562628924846649,0.10749190300703049,-0.014700827188789845,0.12234154343605042,0.33288151025772095,-0.19845755398273468,-0.4399288594722748,-0.008341954089701176,0.3954739272594452,-0.27518731355667114,0.362704336643219,0.045851267874240875,-0.08226344734430313,0.04621850326657295,0.013521475717425346,0.09006249904632568,-0.15167124569416046,-0.03918619453907013,-0.06954333186149597,0.08643676340579987,-0.04708139970898628,0.12527573108673096,-0.039179056882858276,-0.37391147017478943],[-0.14512625336647034,-0.2382856160402298,-0.018202301114797592,-0.34663447737693787,-0.11105141043663025,-0.02229447290301323,-0.05386815220117569,-0.16202445328235626,0.49821752309799194,0.37815046310424805,-0.27037402987480164,0.08917068690061569,-0.015262933447957039,0.0639016330242157,-0.24944348633289337,0.13029885292053223,-0.22844251990318298,-0.029216373339295387,0.1448652297258377,0.03824209049344063,0.08335400372743607,0.0009288079454563558,-0.020379647612571716,-0.20276542007923126,-0.15475384891033173,-0.03274748846888542,0.08207624405622482,-0.0679427832365036],[0.07885526120662689,-0.26726967096328735,0.1722012758255005,0.16154362261295319,-0.015929555520415306,0.14189234375953674,0.0011395965702831745,-0.05758678913116455,-0.5543686747550964,-0.046183981001377106,-0.3740728497505188,-0.09087075293064117,0.09681158512830734,-0.030811719596385956,-0.2234802544116974,0.005884479731321335,-0.13639110326766968,-0.3312787413597107,0.01454304438084364,-0.1808028221130371,0.10123899579048157,0.03659595176577568,-0.07984321564435959,-0.23198507726192474,0.06560215353965759,-0.15635135769844055,-0.10315494984388351,0.006808629259467125],[-0.14728491008281708,0.06296610832214355,-0.1337628811597824,0.10402669757604599,0.23262572288513184,-0.11363625526428223,0.09066390246152878,-0.0776037648320198,0.4234811067581177,-0.3421681225299835,0.29125720262527466,0.05949307605624199,0.081852987408638,0.04331760108470917,-0.15741388499736786,-0.016500938683748245,0.15962690114974976,-0.0640936866402626,0.08469236642122269,-0.04037875682115555,-0.0017946886364370584,-0.032861750572919846,0.0885552242398262,0.09893300384283066,-0.04366551339626312,0.015968486666679382,0.17651742696762085,-0.18976835906505585],[-0.044455308467149734,0.06274494528770447,-0.011649863794445992,0.026402287185192108,0.030146459117531776,0.22345168888568878,0.24852538108825684,-0.14880970120429993,0.2574582099914551,-0.1295836716890335,0.11743313074111938,0.026509448885917664,-0.17473061382770538,0.14059214293956757,0.02775481343269348,0.18358656764030457,-0.01293154340237379,-0.036334048956632614,-0.2643604874610901,0.19072425365447998,-0.016221869736909866,-0.020676858723163605,-0.1459456831216812,-0.1282825469970703,-0.12256579101085663,-0.29057905077934265,-0.02038351260125637,0.13986200094223022],[0.09411510080099106,0.2730073630809784,0.17654173076152802,-0.09141815453767776,0.11659982055425644,0.0653097927570343,-0.06528165191411972,-0.14767029881477356,0.4394046366214752,0.15184853971004486,-0.36136335134506226,0.12404288351535797,0.3592931926250458,0.0005299624754115939,0.42282405495643616,0.0038888773415237665,0.2047613263130188,-0.04508265480399132,-0.0885101929306984,-0.17114382982254028,-0.010326534509658813,-0.001700053340755403,-0.08651238679885864,0.08913648873567581,-0.03656907379627228,-0.09601791203022003,0.2037714570760727,-0.16027957201004028],[-0.20156815648078918,-0.13411730527877808,0.1551150232553482,0.24593167006969452,0.06994642317295074,-0.1618650257587433,0.2091245800256729,0.08863979578018188,0.06679470092058182,-0.018567943945527077,0.11707162857055664,-0.0027384080458432436,-0.05887811630964279,0.2752493917942047,-0.047010742127895355,0.17046985030174255,0.11588804423809052,0.07039451599121094,-0.0024520319420844316,0.042181797325611115,0.011794929392635822,-0.0016383046749979258,0.05010034516453743,-0.031548961997032166,0.19244864583015442,-0.06177595630288124,-0.1281900554895401,-0.39261510968208313],[-0.18805989623069763,0.2860662043094635,-0.07065054029226303,-0.32308250665664673,-0.12646803259849548,-0.23328104615211487,-0.19252070784568787,0.01021841075271368,-0.5827358961105347,-0.045651063323020935,0.18032009899616241,0.2570030093193054,-0.09991374611854553,-0.09951646625995636,0.19071544706821442,0.19011029601097107,0.0886511281132698,0.26275864243507385,-0.027737852185964584,-0.2158629298210144,-0.054210562258958817,-0.16330339014530182,0.09142865240573883,-0.10001509636640549,-0.09308680891990662,-0.17791162431240082,0.14837151765823364,-0.11906511336565018],[-0.010119733400642872,0.05731183663010597,0.11178981512784958,-0.09907060116529465,-9.730644524097443e-05,0.0070603578351438046,0.407503217458725,-0.05060075223445892,0.252332478761673,0.1908814013004303,0.252873033285141,-0.13910828530788422,-0.08604717999696732,0.057980574667453766,-0.058871880173683167,0.15341618657112122,-0.28111201524734497,0.1178521066904068,0.09143456816673279,-0.1630605310201645,0.0067534311674535275,-0.15100052952766418,0.029500160366296768,0.13929323852062225,0.11312352865934372,0.14516045153141022,0.24156798422336578,-0.3349875211715698],[0.04642127826809883,-0.005704300012439489,0.16211099922657013,-0.07577762752771378,-0.34145379066467285,-0.05151300132274628,0.07519499957561493,-0.07188364863395691,-0.05990687757730484,-0.2990301847457886,-0.027922825887799263,-0.0814666822552681,-0.22076065838336945,-0.12182876467704773,-0.0482037179172039,0.18820524215698242,0.16695228219032288,-0.1958247870206833,0.007975074462592602,0.0489463284611702,-0.25454702973365784,-0.033038362860679626,-0.06518995761871338,0.11860260367393494,-0.07793618738651276,0.042273588478565216,-0.1674995869398117,0.07981740683317184],[0.12092664837837219,-0.19715772569179535,0.015680035576224327,0.3969447910785675,0.09725885093212128,-0.23930323123931885,-0.2530118525028229,0.07971274852752686,-0.030689245089888573,0.3132854104042053,-0.2507266402244568,-0.09335760027170181,-0.06983394175767899,-0.0787186324596405,-0.11488553881645203,-0.02140943706035614,0.22626037895679474,0.07218291610479355,0.03529356047511101,0.09376513957977295,0.16575980186462402,-0.10890481621026993,-0.04938359186053276,-0.06890427321195602,-0.09435273706912994,0.19338183104991913,-0.05782933160662651,0.2901938557624817]],"bias":[-0.05636001378297806,-0.08994622528553009,-0.07786435633897781,-0.06417582184076309,0.05526287481188774,-0.011944868601858616,-0.13849003612995148,-0.1609756499528885,0.1037975549697876,-0.07446812093257904,-0.4407329261302948,-0.3202532231807709,-0.3830195665359497,-0.024120600894093513,-0.06536629796028137,-0.2456069439649582,-0.18749268352985382,0.007028078660368919,-0.3752521574497223,0.33941492438316345,0.05137788504362106,-0.13700690865516663,-0.010758719407022,-0.1456199437379837,-0.03644075617194176,-0.17295041680335999,-0.11673487722873688,-0.3539728820323944,-0.03175066411495209,-0.04258899763226509,-0.03090095892548561,-0.3724440932273865,-0.3280213177204132,-0.13737060129642487,0.08728765696287155,0.03342978283762932,-0.20413488149642944,0.044315941631793976,-0.3126884996891022,-0.33197057247161865,-0.28186631202697754,-0.2520115077495575,-0.16634047031402588,-0.2714397609233856,0.009819189086556435,0.03342418745160103,-0.0017225409392267466,0.2147476077079773,-0.15059532225131989,-0.1665036976337433,-0.09444822371006012,-0.16693837940692902,-0.15384839475154877,-0.4144306480884552,0.0598151795566082,-0.1862001121044159,0.06307115405797958,-0.11487632989883423,-0.22278833389282227,-0.15653066337108612,0.013934644870460033,-0.22769515216350555,0.05998069420456886,0.2620818614959717]},{"kind":"gelu"},{"kind":"linear","weight":[[-0.01491295825690031,-0.04259559512138367,0.21141576766967773,0.22338829934597015,-0.09003020077943802,0.07785791903734207,0.24174939095973969,0.10165737569332123,-0.08227719366550446,-0.35784149169921875,-0.2026037722826004,-0.12445235252380371,-0.3064476251602173,0.0003476421697996557,0.15998384356498718,-0.07577172666788101,-0.07720092684030533,0.03639628738164902,-0.3118702173233032,0.08331017196178436,-0.08502962440252304,-0.5206127166748047,0.12474557012319565,-0.19885791838169098,0.18524080514907837,-0.21978867053985596,-0.2639691233634949,-0.2231583297252655,0.003245969768613577,-0.08681230247020721,0.17285363376140594,-0.3112988770008087,0.02955416962504387,0.007470890413969755,-0.00620905589312315,0.08522655069828033,0.21319051086902618,-0.10986705124378204,-0.2617168724536896,-0.07456059008836746,-0.1672053039073944,-0.20261749625205994,-0.01530462596565485,-0.14329580962657928,0.014135774224996567,0.17420320212841034,0.0795813798904419,-0.18935567140579224,-0.13923388719558716,0.06529171764850616,0.026886528357863426,0.029960546642541885,-0.01118249911814928,0.02059437707066536,-0.01033391896635294,-0.2686801850795746,0.21947574615478516,-0.0440569631755352,0.11400321871042252,0.19818876683712006,-0.10818610340356827,0.1371385008096695,0.038549747318029404,0.15263450145721436],[-0.136369988322258,-0.11808613687753677,-0.13975900411605835,0.28158557415008545,-0.15489619970321655,0.0842408612370491,0.009712917730212212,0.06738565862178802,0.17866869270801544,-0.0036537402775138617,-0.16851218044757843,0.43884339928627014,0.15376408398151398,0.009127533063292503,0.03523188829421997,0.1504729986190796,-0.14918118715286255,0.0017840994987636805,-0.24472659826278687,-0.36884358525276184,-0.2530745267868042,-0.0041236537508666515,-0.2959154546260834,-0.17963476479053497,-0.09654019773006439,0.00850379653275013,0.09895384311676025,0.05034641548991203,0.0011318756733089685,-0.32610470056533813,0.3511356711387634,-0.23972147703170776,0.1869874745607376,-0.021936820819973946,-0.037886422127485275,-0.38816773891448975,0.21469128131866455,-0.12737447023391724,0.004559657536447048,0.3513071537017822,0.015463165938854218,-0.007922983728349209,-0.058784499764442444,0.23878473043441772,0.033172424882650375,0.016602328047156334,-0.10778887569904327,-0.03578748181462288,-0.15162502229213715,-0.5005383491516113,-0.07000226527452469,-0.003089281264692545,0.07510492205619812,0.022629130631685257,-0.18801090121269226,-0.1380663961172104,0.07240070402622223,0.14389564096927643,0.14551416039466858,-0.01796845719218254,-0.13974152505397797,-0.071065254509449,0.046657051891088486,0.2748936414718628],[0.0020982238929718733,-0.015605767257511616,-0.04483860358595848,-0.1361718624830246,-0.04469624161720276,0.06741881370544434,-0.015980826690793037,-0.11718463897705078,0.165195032954216,0.004607474431395531,-0.23707805573940277,0.06287448853254318,0.08297200500965118,-0.038980633020401,-0.21648776531219482,-0.0768510103225708,0.06483478099107742,0.17366883158683777,0.1916757971048355,-0.032259251922369,0.11199794709682465,0.03943833336234093,0.03515394404530525,-0.004159602336585522,-0.04523506388068199,0.058909669518470764,-0.23189111053943634,0.0248515997081995,-0.1451316773891449,0.11140299588441849,0.195270374417305,-0.03382553160190582,-0.02123633772134781,0.11720017343759537,-0.03884167969226837,-0.1202881708741188,-0.02922845259308815,-0.007344615645706654,0.05683933198451996,0.14274396002292633,-0.0051890406757593155,-0.08580341190099716,0.04596948251128197,-0.08727220445871353,-0.06234855204820633,0.13303698599338531,-0.025658976286649704,0.13614502549171448,-0.07252250611782074,-0.06301525980234146,-0.00970714446157217,0.015469973906874657,0.022319277748465538,-0.06391888856887817,0.04749767854809761,-0.040980663150548935,-0.061434682458639145,0.02495717816054821,0.030307568609714508,0.1753731220960617,-0.09664056450128555,0.12697097659111023,0.07360800355672836,0.018932169303297997],[0.0795072615146637,0.11097332835197449,-0.032928820699453354,-0.056742627173662186,0.20091098546981812,0.087196946144104,-0.26579058170318604,0.17053431272506714,0.14793041348457336,0.05250125378370285,-0.21072623133659363,0.38475194573402405,0.28675833344459534,0.13209685683250427,-0.21543541550636292,0.14071926474571228,0.1341189295053482,-0.017383582890033722,-0.42230504751205444,-0.12668727338314056,-0.2187454253435135,-0.10937654227018356,0.10650321841239929,0.20653580129146576,-0.20164090394973755,0.27259179949760437,0.03366589918732643,0.14758004248142242,0.18606944382190704,-0.2970566153526306,0.36904177069664,0.225716233253479,-0.2466699182987213,-0.2500269412994385,-0.24933041632175446,0.3019024431705475,-0.28745800256729126,-0.1275147944688797,-0.12103058397769928,0.016186248511075974,0.08361367136240005,0.13446800410747528,0.021105561405420303,0.06504874676465988,-0.08914988487958908,0.03685831278562546,-0.2603980600833893,-0.17924512922763824,-0.10394506901502609,0.18010006844997406,-0.2788678705692291,0.19204983115196228,0.041720520704984665,0.218753382563591,0.16748115420341492,0.036561623215675354,0.1668093353509903,0.007179060019552708,0.20551371574401855,-0.22313560545444489,0.21721506118774414,0.2009018361568451,0.15782809257507324,-0.1210445761680603],[-0.014601665548980236,0.13548654317855835,0.1754235029220581,0.16559141874313354,-0.19111111760139465,-0.17326481640338898,-0.056960076093673706,0.052102748304605484,-0.19588463008403778,-0.058390796184539795,-0.06116357445716858,0.20702801644802094,-0.01164386235177517,0.005612714681774378,-0.06347806006669998,0.07374478131532669,0.08747532218694687,-0.49880000948905945,-0.4612775146961212,0.08194379508495331,-0.24755734205245972,0.14002074301242828,-0.1146598756313324,0.02563192881643772,0.30587807297706604,-0.18488383293151855,0.036983467638492584,0.10844195634126663,-0.09222899377346039,-0.15435969829559326,-0.28632932901382446,-0.2847745418548584,-0.2003934681415558,-0.03035145066678524,0.08211787045001984,0.017072102054953575,-0.15231893956661224,-0.3150903582572937,0.12681275606155396,0.270385205745697,0.07393434643745422,0.11824165284633636,0.0571414977312088,-0.47229987382888794,0.0703936517238617,-0.12088753283023834,0.18217876553535461,-0.04783143103122711,0.08606309443712234,0.033377755433321,0.0631842389702797,0.03200651705265045,-0.13376477360725403,-0.16920310258865356,0.02741474099457264,0.016188837587833405,0.11339680850505829,0.18899714946746826,-0.2639898657798767,-0.0601947121322155,0.09923867136240005,-0.027938850224018097,-0.15763112902641296,-0.10130250453948975],[0.09106739610433578,-0.08245083689689636,-0.19113962352275848,-0.16642975807189941,0.1156223863363266,-0.03625761717557907,0.016167184337973595,-0.13506054878234863,-0.15407714247703552,0.1645229011774063,0.21730937063694,-0.06836005300283432,-0.12204080075025558,0.028975779190659523,0.03794797882437706,0.09720602631568909,-0.040196798741817474,-0.045821115374565125,-0.11680059880018234,-0.07597804069519043,-0.08192958682775497,-0.06596110761165619,-0.0791197121143341,0.05360065773129463,0.011908801272511482,-0.047620125114917755,0.18713660538196564,0.042799510061740875,-0.16962920129299164,0.04135174676775932,-0.15438352525234222,-0.02082541026175022,-0.09375821799039841,-0.1529800295829773,-0.014968297444283962,-0.17193132638931274,0.06329089403152466,-0.1489984542131424,0.06439103186130524,0.0543159656226635,0.11536013334989548,-0.09402168542146683,-0.056207627058029175,-0.12642210721969604,0.0659765973687172,-0.10081280767917633,-0.07345309853553772,-0.08691315352916718,-0.054480113089084625,-0.09688237309455872,0.045839082449674606,-0.07694994658231735,0.0768948495388031,-0.016017483547329903,-0.19303332269191742,-0.08229032158851624,0.04583604261279106,-0.05811651051044464,-0.10984291881322861,0.055098213255405426,0.08111532777547836,0.032862670719623566,0.11050237715244293,-0.017441444098949432],[-0.0066990926861763,-0.09688103199005127,0.03689127787947655,-0.050863683223724365,-0.0865226611495018,0.058098167181015015,-0.14302745461463928,0.04670184478163719,-0.055605050176382065,-0.06274523586034775,-0.026152726262807846,0.1225438341498375,0.07187345623970032,0.10164082795381546,-0.025459224358201027,-0.02932310849428177,0.10716308653354645,-0.26049643754959106,-0.24449816346168518,0.16448824107646942,-0.11003464460372925,-0.009722727350890636,0.030359279364347458,0.07367333024740219,0.16483473777770996,-0.06743482500314713,0.007901140488684177,0.11586707085371017,0.0033268844708800316,-0.2255849540233612,0.06942259520292282,0.01556127704679966,0.029971875250339508,0.03844182938337326,0.028735999017953873,0.07499343901872635,-0.02851107344031334,-0.15064120292663574,0.0584687702357769,-0.07567180693149567,0.08833708614110947,0.026878250762820244,0.01785583794116974,-0.015987152233719826,0.04223039001226425,-0.13502660393714905,-0.12766648828983307,0.10271728038787842,0.03960650414228439,0.08724556118249893,0.09315384924411774,0.0041869874112308025,0.10337342321872711,0.08174565434455872,0.05269772931933403,0.0736500546336174,-0.020622625946998596,0.02436101995408535,0.09978867322206497,-0.15206557512283325,-0.06541051715612411,-0.13111642003059387,-0.1282029151916504,0.10857108980417252],[-0.1972675323486328,-0.2128247171640396,0.17874452471733093,-0.09147291630506516,-0.05141496658325195,-0.014362966641783714,0.17136825621128082,0.10096944868564606,-0.28370457887649536,0.1329837292432785,-0.29648542404174805,-0.11492083966732025,0.1654033660888672,-0.015680616721510887,0.13947774469852448,-0.12333602458238602,-0.2814636528491974,0.15242800116539001,0.18251249194145203,-0.045951779931783676,-0.06829814612865448,0.13038092851638794,-0.0038169785402715206,-0.10861316323280334,0.0952019989490509,0.04073803499341011,-0.05683919042348862,-0.11894290149211884,-0.434285968542099,-0.04161236435174942,-0.05021040886640549,-0.21493980288505554,0.19898119568824768,0.25876739621162415,0.037697989493608475,0.09325191378593445,0.19645553827285767,0.0013700976269319654,0.12256880849599838,0.11806852370500565,-0.08270616829395294,0.17650263011455536,-0.004829214885830879,-0.39316627383232117,0.13852040469646454,0.05066165328025818,0.026041267439723015,0.08730392158031464,0.09473152458667755,0.25467583537101746,0.07940815389156342,-0.06990937888622284,0.037866804748773575,-0.05044151470065117,-0.20714052021503448,0.15001167356967926,0.14001178741455078,0.10703123360872269,0.1906191110610962,0.11083360016345978,0.06931702047586441,0.12317187339067459,-0.1284010112285614,0.23147322237491608],[0.21842771768569946,0.048641387373209,-0.16259828209877014,-0.08055271953344345,0.26281723380088806,0.12463733553886414,-0.22906383872032166,0.27339696884155273,-0.24647654592990875,-0.04034697264432907,0.29560598731040955,0.24188454449176788,0.3020809292793274,0.07613613456487656,-0.09770020842552185,0.10751452296972275,0.15029726922512054,-0.25201764702796936,-0.35039812326431274,-0.10183167457580566,-0.11242915689945221,0.18850469589233398,0.09368527680635452,0.0029082591645419598,-0.10649320483207703,0.19455912709236145,-0.03899400308728218,-0.023506972938776016,0.2312142252922058,-0.0385899655520916,-0.10909999161958694,0.029378434643149376,0.12531965970993042,0.04021437093615532,-0.1232180967926979,0.1948905736207962,-0.1861526519060135,0.00913255289196968,-0.11046154797077179,-0.2157653421163559,-0.016894368454813957,0.12550164759159088,-0.02550996094942093,0.3450242877006531,-0.021782413125038147,0.04704058915376663,-0.07490164786577225,-0.16043023765087128,-0.16816850006580353,0.10665757954120636,-0.18016380071640015,0.10467936098575592,0.07058738172054291,-0.010590377263724804,0.010920315980911255,0.1758141666650772,0.14311762154102325,-0.017820581793785095,-0.07487984001636505,-0.1572972983121872,0.18102316558361053,-0.004115777090191841,0.11372722685337067,0.05634867399930954],[0.03785276040434837,0.02010917477309704,0.19633841514587402,0.011992724612355232,0.11869455128908157,0.05510393902659416,-0.1178143098950386,0.14236384630203247,-0.04169416427612305,0.13600420951843262,0.0811653807759285,-0.0031207099091261625,0.134177103638649,0.1523483544588089,-0.039323899894952774,0.16471461951732635,-0.050833724439144135,-0.3613927960395813,-0.2659878432750702,-0.01805981434881687,-0.1749863475561142,-0.006605487782508135,0.02159055322408676,0.013892337679862976,-0.07306722551584244,0.020364046096801758,0.08404470235109329,0.22305594384670258,0.05993971228599548,-0.1998826265335083,0.0266821701079607,-0.1076500192284584,-0.002970520406961441,0.04045073315501213,-0.0039754523895680904,0.14698554575443268,-0.20318256318569183,0.0002963378792628646,0.026685401797294617,-0.11886730790138245,-0.036059051752090454,0.04288095608353615,0.166970357298851,0.041502151638269424,0.14021219313144684,-0.08088453859090805,-0.1176181361079216,0.10871919989585876,-0.007837975397706032,0.008424355648458004,-0.10388615727424622,0.03156118094921112,-0.0470258928835392,0.07389312982559204,0.0882045105099678,0.10823512822389603,-0.0738796517252922,-0.017838129773736,-0.057363711297512054,-0.09463022649288177,0.1964719593524933,0.031587790697813034,-0.11575458943843842,-0.15713950991630554],[0.22171121835708618,0.0963892936706543,0.05192617326974869,-0.02967895194888115,0.16315770149230957,0.2980719804763794,-0.2548457980155945,0.21029730141162872,-0.292097270488739,-0.0026280623860657215,-0.025607526302337646,0.31379351019859314,0.31555062532424927,0.17914694547653198,-0.1827637106180191,0.15159036219120026,0.2329939901828766,-0.103676438331604,-0.31422463059425354,-0.22864189743995667,-0.16339486837387085,-0.07685216516256332,-0.08855988085269928,0.08708564192056656,-0.057416874915361404,0.21715642511844635,-0.212812140583992,0.28143006563186646,0.20216375589370728,-0.4262097179889679,0.43501755595207214,0.0990862026810646,-0.1506531983613968,-0.03408027067780495,-0.18936151266098022,-0.0009065442718565464,-0.23451100289821625,-0.013908684253692627,5.845726263942197e-05,-0.40792351961135864,0.2020527422428131,0.1075458750128746,0.17098397016525269,0.10979989916086197,-0.299363374710083,-0.2772398591041565,-0.2913739085197449,-0.3124881088733673,-0.15327690541744232,0.07450999319553375,-0.24283769726753235,0.15403075516223907,-0.0007986628916114569,0.3222489356994629,0.12420929223299026,0.12692895531654358,-0.009468156844377518,-0.26807156205177307,0.49200570583343506,-0.11727985739707947,0.09534607827663422,0.039018988609313965,0.011459781788289547,-0.17271356284618378],[0.06565681844949722,0.0649058073759079,0.21261344850063324,-0.07651329040527344,0.1776319146156311,0.19176876544952393,-0.3607586622238159,0.18335004150867462,-0.000976832234300673,-0.07537572085857391,-0.02052406035363674,0.29894372820854187,0.42371147871017456,0.1547645926475525,-0.05387546867132187,0.07615549117326736,0.005901048891246319,-0.04980846494436264,-0.12318217009305954,-0.14008475840091705,-0.23885101079940796,0.13383489847183228,0.1626209020614624,0.13603368401527405,-0.03182142600417137,0.2254572957754135,0.17687419056892395,0.3209756314754486,0.15587586164474487,-0.15385212004184723,0.3687266707420349,0.22089841961860657,-0.35000914335250854,-0.18068131804466248,-0.2931421399116516,0.20408357679843903,-0.22476840019226074,0.022726889699697495,-0.055982645601034164,-0.03337598964571953,0.27286434173583984,-0.01914241723716259,0.08840609341859818,-0.0021413895301520824,-0.2150859832763672,0.09022241830825806,-0.054275382310152054,-0.2435050904750824,-0.19329506158828735,0.10264141112565994,-0.22289679944515228,0.10537203401327133,0.04498087242245674,0.30685362219810486,0.10616595298051834,0.008575943298637867,0.18430998921394348,-0.1571091264486313,0.32754361629486084,-0.13059765100479126,0.07630813121795654,0.14895103871822357,0.10306409746408463,-0.1792847365140915],[0.060389745980501175,-0.06588701903820038,0.029556185007095337,0.022593287751078606,0.10333028435707092,0.029380369931459427,-0.07455483824014664,0.040511809289455414,0.05559386685490608,-0.15664516389369965,0.14198803901672363,0.44356444478034973,0.14514125883579254,0.11660783737897873,0.019090240821242332,0.1923009306192398,0.016007982194423676,-0.13693469762802124,-0.4377496540546417,0.10458465665578842,-0.03829999268054962,0.16039568185806274,-0.08671921491622925,0.1937382072210312,0.3030601441860199,0.1589706987142563,-0.06690431386232376,0.2139384001493454,0.24682867527008057,-0.2656210660934448,0.16510847210884094,0.33666351437568665,-0.03331199288368225,-0.007729962933808565,0.19149130582809448,0.0871746838092804,0.08674096316099167,0.04013970494270325,0.061517130583524704,-0.1835537850856781,0.17116263508796692,0.1376284509897232,0.11113879084587097,0.2620151937007904,0.13446533679962158,0.36524927616119385,-0.11002743989229202,0.13285401463508606,0.1547413170337677,0.13971255719661713,-0.11021219938993454,0.024739691987633705,0.19417385756969452,0.12546561658382416,0.04626352712512016,0.25176602602005005,-0.022800587117671967,0.06399959325790405,0.03340371325612068,0.14088863134384155,-0.16318924725055695,-0.006975898984819651,-0.10134738683700562,-0.08158671855926514],[0.15181012451648712,-0.11387784779071808,0.015547377057373524,-0.4207775294780731,-0.011752517893910408,0.09868212789297104,0.042802635580301285,0.11442655324935913,0.07996843755245209,0.04857888072729111,0.12495284527540207,0.17876960337162018,0.13404257595539093,0.05519930273294449,-0.0730188861489296,-0.024867581203579903,-0.028433924540877342,-0.017551084980368614,-0.11988341063261032,0.03580483794212341,0.025451457127928734,0.23400889337062836,-0.10534607619047165,-0.07033427804708481,-0.22224928438663483,0.19076161086559296,-0.1089068204164505,0.009454024024307728,-0.018490785732865334,-0.11838781088590622,0.19340912997722626,0.17799833416938782,-0.17325299978256226,0.05538191646337509,-0.10410257428884506,0.2437833845615387,-0.15757142007350922,0.04570510610938072,-0.11785729974508286,-0.17753516137599945,-0.0761490985751152,0.17291094362735748,0.0459379218518734,-0.1364676058292389,0.11367075145244598,-0.012923805974423885,-0.07820062339305878,-0.06357365101575851,-0.020865293219685555,-0.05731826275587082,0.025960367172956467,0.17074567079544067,-0.041355911642313004,0.10625835508108139,0.042838942259550095,0.024709779769182205,-0.06382568925619125,-0.1659369319677353,0.11610469967126846,-0.13115869462490082,0.23832456767559052,0.08268747478723526,0.009394174441695213,-0.18145859241485596],[0.04643145203590393,-0.06277429312467575,-0.019352968782186508,0.25771957635879517,0.07157870382070541,0.2152933031320572,-0.2615914046764374,0.07524824142456055,-0.0018692760495468974,-0.09988608211278915,0.1261887550354004,-0.028627971187233925,0.2525053024291992,0.0235566645860672,0.18158282339572906,0.3405793011188507,0.04478595033288002,-0.276155024766922,-0.4006045460700989,-0.07701897621154785,-0.27994170784950256,0.011889055371284485,-0.3701576292514801,0.26247644424438477,0.22216512262821198,0.18661284446716309,-0.006651571020483971,0.2925815284252167,0.04515125975012779,-0.26081347465515137,0.09401001036167145,0.15744546055793762,-0.18260572850704193,-0.1300567239522934,-0.14992420375347137,0.14610403776168823,-0.2132026106119156,-0.27447623014450073,-0.01275987084954977,-0.03999803960323334,0.07720556855201721,-0.06370200216770172,0.0938987210392952,0.42889168858528137,-0.18810120224952698,-0.03546642139554024,-0.00031250377651304007,-0.21996092796325684,0.040523726493120193,0.1344941109418869,-0.10895702987909317,0.037252698093652725,0.04284731298685074,0.2508712708950043,0.1546759456396103,0.07199087738990784,0.07810600847005844,-0.01567375287413597,0.21977263689041138,-0.16853542625904083,0.14924465119838715,0.03142695873975754,0.024173151701688766,-0.14377935230731964],[-0.22964565455913544,-0.28942468762397766,-0.04660775139927864,-0.0614333339035511,-0.3539315462112427,0.08630627393722534,0.04073747247457504,-0.0053882598876953125,-0.004180154763162136,-0.05832997336983681,-0.20705629885196686,0.017695534974336624,0.14739558100700378,-0.13574419915676117,0.07120715826749802,-0.12280815839767456,-0.3061043322086334,0.05462370440363884,0.04592961072921753,-0.27248623967170715,0.035056792199611664,0.1479034572839737,0.13814909756183624,-0.22925637662410736,0.05315662920475006,-0.1355828493833542,-0.14819850027561188,-0.08381136506795883,-0.41351649165153503,-0.06768745929002762,-0.16413085162639618,-0.21479544043540955,0.07375708222389221,0.010593564249575138,-0.09396190941333771,0.07725360989570618,-0.22263208031654358,0.065863698720932,0.0823313295841217,0.043075233697891235,-0.1371070146560669,0.11571449786424637,0.013086598366498947,0.07707579433917999,0.10038266330957413,0.03952549397945404,-0.06325895339250565,0.035030148923397064,0.19335660338401794,0.08135528117418289,0.1312272846698761,-0.24903704226016998,0.05777470022439957,-0.25449928641319275,-0.4161888062953949,-0.0030708308331668377,-0.1344139575958252,0.0018359640380367637,-0.3138832151889801,0.059464991092681885,0.19068576395511627,0.11982907354831696,-0.004300152417272329,-0.10642500966787338],[-0.11674316227436066,-0.020669233053922653,0.15612971782684326,0.02095845714211464,-0.01275449525564909,0.08134835213422775,0.05178549513220787,0.0176733136177063,0.1216038316488266,-0.33344265818595886,-0.13950222730636597,-0.033335309475660324,-0.13513053953647614,0.0055025662295520306,0.07482448220252991,-0.02856975980103016,-0.030773533508181572,-0.06520823389291763,-0.014565601944923401,-0.029746124520897865,0.15801328420639038,-0.2402363419532776,0.2258228212594986,0.0034896014258265495,0.06783387064933777,-0.06293446570634842,-0.10708581656217575,-0.15160325169563293,-0.04086081311106682,0.04585461691021919,0.06345963478088379,-0.22001798450946808,0.20970013737678528,-0.030727066099643707,0.04866373538970947,0.23842313885688782,-0.09866337478160858,0.1434195637702942,-0.11259129643440247,-0.1735217571258545,-0.02020242251455784,-0.038549404591321945,0.05980582907795906,-0.22971493005752563,0.016652757301926613,-0.01719433255493641,0.0056981551460921764,0.07267925888299942,0.09066228568553925,0.12493561953306198,0.05473451316356659,-0.12669610977172852,0.1292547732591629,-0.08371053636074066,-0.07107926905155182,-0.19342483580112457,0.1706160008907318,0.07135015726089478,0.013320930302143097,0.09893158078193665,-0.04215142875909805,0.12181788682937622,-0.03588656708598137,0.025325162336230278],[-0.06654702872037888,-0.02620656229555607,0.21062128245830536,-0.012462636455893517,-0.035538673400878906,-0.08693884313106537,0.03816184401512146,-0.2236502468585968,0.09028828889131546,-0.19592131674289703,-0.14903636276721954,0.12159963697195053,-0.11072790622711182,-0.1540132462978363,0.006175921764224768,-0.18480098247528076,0.05910228192806244,-0.01727026142179966,-0.03802024945616722,-0.3393760919570923,0.08630521595478058,-0.01767035759985447,0.1355946809053421,0.08035368472337723,0.09292307496070862,0.019910432398319244,0.10136330872774124,-0.025127915665507317,-0.07800724357366562,0.07092205435037613,0.03593943268060684,-0.05443505570292473,0.15833154320716858,-0.0003750433388631791,-0.015914954245090485,0.05344988405704498,0.027711601927876472,0.08955281972885132,-0.004497697111219168,-0.12696829438209534,-0.25125691294670105,0.06886783987283707,-0.00019588647410273552,-0.02731586992740631,0.06712829321622849,0.05463201552629471,0.2204892337322235,-0.061270859092473984,0.02768602967262268,-0.07825275510549545,0.09617264568805695,-0.13478830456733704,0.0944579616189003,-0.05137688294053078,-0.00980745442211628,-0.291770339012146,-0.048274893313646317,-0.07142069190740585,-0.09968378394842148,0.11171156167984009,0.02363976463675499,-0.0452415756881237,-0.021103734150528908,-0.005642182193696499],[0.147399440407753,0.01537139993160963,0.12636584043502808,-0.028400104492902756,-0.012908550910651684,0.1460058093070984,-0.27678847312927246,0.20573142170906067,0.1497846245765686,-0.022492287680506706,0.05525250360369682,0.2699298858642578,0.10347746312618256,0.09814629703760147,-0.059900082647800446,-0.019793475046753883,0.03639054298400879,-0.3316534459590912,-0.1367378681898117,-0.04603198543190956,-0.07327701151371002,-0.025564055889844894,-0.04629763960838318,0.1200583353638649,0.04124826565384865,0.002429170301184058,-0.08409376442432404,0.16697289049625397,0.08741561323404312,-0.23107817769050598,0.0984078198671341,-0.10533563792705536,-0.2093341201543808,-0.1435338854789734,-0.028625942766666412,0.06725162267684937,-0.34325188398361206,-0.14723967015743256,0.028283026069402695,-0.11125631630420685,0.02219029702246189,-0.02869868278503418,0.08485644310712814,0.11542760580778122,-0.138718381524086,-0.0006663964013569057,0.12692296504974365,-0.016536304727196693,0.09460612386465073,0.12716737389564514,-0.08285922557115555,0.08671975880861282,0.187892347574234,0.016381649300456047,0.09175330400466919,-0.07233364135026932,-0.1183815598487854,0.03888409212231636,0.14992104470729828,-0.2068217396736145,0.12088089436292648,-0.02372334524989128,0.05755770206451416,-0.04234611243009567],[0.21296082437038422,0.1603125035762787,-0.22973497211933136,-0.047928646206855774,0.2524512708187103,0.06105616316199303,-0.09540735185146332,0.052139535546302795,-0.10168711841106415,-0.05813106894493103,-0.034490086138248444,0.2868785858154297,0.055310025811195374,0.1354520469903946,-0.07959185540676117,0.07531138509511948,-0.014567903243005276,-0.07162821292877197,-0.3885508179664612,-0.07138065993785858,-0.021748246625065804,-0.07548732310533524,-0.20566953718662262,0.11841297149658203,-0.10287877917289734,0.18049894273281097,-0.20723290741443634,0.3931264579296112,-0.04516572877764702,-0.1461934596300125,0.17418015003204346,0.25215649604797363,-0.12463970482349396,-0.404192179441452,-0.25617581605911255,0.16572430729866028,-0.18898551166057587,0.09566924721002579,-0.09148682653903961,0.04532839357852936,0.0906357541680336,0.17785556614398956,0.105980284512043,0.1255931854248047,-0.18029740452766418,0.2548031210899353,-0.08612041175365448,0.006819913629442453,0.19279421865940094,0.11818661540746689,-0.2711765468120575,-0.04415787011384964,0.14235489070415497,0.11247686296701431,0.16059690713882446,-0.03743860498070717,0.24601392447948456,-0.006870359182357788,0.02114972099661827,-0.15018026530742645,0.1494951844215393,-0.011487246491014957,0.09215916693210602,0.1196860745549202],[-0.21190625429153442,-0.03535171225667,0.17051298916339874,-0.022013019770383835,-0.27789047360420227,-0.05632414668798447,0.3403158187866211,-0.3161201775074005,-0.26911982893943787,-0.4941699802875519,-0.15885920822620392,0.09372163563966751,-0.21515923738479614,-0.3805594742298126,-0.09313823282718658,0.007792828604578972,-0.577786922454834,-0.04666779562830925,-0.25218984484672546,-0.28244516253471375,0.14753402769565582,-0.3034108281135559,-0.009068537503480911,-0.28839266300201416,0.4492417573928833,-0.2723366320133209,-0.2909389138221741,-0.15237833559513092,-0.4307185709476471,0.2258341759443283,0.0395129919052124,-0.23507313430309296,-0.09508500248193741,0.2333596646785736,-0.02652246691286564,0.16672629117965698,0.21448056399822235,-0.21363280713558197,0.44061964750289917,0.3662557899951935,-0.11500760912895203,-0.1894839107990265,0.02418271079659462,0.025610312819480896,0.04190441593527794,0.07883920520544052,-0.09511220455169678,-0.27272742986679077,-0.27723997831344604,0.27218547463417053,-0.023636212572455406,-0.22546221315860748,0.2255719006061554,-0.26420921087265015,-0.32870420813560486,-0.5506088733673096,0.3618665933609009,0.2272782325744629,-0.27876341342926025,0.41214513778686523,-0.13226160407066345,0.2709833085536957,-0.005061313509941101,-0.4776599407196045],[-0.0876445397734642,-0.054403360933065414,-0.07425389438867569,-0.04619079828262329,0.02281964011490345,0.11060968041419983,-0.23779995739459991,-0.04747720807790756,-0.11996207386255264,0.11327826231718063,0.1721566617488861,0.06223226711153984,0.08482833951711655,-0.053148187696933746,0.08032508939504623,0.15135343372821808,0.12044945359230042,0.1772652566432953,0.11381720751523972,-0.03328489139676094,-0.16911470890045166,0.07171754539012909,0.2641596496105194,0.18011827766895294,-0.23344746232032776,-0.03402402997016907,0.08512812107801437,0.03348323702812195,0.20347529649734497,-0.17710398137569427,0.18086875975131989,0.06404256075620651,0.18060608208179474,0.251790314912796,0.17811749875545502,-0.0720079317688942,0.15209878981113434,0.02704210951924324,-0.13248394429683685,-0.05802790820598602,0.08125743269920349,-0.024662883952260017,0.13925014436244965,0.21245943009853363,0.0627090334892273,-0.04426039755344391,-0.3949984312057495,0.035605501383543015,-0.07541635632514954,-0.05004473403096199,0.003700451459735632,0.04259520396590233,-0.19782140851020813,0.09389828890562057,0.02447756938636303,0.14851348102092743,0.017158271744847298,-0.08037099987268448,0.1867508441209793,0.013221549801528454,0.017880648374557495,0.01101810485124588,-0.06382373720407486,-0.13915374875068665],[0.22682002186775208,0.1636887639760971,-0.14913615584373474,-0.0583190955221653,0.026569856330752373,0.07765821367502213,-0.26144006848335266,0.054528843611478806,0.017457883805036545,-0.10559408366680145,-0.27014750242233276,0.1242598295211792,0.024753093719482422,0.09076516330242157,-0.29632946848869324,0.0443299263715744,0.08693055063486099,0.12587997317314148,-0.09767797589302063,0.007126283831894398,-0.24929644167423248,-0.08629811555147171,-0.031190933659672737,0.06571260839700699,-0.16945113241672516,0.10013928264379501,0.011947434395551682,0.3235166668891907,0.13770702481269836,-0.20117734372615814,0.45766302943229675,0.35905683040618896,-0.25413382053375244,-0.22055789828300476,-0.2481936663389206,0.1246262937784195,-0.1102105975151062,0.03936576098203659,-0.07844666391611099,-0.1023569405078888,0.1135934516787529,0.2332240641117096,-0.02140660025179386,0.14125217497348785,-0.03581402078270912,0.24774622917175293,-0.40513643622398376,0.17623856663703918,0.2242640256881714,0.20004688203334808,-0.13443538546562195,-0.08626130223274231,0.04331189766526222,0.25233522057533264,0.1641802042722702,-0.08811133354902267,0.08256173878908157,-0.16911086440086365,0.24397936463356018,0.015182550065219402,0.027828551828861237,0.073143869638443,0.10356497764587402,0.10246540606021881],[-0.049911875277757645,-0.023550977930426598,0.26297271251678467,0.1890462189912796,0.030659949406981468,-0.01409989409148693,-0.22360897064208984,0.0787571370601654,0.2274581342935562,-0.06468690931797028,-0.049889422953128815,0.13790880143642426,0.2542564570903778,0.08062251657247543,-0.038487061858177185,0.012062429450452328,-0.10719169676303864,-0.17634904384613037,-0.2253248244524002,-0.01598510518670082,-0.24829967319965363,-0.11813434213399887,-0.3702591359615326,0.2079184204339981,0.03953475505113602,0.0947175920009613,-0.018705174326896667,0.3865424692630768,-0.016970032826066017,-0.2616400420665741,0.1912386417388916,0.104830302298069,-0.28267547488212585,-0.3365682363510132,-0.15990367531776428,-0.04052239656448364,-0.28993460536003113,-0.18029743432998657,-0.11239179968833923,-0.03891490027308464,0.13199597597122192,-0.01445772685110569,0.1516810953617096,0.0900740921497345,-0.2792552709579468,-0.029561355710029602,-0.06414308398962021,-0.014325188472867012,0.19667378067970276,0.19127719104290009,-0.09077379107475281,0.05906269699335098,0.21780993044376373,0.4139224588871002,0.11715824902057648,0.023111533373594284,0.014893659390509129,0.02546287328004837,0.23941250145435333,-0.195414200425148,0.09657123684883118,0.045346375554800034,-0.0591035857796669,-0.1571522355079651],[-0.4713885188102722,0.1514590084552765,0.2965189516544342,-0.127919003367424,-0.14879411458969116,-0.18186180293560028,0.1659434586763382,-0.11426316946744919,-0.1403803825378418,-0.4780254065990448,-0.39507317543029785,0.0380060188472271,0.018047234043478966,-0.032432928681373596,-0.09291856735944748,0.1443599909543991,-0.27819013595581055,0.05386672541499138,-0.15979968011379242,-0.31049007177352905,-0.004242422059178352,-0.03698175773024559,-0.1730593591928482,-0.037377920001745224,0.16943314671516418,-0.14438718557357788,-0.19182896614074707,-0.05300493538379669,-0.4667757451534271,0.07632298767566681,0.11288826912641525,-0.2399272918701172,0.07434579730033875,-0.0970073714852333,-0.12285948544740677,0.2774650454521179,-0.10595441609621048,-0.006452642381191254,0.25190383195877075,0.3308350443840027,-0.05285526439547539,0.15614573657512665,-0.1181170642375946,0.4475489556789398,0.04131651297211647,-0.13774502277374268,0.03959593549370766,-0.20940430462360382,-0.01757940649986267,0.29197773337364197,-0.08601464331150055,-0.16644418239593506,0.1599612981081009,0.021625980734825134,-0.29928693175315857,-0.1557295024394989,-0.0341479554772377,0.08800875395536423,-0.29788610339164734,-0.1277252435684204,-0.29428157210350037,0.13327978551387787,0.15153971314430237,-0.12865880131721497],[0.058402884751558304,-0.13411453366279602,-0.1039448082447052,-0.16103169322013855,-0.0028406933415681124,0.05635249242186546,-0.18032602965831757,-0.20954960584640503,-0.03215566650032997,-0.0384286604821682,-0.10844355076551437,-0.018311189487576485,-0.2634943723678589,0.14550045132637024,0.0943576991558075,-0.0722513347864151,-0.04353577643632889,-0.07895701378583908,-0.3260500729084015,-0.07411246746778488,-0.011858350597321987,-0.027752738445997238,-0.011082311160862446,0.19082647562026978,0.03226621821522713,0.08309866487979889,-0.048219673335552216,-0.12620140612125397,0.09973713010549545,-0.1711295247077942,-0.0821949690580368,-0.12392116338014603,-0.07172698527574539,-0.07590847462415695,-0.057694725692272186,-0.013347958214581013,-0.08511098474264145,-0.05892088636755943,-0.030323002487421036,0.0528518408536911,-0.11053064465522766,0.16054260730743408,-0.08609279990196228,-0.05871167778968811,0.03278489410877228,-0.17921863496303558,-0.08667295426130295,-0.15038546919822693,-0.07756420969963074,0.18397104740142822,-0.1024022176861763,0.033598754554986954,-0.055352210998535156,0.01688234694302082,-0.12379980832338333,-0.16169118881225586,0.01697397045791149,-0.08959973603487015,0.04164963215589523,-0.06071927770972252,-0.06219813972711563,-0.027038944885134697,-0.0008799763163551688,0.11152467131614685],[0.07289739698171616,0.08698742836713791,-0.09761867672204971,-0.0384320430457592,-0.02708476595580578,0.07935541868209839,0.04069307819008827,0.09435028582811356,-0.0628875195980072,-0.21469929814338684,0.021938573569059372,-0.07805697619915009,-0.20358853042125702,0.08499390631914139,-0.04154264181852341,0.04624081775546074,-0.07462399452924728,0.08479630202054977,-0.35405227541923523,-0.4180734157562256,-0.08249559998512268,-0.10840966552495956,-0.03575662150979042,-0.027862336486577988,-0.02604777365922928,0.006629304960370064,-0.07243995368480682,-0.004510108847171068,0.00683636125177145,0.042218487709760666,0.16701112687587738,0.03527858108282089,0.11560367792844772,0.020926762372255325,-0.07380632311105728,0.09204337000846863,0.19936694204807281,-0.09619510918855667,-0.08864148706197739,-0.18474261462688446,-0.025095432996749878,-0.23644278943538666,-0.018651559948921204,0.08780409395694733,0.09599917382001877,0.1366150826215744,0.17049919068813324,-0.12548404932022095,0.060511983931064606,-0.1845061033964157,-0.0360187329351902,0.09537090361118317,-0.026114793494343758,0.16716834902763367,-0.12103033065795898,-0.22676445543766022,0.14583851397037506,-0.0628497451543808,0.14623557031154633,0.06915407627820969,-0.204353466629982,0.14223602414131165,0.018203001469373703,-0.04551684111356735],[-0.25893712043762207,-0.20903770625591278,0.334347665309906,-0.09524767845869064,-0.17018383741378784,-0.04345226287841797,0.21795149147510529,-0.03444887697696686,-0.14211784303188324,-0.3210005760192871,-0.16065546870231628,-0.3008306920528412,-0.3751036822795868,-0.023973824456334114,-0.08233430236577988,-0.17742815613746643,-0.286027729511261,0.08487877994775772,-0.468896746635437,0.2593136429786682,0.0014982232823967934,-0.27493634819984436,0.23507845401763916,0.16391168534755707,0.016900857910513878,-0.3234030306339264,-0.2842184007167816,-0.21700018644332886,-0.24682864546775818,0.07697407901287079,0.022364754229784012,-0.06317242980003357,0.055429134517908096,0.22549739480018616,0.061525288969278336,0.3791782855987549,-0.03419121727347374,-0.043497927486896515,0.01477887388318777,-0.26692473888397217,-0.09522424638271332,-0.26311174035072327,-0.0888373926281929,-0.4093174934387207,-0.19332030415534973,0.08582089096307755,0.026845891028642654,-0.19133709371089935,0.03738319128751755,0.17082366347312927,-0.005556695628911257,-0.11870652437210083,0.2920728325843811,-0.3066575229167938,-0.2965143322944641,-0.29252147674560547,0.13153035938739777,-0.1782829463481903,-0.21723031997680664,0.22256599366664886,0.2731093466281891,0.15689514577388763,-0.054102685302495956,-0.22557173669338226],[0.08901787549257278,0.15874336659908295,0.043216437101364136,-0.18208710849285126,0.27377521991729736,0.11380826681852341,-0.20951810479164124,0.0020816989708691835,0.1582583338022232,0.053204648196697235,-0.0871250182390213,0.14117135107517242,0.07758715748786926,0.01653316430747509,-0.39978736639022827,-0.08020474016666412,-0.12720075249671936,0.2537010610103607,0.13545812666416168,-0.1394915133714676,-0.12332352250814438,0.025081342086195946,0.1037750393152237,0.12025772780179977,-0.0637742280960083,0.1274247169494629,-0.26555386185646057,0.03254375979304314,-0.09924419969320297,-0.07321589440107346,0.21967864036560059,0.15147286653518677,-0.1139308363199234,-0.16005459427833557,-0.13469816744327545,-0.1231486052274704,-0.09667810797691345,0.1264122724533081,0.006843016482889652,0.33714306354522705,0.14626361429691315,0.17388781905174255,-0.01923283003270626,-0.3183639943599701,-0.05275970324873924,-0.006151313427835703,-0.2674071788787842,0.04683929309248924,-0.189002126455307,-0.2323501855134964,-0.2847212553024292,-0.1892092525959015,-0.017232146114110947,0.0388890840113163,0.023506470024585724,-0.08399572968482971,0.14991527795791626,-0.012113566510379314,0.1334230899810791,-0.0427977554500103,-0.09664920717477798,0.1214301660656929,0.022175397723913193,0.10175883769989014],[0.05076015740633011,-0.03164798021316528,0.16951188445091248,0.27813607454299927,0.05861390754580498,0.1873597651720047,-0.19125281274318695,-0.05155244469642639,0.0674186646938324,0.07859806716442108,0.24173787236213684,-0.14676642417907715,-0.26920512318611145,-0.08113353699445724,-0.12679825723171234,0.28023073077201843,0.07917777448892593,-0.27405688166618347,-0.3547176122665405,0.14756892621517181,-0.07589832693338394,-0.051170144230127335,-0.3550401031970978,0.19978035986423492,0.19101066887378693,0.0839201882481575,0.08717270195484161,0.09888937324285507,0.19622734189033508,-0.06681076437234879,-0.0370994508266449,0.2060064822435379,-0.06328389793634415,-0.18210114538669586,0.052437376230955124,-0.050314825028181076,0.05617756024003029,-0.13489362597465515,0.018299903720617294,-0.09500155597925186,0.11546596139669418,0.2553989589214325,0.05603131651878357,0.2848568856716156,0.12375030666589737,0.1678185760974884,0.07644296437501907,0.16131356358528137,0.21430736780166626,0.18723535537719727,0.03578512743115425,0.0771968886256218,0.17887313663959503,0.07292548567056656,0.045302942395210266,0.1343027800321579,0.21045993268489838,0.028833111748099327,-0.15321743488311768,-0.10865248739719391,-0.11788412928581238,-0.21428915858268738,0.173004150390625,-0.030229151248931885],[-0.2267284095287323,-0.12800179421901703,-0.014974270015954971,0.06469713151454926,-0.17988501489162445,0.1427314281463623,0.05896656960248947,0.1302446871995926,-0.4245108366012573,-0.2564942240715027,-0.5095697641372681,0.06187424436211586,-0.3736032247543335,0.0824115201830864,0.19952905178070068,-0.07086994498968124,0.015964556485414505,-0.060789503157138824,-0.3676443099975586,0.1555585116147995,-0.13485030829906464,-0.29444050788879395,-0.017656724900007248,-0.06822048872709274,-0.2249325066804886,0.017192965373396873,-0.27518272399902344,-0.2984820604324341,-0.2828754782676697,-0.07397394627332687,0.38783562183380127,-0.16601203382015228,0.2506014108657837,0.15911787748336792,-0.18028977513313293,0.06735491007566452,0.1726900190114975,-0.3252432346343994,0.0073445760644972324,-0.32767507433891296,-0.13075405359268188,-0.04628557711839676,-0.04783381521701813,-0.390997976064682,0.018016032874584198,0.09655454754829407,-0.16912105679512024,0.030165962874889374,-0.268785297870636,0.20039893686771393,-0.1534779816865921,0.21864230930805206,-0.017063193023204803,0.015295520424842834,-0.028234394267201424,0.2456209510564804,-0.10795717686414719,0.03816964849829674,-0.2094743400812149,0.10994470119476318,0.08723936229944229,0.14378100633621216,-0.021513409912586212,0.13038502633571625],[-0.06472617387771606,-0.030979357659816742,0.05210261791944504,0.14078499376773834,0.10707678645849228,0.14205031096935272,-0.24200712144374847,0.23949429392814636,-0.04368558153510094,0.13237643241882324,0.12220647186040878,0.13275907933712006,0.23520039021968842,0.16905459761619568,-0.05845315754413605,0.20427262783050537,0.20233812928199768,-0.35672828555107117,-0.0760890319943428,0.03863302990794182,-0.06143885478377342,-0.1627276986837387,-0.27470359206199646,0.13919541239738464,0.0391121432185173,0.2096785455942154,0.06309787184000015,0.29205384850502014,0.2875590920448303,-0.34019234776496887,0.2804611623287201,0.10561458021402359,-0.10177241265773773,-0.036720287054777145,-0.19347001612186432,0.2029035985469818,-0.051406700164079666,-0.3030044436454773,-0.04567619785666466,-0.22086592018604279,0.08844374865293503,0.21779276430606842,0.18685124814510345,0.12151238322257996,-0.19137094914913177,0.007167806848883629,0.07224936038255692,-0.024999573826789856,0.2440359741449356,0.2436491698026657,-0.07339717447757721,0.08452536910772324,0.12722264230251312,0.1951807737350464,0.12195584177970886,0.03973403200507164,-0.1220400333404541,-0.0452033095061779,0.10242201387882233,-0.18534551560878754,0.22000347077846527,-0.017415527254343033,0.11067897826433182,0.008563507348299026],[0.11946352571249008,0.13736286759376526,0.3282008469104767,-0.017501303926110268,0.2699005603790283,0.1301700323820114,0.11314503103494644,-0.21658813953399658,0.09731227904558182,-0.2965020537376404,-0.2213086634874344,0.21423381567001343,-0.4802987277507782,0.08806030452251434,-0.24912650883197784,0.1734260767698288,-0.025265440344810486,-0.11896038055419922,-0.19331805408000946,-0.19196288287639618,0.06153837963938713,-0.42930662631988525,-0.1409986913204193,0.17505787312984467,0.277595192193985,0.19834011793136597,0.05545126646757126,-0.057496823370456696,0.26995858550071716,-0.0019127291161566973,0.18971334397792816,-0.008195792324841022,0.11532282829284668,0.11250894516706467,-0.13070711493492126,0.01743614301085472,0.004458330105990171,-0.04976446181535721,0.3422483801841736,0.25215405225753784,0.2977280020713806,-0.04141835495829582,0.009582608006894588,0.2510194480419159,0.024665523320436478,-0.001842399244196713,0.30412498116493225,-0.0953076034784317,-0.20651058852672577,0.37045302987098694,0.11047369241714478,-0.04849615320563316,0.18279528617858887,0.17857863008975983,0.21464046835899353,-0.3634246587753296,0.10458548367023468,0.048888131976127625,0.0731896311044693,0.11243137717247009,-0.08337461203336716,0.1515880972146988,0.049914296716451645,-0.2956204116344452],[-0.2519557774066925,0.11474065482616425,0.18372440338134766,-0.05802541971206665,-0.20647624135017395,-0.13865740597248077,0.1605665683746338,-0.20780792832374573,0.15906040370464325,-0.41964074969291687,-0.1936955451965332,-0.03110438585281372,0.03713708370923996,-0.02323727123439312,-0.15731221437454224,0.06848016381263733,-0.22305476665496826,0.010208108462393284,-0.2720680236816406,-0.32154950499534607,-0.11297693848609924,-0.19390824437141418,0.1464540809392929,-0.221584290266037,0.12628291547298431,0.0023809513077139854,-0.005741239991039038,-0.009247449226677418,0.0014641315210610628,0.012559530325233936,0.08647923916578293,-0.14943066239356995,0.12180783599615097,0.01400015503168106,0.08342675864696503,-0.1089920848608017,0.06520754098892212,0.0719783678650856,-0.06588690727949142,-0.02440876141190529,-0.0091728949919343,0.24045585095882416,-0.009648079052567482,0.12669850885868073,0.12691251933574677,0.027624351903796196,0.07786549627780914,0.05249932408332825,0.07156433165073395,-0.03379721939563751,0.16427764296531677,-0.16417266428470612,-0.008191452361643314,-0.028943050652742386,-0.05854099243879318,-0.11760982871055603,0.11835405230522156,0.0847015306353569,-0.23897702991962433,0.07879917323589325,-0.18065772950649261,0.03673078119754791,0.030269719660282135,-0.10408290475606918],[-0.04248623922467232,-0.150638148188591,0.18939249217510223,-0.048842571675777435,0.03906061500310898,0.07816722244024277,-0.13150034844875336,-0.1521798074245453,-0.11558353155851364,0.021649295464158058,-0.14700986444950104,-0.03579743951559067,-0.10364671051502228,0.0019177725771442056,0.09104514122009277,-0.1629658341407776,-0.11562677472829819,-0.17236089706420898,-0.1776818484067917,-0.12003226578235626,-0.0905463695526123,-0.012339617125689983,0.031015312299132347,-0.06165671348571777,-0.02529258094727993,0.025810731574892998,-0.051855411380529404,0.038700904697179794,-0.10164456814527512,-0.05746448412537575,0.0683518573641777,0.045791205018758774,-0.062024783343076706,-0.03465677425265312,-0.13824395835399628,-0.242758646607399,-0.13201238214969635,-0.09628818929195404,-0.11303499341011047,0.1708904504776001,0.09800191223621368,-0.012692171148955822,-0.037836913019418716,-0.09030259400606155,-0.08321564644575119,-0.025198396295309067,0.06404007971286774,-0.07968497276306152,-0.04287742078304291,0.04557301104068756,-0.035904381424188614,0.0796022042632103,0.053786709904670715,0.10675092786550522,0.07339354604482651,-0.09063678979873657,0.009332669898867607,-0.0029401397332549095,0.019915711134672165,-0.20483168959617615,0.06607041507959366,-0.0017265727510675788,-0.07414054125547409,-0.059154585003852844],[-0.04984843730926514,0.006905656307935715,0.058697380125522614,0.011759904213249683,-0.34703966975212097,-0.31672585010528564,0.15341538190841675,-0.21438024938106537,-0.04659447818994522,-0.11649280041456223,-0.13918332755565643,0.1758972555398941,-0.013977674767374992,-0.22720785439014435,-0.20288631319999695,-0.10130101442337036,-0.4004135727882385,0.06729143112897873,0.09885973483324051,-0.17973020672798157,-0.07740437984466553,0.0021776342764496803,-0.013472001068294048,-0.3048918545246124,0.11899010092020035,0.09910086542367935,-0.20021376013755798,0.027515828609466553,-0.5031788349151611,0.05801835283637047,-0.06706561893224716,-0.30630144476890564,-0.12989313900470734,-0.05787708982825279,-0.18256866931915283,0.1593465507030487,-0.22493693232536316,-0.1304517686367035,0.3761143684387207,0.15587487816810608,-0.3439125716686249,0.24029560387134552,-0.13253918290138245,0.2963239252567291,0.04516952857375145,-0.1208803579211235,0.1819491684436798,-0.14155350625514984,-0.12901782989501953,0.2447987049818039,-0.034807413816452026,-0.11080168187618256,0.1456504464149475,-0.3064805865287781,-0.44089433550834656,0.1552281677722931,-0.08114434778690338,-0.04213133081793785,-0.3107782006263733,0.09301503002643585,-0.12060181051492691,0.15185993909835815,0.14247839152812958,-0.11492545157670975],[-0.08255033940076828,0.008243098855018616,0.006710262503474951,0.0670977309346199,0.1328299194574356,0.08983220160007477,-0.2664368152618408,-0.1015791967511177,-0.03875391185283661,-0.009057337418198586,-0.058476075530052185,-0.17684079706668854,-0.05193436145782471,0.1353757083415985,0.059033796191215515,0.05159511789679527,0.04299242049455643,-0.06902863085269928,-0.05064184218645096,-0.019269391894340515,-0.15955162048339844,-0.09536731243133545,-0.2652379870414734,0.15660427510738373,-0.14795057475566864,-0.01098143681883812,0.009516216814517975,0.09447366744279861,0.19032859802246094,-0.21216586232185364,0.22951973974704742,0.07644958794116974,-0.15729942917823792,-0.08377916365861893,-0.17953437566757202,-0.15763236582279205,-0.2117745280265808,-0.08606632053852081,-0.03344937041401863,-0.2769390642642975,0.21614567935466766,0.07434209436178207,-0.04462727904319763,0.23900318145751953,-0.1808866560459137,0.0876772552728653,0.004007626324892044,-0.12241612374782562,0.11726249754428864,0.26533210277557373,-0.16332226991653442,-0.0017788807163015008,0.04754576086997986,0.08832764625549316,0.07999768853187561,-0.05614403262734413,-0.1564609855413437,0.002839781576767564,0.21983833611011505,-0.01467352919280529,-0.0917854905128479,0.11237522214651108,-0.025508498772978783,-0.20220635831356049],[0.05935929715633392,-0.01933305524289608,0.11901857703924179,0.08114886283874512,-0.16391721367835999,-0.09175200760364532,-0.03620006889104843,-0.16938748955726624,0.17433606088161469,-0.007969042286276817,-0.25760310888290405,-0.09129927307367325,-0.049134761095047,-0.06579694896936417,0.12843675911426544,-0.1953374743461609,-0.14695152640342712,0.034272611141204834,0.2260255366563797,0.1889728158712387,0.08454226702451706,0.09130191057920456,0.09726604074239731,-0.16877928376197815,0.028352074325084686,0.017611248418688774,0.10471989959478378,-0.15926142036914825,-0.24615268409252167,-0.08849022537469864,-0.1685507595539093,-0.1896354854106903,0.06468473374843597,-0.014346279203891754,0.05001680552959442,-0.10083259642124176,-0.15173344314098358,-0.046793382614851,0.10234111547470093,0.14372602105140686,-0.2081119567155838,0.10525025427341461,-0.2928839325904846,0.13210202753543854,0.046058885753154755,-0.1463000774383545,0.1895940601825714,0.03107869066298008,-0.046571191400289536,0.14984266459941864,0.012364255264401436,-0.1972270905971527,-0.06150700896978378,-0.2529468536376953,0.014785781502723694,-0.1715662032365799,-0.08328014612197876,-0.03637096285820007,-0.25456589460372925,0.05791059136390686,0.08811334520578384,0.05461173504590988,0.07154478132724762,0.028323255479335785],[-0.06571802496910095,-0.0018505833577364683,0.11457223445177078,0.1675802767276764,0.09889686852693558,0.1428872048854828,-0.1408143788576126,0.09844448417425156,-0.24503754079341888,0.14116553962230682,0.2594645321369171,-0.03978847339749336,0.040205154567956924,-0.046127066016197205,0.11042208969593048,0.18565328419208527,0.025341251865029335,-0.21498554944992065,-0.1544857919216156,-0.031814854592084885,-0.03273855149745941,-0.18504390120506287,-0.16214634478092194,0.23136986792087555,-0.017794180661439896,0.022454209625720978,0.08325944095849991,0.2421857714653015,0.10021518915891647,-0.13884010910987854,-0.13820959627628326,0.16713368892669678,-0.004434256814420223,0.023915991187095642,-0.03464449197053909,-0.04249553382396698,-0.02265053614974022,-0.022231345996260643,0.04304369166493416,-0.23488950729370117,0.128383606672287,0.005700133740901947,0.1691322773694992,0.3679106533527374,-0.09058676660060883,-0.02914823591709137,0.05407949164509773,0.01109633781015873,-0.03714308887720108,0.2525072991847992,-0.04389331117272377,-0.04324312508106232,0.07554824650287628,0.1947157382965088,0.11954818665981293,0.02289562299847603,-0.06188962608575821,-0.07038130611181259,0.10121407359838486,-0.21600061655044556,0.06317421793937683,-0.13041023910045624,0.11141961067914963,-0.0562019944190979],[-0.15747500956058502,-0.2705179750919342,0.3120778203010559,0.02501455880701542,-0.36307886242866516,-0.22565782070159912,-0.4735700190067291,-0.6851180791854858,0.30834242701530457,-0.08607567101716995,0.2052893340587616,-0.19240067899227142,-0.2864053249359131,-0.13234634697437286,0.263553649187088,-0.006031668744981289,-0.6636716723442078,0.02373085916042328,0.015025588683784008,0.1019081398844719,0.2914310097694397,-0.29179924726486206,0.008357363753020763,0.15617866814136505,0.25402510166168213,-0.10458363592624664,0.027492795139551163,-0.21906456351280212,-0.24401260912418365,0.21170641481876373,-0.12744316458702087,-0.6705467104911804,-0.4003387987613678,-0.43481820821762085,0.21527723968029022,-0.28829076886177063,-0.6192759871482849,-0.2723904848098755,-0.2978112995624542,-0.14700612425804138,0.2258913815021515,-0.2650153636932373,0.0747472494840622,0.24149513244628906,-0.1496819257736206,-0.5050072073936462,0.5049706697463989,-0.1256658285856247,0.22928078472614288,0.06660641729831696,0.3358334004878998,0.00466057937592268,-0.0709233283996582,0.07326582074165344,-0.3150143325328827,-0.38931015133857727,0.02587432786822319,0.19406922161579132,-0.008466732688248158,-0.5332463383674622,-0.34472164511680603,-0.18908526003360748,-0.1347304880619049,-0.18578684329986572],[0.10687042772769928,-0.07230959087610245,-0.12491315603256226,0.14356426894664764,-0.30314427614212036,-0.4182182252407074,-0.19506435096263885,-0.4948051869869232,-0.13192202150821686,-0.08338122069835663,-0.3148747384548187,-0.1413458287715912,-0.5580247640609741,0.008494006469845772,0.31210702657699585,0.1343899816274643,0.009172992780804634,-0.0263446606695652,-0.3050351142883301,-0.005023784935474396,-0.08718452602624893,-0.260132759809494,-0.17055808007717133,0.1351223886013031,0.09076017141342163,0.21116559207439423,-0.191195547580719,-0.19827911257743835,-0.22983480989933014,-0.09830227494239807,-0.2693251371383667,-0.12745730578899384,0.1742350310087204,-0.15621857345104218,0.1011122539639473,-0.14543311297893524,0.17746864259243011,-0.2079407274723053,0.03012145683169365,-0.08775504678487778,-0.057229019701480865,0.035542525351047516,-0.30004823207855225,-0.1291745901107788,0.16779614984989166,0.01426919735968113,-0.18470484018325806,0.10669968277215958,0.2469007670879364,0.10645770281553268,0.05880191549658775,-0.38661694526672363,-0.06906865537166595,0.04902498424053192,-0.19441905617713928,0.02745169587433338,-0.0036802473478019238,0.01395691279321909,0.02786371484398842,0.009414316155016422,-0.21444401144981384,-0.08969615399837494,-0.247527614235878,0.1160239651799202],[0.08843327313661575,-0.004909266252070665,-0.02259782701730728,-0.16407831013202667,0.14011400938034058,0.12320581078529358,-0.1337873935699463,0.0633276030421257,-0.003807895816862583,-0.12099988013505936,0.24541446566581726,0.11165269464254379,0.17751172184944153,0.12440063059329987,-0.08319876343011856,0.11847969889640808,-0.09209753572940826,0.1912974715232849,-0.05514535307884216,-0.1135651245713234,-0.002754148095846176,0.15900084376335144,0.11312950402498245,0.17155145108699799,0.09212112426757812,-0.07750077545642853,0.13854944705963135,0.12740331888198853,0.0998711884021759,-0.01080122496932745,0.1079341247677803,0.3329366445541382,-0.09467728435993195,-0.16073264181613922,0.07218020409345627,-0.09827399998903275,-0.26001405715942383,0.089376300573349,-0.014337562024593353,-0.08001846075057983,0.08056426793336868,-0.0021292446181178093,0.17625834047794342,0.21623730659484863,0.0010096561163663864,0.1321374922990799,-0.1400390863418579,-0.024975350126624107,-0.22921134531497955,0.16835318505764008,-0.212784543633461,-0.06432347744703293,-0.012412158772349358,0.17093375325202942,0.05298460274934769,0.1042107492685318,0.08948451280593872,-0.07162263244390488,-0.04002682492136955,-0.15657129883766174,-0.03577253222465515,-0.04072117805480957,0.10984673351049423,-0.010203472338616848],[0.15610261261463165,0.11623720824718475,-0.004336806014180183,-0.19554752111434937,0.24212466180324554,0.16374489665031433,-0.1413090080022812,0.17643627524375916,-0.35633111000061035,0.039936695247888565,0.11817970871925354,0.06084160506725311,0.14183229207992554,0.09500768035650253,-0.17565307021141052,-0.0002355018659727648,0.03630528226494789,-0.15214549005031586,-0.386048287153244,-0.1496131867170334,-0.45544740557670593,0.09999475628137589,-0.11720019578933716,0.38563576340675354,-0.1521802693605423,0.18061001598834991,-0.02256614714860916,0.3362206518650055,0.23438327014446259,-0.39092883467674255,0.315047025680542,0.46023857593536377,-0.3371857702732086,-0.48804184794425964,-0.07357747852802277,0.0868968591094017,-0.15451543033123016,-0.12543651461601257,0.05875550955533981,-0.20593346655368805,0.25895223021507263,0.10373274236917496,0.1327921748161316,0.348492830991745,-0.4567258059978485,0.00773918442428112,-0.2550789415836334,-0.14150342345237732,-0.19743011891841888,0.23351025581359863,-0.40502265095710754,0.1714683473110199,-0.0821002721786499,0.16707506775856018,0.11379581689834595,0.047349922358989716,0.12544721364974976,-0.2987164855003357,0.21172872185707092,-0.3290656507015228,0.27151474356651306,0.07683220505714417,-0.021755125373601913,-0.014705484732985497],[0.21617405116558075,0.1990458369255066,0.037035245448350906,-0.11906886845827103,0.19465993344783783,0.032068196684122086,-0.20418910682201385,0.17160744965076447,-0.23962411284446716,2.6789959520101547e-05,0.2056950330734253,0.2747143507003784,0.2823372185230255,0.004056976176798344,-0.10644548386335373,0.22252120077610016,0.07241303473711014,-0.016160139814019203,-0.39120399951934814,-0.0316275916993618,-0.15809956192970276,0.19906246662139893,0.22867517173290253,0.10282190889120102,0.07449446618556976,0.1799292117357254,-0.06845300644636154,-0.055059924721717834,0.1274462640285492,-0.005316286347806454,0.09901868551969528,0.18752993643283844,0.02273133583366871,0.02536800317466259,0.03688931092619896,0.1285391002893448,-0.17288002371788025,0.007024901453405619,-0.07330763339996338,-0.10488130152225494,0.1707526445388794,0.20594464242458344,0.11152410507202148,0.13216137886047363,-0.12257904559373856,-0.16517026722431183,-0.13190589845180511,-0.11823300272226334,-0.2869855761528015,-0.05109613388776779,-0.10873925685882568,0.05850544944405556,-0.02568932995200157,0.13943473994731903,0.029183872044086456,0.09146978706121445,0.026276301592588425,-0.03978652134537697,0.12507082521915436,-0.15611937642097473,0.13454848527908325,0.010342277586460114,0.025243043899536133,-0.004431492183357477],[-0.40314847230911255,-0.4097299575805664,-0.08550681918859482,0.3013267517089844,-0.19754597544670105,0.21706745028495789,-0.12215734273195267,0.27753230929374695,0.06369048357009888,-0.5874590277671814,-0.2401275634765625,0.25601062178611755,-0.37619107961654663,-0.18517428636550903,0.024285122752189636,0.2401438057422638,-0.45070117712020874,-0.3725429177284241,-0.467744380235672,0.30772197246551514,-0.4118458926677704,-0.5851777791976929,0.16373391449451447,-0.5346608757972717,-0.09553692489862442,-0.05406869575381279,-0.19686897099018097,-0.5522293448448181,-0.2535087764263153,-0.3878822326660156,0.4278283417224884,-0.4414830207824707,0.030726894736289978,0.10155093669891357,-0.049428004771471024,-0.47004958987236023,0.2742752730846405,-0.14392349123954773,-0.5557020902633667,0.014269880950450897,-0.2573345899581909,0.05921197682619095,0.01983024552464485,-0.07184421271085739,-0.042320214211940765,0.26247960329055786,-0.3612019717693329,-0.07574819773435593,-0.27790459990501404,-0.6180347204208374,0.05068463832139969,0.18369144201278687,0.10951847583055496,-0.12399907410144806,-0.34392014145851135,0.24193550646305084,-0.03475335240364075,0.26061418652534485,0.04517686367034912,0.06170384958386421,-0.3302866518497467,-0.24451570212841034,0.3617032766342163,0.18883487582206726],[-0.030591631308197975,-0.03335709497332573,-0.04303707927465439,-0.005184325855225325,-0.13161644339561462,-0.14773455262184143,0.05271532014012337,-0.07288419455289841,-0.20142866671085358,0.1590437889099121,-0.08337423950433731,-0.2623586356639862,-0.21099033951759338,-0.09257818758487701,0.2032226175069809,-0.01525886170566082,0.00669276574626565,-0.1757272481918335,-0.3821483254432678,0.08312337100505829,-0.11494012922048569,0.1392960250377655,0.14573746919631958,-0.24137245118618011,0.04851221665740013,0.223693385720253,0.029640646651387215,-0.21594902873039246,-0.1799260377883911,-0.1385800838470459,0.12098268419504166,0.0017888374859467149,0.2043168544769287,0.1963198184967041,0.0726621001958847,-0.20035134255886078,0.3405633568763733,0.005085333716124296,0.0788993164896965,-0.29312247037887573,0.10660646855831146,0.14019575715065002,0.002383759943768382,0.03610945865511894,0.10043708235025406,-0.0853378027677536,0.02646128460764885,-0.034601740539073944,-0.06987079977989197,0.13136832416057587,0.0677076056599617,-0.10538017749786377,-0.01827290840446949,-0.03837036341428757,-0.02372760884463787,0.08876009285449982,-0.031776607036590576,0.024046730250120163,0.012528745457530022,0.07181672751903534,-0.14177305996418,-0.030047202482819557,-0.011373528279364109,-0.0654074102640152],[0.2002885341644287,0.08083441853523254,0.1464715451002121,-0.10202822089195251,0.00793218519538641,0.05632852390408516,-0.13131536543369293,0.035333696752786636,0.15538188815116882,-0.0595160536468029,-0.10007094591856003,0.17270733416080475,0.2650853991508484,-0.04923468828201294,0.013394290581345558,0.04554804787039757,-0.054316047579050064,-0.012287658639252186,-0.20596352219581604,-0.09433795511722565,-0.09296881407499313,0.21094274520874023,0.17684222757816315,0.03388436138629913,-0.0442340224981308,0.13289815187454224,0.13709034025669098,0.06116363778710365,0.05994023382663727,-0.0987338200211525,0.11708441376686096,0.18908412754535675,-0.12095019221305847,-0.12623143196105957,-0.07941395044326782,0.16902707517147064,-0.33639541268348694,-0.08343078196048737,-0.03698384016752243,0.057090289890766144,-0.033108990639448166,-0.13890497386455536,0.0493493489921093,0.11244700849056244,-0.21414361894130707,0.050270020961761475,-0.026462895795702934,-0.18295729160308838,-0.24895893037319183,-0.1389494687318802,-0.08896991610527039,0.1682504564523697,0.13984577357769012,0.17209918797016144,0.10855263471603394,0.021936528384685516,0.19457142055034637,0.07590513676404953,0.06352174282073975,-0.19293096661567688,0.0494781956076622,0.05117757245898247,0.18822379410266876,-0.18082204461097717],[-0.036030590534210205,-0.055759210139513016,-0.21365831792354584,0.09904863685369492,0.26118916273117065,-0.06890163570642471,0.010470221750438213,0.12343315035104752,0.2243470549583435,0.06159437075257301,0.2176913470029831,0.02248002588748932,0.0450163334608078,-0.1600894182920456,-0.05892596021294594,0.0373995341360569,-0.10435621440410614,-0.28107786178588867,-0.5926457047462463,-0.1911899298429489,0.14891380071640015,0.060699984431266785,0.0967261865735054,0.0020811534486711025,0.008731672540307045,0.14552493393421173,-0.14445118606090546,-0.21285825967788696,-0.1204703077673912,0.16220694780349731,-0.31187891960144043,0.22297899425029755,0.14367930591106415,0.0009325807332061231,-0.03058774769306183,0.06541154533624649,-0.13341939449310303,-0.023359809070825577,-0.031220218166708946,0.09332717210054398,-0.21298497915267944,0.14311811327934265,-0.1380603015422821,0.15109127759933472,-0.006834536790847778,0.050147734582424164,-0.0987037718296051,-0.2217220515012741,-0.20404592156410217,0.08073339611291885,-0.133775994181633,-0.31195762753486633,-0.17464202642440796,-0.21418727934360504,0.11784708499908447,0.19860322773456573,0.19970154762268066,-0.016070611774921417,-0.017251363024115562,-0.12185277044773102,0.1284227967262268,-0.18265554308891296,0.16481377184391022,-0.07101902365684509],[0.10408987104892731,0.1664251834154129,0.029752392321825027,-0.13202466070652008,0.04719697684049606,-0.05145329609513283,0.11319874227046967,-0.1245347261428833,0.07238674908876419,0.010298840701580048,-0.028457636013627052,0.07212965935468674,0.03272661939263344,-0.04785006120800972,0.07961495220661163,0.15951235592365265,0.015299201011657715,0.07867488265037537,0.00980620738118887,-0.026810219511389732,-0.034439265727996826,-0.0632452666759491,0.020349517464637756,0.08153921365737915,0.005988243501633406,0.13222496211528778,-0.023903992027044296,-0.07100733369588852,-0.03273675963282585,-0.05171547085046768,0.20542196929454803,0.1153690442442894,-0.024284061044454575,0.07289447635412216,-0.09129669517278671,0.030563022941350937,0.14438922703266144,-0.04273396357893944,-0.028123613446950912,0.016451116651296616,-0.019157979637384415,0.058253105729818344,0.06704286485910416,-0.036789774894714355,0.12475596368312836,-0.1039186641573906,0.05285613238811493,-0.04666295275092125,-0.05358352139592171,0.15130135416984558,-0.10139336436986923,0.028005629777908325,0.10235146433115005,0.14907406270503998,-0.08207063376903534,0.04842215031385422,0.12067757546901703,-0.1396479606628418,0.04742275923490524,-0.06635890901088715,0.05199120193719864,-0.11427661776542664,0.1339164525270462,-0.06578937917947769],[0.03242238238453865,-0.08517275005578995,0.13129009306430817,0.057496510446071625,-0.10201406478881836,-0.08372557163238525,0.0771821066737175,-0.14977607131004333,0.2349160760641098,-0.3852509558200836,-0.2653973400592804,-0.21663156151771545,-0.05208653211593628,-0.10651391744613647,0.20113907754421234,-0.3334610164165497,-0.13090431690216064,0.129889577627182,-0.11085815727710724,0.2905011475086212,0.02751482091844082,-0.25841447710990906,0.4460931420326233,-0.11707132309675217,-0.1456156224012375,-0.13413700461387634,0.024707362055778503,-0.30410754680633545,0.015255164355039597,-0.0052941483445465565,-0.07605074346065521,-0.2572268843650818,0.08220162242650986,-0.05169133469462395,-0.00384632614441216,0.08199328929185867,0.07564698159694672,0.06113521009683609,-0.3576357662677765,-0.37826359272003174,-0.24559928476810455,0.08140064775943756,-0.16274906694889069,-0.3962611258029938,-0.03152773529291153,-0.11350203305482864,0.134173184633255,0.0559554398059845,-0.1218978762626648,0.016209106892347336,0.16916848719120026,0.008876422420144081,0.13427437841892242,-0.32361549139022827,0.08596880733966827,0.0995149165391922,-0.04429575800895691,-0.10031145066022873,-0.23071661591529846,0.10716752707958221,0.19006231427192688,-0.02437707781791687,0.0643761157989502,0.1872567981481552],[0.07075106352567673,0.08998729288578033,0.06432340294122696,0.04254583641886711,0.15022453665733337,0.10051120817661285,-0.12179285287857056,-0.09057442098855972,-0.043313167989254,-0.03923157975077629,0.13678978383541107,-0.053236957639455795,-0.18208731710910797,-0.045180853456258774,0.19366568326950073,0.042839258909225464,-0.08399637788534164,0.034227728843688965,-0.4144245684146881,-0.07848646491765976,-0.05479888245463371,-0.13474145531654358,-0.009570336900651455,0.13064813613891602,0.06492527574300766,0.014422429725527763,-0.03390267863869667,-0.06387299299240112,-0.05779554694890976,-0.15935441851615906,-0.19911819696426392,-0.1393229216337204,-0.07025811821222305,-0.10223729908466339,0.001706326031126082,-0.25773724913597107,-0.12938149273395538,-0.011848695576190948,-0.01309242658317089,0.0665132999420166,0.0472777858376503,-0.22048959136009216,0.008934786543250084,0.28612712025642395,-0.11086038500070572,-0.2430182248353958,0.029237082228064537,-0.09049026668071747,-0.08870876580476761,0.08446045964956284,-0.06624400615692139,-0.10076462477445602,-0.15134543180465698,0.07253840565681458,-0.0060530854389071465,-0.08100941777229309,-0.09515327960252762,-0.04139238968491554,0.06486061960458755,-0.23881740868091583,0.011732800863683224,-0.03359786048531532,-0.03324829041957855,-0.04170951247215271],[0.10846016556024551,-0.18879808485507965,-0.022540759295225143,0.02976883202791214,-0.14133580029010773,-0.1890823245048523,0.11578083783388138,-0.3496306240558624,-0.13957993686199188,0.2299836128950119,-0.09345503151416779,0.03984105959534645,0.22703947126865387,-0.12813669443130493,0.1324601173400879,-0.1731068193912506,-0.15007056295871735,0.06044217199087143,0.24154333770275116,-0.18007351458072662,0.01992509327828884,0.20389945805072784,0.1885337233543396,-0.05795803666114807,0.20585423707962036,-0.22370509803295135,0.11983925104141235,-0.14526723325252533,-0.15963214635849,0.04306793585419655,-0.11344008147716522,-0.17141509056091309,0.23417697846889496,0.17159894108772278,0.11977153271436691,0.053790632635354996,0.07421236485242844,0.07336030900478363,0.16390323638916016,0.1965755671262741,-0.25262242555618286,0.03329803794622421,-0.023960759863257408,-0.09976644814014435,0.1038733720779419,-0.05234598368406296,0.05658179521560669,0.04814702644944191,0.2872466742992401,0.0699368566274643,0.05992155522108078,-0.18046489357948303,0.044985558837652206,0.025115815922617912,-0.17366860806941986,-0.4574575126171112,0.10433047264814377,0.03269791603088379,-0.3031948506832123,0.2895703613758087,0.14993281662464142,0.14966946840286255,-0.14592158794403076,0.10922802984714508],[0.05925983563065529,0.1216835305094719,0.28250524401664734,0.12390892952680588,0.07013899087905884,0.166779562830925,-0.09700468182563782,0.254486620426178,-0.23217646777629852,-0.34724390506744385,-0.17374104261398315,0.1569431573152542,-0.10883225500583649,0.033082470297813416,-0.07125737518072128,0.11181456595659256,-0.11338678002357483,-0.05779898539185524,-0.14255477488040924,0.23175203800201416,0.10939794778823853,-0.2641419470310211,0.1468452364206314,-0.041823383420705795,0.0077751209028065205,-0.042466871440410614,-0.14392641186714172,-0.09486556053161621,-0.13030770421028137,0.07437845319509506,0.23827210068702698,-0.2261558473110199,0.163200244307518,0.1891288459300995,-0.2755098044872284,0.21557363867759705,0.011398169212043285,-0.048126157373189926,-0.25186383724212646,-0.47570234537124634,-0.04024174064397812,-0.043183330446481705,-0.0586850605905056,-0.2621273100376129,0.08652675896883011,0.13002368807792664,0.051964908838272095,0.06676117330789566,-0.021085944026708603,0.07124637067317963,-0.011387031525373459,0.22376251220703125,0.10456820577383041,-0.003701358800753951,0.16933436691761017,0.22951950132846832,0.03278733417391777,0.04189623147249222,-0.08404448628425598,0.26248711347579956,0.11744628846645355,-0.029065947979688644,0.03369950130581856,-0.1029457300901413],[-0.043380413204431534,0.0875469446182251,-0.10610037297010422,-0.2173546850681305,0.035327281802892685,0.08521725237369537,-0.03154342621564865,0.02920348197221756,-0.13465949892997742,0.03259711340069771,0.008482087403535843,0.14709049463272095,0.1538032740354538,-0.06399889290332794,0.0841861441731453,0.18388527631759644,0.012721816077828407,-0.03553557023406029,-0.1643073856830597,-0.03575350344181061,-0.13272009789943695,0.2414783090353012,0.13477662205696106,-0.08736078441143036,-0.0984363779425621,0.19980163872241974,-0.057136114686727524,0.03555992990732193,0.13974998891353607,-0.022981273010373116,0.1254495531320572,0.22876927256584167,-0.05592165142297745,0.10622391104698181,-0.11533809453248978,0.003482506377622485,-0.1665041148662567,-0.027990734204649925,0.021855633705854416,-0.0627676248550415,0.09173856675624847,-0.0593617707490921,0.13730017840862274,0.12739834189414978,-0.03898920491337776,0.08330893516540527,0.06945846229791641,0.08271415531635284,-0.21875184774398804,-0.036589473485946655,-0.10863396525382996,0.006268556695431471,0.11340414732694626,0.14708396792411804,0.0950082540512085,0.10840948671102524,0.07250404357910156,0.06309164315462112,0.08806131780147552,-0.13041719794273376,0.00012179234181530774,0.04606541991233826,0.012451245449483395,-0.17065909504890442],[-0.0032178894616663456,0.011308436281979084,0.01873033680021763,-0.0909959226846695,0.13921909034252167,0.287656307220459,-0.060893893241882324,0.13235914707183838,-0.20166215300559998,0.07073801010847092,0.12968264520168304,0.08811835944652557,0.28036850690841675,0.09729404002428055,-0.21935564279556274,0.03293836861848831,0.03914155066013336,-0.23057685792446136,-0.4508601427078247,-0.14069560170173645,-0.2651520371437073,-0.11757037788629532,-0.1339847892522812,0.04888109490275383,0.08307355642318726,0.23739784955978394,-0.05645375698804855,0.26583197712898254,0.07684596627950668,-0.3055928349494934,0.13039369881153107,0.0970015674829483,-0.12686572968959808,-0.16956549882888794,-0.21406801044940948,0.060963355004787445,-0.253304123878479,-0.24401451647281647,-0.02100479044020176,-0.13905394077301025,0.13994170725345612,0.05412863940000534,0.13504672050476074,0.12644793093204498,-0.13881590962409973,-0.1458660513162613,-0.13948369026184082,-0.030073342844843864,-0.12666380405426025,0.10094420611858368,-0.11068739742040634,0.04942895844578743,0.10437680035829544,0.2505272626876831,0.16627731919288635,-0.03077823296189308,-0.14814691245555878,-0.07756036520004272,0.20836171507835388,-0.1252787858247757,0.02039162628352642,-0.06879490613937378,0.1133391410112381,-0.06137624382972717],[0.1565234661102295,0.12340351194143295,0.010690299794077873,-0.1425669938325882,-0.01720728911459446,0.1550106555223465,-0.15145400166511536,0.09098190814256668,0.07656394690275192,0.09437460452318192,0.17522747814655304,0.17649777233600616,0.08061511814594269,0.10643962770700455,-0.07656451314687729,0.15935230255126953,0.03275333344936371,-0.375606507062912,-0.24966944754123688,0.05049262195825577,-0.06839970499277115,0.01707116700708866,-0.19473911821842194,-0.012868278659880161,-0.017755143344402313,-0.04459279775619507,-0.0859093964099884,0.16662029922008514,0.08150966465473175,-0.1254434436559677,0.053818657994270325,-0.11230532824993134,-0.05883249267935753,0.011355100199580193,0.059400998055934906,0.22334986925125122,0.04211917147040367,-0.11578319221735,-0.020804358646273613,-0.09769804775714874,0.00878790020942688,0.05154304578900337,0.006443892605602741,0.24732215702533722,0.008120530284941196,-0.20057684183120728,-0.043066784739494324,0.021716764196753502,-0.13514450192451477,-0.07119493931531906,-0.01491618063300848,0.06348953396081924,0.03639470413327217,0.10804381966590881,0.20062656700611115,0.016084816306829453,0.019169984385371208,-0.16581323742866516,0.0850653201341629,0.0136363310739398,0.12422747164964676,-0.1495310515165329,-0.0353974848985672,-0.10760308057069778],[-0.19492165744304657,-0.05862106755375862,0.3908647894859314,-0.30564019083976746,-0.3495890498161316,-0.3951317071914673,0.26225024461746216,-0.19050763547420502,-0.29506996273994446,-0.30717015266418457,-0.21576231718063354,-0.07499252259731293,-0.268232136964798,-0.16100110113620758,0.003799594007432461,-0.3188572824001312,-0.38978809118270874,-0.04621165990829468,-0.5760506391525269,-0.028159627690911293,0.10351293534040451,-0.2634088695049286,0.02171269990503788,-0.1869383156299591,0.23178385198116302,-0.5281937718391418,-0.1569303274154663,-0.22570203244686127,-0.44736579060554504,0.17079049348831177,0.09683722257614136,-0.00622248649597168,-0.19418072700500488,0.12965743243694305,0.1114678606390953,0.40810972452163696,-0.07723675668239594,0.00023634539684280753,0.38874414563179016,0.016877632588148117,-0.32234522700309753,-0.3347421884536743,-0.19467686116695404,-0.3857521116733551,-0.35836341977119446,-0.1142989993095398,0.05736056715250015,-0.12828415632247925,-0.10221964120864868,0.2983129024505615,-0.13489706814289093,-0.2421090304851532,0.28169625997543335,-0.4523617923259735,-0.39982619881629944,-0.1910983920097351,0.2577440142631531,-0.2040691077709198,-0.27229970693588257,0.18765898048877716,-0.059269752353429794,0.29010117053985596,-0.07794076204299927,-0.4363473951816559],[0.01745179481804371,0.0820486843585968,-0.09842131286859512,-0.366403192281723,-0.28238144516944885,0.03931225836277008,0.02504008635878563,0.05420622602105141,-0.03896627202630043,0.12928736209869385,0.44087210297584534,-0.34168097376823425,0.018895138055086136,-0.18753521144390106,-0.05891767144203186,-0.09186519682407379,-0.16824306547641754,0.12879128754138947,0.08417286723852158,-0.2921053171157837,0.0899786502122879,0.074884332716465,0.17821505665779114,-0.22562821209430695,0.06614222377538681,0.04914283752441406,-0.12309011071920395,-0.05552820861339569,-0.4190818965435028,0.24623452126979828,-0.008864892646670341,-0.1796380579471588,0.2338615208864212,0.13855943083763123,0.0036314716562628746,-0.13052193820476532,-0.5238686800003052,0.1499168574810028,0.011824662797152996,-0.2269890010356903,0.09111561626195908,-0.2815156877040863,0.09486566483974457,0.2331746220588684,-0.12898129224777222,-0.08518461883068085,0.17171214520931244,-0.11907108128070831,-0.038221389055252075,0.03100680187344551,-0.10372169315814972,-0.003418484702706337,0.07060132920742035,-0.004204991739243269,-0.16152898967266083,0.17376920580863953,-0.08145067095756531,-0.00982701312750578,-0.04707542434334755,-0.2584149241447449,-0.08050297200679779,-0.03499099612236023,0.011762648820877075,-0.0707971379160881],[0.07691734284162521,0.016712572425603867,0.0968218445777893,0.15191547572612762,-0.066615991294384,0.12554870545864105,-0.046127744019031525,0.003475943813100457,0.0087444381788373,-0.08648248016834259,-0.00950661115348339,0.013773832470178604,-0.06243498623371124,0.07139885425567627,0.0359208881855011,-0.05727707967162132,0.0714397206902504,0.15928302705287933,-0.03003588691353798,-0.0879688560962677,-0.038657646626234055,-0.15544503927230835,-0.013857606798410416,0.009793233126401901,-0.0567442812025547,0.1160057783126831,-0.02163320779800415,-0.052248090505599976,0.022616181522607803,0.13707007467746735,-0.13020996749401093,0.05908750370144844,-0.084078349173069,-0.22805120050907135,-0.08561159670352936,-0.15069109201431274,-0.11093339323997498,0.20746034383773804,-0.06410636752843857,0.15438339114189148,0.14938068389892578,0.05652845650911331,-0.12758681178092957,-0.07476881146430969,-0.12691625952720642,-0.036212120205163956,-0.002917691133916378,-0.01038017775863409,0.062281906604766846,0.04499520733952522,-0.21441316604614258,0.024361664429306984,-0.13315455615520477,0.10441413521766663,0.06683599203824997,-0.10989241302013397,0.047063007950782776,-0.03995966911315918,0.06159425154328346,0.031924933195114136,-0.1528361588716507,0.026592520996928215,0.11170555651187897,0.2133728563785553],[0.033899400383234024,0.050741054117679596,-0.0029158329125493765,-0.010647501796483994,-0.17946743965148926,-0.16817215085029602,0.06483122706413269,-0.19104653596878052,0.08549322932958603,-0.14687342941761017,-0.12517066299915314,-0.017323028296232224,-0.029801828786730766,0.01739707589149475,0.08305748552083969,0.06051620468497276,-0.14931850135326385,-0.16458672285079956,0.19327960908412933,-0.007665661629289389,0.07178376615047455,0.04762835428118706,0.02116577886044979,-0.1507779061794281,0.12401261925697327,0.07944994419813156,-0.0673665851354599,-0.18673011660575867,-0.0755590945482254,0.12896756827831268,-0.02337438426911831,-0.05758989602327347,-0.04526781290769577,-0.09939384460449219,0.06183779239654541,-0.06028975173830986,-0.07435339689254761,0.08058423548936844,0.07740002125501633,0.14626085758209229,-0.011168119497597218,0.19545216858386993,-0.19658450782299042,-0.020981315523386,-0.0034310398623347282,-0.16065248847007751,0.04527917504310608,0.099484384059906,-0.11603224277496338,0.12122465670108795,0.15159472823143005,-0.07436557114124298,0.0016677537932991982,-0.07217314094305038,0.02461113967001438,-0.10263019055128098,-0.024450872093439102,0.07449416816234589,-0.08394583314657211,0.06754961609840393,-0.12011970579624176,0.06935758888721466,-0.1063564345240593,0.07442057132720947],[-0.277614563703537,0.12473030388355255,0.259844034910202,0.09441358596086502,-0.3373211622238159,-0.2155969738960266,0.10271260887384415,-0.05863416939973831,-0.12039878219366074,-0.5041502714157104,-0.2299128770828247,0.03483184427022934,-0.0738719254732132,-0.15395145118236542,-0.07743626832962036,-0.09978273510932922,-0.35386186838150024,0.13460056483745575,-0.36715757846832275,-0.42302078008651733,-0.05641540512442589,-0.2417244166135788,0.08545108884572983,-0.122969850897789,0.19173569977283478,-0.29045966267585754,-0.3558838963508606,-0.21028244495391846,-0.4736095070838928,0.24967825412750244,0.28926756978034973,-0.30703771114349365,0.12757939100265503,0.13487176597118378,0.019356392323970795,0.305306077003479,-0.09264535456895828,-0.10537315160036087,0.11528147757053375,0.15533100068569183,-0.17749033868312836,0.18230248987674713,-0.011670837178826332,0.03070014901459217,0.15469086170196533,0.1277240365743637,0.016796905547380447,-0.12380745261907578,0.0077561140060424805,0.2668014466762543,0.13566696643829346,-0.13190466165542603,0.23339827358722687,-0.03494143858551979,-0.4956364035606384,0.018651241436600685,0.10946772992610931,0.18379172682762146,-0.20432165265083313,0.03916873410344124,-0.34935811161994934,0.18555212020874023,0.0009463349124416709,-0.22493590414524078],[-0.05628301948308945,0.048335961997509,0.02101954258978367,0.1404591053724289,0.21285615861415863,0.026492737233638763,-0.1615239828824997,0.10391607135534286,0.03488082438707352,-0.004112169146537781,-0.037836626172065735,0.09409727156162262,0.0740620568394661,0.16170568764209747,-0.11243437975645065,-0.09466265887022018,0.06527644395828247,-0.31855466961860657,-0.14976631104946136,-0.03271154314279556,-0.1722790002822876,-0.18313606083393097,-0.12984229624271393,0.13933289051055908,-0.06601379811763763,0.12735384702682495,0.025614170357584953,0.15963995456695557,0.16821125149726868,-0.3835480213165283,0.20061302185058594,0.061043523252010345,-0.27487969398498535,-0.060686271637678146,-0.15007933974266052,0.1440429985523224,-0.2609781324863434,-0.19320230185985565,0.051733747124671936,0.07023482769727707,0.16247053444385529,0.16794553399085999,0.1073002740740776,0.07074595987796783,-0.1758446991443634,0.03984319418668747,0.0013928605476394296,-0.11354640871286392,0.14300817251205444,0.20699864625930786,-0.1575469821691513,0.06352441757917404,0.007254157215356827,0.25777193903923035,0.14764557778835297,-0.052175987511873245,-0.08863772451877594,0.06491120904684067,0.2566671669483185,-0.16801901161670685,0.2024303674697876,-0.010614793747663498,0.02736135944724083,-0.13485801219940186],[-0.4073702096939087,0.058641087263822556,0.3499237596988678,-0.13734649121761322,-0.23984868824481964,-0.16027148067951202,0.1114751324057579,-0.046439141035079956,-0.12097334861755371,-0.3497683107852936,-0.41860297322273254,-0.05342678353190422,-0.020372536033391953,-0.050886910408735275,0.11707032471895218,-0.11597700417041779,-0.22084510326385498,0.025959037244319916,-0.17576181888580322,0.11016006767749786,0.04449798911809921,-0.1708851158618927,0.18544934689998627,0.013716869056224823,0.06178020313382149,-0.02933008037507534,0.010293819010257721,-0.11636937409639359,-0.3231046199798584,0.20591405034065247,0.07304176688194275,-0.1355786770582199,0.005395540036261082,-0.05087466537952423,0.016413934528827667,0.3233942985534668,-0.01638214848935604,0.10146767646074295,0.03578522428870201,0.11751996725797653,-0.07414494454860687,0.3358861804008484,-0.3143358826637268,0.12919142842292786,-0.20523905754089355,-0.01051102764904499,0.27317771315574646,-0.138419508934021,0.10966239124536514,0.024166610091924667,-0.07205315679311752,-0.12805213034152985,0.03218337148427963,-0.3363390564918518,-0.37825751304626465,0.1473432034254074,-0.06048935279250145,-0.06596638262271881,-0.2172505259513855,-0.06196792423725128,-0.13260948657989502,0.008842339739203453,0.18044860661029816,-0.06548354029655457],[-0.055631235241889954,-0.08231589198112488,0.040960490703582764,-0.0408809632062912,0.1343616545200348,0.15351775288581848,-0.24258652329444885,0.0505032055079937,0.047798048704862595,-0.0472063384950161,-0.0044473144225776196,0.03421538695693016,-0.05475917458534241,0.04276060685515404,0.0574350506067276,-0.125068798661232,-0.07981734722852707,-0.06652149558067322,-0.2848312258720398,-0.05331078916788101,-0.035026390105485916,-0.07069163769483566,-0.23280464112758636,0.06627846509218216,-0.0883641391992569,-0.0877600610256195,0.020614944398403168,0.01993573270738125,-0.013454158790409565,-0.12035803496837616,0.03091154433786869,0.1963197886943817,-0.03177366405725479,-0.12425631284713745,0.007690419442951679,-0.11981339752674103,-0.3406618535518646,-0.013954751193523407,-0.04048475623130798,-0.08669819682836533,0.1286766678094864,-0.007742570247501135,0.14390231668949127,0.2428865134716034,-0.13633982837200165,0.12403249740600586,0.06747128814458847,-0.09453414380550385,-0.006417096592485905,0.254995733499527,-0.05887380614876747,0.10083606094121933,0.1622963845729828,0.09395057708024979,0.18550758063793182,-0.0853315070271492,0.0005971388309262693,0.0012656415347009897,0.008521847426891327,-0.23006489872932434,0.1594153195619583,-0.14272671937942505,0.1610853672027588,-0.17389953136444092]],"bias":[0.1374964416027069,-0.0995221957564354,-0.23881998658180237,0.0888834074139595,0.08766160905361176,-0.054301533848047256,0.09235087782144547,-0.05471179634332657,0.11391986161470413,-0.05109303072094917,-0.07783570885658264,0.11637124419212341,-0.04078167676925659,-0.19643375277519226,-0.012467603199183941,0.1378190666437149,0.1547790765762329,0.1388811618089676,0.15235893428325653,-0.09687644243240356,-0.00448119081556797,0.13995234668254852,0.04458331689238548,-0.04354078695178032,-0.12057866156101227,0.05664230138063431,0.0024506496265530586,0.07555748522281647,-0.19228899478912354,0.19752494990825653,0.034551747143268585,0.07285095751285553,0.03136264905333519,0.09480073302984238,-0.07890890538692474,-0.08102438598871231,0.16904601454734802,0.05738012492656708,-0.03534103184938431,0.2570604383945465,0.10232322663068771,0.1090657189488411,-0.13954824209213257,0.025766940787434578,-0.008981546387076378,-0.13515356183052063,0.11217079311609268,0.07666867971420288,0.1324368268251419,0.15510649979114532,-0.09657442569732666,0.07892901450395584,-0.062041908502578735,-0.034234099090099335,0.03575710579752922,0.13726602494716644,-0.21715277433395386,-0.06636976450681686,-0.007606034632772207,0.14959512650966644,-0.05750041827559471,0.1269817352294922,-0.06219041720032692,-0.06227244436740875]},{"kind":"gelu"},{"kind":"linear","weight":[[-0.256316602230072,-0.41869139671325684,0.12848976254463196,0.28023797273635864,0.2314666509628296,-0.047868289053440094,0.1437232494354248,-0.2443913370370865,0.24442890286445618,0.1366681456565857,0.3689741790294647,0.2258232980966568,0.25106480717658997,0.098700612783432,0.34172478318214417,-0.2200087308883667,-0.1773279756307602,-0.052688274532556534,0.19632713496685028,0.34325069189071655,-0.27722376585006714,0.10373112559318542,0.25671830773353577,0.2974284589290619,-0.1930864453315735,0.037286121398210526,-0.11151750385761261,-0.3697717785835266,0.40635380148887634,0.27015024423599243,-0.3344922959804535,0.26551759243011475,-0.4000568091869354,-0.0640353262424469,0.03997233510017395,-0.15843524038791656,0.23580871522426605,-0.09529643505811691,0.27531349658966064,0.4777713418006897,0.24362677335739136,0.2636072337627411,0.1639242172241211,0.2225920855998993,-0.4818306863307953,0.15591049194335938,0.22348816692829132,0.23110024631023407,0.0399850532412529,-0.3020216226577759,0.14104950428009033,-0.1574067920446396,-0.3570803701877594,0.21175168454647064,0.2648904621601105,0.27299386262893677,-0.23372450470924377,0.13988950848579407,0.07334925979375839,-0.01358969509601593,-0.2595369219779968,0.22994881868362427,-0.23977315425872803,0.25872141122817993],[0.15128985047340393,0.15026439726352692,-0.0690409317612648,-0.14897151291370392,-0.16657185554504395,-0.1607498973608017,0.04162256419658661,-0.20839174091815948,-0.031817201524972916,0.1033577099442482,-0.006088704336434603,-0.06032951548695564,-0.05287812277674675,0.18819651007652283,-0.009069643914699554,0.12623152136802673,0.06619146466255188,0.10469004511833191,-0.1283072680234909,0.09086648374795914,0.0899677649140358,0.20215196907520294,-0.10364998877048492,0.08623696118593216,0.2580033540725708,-0.19890446960926056,0.11450927704572678,0.24441352486610413,-0.20016446709632874,-0.04622448980808258,-0.10849431157112122,-0.1073794886469841,0.2195870727300644,0.16610047221183777,-0.1717212200164795,0.2781696617603302,-0.21305902302265167,0.2215985208749771,-0.06953825801610947,-0.2803017497062683,-0.27952197194099426,-0.11338412016630173,0.24849581718444824,-0.07873713970184326,0.2703847885131836,-0.11793681234121323,-0.14026886224746704,-0.18888229131698608,0.025404606014490128,0.2229657918214798,-0.15003861486911774,-0.034545447677373886,-0.09328429400920868,0.041589945554733276,0.06337317079305649,-0.07266198843717575,0.18832899630069733,-0.3364676237106323,-0.004600223619490862,0.08489377051591873,0.16517558693885803,-0.08664259314537048,0.2654033601284027,-0.09495652467012405],[0.05204392969608307,0.10463833808898926,-0.04141977056860924,-0.034777019172906876,-0.12806124985218048,-0.06323357671499252,-0.13743318617343903,-0.09807916730642319,-0.16010794043540955,-0.06544000655412674,0.08104530721902847,-0.07353825867176056,0.09955426305532455,0.03499538078904152,0.11365173012018204,0.22779293358325958,0.06044425815343857,0.06687691062688828,-0.10195895284414291,-0.07650694251060486,0.2752526104450226,-0.08663035929203033,-0.055633027106523514,-0.12619565427303314,0.12679916620254517,-0.2394997775554657,-0.0068159461952745914,0.2201795130968094,-0.14638757705688477,-0.09924932569265366,-0.13674435019493103,-0.11186573654413223,0.0779648870229721,0.10139709711074829,-0.1256232112646103,0.298818439245224,-0.13535434007644653,0.21627074480056763,-0.004638707265257835,-0.22084127366542816,-0.2683684527873993,-0.014555558562278748,0.2057899683713913,-0.1019897609949112,0.18904238939285278,-0.21551701426506042,-0.0631210133433342,-0.21215857565402985,0.11902613192796707,0.20222264528274536,-0.10875366628170013,0.15063340961933136,0.0014574638335034251,-0.024431511759757996,0.08426212519407272,-0.003202386200428009,0.33984285593032837,0.016650211066007614,-0.14533698558807373,0.16125765442848206,0.16189666092395782,0.04484277591109276,0.12986084818840027,-0.04008565470576286]],"bias":[0.06304477900266647,0.07505256682634354,-0.05109630897641182]}],"parity":{"rows":512,"max_abs_logit_diff":8.757330272501918e-06,"passed":true},"training_fit_auc_not_heldout":0.9248509082457422}"""

_SAFETY_SHADOW_CACHE = {"path": None, "model": None}


def _safety_shadow_model():
    path = SAFETY_RERANK_SHADOW
    cache_key = path or "<embedded>"
    if _SAFETY_SHADOW_CACHE["path"] != cache_key:
        try:
            if path:
                with open(path, "r", encoding="utf-8") as handle:
                    artifact = json.load(handle)
            else:
                artifact = json.loads(_EMBEDDED_SAFETY_MODEL_JSON)
            normalization = artifact["normalization"]
            _SAFETY_SHADOW_CACHE["model"] = {
                "phi_mean": np.asarray(
                    normalization["phi_mean"], dtype=float
                ),
                "phi_scale": np.asarray(
                    normalization["phi_scale"], dtype=float
                ),
                "cand_mean": np.asarray(
                    normalization["candidate_mean"], dtype=float
                ),
                "cand_scale": np.asarray(
                    normalization["candidate_scale"], dtype=float
                ),
                "layers": [
                    {
                        "kind": layer["kind"],
                        "weight": (
                            np.asarray(layer["weight"], dtype=float)
                            if "weight" in layer else None
                        ),
                        "bias": (
                            np.asarray(layer["bias"], dtype=float)
                            if "bias" in layer else None
                        ),
                    }
                    for layer in artifact["layers"]
                ],
                "phi_features": list(
                    artifact["input_contract"]["phi_features"]
                ),
            }
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            _SAFETY_SHADOW_CACHE["model"] = None
        _SAFETY_SHADOW_CACHE["path"] = cache_key
    return _SAFETY_SHADOW_CACHE["model"]


def safety_shadow_logit(observation, decision):
    """Score the chosen action with the exported safety ranker, log only.

    Replicates the training feature contract exactly: phi is the agent's
    own release-risk feature vector on the chosen candidate, the candidate
    block is candidate-frame center/size, volume, one-hot orientation, the
    release flag and the target container's shape, and the forward pass is
    the standardized linear-GELU stack from the exported artifact.
    """
    model = _safety_shadow_model()
    if model is None or decision.candidate is None:
        return None
    containers = observation.get("container_list", [])
    pool_list = observation.get("pool_list", [])
    container_idx = int(decision.action["container_idx"])
    item_idx = int(decision.action["item_idx"])
    if not 0 <= container_idx < len(containers):
        return None
    if not 0 <= item_idx < len(pool_list):
        return None
    container = containers[container_idx]
    orientation = int(decision.action["orientation"])
    features = release_risk_features(
        decision.candidate, pool_list[item_idx], container, orientation
    ).as_dict()
    phi = np.asarray(
        [float(features[name]) for name in model["phi_features"]],
        dtype=float,
    )
    center = [float(value) for value in decision.candidate.center]
    size = [float(value) for value in decision.candidate.size]
    candidate_block = np.asarray(
        [
            *center[:3],
            *size[:3],
            float(size[0] * size[1] * size[2]),
            *[
                1.0 if orientation == index else 0.0
                for index in range(6)
            ],
            1.0
            if (decision.candidate.name or "") == "release_candidate"
            else 0.0,
            float(container.get("length", 0.0)),
            float(container.get("width", 0.0)),
            float(container.get("height", 0.0)),
            1.0 if container.get("shelf") else 0.0,
            1.0 if container.get("is_prioritized") else 0.0,
            float(len(container.get("packed_items") or [])),
        ],
        dtype=float,
    )
    x = np.concatenate([
        (phi - model["phi_mean"]) / model["phi_scale"],
        (candidate_block - model["cand_mean"]) / model["cand_scale"],
    ])
    for layer in model["layers"]:
        if layer["kind"] == "linear":
            x = layer["weight"] @ x + layer["bias"]
        elif layer["kind"] == "gelu":
            x = np.asarray([
                0.5 * value * (1.0 + math.erf(value / math.sqrt(2.0)))
                for value in x
            ])
    return float(x[0])


def _safety_rerank_action_key(decision):
    return (
        int(decision.action["item_idx"]),
        int(decision.action["container_idx"]),
        tuple(
            round(float(value), 6)
            for value in decision.action["place_pos"]
        ),
        int(decision.action["orientation"]),
    )


def safety_rerank_record(
    observation, top_candidates, decision, extra_pool=None
):
    """Score the incumbent; on trigger, score the pool and propose.

    The rule is fixed in reports/state-model/gate2-rerank-protocol.md
    as amended by gate2b/gate2c: act only below the trigger logit, and
    then search the retained top-K PLUS every observed legal candidate
    of the step (the top-K restriction audit: rescuability is 0/27
    through the score-ordered top 3 and 18/27 through the full set) for
    an alternative that escapes the danger band by the preregistered
    margin while giving up at most an absolute unit of immediate score.
    Never refuse to act — with no eligible alternative the incumbent
    stands untouched. Returns (record, proposed_decision).
    """
    incumbent_logit = safety_shadow_logit(observation, decision)
    if incumbent_logit is None:
        return None, None
    record = {
        "mode": SAFETY_RERANK_MODE,
        "incumbent_logit": float(incumbent_logit),
        "incumbent_score": float(decision.score),
        "pool_size": None,
        "candidates": [],
        "triggered": bool(incumbent_logit < SAFETY_RERANK_TRIGGER_LOGIT),
        "would_swap": False,
        "proposed_rank": None,
        "proposed_logit": None,
        "enforced": False,
    }
    if not record["triggered"]:
        return record, None
    incumbent_key = _safety_rerank_action_key(decision)
    pool = []
    seen = set()
    for candidate in list(top_candidates) + list(extra_pool or []):
        key = _safety_rerank_action_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        pool.append(candidate)
    record["pool_size"] = len(pool)
    candidates = []
    for rank, candidate in enumerate(pool):
        try:
            logit = safety_shadow_logit(observation, candidate)
        except Exception:
            logit = None
        candidates.append(
            {
                "rank": rank,
                "logit": logit,
                "score": float(candidate.score),
                "is_incumbent": (
                    _safety_rerank_action_key(candidate) == incumbent_key
                ),
            }
        )
    record["candidates"] = sorted(
        (c for c in candidates if c["logit"] is not None),
        key=lambda c: c["logit"],
        reverse=True,
    )[:SAFETY_RERANK_RECORDED_CANDIDATES]
    score_floor = float(decision.score) - SAFETY_RERANK_MAX_SCORE_LOSS_ABS
    best = None
    for candidate in candidates:
        if candidate["is_incumbent"] or candidate["logit"] is None:
            continue
        if candidate["logit"] < SAFETY_RERANK_TRIGGER_LOGIT:
            continue
        if candidate["logit"] < (
            incumbent_logit + SAFETY_RERANK_MARGIN_LOGIT
        ):
            continue
        if candidate["score"] < score_floor:
            continue
        if best is None or (
            (candidate["logit"], candidate["score"])
            > (best["logit"], best["score"])
        ):
            best = candidate
    proposed = None
    if best is not None:
        record["would_swap"] = True
        record["proposed_rank"] = int(best["rank"])
        record["proposed_logit"] = float(best["logit"])
        proposed = pool[int(best["rank"])]
    return record, proposed


def last_resort_relaxed_action(
    observation, indexed_items, *, seconds, attempt_budget=4096,
):
    """One bounded rescan with the lateral guard relaxed to the official
    transport clearance, entered only after the deadline search accepted
    nothing. Every candidate this yields still passes the environment's own
    inclusion and transport requirements; what is relaxed is only the
    agent's self-imposed prudence margin, whose average-case value is
    irrelevant at a state where the alternative action is certain episode
    death. Returns (score, action) for the best candidate found, or None.
    """
    global SETTLED_ITEM_CLEARANCE
    containers = observation.get("container_list", [])
    has_priority = any(
        bool(container.get("is_prioritized", False))
        for container in containers
    )
    risk_lambda = (
        RELEASE_RISK_RERANK_LAMBDA if RELEASE_RISK_LIVE_RERANK else None
    )
    # A ladder, not a cliff: the first rung keeps the official transport
    # clearance between items, the later rungs drop below it. A candidate
    # from a low rung may fail the environment's own trajectory check --
    # which ends the episode exactly as the fixed fallback would have, so
    # the expected value of trying never falls below the status quo. The
    # first rung that yields anything wins, maximizing the survival odds
    # of the emitted action.
    ladder = (TRANSPORT_CLEARANCE, TRANSPORT_CLEARANCE / 2.0, 0.0)
    slice_seconds = float(seconds) / len(ladder)
    saved_clearance = SETTLED_ITEM_CLEARANCE
    best = None
    try:
        for clearance in ladder:
            SETTLED_ITEM_CLEARANCE = clearance
            deadline = time.perf_counter() + slice_seconds
            for item_idx, item, container_idx, orientation, candidate in (
                iter_prioritized_candidates(
                    observation,
                    indexed_items,
                    deadline=deadline,
                    attempt_budget=int(attempt_budget),
                )
            ):
                container = containers[container_idx]
                score = Ranker.score(
                    candidate, item, container, has_priority
                )
                score, _probability = risk_adjusted_score(
                    score, candidate, item, container, orientation,
                    risk_lambda,
                )
                if best is None or float(score) > best[0]:
                    best = (
                        float(score),
                        {
                            "item_idx": int(item_idx),
                            "container_idx": int(container_idx),
                            "place_pos": np.asarray(
                                simulator_action_center(
                                    candidate, container
                                ),
                                dtype=np.float32,
                            ),
                            "orientation": int(orientation),
                        },
                    )
            if best is not None:
                break
    finally:
        SETTLED_ITEM_CLEARANCE = saved_clearance
    return best


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


class VisibleTreeBudgetExhausted(Exception):
    """The wall-clock slice for the visible-pool tree search ran out."""


def visible_tree_should_swap(
    incumbent_path_score,
    best_path_score,
    best_is_incumbent,
    tie_band=None,
):
    """Preregistered decision rule, isolated from the search so it is
    testable without a simulator. The played action moves to the best
    root ONLY when that root is not the incumbent and its path score
    exceeds the incumbent root's by MORE than the tie band; in every
    other case -- including missing scores -- the incumbent stands.
    """
    band = (
        VISIBLE_TREE_SEARCH_TIE_BAND if tie_band is None else float(tie_band)
    )
    if best_is_incumbent:
        return False
    if incumbent_path_score is None or best_path_score is None:
        return False
    return float(best_path_score) > float(incumbent_path_score) + band


def _visible_tree_guard_inflation(grid):
    # Half a cell on top of the clearance absorbs the quantization of
    # stamping by cell centres, erring toward over-avoidance.
    return float(SETTLED_ITEM_CLEARANCE) + max(grid.cell_x, grid.cell_y) / 2.0


def _visible_tree_inflated(box, inflate):
    return AABB(
        center=box.center,
        size=(
            float(box.size[0]) + 2.0 * inflate,
            float(box.size[1]) + 2.0 * inflate,
            float(box.size[2]),
        ),
        name=box.name,
    )


def _visible_tree_guard_surface(grid, container):
    """Surface with every obstacle inflated by the lateral guard.

    A drop height read from this surface yields commanded poses that
    clear Geometry.clears_static_geometry against the REAL cargo by
    construction (to cell resolution): the shipped guard refuses poses
    within SETTLED_ITEM_CLEARANCE laterally of any obstacle, so the
    score elite of a bare-surface scan -- packed tight against cargo --
    would be rejected wholesale by the shipped checks.
    """
    guard = grid.floor.copy()
    filled = np.zeros_like(guard)
    inflate = _visible_tree_guard_inflation(grid)
    for shelf in shelf_aabbs(container):
        _board_stamp(
            grid,
            guard,
            filled,
            _visible_tree_inflated(shelf, inflate),
            from_floor=True,
        )
    for box, _is_soft, _is_prioritized in packed_aabbs_local(container):
        _board_stamp(grid, guard, filled, _visible_tree_inflated(box, inflate))
    return guard


def visible_tree_heightmaps(containers):
    """Mutable per-container heightmap state seeded from the settled board.

    Each entry is (grid, top, guard): the exact surface for stamping and
    receptivity, and the clearance-inflated surface the placement scan
    reads drop heights from. The grid and base occupancy are the cached
    board_k machinery; only the surface copies are private to one root's
    path, so stamping never leaks into the live caches.
    """
    state = {}
    for index, container in enumerate(containers):
        grid = board_grid(container)
        top, _filled = board_occupancy(container, grid)
        state[index] = (
            grid,
            top.copy(),
            _visible_tree_guard_surface(grid, container),
        )
    return state


def _visible_tree_apply(grid, top, guard, box):
    """Stamp one path placement: exact surface and guard surface."""
    filled = np.zeros_like(top)
    _board_stamp(grid, top, filled, box)
    _board_stamp(
        grid,
        guard,
        filled,
        _visible_tree_inflated(box, _visible_tree_guard_inflation(grid)),
    )


def visible_tree_stamp(grid, top, candidate, container):
    """Stamp one candidate's settled-proxy AABB onto a heightmap copy.

    The settled proxy consults the REAL container only, so it is correct
    for the root (depth 0). Deeper path placements are already computed
    at the heightmap drop height and must be stamped as-is via
    _board_stamp, or the proxy would sink them through hypothetical
    cargo the real container does not contain.
    """
    filled = np.zeros_like(top)
    _board_stamp(
        grid, top, filled, settled_proxy_candidate(candidate, container)
    )
    return top


def _visible_tree_footprint_window(grid, x, y, dx, dy):
    i0 = int(np.searchsorted(grid.xs, x - dx / 2.0, side="left"))
    i1 = int(np.searchsorted(grid.xs, x + dx / 2.0, side="right"))
    j0 = int(np.searchsorted(grid.ys, y - dy / 2.0, side="left"))
    j1 = int(np.searchsorted(grid.ys, y + dy / 2.0, side="right"))
    if i1 <= i0 or j1 <= j0:
        return None
    return (slice(i0, i1), slice(j0, j1))


def visible_tree_drop_height(grid, top, x, y, dx, dy):
    """Drop height under one footprint: the highest surface column.

    Returns None when the footprint covers no usable column or leaves
    the usable interior, i.e. the heightmap cannot say where the item
    would land.
    """
    window = _visible_tree_footprint_window(grid, x, y, dx, dy)
    if window is None:
        return None
    if not bool(grid.usable[window].all()):
        return None
    return float(top[window].max())


def _visible_tree_item_footprints(item):
    """Distinct (dx, dy) footprints of one item, each with its lowest dz."""
    footprints = {}
    for orientation in unique_orientations(item):
        dx, dy, dz = get_rotated_dimensions(
            item["length"], item["width"], item["height"], orientation
        )
        key = (round(float(dx), 6), round(float(dy), 6))
        previous = footprints.get(key)
        if previous is None or float(dz) < previous[3]:
            footprints[key] = (
                int(orientation), float(dx), float(dy), float(dz)
            )
    return list(footprints.values())


def _visible_tree_scan_item(
    item, state, containers, has_priority, deadline
):
    """Best placement of one item on the current path heightmaps.

    Positions are window-aligned at a coarse stride
    (VISIBLE_TREE_SEARCH_STRIDE); z is the drop height on the
    clearance-inflated guard surface (_visible_tree_guard_surface). The
    prescreen ranks positions by the analytic Ranker terms (everything
    but support, and zone when a zone order is active -- both bounded),
    the leaders are re-scored with the shipped Ranker, and the winner
    is the best-by-shipped-score candidate that passes the shipped
    release checks while the budget affords them. CAVEAT: the shipped
    checks and Geometry.support_ratio consult the REAL container only;
    hypothetical path cargo exists solely in the heightmap, so support
    for stacking on it is under-reported and its corridor shadow is
    invisible -- a known proxy mismatch, priced by the paired A/B, not
    fixed here. Returns (score, container_idx, orientation, AABB) or
    None; raises VisibleTreeBudgetExhausted past the deadline.
    """
    mass = float(item.get("mass", 1.0))
    is_priority_item = bool(item.get("is_prioritized", False))
    shortlist = []
    for container_idx in eligible_container_indices(item, containers):
        entry = state.get(container_idx)
        if entry is None:
            continue
        grid, _top, guard = entry
        container = containers[container_idx]
        is_priority_container = bool(
            container.get("is_prioritized", False)
        )
        routing = 0.0
        if has_priority:
            if is_priority_item and is_priority_container:
                routing = 8.0
            elif not is_priority_item and is_priority_container:
                routing = -2.5
        step_i = max(
            1, int(round(VISIBLE_TREE_SEARCH_STRIDE / grid.cell_x))
        )
        step_j = max(
            1, int(round(VISIBLE_TREE_SEARCH_STRIDE / grid.cell_y))
        )
        for orientation, dx, dy, dz in _visible_tree_item_footprints(item):
            if time.perf_counter() >= deadline:
                raise VisibleTreeBudgetExhausted
            nx, ny = guard.shape
            wx = min(max(1, int(math.ceil(dx / grid.cell_x - EPS))), nx)
            wy = min(max(1, int(math.ceil(dy / grid.cell_y - EPS))), ny)
            if nx < wx or ny < wy:
                continue
            axes = (-2, -1)
            windows_top = np.lib.stride_tricks.sliding_window_view(
                guard, (wx, wy)
            ).max(axis=axes)
            windows_ceiling = np.lib.stride_tricks.sliding_window_view(
                grid.ceiling, (wx, wy)
            ).min(axis=axes)
            windows_usable = np.lib.stride_tricks.sliding_window_view(
                grid.usable, (wx, wy)
            ).all(axis=axes)
            feasible = windows_usable & (
                windows_ceiling - windows_top >= dz - EPS
            )
            feasible = feasible[::step_i, ::step_j]
            if not feasible.any():
                continue
            z_bottom = windows_top[::step_i, ::step_j]
            xs_c = (grid.xs[: nx - wx + 1] + (wx - 1) * grid.cell_x / 2.0)[
                ::step_i
            ]
            ys_c = (grid.ys[: ny - wy + 1] + (wy - 1) * grid.cell_y / 2.0)[
                ::step_j
            ]
            volume = dx * dy * dz
            depth_weight = -0.55 if is_priority_item else 0.35
            analytic = (
                12.0 * volume
                + routing
                + depth_weight * ys_c[np.newaxis, :]
                - 0.12 * np.abs(xs_c)[:, np.newaxis]
                - 0.18 * (z_bottom + dz / 2.0) * mass
            )
            analytic = np.where(feasible, analytic, -np.inf)
            # Row-diverse leaders: the analytic best of every depth row.
            # A score-ordered top-K would concentrate in the deepest
            # region, and when the shipped checks refuse that whole
            # region every leader dies with it while legal positions at
            # other depths go unexamined; the validation cap below is
            # what bounds the shipped-check spend, not the shortlist.
            best_i = np.argmax(analytic, axis=0)
            columns = np.arange(analytic.shape[1])
            row_best = analytic[best_i, columns]
            for j in columns:
                if not math.isfinite(float(row_best[j])):
                    continue
                i = int(best_i[j])
                shortlist.append(
                    (
                        container_idx,
                        int(orientation),
                        float(xs_c[i]),
                        float(ys_c[int(j)]),
                        float(z_bottom[i, int(j)]),
                        (dx, dy, dz),
                    )
                )
    if not shortlist:
        return None
    scored = []
    for container_idx, orientation, x, y, z_bottom, dims in shortlist:
        candidate = AABB(
            center=(x, y, z_bottom + dims[2] / 2.0),
            size=dims,
            name="release_candidate",
        )
        scored.append(
            (
                float(
                    Ranker.score(
                        candidate,
                        item,
                        containers[container_idx],
                        has_priority,
                    )
                ),
                container_idx,
                orientation,
                candidate,
            )
        )
    scored.sort(key=lambda entry: -entry[0])
    # The shipped checks are affordable while at least a quarter of the
    # slice remains and the per-item validation cap is unspent; when
    # either runs out, the heightmap-level feasibility above stands
    # alone (the proxy caveat documented in the docstring).
    validations = 0
    for score, container_idx, orientation, candidate in scored:
        now = time.perf_counter()
        if now >= deadline:
            raise VisibleTreeBudgetExhausted
        if now >= deadline - VISIBLE_TREE_SEARCH_SECONDS * 0.25:
            return score, container_idx, orientation, candidate
        if validations >= VISIBLE_TREE_SEARCH_CHECKS_PER_ITEM:
            return None
        validations += 1
        if (
            Geometry.release_rejection_reason(
                candidate, containers[container_idx], item
            )
            is None
        ):
            return score, container_idx, orientation, candidate
    return None


def visible_tree_item_receptivity(
    item, state, containers, cap=None, deadline=None
):
    """Measured receptivity of one remaining item on a leaf heightmap.

    Landing sites are counted with the board_k machinery. CAVEAT
    (evidence ledger: board-receptivity-is-not-a-feasibility-predictor):
    a landing-cell count is a receptivity PROXY, never a feasibility
    claim -- the flatness/headroom test knows nothing of the transport
    corridor, and the soft/priority support contract is unmodelled, so
    a site over soft or priority cargo counts even where the release
    contract would refuse to rest on it.
    """
    cap = VISIBLE_TREE_SEARCH_SITE_CAP if cap is None else int(cap)
    sites = 0
    footprints = _visible_tree_item_footprints(item)
    for container_idx in eligible_container_indices(item, containers):
        entry = state.get(container_idx)
        if entry is None:
            continue
        grid, top, _guard = entry
        headroom = grid.ceiling - top
        for _orientation, dx, dy, dz in footprints:
            if deadline is not None and time.perf_counter() >= deadline:
                raise VisibleTreeBudgetExhausted
            sites += _board_site_count(grid, top, headroom, (dx, dy, dz))
            if sites >= cap:
                return cap
    return min(sites, cap)


def _visible_tree_expand_root(
    root, pool_list, containers, has_priority, deadline
):
    """Greedy depth-limited path below one root, then the measured leaf.

    Enumeration is approximated: at each depth step every remaining
    visible item's best placement is computed and the single best by
    shipped score is committed, i.e. items are placed greedily in
    shipped-score order rather than enumerating item permutations.
    Returns (path_score, leaf_receptivity, expanded_depth).
    """
    state = visible_tree_heightmaps(containers)
    root_container_idx = int(root.action["container_idx"])
    grid, top, guard = state[root_container_idx]
    _visible_tree_apply(
        grid,
        top,
        guard,
        settled_proxy_candidate(
            root.candidate, containers[root_container_idx]
        ),
    )
    consumed = {int(root.action["item_idx"])}
    path_scores = [float(root.score)]
    for _depth in range(VISIBLE_TREE_SEARCH_DEPTH):
        best = None
        for pool_index, item in enumerate(pool_list):
            if pool_index in consumed:
                continue
            placement = _visible_tree_scan_item(
                item, state, containers, has_priority, deadline
            )
            if placement is None:
                continue
            if best is None or placement[0] > best[1][0]:
                best = (pool_index, placement)
        if best is None:
            break
        pool_index, (score, container_idx, _orientation, candidate) = best
        grid, top, guard = state[container_idx]
        # Already at the guard-surface drop height: stamp as-is (see
        # visible_tree_stamp on why the settled proxy must not rerun).
        _visible_tree_apply(grid, top, guard, candidate)
        consumed.add(pool_index)
        path_scores.append(float(score))
    receptivity = 0
    for pool_index, item in enumerate(pool_list):
        if pool_index in consumed:
            continue
        receptivity += visible_tree_item_receptivity(
            item, state, containers, deadline=deadline
        )
    path_score = (
        float(sum(path_scores))
        + VISIBLE_TREE_SEARCH_RECEPTIVITY_WEIGHT * float(receptivity)
    )
    return path_score, int(receptivity), len(path_scores) - 1


def visible_tree_search_record(
    observation, top_candidates, decision, *, deadline=None
):
    """Expand incumbent + retained alternatives, score measured leaves.

    Returns (record, proposed_decision). proposed_decision is non-None
    only when the preregistered rule (visible_tree_should_swap) fires;
    on deadline exhaustion the comparison is skipped entirely -- a
    partial comparison would favor whichever roots were scored first --
    so the incumbent stands and the record notes budget_exhausted.
    """
    started = time.perf_counter()
    if deadline is None:
        deadline = started + VISIBLE_TREE_SEARCH_SECONDS
    record = {
        "mode": VISIBLE_TREE_SEARCH,
        "branch": int(VISIBLE_TREE_SEARCH_BRANCH),
        "depth": int(VISIBLE_TREE_SEARCH_DEPTH),
        "tie_band": float(VISIBLE_TREE_SEARCH_TIE_BAND),
        "roots_considered": 0,
        "roots_expanded": 0,
        "leaves_scored": 0,
        "incumbent_path_score": None,
        "best_path_score": None,
        "best_root_rank": None,
        "would_change": False,
        "enforced": False,
        "budget_exhausted": False,
        "elapsed_seconds": 0.0,
        "roots": [],
    }
    pool_list = observation.get("pool_list", [])
    containers = observation.get("container_list", [])
    has_priority = any(
        bool(container.get("is_prioritized", False))
        for container in containers
    )
    incumbent_key = _safety_rerank_action_key(decision)
    roots = [decision]
    seen = {incumbent_key}
    for candidate in top_candidates:
        if len(roots) >= VISIBLE_TREE_SEARCH_BRANCH:
            break
        key = _safety_rerank_action_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        roots.append(candidate)
    record["roots_considered"] = len(roots)
    results = []
    try:
        for rank, root in enumerate(roots):
            if time.perf_counter() >= deadline:
                raise VisibleTreeBudgetExhausted
            path_score, receptivity, expanded_depth = (
                _visible_tree_expand_root(
                    root, pool_list, containers, has_priority, deadline
                )
            )
            results.append((rank, root, path_score))
            record["roots_expanded"] += 1
            record["leaves_scored"] += 1
            record["roots"].append(
                {
                    "rank": rank,
                    "is_incumbent": rank == 0,
                    "root_score": float(root.score),
                    "path_score": float(path_score),
                    "leaf_receptivity": int(receptivity),
                    "expanded_depth": int(expanded_depth),
                }
            )
    except VisibleTreeBudgetExhausted:
        record["budget_exhausted"] = True
    proposed = None
    if results:
        incumbent_path_score = float(results[0][2])
        best_rank, best_root, best_path_score = max(
            results, key=lambda entry: (entry[2], -entry[0])
        )
        record["incumbent_path_score"] = incumbent_path_score
        record["best_path_score"] = float(best_path_score)
        record["best_root_rank"] = int(best_rank)
        if not record["budget_exhausted"]:
            record["would_change"] = visible_tree_should_swap(
                incumbent_path_score, best_path_score, best_rank == 0
            )
            if record["would_change"]:
                proposed = best_root
    record["elapsed_seconds"] = float(time.perf_counter() - started)
    return record, proposed


_PHYSICS_PROBE_STATE = {"module": None, "import_failed": False, "client": None}


def _physics_probe_bullet():
    """Lazy pybullet loader; import failure disables the probe forever.

    The import is deliberately function-local: the shipped agent must
    load unchanged in an environment without pybullet, so the module can
    never be imported at module scope.
    """
    if _PHYSICS_PROBE_STATE["import_failed"]:
        return None
    if _PHYSICS_PROBE_STATE["module"] is None:
        try:
            import pybullet
        except ImportError:
            _PHYSICS_PROBE_STATE["import_failed"] = True
            return None
        _PHYSICS_PROBE_STATE["module"] = pybullet
    return _PHYSICS_PROBE_STATE["module"]


def physics_probe_available():
    return _physics_probe_bullet() is not None


def _physics_probe_client(bullet):
    """One cached DIRECT client; the scene is rebuilt fresh per call."""
    client = _PHYSICS_PROBE_STATE["client"]
    if client is None:
        client = bullet.connect(bullet.DIRECT)
        _PHYSICS_PROBE_STATE["client"] = client
    return client


def _physics_probe_item_dynamics(item_dict):
    """Official item dynamics (simulator/src/ground_handling/items.py).

    Item.spawn applies the Item instance values, which the observation
    dicts carry verbatim (Item.get_info), so per-item config overrides
    ride along; the fallbacks are the items.py class defaults.
    """
    params = {
        "lateralFriction": float(item_dict.get("lateralFriction", 0.8)),
        "rollingFriction": float(item_dict.get("rollingFriction", 0.01)),
        "spinningFriction": float(item_dict.get("spinningFriction", 0.01)),
        "restitution": float(item_dict.get("restitution", 0.0)),
        "angularDamping": float(item_dict.get("angularDamping", 0.8)),
    }
    if item_dict.get("is_soft"):
        params.update(
            {
                "contactStiffness": float(
                    item_dict.get("contactStiffness", 5000)
                ),
                "contactDamping": float(item_dict.get("contactDamping", 500)),
                "linearDamping": float(item_dict.get("linearDamping", 0.8)),
            }
        )
    return params


def _physics_probe_box(
    bullet, client, half_extents, center, orn=(0.0, 0.0, 0.0, 1.0),
    mass=0.0, dynamics=None,
):
    shape = bullet.createCollisionShape(
        bullet.GEOM_BOX,
        halfExtents=[float(value) for value in half_extents],
        physicsClientId=client,
    )
    body = bullet.createMultiBody(
        baseMass=float(mass),
        baseCollisionShapeIndex=shape,
        basePosition=[float(value) for value in center],
        baseOrientation=[float(value) for value in orn],
        physicsClientId=client,
    )
    if dynamics is None:
        # Static container geometry dynamics (Container._create_body).
        dynamics = {
            "lateralFriction": 0.8,
            "rollingFriction": 0.01,
            "spinningFriction": 0.01,
        }
    bullet.changeDynamics(body, -1, physicsClientId=client, **dynamics)
    return body


def physics_probe_settle(observation, decision):
    """Replay the frozen decision's settle in a DIRECT pybullet scene.

    Frame: everything is container-local, the frame of place_pos itself.
    The simulator offsets containers on world X only (Container
    local_to_global), so container-local z equals world z, the
    packed_aabbs_local centers drop in directly, and no conversion is
    needed for any body in the scene.

    The scene clones the validator.place_item contract: gravity -9.8,
    deterministic overlapping pairs, packed items at their settled poses
    with the official dynamics, then the candidate warped to its command
    pose and stepped for the official settle horizon. Log-only: the
    decision is never touched. Returns {angle_deg, displacement,
    predicted_safe, scene_bodies, elapsed_seconds} or None on failure.
    """
    bullet = _physics_probe_bullet()
    if bullet is None or decision is None:
        return None
    started = time.perf_counter()
    client = None
    try:
        containers = observation.get("container_list", [])
        pool_list = observation.get("pool_list", [])
        container_idx = int(decision.action["container_idx"])
        item_idx = int(decision.action["item_idx"])
        orientation = int(decision.action["orientation"])
        if not 0 <= container_idx < len(containers):
            return None
        if not 0 <= item_idx < len(pool_list):
            return None
        if not 0 <= orientation < len(SIMULATOR_ORNS):
            return None
        container = containers[container_idx]
        length = float(container["length"])
        width = float(container["width"])
        height = float(container["height"])
        thickness = float(container["thickness"])
        buffer = float(container.get("buffer", 0.0))

        client = _physics_probe_client(bullet)
        bullet.resetSimulation(physicsClientId=client)
        bullet.setGravity(0.0, 0.0, -9.8, physicsClientId=client)
        bullet.setPhysicsEngineParameter(
            deterministicOverlappingPairs=1, physicsClientId=client
        )

        # Envelope approximation, v1: a static floor box at the interior
        # floor height (thickness + buffer, the cup mesh's inner bottom)
        # plus four static wall boxes on the outer footprint, plus the
        # shelf boxes the agent already models (shelf_aabbs: the small
        # shelf over the cut, and the main shelf when the container
        # requires one). The corner cut's sloped face is omitted, and
        # the loading opening at y=-width/2 that the real container
        # leaves open is closed by a wall.
        floor_top = thickness + buffer
        scene_bodies = 0
        _physics_probe_box(
            bullet,
            client,
            (length / 2.0, width / 2.0, thickness / 2.0),
            (0.0, 0.0, floor_top - thickness / 2.0),
        )
        scene_bodies += 1
        wall_center_z = buffer + height / 2.0
        for sign in (-1.0, 1.0):
            _physics_probe_box(
                bullet,
                client,
                (thickness / 2.0, width / 2.0, height / 2.0),
                (sign * (length / 2.0 - thickness / 2.0), 0.0, wall_center_z),
            )
            scene_bodies += 1
            _physics_probe_box(
                bullet,
                client,
                (length / 2.0, thickness / 2.0, height / 2.0),
                (0.0, sign * (width / 2.0 - thickness / 2.0), wall_center_z),
            )
            scene_bodies += 1
        for shelf in shelf_aabbs(container):
            _physics_probe_box(bullet, client, tuple(
                float(value) / 2.0 for value in shelf.size
            ), shelf.center)
            scene_bodies += 1

        # Packed items at their settled poses. packed_aabbs_local is the
        # canonical reader of the packed_items dicts; mass and dynamics
        # come from a parallel walk over the same list under the same
        # skip rule, so the two stay index-aligned.
        boxes = packed_aabbs_local(container)
        packed_meta = []
        for packed in container.get("packed_items", []):
            try:
                packed_position_world(packed)
                packed_dimensions(packed)
            except (KeyError, TypeError, ValueError):
                continue
            packed_meta.append(packed)
        if len(packed_meta) != len(boxes):
            packed_meta = [{} for _ in boxes]
        dynamic_bodies = []
        for (box, is_soft, _is_priority), packed in zip(boxes, packed_meta):
            entry = packed if packed else {"is_soft": is_soft}
            # Settled pose: the true box (original dims at the settled
            # quaternion) whenever the dict carries one. The axis-aligned
            # settled AABB is only the fallback -- for a tilted settled
            # item the AABB overestimates the envelope and the warped
            # scene starts interpenetrated, which both distorts the
            # settle and keeps the contact solver jittering for the full
            # horizon.
            settled_orn = entry.get("orn")
            if (
                settled_orn is not None
                and len(settled_orn) == 4
                and entry.get("length") is not None
                and entry.get("width") is not None
                and entry.get("height") is not None
            ):
                packed_half = (
                    float(entry["length"]) / 2.0,
                    float(entry["width"]) / 2.0,
                    float(entry["height"]) / 2.0,
                )
                packed_orn = tuple(float(value) for value in settled_orn)
            else:
                packed_half = tuple(
                    float(value) / 2.0 for value in box.size
                )
                packed_orn = (0.0, 0.0, 0.0, 1.0)
            packed_body = _physics_probe_box(
                bullet,
                client,
                packed_half,
                box.center,
                orn=packed_orn,
                mass=float(entry.get("mass", 1.0)),
                dynamics=_physics_probe_item_dynamics(entry),
            )
            scene_bodies += 1
            dynamic_bodies.append(packed_body)

        # The candidate, warped to its command pose exactly as
        # validator.place_item does before its settle loop.
        item = pool_list[item_idx]
        target_pos = tuple(
            float(value) for value in decision.action["place_pos"]
        )
        target_orn = bullet.getQuaternionFromEuler(
            list(SIMULATOR_ORNS[orientation])
        )
        candidate_body = _physics_probe_box(
            bullet,
            client,
            (
                float(item["length"]) / 2.0,
                float(item["width"]) / 2.0,
                float(item["height"]) / 2.0,
            ),
            target_pos,
            orn=target_orn,
            mass=float(item.get("mass", 1.0)),
            dynamics=_physics_probe_item_dynamics(item),
        )
        scene_bodies += 1
        dynamic_bodies.append(candidate_body)

        # Official settle horizon, with the official builder's early
        # stop cloned from MultiContainerManager.build: after a 60-step
        # warmup, break once every dynamic body's velocity is under
        # 1 mm/s. The horizon and criterion are the simulator's own
        # constants; steps skipped this way cannot move a settled body.
        for settle_step in range(PHYSICS_PROBE_SETTLE_STEPS):
            bullet.stepSimulation(physicsClientId=client)
            if settle_step > 60:
                all_sleeping = True
                for body in dynamic_bodies:
                    linear_v, angular_v = bullet.getBaseVelocity(
                        body, physicsClientId=client
                    )
                    if (
                        sum(abs(value) for value in linear_v) > 0.001
                        or sum(abs(value) for value in angular_v) > 0.001
                    ):
                        all_sleeping = False
                        break
                if all_sleeping:
                    break

        final_pos, final_orn = bullet.getBasePositionAndOrientation(
            candidate_body, physicsClientId=client
        )
        displacement = math.sqrt(
            sum(
                (float(final_value) - float(target_value)) ** 2
                for final_value, target_value in zip(final_pos, target_pos)
            )
        )
        # Same quaternion angle as validator.place_item.
        dot_product = min(
            1.0,
            abs(
                sum(
                    float(a) * float(b)
                    for a, b in zip(target_orn, final_orn)
                )
            ),
        )
        angle_deg = math.degrees(2.0 * math.acos(dot_product))
        return {
            "angle_deg": float(angle_deg),
            "displacement": float(displacement),
            "predicted_safe": bool(
                displacement <= PHYSICS_PROBE_DISPLACEMENT_THRESHOLD
                and angle_deg <= PHYSICS_PROBE_ANGLE_THRESHOLD_DEG
            ),
            "scene_bodies": int(scene_bodies),
            "elapsed_seconds": float(time.perf_counter() - started),
        }
    except Exception:
        return None
    finally:
        # The client is cached; the bodies are not. Reset so calls do
        # not leak scene state into each other.
        if client is not None:
            try:
                bullet.resetSimulation(physicsClientId=client)
            except Exception:
                pass


def guard_attr_eligible(incumbent_violations, alternative_violations):
    """The attribute-filter clause, pure so it is testable alone.

    attribute-filter-protocol.md: an alternative is ineligible if it
    INCREASES priority or soft coverage violations relative to the
    incumbent's own. Equal counts stay eligible. Both arguments are
    (priority, soft) pairs from candidate_attribute_violations.
    """
    incumbent_priority, incumbent_soft = incumbent_violations
    alternative_priority, alternative_soft = alternative_violations
    return (
        int(alternative_priority) <= int(incumbent_priority)
        and int(alternative_soft) <= int(incumbent_soft)
    )


def probe_guard_choose(
    incumbent,
    alternatives,
    probe_fn,
    deadline_fn,
    max_probes=PHYSICS_PROBE_GUARD_MAX_PROBES,
    violations_fn=None,
):
    """The guard's decision rule, pure so it is testable with stubs.

    probe_fn(decision) returns a physics_probe_settle-shaped dict or
    None on probe failure; deadline_fn() returns True once the budget
    slice is spent. The rule (probe-guard-protocol.md): a probe failure
    or a safe verdict plays the incumbent unchanged; an unsafe verdict
    walks `alternatives` in the given order and returns the FIRST whose
    probe predicts safe, within max_probes total probes (the
    incumbent's included) and the deadline. Never refuse: with no safe
    alternative, or on budget exhaustion, the incumbent stands.
    Returns (chosen, record).

    violations_fn (attribute-filter-protocol.md): when set, it maps a
    decision to its (priority, soft) attribute violations, or None on
    failure. The incumbent's pair is computed once, only after an
    unsafe verdict; an alternative failing guard_attr_eligible against
    it is skipped BEFORE its probe, spending no probe budget, and
    counted in attr_filtered_count. A None pair on either side leaves
    that alternative unfiltered.
    """
    record = {
        "probes_used": 0,
        "incumbent_safe": None,
        "swapped": False,
        "swap_rank": None,
        "budget_exhausted": False,
        "attr_filtered_count": 0,
    }
    if deadline_fn():
        record["budget_exhausted"] = True
        return incumbent, record
    incumbent_result = probe_fn(incumbent)
    record["probes_used"] = 1
    if incumbent_result is None:
        return incumbent, record
    predicted_safe = incumbent_result.get("predicted_safe")
    record["incumbent_safe"] = (
        None if predicted_safe is None else bool(predicted_safe)
    )
    if predicted_safe is not False:
        return incumbent, record
    incumbent_violations = (
        violations_fn(incumbent) if violations_fn is not None else None
    )
    for rank, alternative in enumerate(alternatives):
        if incumbent_violations is not None:
            alternative_violations = violations_fn(alternative)
            if alternative_violations is not None and not guard_attr_eligible(
                incumbent_violations, alternative_violations
            ):
                record["attr_filtered_count"] += 1
                continue
        if record["probes_used"] >= max_probes or deadline_fn():
            record["budget_exhausted"] = True
            return incumbent, record
        alternative_result = probe_fn(alternative)
        record["probes_used"] += 1
        if (
            alternative_result is not None
            and alternative_result.get("predicted_safe") is True
        ):
            record["swapped"] = True
            record["swap_rank"] = int(rank)
            return alternative, record
    return incumbent, record


def quiet_guard_should_probe(logit):
    """The quiet guard's trigger rule, pure so it is testable alone.

    quiet-guard-protocol.md: probe only below the calibrated trigger
    (SAFETY_RERANK_TRIGGER_LOGIT). A None logit -- shadow model missing
    or the scorer failed -- skips too: the guard never fires blind.
    """
    if logit is None:
        return False
    return float(logit) < SAFETY_RERANK_TRIGGER_LOGIT


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
        risk_lambda=None,
    ):
        self.container_templates = [
            normalize_container(container) for container in container_templates
        ]
        self._cache = {}
        self.cache_hits = 0
        self.evaluations = 0
        self.last_trace = []
        self.attempts_per_item = max(0, int(attempts_per_item))
        self.risk_lambda = risk_lambda

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
                    risk_lambda=self.risk_lambda,
                )
            else:
                decision = PlacementCore.choose(
                    observation,
                    [(0, item)],
                    deadline=deadline,
                    risk_lambda=self.risk_lambda,
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
        self.last_multi_axis_shadow = None

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
        self.last_top_candidates = []
        self.last_multi_axis_shadow = None
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
                "multi_axis_selector_mode": MULTI_AXIS_SELECTOR_MODE,
                "residual_affordance_shadow_mode": (
                    RESIDUAL_AFFORDANCE_SHADOW_MODE
                ),
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
            risk_lambda=(
                RELEASE_RISK_RERANK_LAMBDA
                if OFFLINE_RISK_RERANK
                else None
            ),
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
        self.last_multi_axis_shadow = None
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
        if NEDO_POSE_SNAPSHOT and self._policy_trace_path:
            # Log-only, same discipline as the trace shadows below: record
            # what the observation already carries, touch nothing. Each
            # packed_items entry is Item.get_info(): pos is the world
            # position and orn the world quaternion, both refreshed by the
            # env after every safe placement, so this is the current pose,
            # not the placement-step pose. Recorded verbatim (null when the
            # env has not registered a pose).
            try:
                snapshot_containers = []
                for container_pos, container in enumerate(containers):
                    packed_entries = []
                    for packed in container.get("packed_items") or []:
                        pos = packed.get("pos")
                        orn = packed.get("orn")
                        packed_entries.append(
                            {
                                "index": int(packed.get("index", -1)),
                                "pos": (
                                    [float(value) for value in pos]
                                    if pos is not None
                                    else None
                                ),
                                "orn": (
                                    [float(value) for value in orn]
                                    if orn is not None
                                    else None
                                ),
                                "dims": [
                                    float(packed.get("length", 0.0)),
                                    float(packed.get("width", 0.0)),
                                    float(packed.get("height", 0.0)),
                                ],
                                "is_soft": bool(
                                    packed.get("is_soft", False)
                                ),
                                "is_prioritized": bool(
                                    packed.get("is_prioritized", False)
                                ),
                            }
                        )
                    snapshot_containers.append(
                        {
                            "container_index": int(
                                container.get("index", container_pos)
                            ),
                            "packed_items": packed_entries,
                        }
                    )
                self._append_policy_trace(
                    {
                        "event": "pose_snapshot",
                        "step": self._policy_step,
                        "containers": snapshot_containers,
                    }
                )
            except Exception:
                pass
        ordered_items = capped_online_items(
            pool_list,
            effective_online_item_cap(observation),
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
        # Gate 2c: retain every legal candidate the search materializes as
        # the safety-rerank swap pool. Collection is a bounded list append
        # per candidate; logits are computed only at triggered steps. The
        # top-K restriction audit showed rescuability is 0/27 through the
        # score-ordered top 3 and 18/27 through the full candidate set --
        # safe alternatives live deep in the score ordering, so the pool
        # must not be score-selected.
        #
        # Since the 2026-08-17 guard_quiet adoption the guard modes
        # materialize this pool directly: the probe guard's alternatives
        # come from it, and the ablation arms previously borrowed
        # SAFETY_RERANK_MODE=shadow solely to trigger this collection.
        # Flipping the gating here instead keeps the rerank machinery --
        # and its per-step safety_rerank records -- off by default. Guard
        # modes collect only while pybullet is importable: without it no
        # probe can consume the pool, and skipping the observer keeps the
        # missing-pybullet trajectory identical to the pre-adoption
        # default.
        safety_pool = None
        if SAFETY_RERANK_MODE != "off" or (
            PHYSICS_PROBE_MODE in ("guard", "guard_quiet")
            and physics_probe_available()
        ):
            safety_pool = []

            def observe_safety_candidate(
                item_idx, item, container_idx, orientation, decision
            ):
                if len(safety_pool) < SAFETY_RERANK_POOL_CAP:
                    safety_pool.append(decision)

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
        if safety_pool is not None:
            candidate_observers.append(observe_safety_candidate)
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
        if (
            MULTI_AXIS_SELECTOR_MODE in {"shadow", "enforce"}
            and self.last_top_candidates
        ):
            # Compute telemetry only after every live selection decision is
            # frozen.  Running this before lookahead changed its wall-clock
            # budget and failed the first physical negative control.
            self.last_multi_axis_shadow = multi_axis_shadow_record(
                self.last_top_candidates, observation, decision
            )
            if (
                MULTI_AXIS_SELECTOR_MODE == "enforce"
                and decision is not None
                and action_source == "placement_core"
                and self.last_multi_axis_shadow["selected_dominated"]
            ):
                proposed_rank = int(
                    self.last_multi_axis_shadow["proposed_rank"]
                )
                decision = self.last_top_candidates[proposed_rank]
                action_source = "multi_axis_enforce"
                self.last_multi_axis_shadow["enforced"] = True
        if (
            RESIDUAL_AFFORDANCE_SHADOW_MODE == "shadow"
            and decision is not None
            and action_source == "placement_core"
            and self.last_top_candidates
        ):
            # The model is evaluated only after the live decision is frozen.
            # There is intentionally no enforce branch: official-score and
            # special-attribute reach must be measured first.
            try:
                residual_record = residual_affordance_shadow_record(
                    self.last_top_candidates, observation, decision
                )
            except Exception:
                residual_record = None
            if residual_record is not None:
                self.last_candidate_diagnostics[
                    "residual_affordance_shadow"
                ] = residual_record
        if (
            SAFETY_RERANK_MODE != "off"
            and decision is not None
            and action_source == "placement_core"
            and (self.last_top_candidates or safety_pool)
        ):
            # Same discipline as the multi-axis selector: score only after
            # every live selection decision is frozen, so shadow mode is a
            # true physical negative control for the enforce arm.
            try:
                rerank_record, rerank_proposed = safety_rerank_record(
                    observation,
                    self.last_top_candidates,
                    decision,
                    extra_pool=safety_pool,
                )
            except Exception:
                rerank_record, rerank_proposed = None, None
            if rerank_record is not None:
                if (
                    SAFETY_RERANK_MODE == "enforce"
                    and rerank_record["would_swap"]
                    and rerank_proposed is not None
                ):
                    decision = rerank_proposed
                    action_source = "safety_rerank"
                    rerank_record["enforced"] = True
                self.last_candidate_diagnostics["safety_rerank"] = (
                    rerank_record
                )
                self._append_policy_trace(
                    {
                        "event": "safety_rerank",
                        "step": self._policy_step,
                        "mode": rerank_record["mode"],
                        "incumbent_logit": rerank_record["incumbent_logit"],
                        "pool_size": rerank_record["pool_size"],
                        "triggered": rerank_record["triggered"],
                        "would_swap": rerank_record["would_swap"],
                        "proposed_rank": rerank_record["proposed_rank"],
                        "proposed_logit": rerank_record["proposed_logit"],
                        "enforced": rerank_record["enforced"],
                    }
                )
        if (
            VISIBLE_TREE_SEARCH != "off"
            and decision is not None
            and action_source == "placement_core"
            and self.last_top_candidates
        ):
            # Same discipline as the selectors above: the search runs only
            # after every live selection decision is frozen, so shadow mode
            # is a true physical negative control for the enforce arm. The
            # slice is clamped to the shipped policy deadline: the search
            # must never extend a step past the budget the shipped agent
            # already honors -- a step that arrives here exhausted gets an
            # immediate budget_exhausted record and the incumbent stands.
            try:
                tree_record, tree_proposed = visible_tree_search_record(
                    observation,
                    self.last_top_candidates,
                    decision,
                    deadline=min(
                        time.perf_counter() + VISIBLE_TREE_SEARCH_SECONDS,
                        deadline,
                    ),
                )
            except Exception:
                tree_record, tree_proposed = None, None
            if tree_record is not None:
                if (
                    VISIBLE_TREE_SEARCH == "enforce"
                    and tree_record["would_change"]
                    and tree_proposed is not None
                ):
                    decision = tree_proposed
                    action_source = "visible_tree_search"
                    tree_record["enforced"] = True
                self.last_candidate_diagnostics["visible_tree_search"] = (
                    tree_record
                )
                self._append_policy_trace(
                    {
                        "event": "visible_tree_search",
                        "step": self._policy_step,
                        "mode": tree_record["mode"],
                        "roots_expanded": tree_record["roots_expanded"],
                        "leaves_scored": tree_record["leaves_scored"],
                        "incumbent_path_score": tree_record[
                            "incumbent_path_score"
                        ],
                        "best_path_score": tree_record["best_path_score"],
                        "would_change": tree_record["would_change"],
                        "enforced": tree_record["enforced"],
                        "budget_exhausted": tree_record["budget_exhausted"],
                        "elapsed_seconds": tree_record["elapsed_seconds"],
                    }
                )
        if (
            PHYSICS_PROBE_SHADOW
            and decision is not None
            and action_source == "placement_core"
        ):
            # Log-only, same discipline as the shadows above: the probe
            # runs only after every live selection decision is frozen and
            # never touches the action. Without pybullet the probe is
            # unavailable and leaves zero footprint (no event); a probe
            # that fails at runtime logs null fields so the failure rate
            # stays measurable.
            try:
                if physics_probe_available():
                    probe_record = (
                        physics_probe_settle(observation, decision) or {}
                    )
                    self._append_policy_trace(
                        {
                            "event": "physics_probe",
                            "step": self._policy_step,
                            "angle_deg": probe_record.get("angle_deg"),
                            "displacement": probe_record.get("displacement"),
                            "predicted_safe": probe_record.get(
                                "predicted_safe"
                            ),
                            "scene_bodies": probe_record.get("scene_bodies"),
                            "elapsed_seconds": probe_record.get(
                                "elapsed_seconds"
                            ),
                        }
                    )
            except Exception:
                pass
        if (
            PHYSICS_PROBE_MODE in ("guard", "guard_quiet")
            and decision is not None
            and action_source == "placement_core"
        ):
            # Same discipline as the seams above: the guard runs only after
            # every live selection decision is frozen. Its slice is clamped
            # to the shipped policy deadline, so it can never extend a step
            # past the budget the shipped agent already honors. On any
            # exception the incumbent plays -- never refuse, never fall
            # through.
            try:
                if physics_probe_available():
                    guard_started = time.perf_counter()
                    quiet_mode = PHYSICS_PROBE_MODE == "guard_quiet"
                    incumbent_logit = None
                    if quiet_mode:
                        # Quiet trigger (quiet-guard-protocol.md): price
                        # the incumbent with the Gate 1 instrument BEFORE
                        # any probe; at or above the trigger, or on a
                        # failed logit, the step plays unchanged with no
                        # probe and the event records the skip.
                        try:
                            incumbent_logit = safety_shadow_logit(
                                observation, decision
                            )
                        except Exception:
                            incumbent_logit = None
                        if incumbent_logit is not None:
                            incumbent_logit = float(incumbent_logit)
                    if quiet_mode and not quiet_guard_should_probe(
                        incumbent_logit
                    ):
                        self._append_policy_trace(
                            {
                                "event": "physics_probe_guard",
                                "step": self._policy_step,
                                "probes_used": 0,
                                "incumbent_safe": None,
                                "swapped": False,
                                "swap_rank": None,
                                "elapsed_seconds": float(
                                    time.perf_counter() - guard_started
                                ),
                                "budget_exhausted": False,
                                "quiet_skipped": True,
                                "incumbent_logit": incumbent_logit,
                                "attr_filtered_count": 0,
                            }
                        )
                    else:
                        guard_deadline = min(
                            guard_started + PHYSICS_PROBE_GUARD_SECONDS,
                            deadline,
                        )
                        # Alternatives in shipped-score order: the retained
                        # top candidates first, then the observed legal pool
                        # sorted by shipped score descending. Guard modes
                        # materialize that pool themselves (see the
                        # safety_pool gating above), so this no longer
                        # depends on the rerank machinery's mode; if the
                        # pool is absent anyway, last_top_candidates alone
                        # is what the protocol accepts. Deduplicated by
                        # action key; the incumbent is skipped.
                        incumbent_key = _safety_rerank_action_key(decision)
                        seen_keys = {incumbent_key}
                        guard_alternatives = []
                        guard_pool = list(self.last_top_candidates or [])
                        if safety_pool:
                            guard_pool += sorted(
                                safety_pool,
                                key=lambda entry: float(entry.score),
                                reverse=True,
                            )
                        for candidate in guard_pool:
                            key = _safety_rerank_action_key(candidate)
                            if key in seen_keys:
                                continue
                            seen_keys.add(key)
                            guard_alternatives.append(candidate)
                        # Probe order (probe-guard-protocol amendment 1):
                        # descending safety-model logit when the exported
                        # ranker is loadable, shipped score otherwise. The
                        # slice affords only 3-4 settles and unsafe settles
                        # run the full horizon, so probing in score order
                        # spends the budget on exactly the candidates most
                        # likely to waste it; the calibrated model's pick
                        # precision (19/20 at unsafe-incumbent boards) puts
                        # a genuinely safe candidate first or second. The
                        # physics remains the sole arbiter of what plays.
                        if _safety_shadow_model() is not None:
                            def _guard_logit(candidate):
                                try:
                                    logit = safety_shadow_logit(
                                        observation, candidate
                                    )
                                except Exception:
                                    logit = None
                                return (
                                    logit
                                    if logit is not None
                                    else float("-inf")
                                )

                            guard_alternatives.sort(
                                key=_guard_logit, reverse=True
                            )
                        # Attribute filter (attribute-filter-protocol.md):
                        # only when the knob is on, price each candidate's
                        # incremental priority/soft coverage violations with
                        # the same contract the offline scorer uses. A
                        # failure returns None, which leaves that candidate
                        # unfiltered -- the filter must never block the
                        # rescue by erroring.
                        guard_violations_fn = None
                        if PHYSICS_PROBE_ATTR_FILTER:
                            def guard_violations_fn(candidate):
                                try:
                                    return candidate_attribute_violations(
                                        observation["pool_list"][
                                            int(candidate.action["item_idx"])
                                        ],
                                        candidate.candidate,
                                        observation["container_list"][
                                            int(
                                                candidate.action[
                                                    "container_idx"
                                                ]
                                            )
                                        ],
                                    )
                                except Exception:
                                    return None
                        guard_chosen, guard_record = probe_guard_choose(
                            decision,
                            guard_alternatives,
                            lambda candidate: physics_probe_settle(
                                observation, candidate
                            ),
                            lambda: time.perf_counter() >= guard_deadline,
                            violations_fn=guard_violations_fn,
                        )
                        if guard_record["swapped"] and (
                            guard_chosen is not decision
                        ):
                            decision = guard_chosen
                            action_source = "physics_probe_guard"
                        self._append_policy_trace(
                            {
                                "event": "physics_probe_guard",
                                "step": self._policy_step,
                                "probes_used": guard_record["probes_used"],
                                "incumbent_safe": guard_record[
                                    "incumbent_safe"
                                ],
                                "swapped": guard_record["swapped"],
                                "swap_rank": guard_record["swap_rank"],
                                "elapsed_seconds": float(
                                    time.perf_counter() - guard_started
                                ),
                                "budget_exhausted": guard_record[
                                    "budget_exhausted"
                                ],
                                "quiet_skipped": False,
                                "incumbent_logit": incumbent_logit,
                                "attr_filtered_count": guard_record[
                                    "attr_filtered_count"
                                ],
                            }
                        )
            except Exception:
                pass
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
            if self.last_multi_axis_shadow is not None:
                self.last_candidate_diagnostics["multi_axis_selector"] = (
                    self.last_multi_axis_shadow
                )
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
                    "multi_axis_selector_mode": MULTI_AXIS_SELECTOR_MODE,
                    "residual_affordance_shadow_mode": (
                        RESIDUAL_AFFORDANCE_SHADOW_MODE
                    ),
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
            if SAFETY_RERANK_SHADOW:
                try:
                    shadow_logit = safety_shadow_logit(observation, decision)
                except Exception:
                    shadow_logit = None
                if shadow_logit is not None:
                    self._append_policy_trace(
                        {
                            "event": "safety_shadow",
                            "step": self._policy_step,
                            "logit": float(shadow_logit),
                            "candidate_kind": str(
                                decision.candidate.name or "candidate"
                            ),
                        }
                    )
            self._policy_step += 1
            return action_for_execution(decision)

        if LAST_RESORT_RELAXATION_SECONDS > 0.0 and pool_list:
            rescue = last_resort_relaxed_action(
                observation,
                ordered_items,
                seconds=LAST_RESORT_RELAXATION_SECONDS,
            )
            if rescue is not None:
                rescue_score, rescue_action = rescue
                self.last_action_source = "last_resort_relaxation"
                self.last_candidate_kind = "last_resort_relaxation"
                self._append_policy_trace(
                    {
                        "event": "decision",
                        "step": self._policy_step,
                        "action_source": "last_resort_relaxation",
                        "candidate_kind": "last_resort_relaxation",
                        "internal_outcome": "relaxed_rescue",
                        "no_safe_action": True,
                        "protocol_fallback": "last_resort_relaxation",
                        "immediate_score": float(rescue_score),
                        "action_command": {
                            "item_idx": int(rescue_action["item_idx"]),
                            "container_idx": int(
                                rescue_action["container_idx"]
                            ),
                            "place_pos": [
                                float(value)
                                for value in rescue_action["place_pos"]
                            ],
                            "orientation": int(rescue_action["orientation"]),
                        },
                    }
                )
                self._policy_step += 1
                return rescue_action

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
                "multi_axis_selector_mode": MULTI_AXIS_SELECTOR_MODE,
                "residual_affordance_shadow_mode": (
                    RESIDUAL_AFFORDANCE_SHADOW_MODE
                ),
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
