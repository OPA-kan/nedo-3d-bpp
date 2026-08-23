# V-MCTS-0 shadow result: H1+V vs H2 physical measurement

Date: 2026-08-23 (Linux, PyBullet 3.2.7, torch CPU)
Comparison JSON: `reports/self-play-paired-physical/vmcts0-h1v-20260823/h1v-vs-h2-shadow.json`
Instrument: `scripts/compare_h1v_shadow.py` (member-wise same-world vote)

## Setup

- Leaf model: V^pi_behavior Set Transformer ensemble (3 members, dim 64,
  100 epochs) trained on 24 freshly collected, genuinely terminated
  rank-0 episodes (276 suffix states, all 12 trajectory heads eligible,
  terminal stability measured). Group-held-out audit (4 folds, whole
  trajectories): fill_return pearson 0.93, placed 0.93, surface TV 0.94,
  CoM 0.97, terminal_stability_max_shift 0.76, game_return 0.63;
  soft_violation_return is *worse than the constant baseline* and
  priority_misrouted / stream_completed / items_toppled are constant in
  this corpus.
- H1+V arm: 4 cells re-run at horizon 1 with the frozen ensemble
  recorded on every horizon leaf (shadow only — backup and rank-0
  execution unchanged; all 4 cells pass the extended paired audit,
  0 violations). Same configs, seeds and exogenous worlds as the H2
  arm, so (candidate, world) blocks align exactly: 35 shared roots,
  420 vs 840 physical steps.

## Headline: the second physical step was cheap to replace — but by
## nothing, not by V

Fill ordering against the H2 reference (which is itself noiseless here:
split-half self-consistency tau +1.000 over 16 roots):

| arm | fill ordering tau vs H2 | physical budget |
|---|---|---|
| H1 measured only (V discarded) | **+0.889** | half |
| H1 + V composite | +0.630 | half |

Two conclusions, both real:

1. **The one-step measured delta already reproduces the two-step
   ordering almost perfectly.** For fill at these depths the first
   physical step carries nearly all the discriminating information; H2's
   second step is mostly spent re-measuring what H1 knew.
2. **Adding the current V bootstrap makes the composite *worse*, not
   better.** V's leaf prediction error (trained on 276 rows, evaluated
   one action off-trajectory) exceeds the marginal information the
   suffix adds. The V-as-leaf-bootstrap design is not wrong — this V is
   simply too weak to pay its way yet, exactly the failure mode the
   shadow protocol exists to catch before any search integration.

## Dominance and Pareto

Member-wise unanimous vote (3/3) certifies almost nothing: dominated
recall 0.043 against H2's point-estimate relations (precision 0.5,
1 recovered of 23). Relaxing the vote trades precision away fast
(vote>=1: recall 0.435, precision 0.27). The apparent
`relation_agreement 0.835` is again dominated by trivially-negative
pairs and must not be quoted as skill. Consistent with PoC-2: dominance
certification stays a paired *physical* measurement; no learned
distribution has yet crossed that bar.

## What V does add

Stability heads (`terminal_stability_*`) now exist at every H1 leaf with
honest group-held-out quality (max_shift pearson 0.76) — the first
branch-level stability signal in the pipeline. H2 cannot measure these,
so this capability is *unvalidated at branch level* and is reported, not
compared. Validating it needs either per-branch shake passes on a small
probe set or terminal-linked trajectories through the same roots.

## Decision guidance

- **Do not integrate V into search yet.** The gate failed on its own
  terms: H1+V is dominated by plain H1 at equal budget.
- **The cheap win is H1 itself:** for candidate ordering, halving the
  branch horizon loses almost nothing today. If the next physical matrix
  only needs ordering (not dominance certification), H1 doubles the
  replica count per root at constant budget — which is exactly what the
  Wilson-LCB elimination gate is starved for (16+ paired worlds).
- V improvement path, in order of expected value: 10-20x more complete
  rank-0 trajectories (the trainer and collection scripts now make this
  one command per cell); paired-difference calibration at leaves; only
  then revisit the composite gate.

## Repro

```
python scripts/build_self_play_pv_dataset.py --root <vtrain-cells> \
  --manifest-glob rank0/manifest.json --output vtrain-pv.jsonl --summary ...
python scripts/train_self_play_set_value.py --dataset vtrain-pv.jsonl \
  --output-dir v-model --ensemble-size 3 --epochs 100 --folds 4
python scripts/run_self_play_packing.py ... --mcts-horizon 1 \
  --mcts-root-allocation-mode paired_round_robin \
  --mcts-leaf-vector-model-dir v-model
python scripts/compare_h1v_shadow.py --h2-run ... --h1v-run ... \
  --vote-threshold 3 --output h1v-vs-h2-shadow.json
```

Checkpoints stay out of git (regenerable from the committed vtrain
manifests plus seeds); the audit numbers above are the model's record.
