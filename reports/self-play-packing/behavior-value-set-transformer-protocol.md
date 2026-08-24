# Behavior-value Set Transformer protocol

## Target semantics

Played-state suffix labels estimate

`V^pi_behavior(s) = E[terminal multi-head return | s, pi_behavior]`,

not `V*`. Branch root-to-leaf gains are `Q_H` supervision and must never be
used as leaf-state V labels.

## Split and masks

- split unit: complete physical trajectory group;
- state features: container, packed-item and visible-item sets only; there is
  no player, block, handoff or scalar-game feature in the single-agent arm;
- targets: every eligible numeric component suffix head; no scalar
  `return_to_go`;
- missing or censored heads: masked, never converted to zero;
- forbidden learner inputs: Ranker score, immediate score, rank, prior and
  selection fields.

## Model and uncertainty

- three to five independently initialized, group-bootstrap members;
- every shadow uses the fold ensemble that excluded that root's
  complete trajectory group; the all-data final ensemble is not used there;
- separate Set Transformer encoders for containers, packed items and visible
  items;
- one output head per target;
- epistemic uncertainty per head is variance across ensemble members;
- no policy head and no weighted combination of official-score proxies.

## Gates

1. group-held-out model audit;
2. fixed rescued candidate support, fixed Pareto-PUCT and H2 budget;
3. compare `H2+V` against `H2+0` on terminal-Pareto and resurrection
   recovery under identical genuine-terminal root-action truth;
4. only after the V effect is isolated, use uncertainty for depth allocation;
5. progressive widening comes after that comparison;
6. policy and proposal heads remain closed.

## First single-agent shadow

Run `32721721093` trained successfully and completed all six physical cells at
commit `e6d224e`; only its aggregate entrypoint failed because the new script
omitted the repository root from `sys.path`. Re-aggregating the untouched cell
artifacts after fixing that import produced 10 complete roots, zero censoring
and identical terminal truth:

- `H2+0`: resurrection frontier 0/11; terminal-Pareto 18/30; false frontier 3;
- unfiltered `H2+V`: resurrection frontier 11/11; terminal-Pareto 30/30;
  false frontier 15 (all 45 root actions became non-dominated).

This is recall without discrimination, so the adoption gate fails. The OOF
audit explains the blow-up: fill, CoG-z and surface-TV beat their constant
baselines, while soft, priority and stability heads do not. The next shadow
therefore abstains from future prediction for any head whose group-held-out
Pearson is non-positive or whose RMSE does not beat the training-fold constant.
That axis keeps its measured H2 prefix; no weight or exchange rate is added.

## Fidelity-gated rerun

Run `32723063464` at commit `08bfeb1` completed training, all six physical
cells and aggregation successfully. The 10 roots again had complete paired
terminal truth with zero censoring and the same 11 resurrection actions:

- `H2+0`: resurrection frontier 0/11; terminal-Pareto 18/30; false frontier 3;
- fidelity-gated `H2+V`: resurrection frontier 10/11; terminal-Pareto 29/30;
  false frontier 10.

The binary OOF abstention removes the worst blow-up (15 to 10 false-frontier
actions), but still fails the adoption gate because false frontier exceeds the
measured arm. A post-hoc head ablation on the exact explored nodes localizes
the failure:

| evaluated suffix | resurrection frontier | terminal-Pareto | false frontier |
|---|---:|---:|---:|
| measured only | 0/11 | 18/30 | 3 |
| fill V only | 2/11 | 17/30 | 3 |
| surface-TV V only | 5/11 | 12/30 | 6 |
| fill + surface-TV V | 10/11 | 29/30 | 10 |

The apparent high recall is therefore not evidence that the current V is a
good terminal evaluator. The two barely-above-constant heads make different
errors; hard Pareto composition lets an action survive when either noisy axis
looks favorable. Do not integrate this V or proceed to progressive widening.
The next value gate must calibrate/shrink held-out predictions and train or
evaluate paired root-action differences (or joint dominance probabilities) on
more independent trajectory groups before uncertainty controls depth.

## Immediate shake companion

For the 15 roots whose deep Q-top changed, rebuild the identical root twice,
force the old or rescued action exactly once, and shake immediately. Report
maximum instantaneous aggregate KE, KE/item, KE/mass, shifts, topples and
post-shake attribute counts as separate axes. No continuation policy is run.
