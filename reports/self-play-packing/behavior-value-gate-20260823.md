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

## Partial official-vector shadow and paired continuation

The official objective is not fill alone. The local decision contract keeps
fill, CoG, stability, priority placement and soft handling as separate axes;
`num_placed_items` is the published activation gate, not another score term.
Official normalization and exchange rates are unpublished, so no weighted
total was fitted or reported.

Run `32621960562` evaluated group-excluded component predictions on the frozen
physical branches. At beta 1.0 it changed 0/348 eligible roots. Reapplying a
declared confidence bound to the stored estimates nominated 13 roots at beta
0 and only two at beta 0.25; beta 0.5 or greater nominated none. The two beta
0.25 roots were frozen before physical evaluation.

Runs `32623583899` and `32623930649` each completed both physical shards for
those two roots. Each root was reconstructed twice, the MCTS incumbent or
component-V candidate was forced once, and both arms then used the unchanged
hand-coded policy to terminal before deterministic local shake. Every one of
the four comparisons was incomparable, never candidate-dominant.

The step-6 result reproduced exactly: placed gate +0.073 and slightly lower
CoG-z, but fill -1.496, shake peak KE +31.583 and one additional toppled item.
The step-4 continuation did not reproduce. It was a complete tie in the first
run, then fill +6.198 and shake peak KE -77.435 but CoG-z +0.148 in the green
rerun. Thus the action-adoption verdict is consistently negative, while the
downstream vector is not deterministic under the current time-bounded Agent
continuation. Do not treat either run's pooled means as a stable effect.

The first aggregate job failed only because its clean runner imported the
simulator stack without NumPy; its artifacts were recovered. The aggregate was
made pure-stdlib and run `32623930649` completed 2/2 shards plus aggregate.

## Next gate

1. Keep exact PyBullet legality and immediate soft/priority accounting.
2. Keep the current component-V action selector closed: even the two beta-0.25
   proposals failed paired terminal dominance.
3. Replace the wall-clock-dependent continuation with a fixed-attempt,
   deterministic continuation policy before drawing a causal action-effect
   conclusion. Diagnose action-difference calibration explicitly: strong
   per-state OOF correlations do not establish that subtracting two leaf
   predictions ranks sibling actions correctly.
4. The next learner, if pursued, must target paired counterfactual component
   deltas/search improvement and be evaluated on whole unseen trajectories;
   stability remains a separately measured head/gate.
5. Progressive widening, P and proposal heads remain closed until a learned
   selector beats the fixed-support physical incumbent on fresh paired roots.

No score-improving learned agent is established by these runs.
