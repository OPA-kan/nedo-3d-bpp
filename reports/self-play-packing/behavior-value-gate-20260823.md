# Behavior-value gate, 2026-08-23

## Verdict

The scalar terminal-game-return leaf value is rejected.  Under frozen
candidate support, `H2+V` moved away from the deep physical reference rather
than toward it.  Progressive widening and policy/proposal learning remain
closed.

The multi-head experiment does, however, establish strong grouped-held-out
signal for several physical suffix components.  The next experiment must keep
those components separate and test a confidence-gated, Pareto/constrained
policy improvement.  It must not turn them into an undocumented weighted sum.

## Fixed-support scalar shadow

Actions run `32618598497` completed all eight physical shards.  Its aggregate
job failed only because direct script execution did not put the repository
root on `sys.path`; the uploaded eight-shard artifact was recovered and
aggregated locally after fixing that entrypoint.

- roots: 58
- support: Top-3 + exhaustion K64 + stride-4 provider-zero rescue
- search: H2 S48, identical seeds and support in both arms
- split: every root used only models excluding its whole trajectory group
- Q-top agreement with deep reference: 46/58 -> 22/58
- visit-top agreement: 45/58 -> 20/58
- full signature agreement: 19/58 -> 5/58
- paired Q-top improved/regressed: 2/26
- leaf calls/clipped: 2,784/282
- gate: **FAIL**

A post-hoc uncertainty threshold sweep cannot rescue this model.  The best
Q-top result is the baseline 46/58 obtained by never injecting V; thresholds
100/200/300/400/500/750/1000 use V on 9/15/23/33/38/46/49 roots and obtain
44/40/37/32/30/28/28 matches.  This diagnostic is not a deployable gate.

The scalar model itself had only weak grouped-held-out signal: Pearson 0.409
and RMSE 47.82 versus constant 48.52.  Its apparent MAE improvement was not
enough to preserve action ordering when normalized terminal returns were
backed up through PUCT.

## Fresh multi-head teacher and ensemble

Actions run `32618609173` completed all 32 paired physical games.  The
aggregate workflow failed after creating the aggregate and schema-v3 dataset
because its clean runner had not installed NumPy; the artifact was recovered
and the workflow dependency was fixed.

- rows / trajectory groups: 413 / 32
- unique game states: 261
- physical branch samples: 4,572
- multi-head policy rows: 381/381
- eligible suffix heads: 12, each eligible on 413/413 rows
- forbidden heuristic leakage hits: 0

Actions run `32620348564` trained a three-member, five-fold group-excluded Set
Transformer ensemble with 13 total outputs (terminal return plus 12 physical
heads).  Selected OOF results:

| head | Pearson | RMSE | constant RMSE |
| --- | ---: | ---: | ---: |
| return_to_go | 0.126 | 55.166 | 48.174 |
| game_return | 0.127 | 55.084 | 48.174 |
| fill_return | 0.950 | 1.233 | 3.910 |
| placed_return | 0.927 | 1.718 | 4.589 |
| soft_violation_return | 0.887 | 0.263 | 0.576 |
| priority_covered_return | 0.600 | 0.468 | 0.599 |
| center_of_mass_z_return | 0.966 | 0.064 | 0.249 |
| surface_total_variation_return | 0.934 | 0.00144 | 0.00400 |
| terminal stability heads | -0.032 to 0.053 | worse than constant | n/a |

`deployment_ready` is false.  The result separates two hypotheses: model-
visible board state carries substantial information about future fill,
placed, soft, CoM and surface shape, but the current sparse/discontinuous
zero-sum terminal return and terminal shake outcomes are not learned well
enough for scalar leaf backup.

## One-step paired shake

Actions run `32618250038` completed the exact 15-root old/rescue one-action
paired shake.  No pair introduced item loss, topple, soft violation, priority
coverage or priority misrouting.  Rescue-minus-old peak KE was worse/tie/better
on 6/6/3 pairs, and max displacement on 6/9/0.  Candidate-support rescue is
therefore retained, while stability remains a separate production axis rather
than a scalar reward inferred from this small sample.

## Next gate

1. Keep exact PyBullet legality and immediate soft/priority accounting.
2. Evaluate component suffix heads separately on counterfactual branches.
3. Permit a policy change only for confidence-bounded Pareto dominance over
   fill/placed/attribute components; otherwise retain the physical-search
   incumbent.
4. Measure the selected action with paired physical continuation and fresh
   trajectories, reporting fill, official attributes and stability separately.
5. Reopen uncertainty allocation, progressive widening and P only after that
   component-policy gate passes.

No score-improving learned agent is established by these runs.
