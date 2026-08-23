# Phase 1B complete: union support flows end to end

Date: 2026-08-23 (Linux, PyBullet 3.2.7)
Data: `reports/self-play-paired-physical/union-collection-20260823/`

## What ran

Two cells (`single-empty-noshelf-original`, `dual-shelf-mixed-original`,
seed 20260822, 8 steps each) with the coverage union enabled:
48 volume-mode coverage samples per step through the same fresh-replay
filter, up to 3 safe ones unioned with the legacy top-3 into the
searched support, paired round-robin (12 simulations, horizon 1) over
the union, execution and termination pinned to legacy rank-0.

## Verified

1. **Paired contract holds on union sets**: 16 searched roots, 0
   violations — complete candidate x world blocks over 3-6 candidates
   (the divisor trim kept every union size a divisor of 12).
2. **Coverage is measurement-only, proven bit-exact**: both cells'
   executed action sequences match the legacy-only runs of the same
   seeds step for step (`non_rank0_action_count = 0`). Turning the
   union on does not move the behavior trajectory.
3. **Mixed provenance flows the whole pipeline**: 31 coverage
   candidates entered searched supports; the runs produced **69
   JointOutcomeSample v2 rows with `source = coverage`** (against 123
   legacy rows), and `build_paired_joint_outcome_dataset` ingests them
   unchanged — 192/192 rows fully eligible, coverage seed and sequence
   index preserved into `audit_only.provenance`.

These 69 rows are the first physical outcome measurements outside the
legacy generator's support in this project. This is the raw material a
proposal beta that is not a legacy distillation trains on.

## Notes for scale-up

- Coverage cost at this setting: 48 extra preview replays per step.
  Safe-coverage yield per step was 1-3 (consistent with the 6.5%
  manifold rate); steps with fewer than 3 safe coverage candidates
  simply carried smaller unions (counts 3-6, always a divisor of 12).
- One contract check earned its keep during bring-up: degenerate
  coverage candidate ids (a truncation bug) were rejected by the paired
  search's duplicate-id guard before any data was written.
- Scale-up is one flag set per cell
  (`--coverage-candidates-per-step / --coverage-sample-budget /
  --coverage-seed`); the seed offsets by step, so a matrix over
  cells x seeds keeps every sample addressable.

## Phase status

1A done, 1B done. Next per the frozen roadmap: Phase 2 — the mainline
single-agent contract (drop player/handoff), with this union pipeline
as the concrete behavior it must reproduce.
