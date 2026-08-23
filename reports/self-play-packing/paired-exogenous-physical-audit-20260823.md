# Paired exogenous-world contract: first real-physics audit

Date: 2026-08-23 (Linux, PyBullet 3.2.7, Python 3.12.3)
Branch: `claude/exogenous-world-joint-outcome-v2-it42g2` (`c034380` + this audit)

## Question

Does the paired round-robin root allocation
(`--mcts-root-allocation-mode paired_round_robin`) keep its contract when
the rollouts are real PyBullet physics rather than the unit-test fakes?

## Setup

- Scenario `single-empty-noshelf`, stream `original`, environment seed 42,
  game seed 20260823, one episode, 8 steps.
- Paired arm: physical PUCT, 12 simulations, horizon 2, top-3 candidates,
  uniform prior, no Dirichlet noise, `pi0-paired0`.
- Control arm: `rank0` selection over the identical scenario and seeds.
- Auditor: `scripts/audit_paired_physical_contract.py` over the paired
  manifest (`reports/self-play-paired-physical/.../paired-contract-audit.json`).

## Contract result: PASS (8 searched roots, 0 violations)

Every searched root satisfied, on real physics:

- equal allocation: 3 candidates x 4 replicas = 12 rollouts at every root;
- sibling pairing: replica `r` of all three candidates shares one
  `exogenous_world_id`; 4 distinct worlds per root, sample_index consistent;
- complete blocks: candidate x world grid full, no duplicates, one
  `candidate_set_id` per root matching the search record;
- no policy target emitted, `policy_target_eligible=false`, no root
  Dirichlet noise;
- rank-0 execution preserved: the executed trajectory (candidate ids,
  ranks, actions) is **identical** to the independent rank0 control run,
  `non_rank0_action_count=0` in both arms. Search did not contaminate the
  real trajectory.
- All 12/12 samples per root terminated at `horizon` and were eligible on
  all nine measured heads.

## Findings beyond pass/fail

1. **Post-shake stability heads are structurally unmeasured in branch
   rollouts.** `stability_max_shift`, `stability_peak_kinetic_energy`, and
   `stability_items_toppled` are `None` in every physical branch sample, so
   any joint objective that requires them censors 100% of the data. The
   auditor's Pareto set now excludes them explicitly
   (`unmeasured_branch_heads` in the audit JSON). If these heads should
   join the joint outcome vector, the branch rollout needs its own
   post-shake measurement pass — that is a physical-budget decision, not a
   schema change.
2. **Real dominance signal exists but 4 replicas cannot certify it.**
   16 of 48 pairwise root comparisons show joint strict dominance with
   point estimate 1.0 across all 4 paired worlds. The Wilson lower bound at
   n=4 with perfect dominance is 0.510, below the 0.8 elimination
   threshold, so the frontier correctly retains all 3 candidates at every
   root: the conservative LCB gate is doing its job rather than failing.
   Certifying elimination at threshold 0.8 (z=1.96) needs at least 16
   paired worlds per comparison even with zero observed reversals
   (n=13 -> 0.772, n=16 -> 0.806). At top-3 that means 48+ simulations per
   root, or a lower z / threshold chosen in advance for the pilot regime.
3. Runtime: the 8-step, 12-simulation paired episode took ~4.5 minutes on
   this container's CPU (step-000 snapshot 10:33:26 to final manifest
   10:37:01, plus provider warm-up); the rank0 control ~1 minute. A
   16-replica (48-simulation) root schedule scales roughly linearly (~4x)
   per step.

## Artifacts

- `reports/self-play-paired-physical/single-empty-noshelf-original-game-20260823/configs/` — generated scenario matrix
- `.../paired/manifest.json` — paired arm with all 96 joint outcome samples (schema v2)
- `.../rank0/manifest.json` — rank-0 control arm
- `.../paired-contract-audit.json` — machine-checked invariant + Pareto report
- Per-step raw state snapshots are regenerable from the seeds and stay
  untracked (`game-*/` is ignored for this experiment family).

## Verdict

The paired exogenous outcome contract holds under real PyBullet physics
end to end. The next physical run that intends to *eliminate* candidates —
not merely collect vectors — must budget replicas for the LCB gate:
16 paired worlds per comparison at the current 0.8 threshold, or a
preregistered weaker gate for small pilots.
