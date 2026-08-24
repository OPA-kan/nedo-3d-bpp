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

## Immediate shake companion

For the 15 roots whose deep Q-top changed, rebuild the identical root twice,
force the old or rescued action exactly once, and shake immediately. Report
maximum instantaneous aggregate KE, KE/item, KE/mass, shifts, topples and
post-shake attribute counts as separate axes. No continuation policy is run.
