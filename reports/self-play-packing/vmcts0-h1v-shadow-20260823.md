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

## Headline (scope-corrected 2026-08-23, second pass)

Fill ordering agreement between the arms, on the 18 of 35 shared roots
where fill means are not tied (the only heads with more than one
comparable root are fill; `game` and `priority_covered` each produced a
single root):

| arm | fill ordering tau vs the H2 arm | physical budget |
|---|---|---|
| H1 measured only (V discarded) | +0.889 (n=18) | half |
| H1 + V composite | +0.630 (n=18) | half |

What this does and does not establish:

1. **Established:** on these 18 roots, the one-step measured fill delta
   reproduces the *H2 arm's* fill ordering, and adding the current V
   bootstrap degrades that agreement. The V-as-leaf-bootstrap gate
   therefore fails: this V must not enter search.
2. **Not established: "H1 is enough" or "the second step carries no
   information."** The H2 reference is itself shallow — its second step
   is the existing scalar-PUCT continuation, not a deep or terminal
   outcome. H1 ~ H2 is equally consistent with "immediate fill dominates
   bounded fill at depth 2" (plausible in 3D-BPP: one-step fill deltas
   are volume-dominated, and if second-step volumes are similar across
   siblings the ordering cannot move) *and* with "H2 is too shallow to
   see residual-space futures diverge" — which is the very reason search
   exists. Distinguishing these requires a depth ladder
   (tau of H1/H2 orderings against deeper and terminal outcomes on the
   same paired worlds), not more H1-vs-H2 cells.
3. The H2 split-half self-consistency (tau +1.000 over 16 roots) is a
   **measurement-noise ceiling only**: it says the H2 arm's fill
   ordering is reproducible across its worlds, not that it is correct
   with respect to the terminal objective. A consistently myopic
   ordering also reproduces perfectly.

## Why "pearson 0.93" and "V degrades ordering" do not contradict

The held-out audit's fill_return pearson 0.93 is a *global* statistic:
suffix fill varies enormously across trajectory positions (early states
have most of their fill ahead, late states almost none), so a model that
tracks board progress scores high while still misranking the three
nearly identical sibling leaves that grow from one root. What V-MCTS
actually needs is **within-root discrimination** — pairwise accuracy /
tau between V(s'_i) and the true suffix outcome of each sibling leaf —
and that quantity was never measured before this gate ran. The audit
metric was the wrong yardstick for this use; the shadow gate is the
first metric that tested the real requirement, and it said no.

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
  terms: H1+V is dominated by plain H1 at equal budget against the H2
  reference.
- **Do not conclude "H1 is enough."** That claim needs the depth
  ladder: on a small root set with the same paired worlds, collect
  H1/H2/deeper/terminal outcomes and compute tau(H1, H_d) and
  tau(H2, H_d) as depth grows. If tau(H1, terminal) collapses, H2 was
  simply too shallow a reference and the whole H1-vs-H2 agreement was
  about bounded fill only.
- **V's next verdict needs the right metric:** run behavior-policy
  continuations from counterfactual sibling leaves ((s, a_i) -> s'_i ->
  pi_b to genuine termination, same exogenous worlds) and compare
  V(s'_i) against the realized suffix within each root. That separates
  off-distribution failure, global-vs-local correlation, and composition
  errors — and doubles as the terminal rung of the depth ladder.
- Only after those two measurements: decide between deeper physical
  matrices and V retraining (more complete rank-0 trajectories;
  paired-difference calibration), re-gated by this same shadow
  instrument.

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
