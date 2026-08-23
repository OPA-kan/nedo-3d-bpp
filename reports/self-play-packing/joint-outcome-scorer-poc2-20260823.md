# PoC-2 result: joint outcome scorer vs paired physical measurement

Date: 2026-08-23 (Linux, PyBullet 3.2.7, torch CPU, Python 3.12)
Contract: `joint-outcome-scorer-contract.md`
Result JSON: `reports/self-play-paired-physical/poc2-collection-20260823/joint-outcome-scorer-poc2.json`

## Data

Thirteen paired collection cells (twelve scenario x stream cells at game
seed 20260822 plus the 20260823 audit cell), every cell passing the
paired contract audit: 1368 JointOutcomeSample v2 rows, 102 unique roots,
1300 fully eligible. Split: three held-out cells
(`dual-shelf-mixed-original`, `single-preloaded-source-001`,
`audit-cell-20260823`) -> 1036 training rows, 216 held-out rows over 18
held-out roots after removing roots whose id also appears in training
cells (empty-board fingerprints collide across scenarios — see
"instrument findings").

Model: 3-member Set Transformer ensemble, joint Gaussian output
(mean + full Cholesky), 60 epochs, dim 64, root-group bootstrap.

## Held-out answers to the PoC-2 question

**Candidate ordering: works on the heads that carry signal.**

- `fill_gain` Kendall tau **+0.733** (10 of 18 roots have non-tied
  measured means; the rest are degenerate);
- `surface_total_variation_delta` +0.394 (n=11);
- `center_of_mass_z_delta` −0.152 (n=11) — a diagnostic head the model
  does not order;
- top-pick regret on `fill_gain`: **zero in 88.9% of roots**, mean 0.103
  fill points, worst 1.34; `game_reward` regret zero everywhere.

**Joint dominance probability: no signal. This is the honest headline.**

The model-side dominance estimate (independent sampling from the two
predictive Gaussians) collapses to ~0.01 for every pair — including all
14 measured-dominant pairs (max 0.027) — because the fitted covariance is
world-level aleatoric variance, which same-world pairing cancels but
independent sampling doubles. AUC separating measured-dominant from
measured-nondominant pairs is **0.506**: chance. The raw
`direction_agreement` of 0.859 in the JSON is an artifact of the 85
trivially-negative pairs and must not be quoted as skill.

**Consequences.**

1. F(s, a) as built is usable as a **ranker/screener** (which candidates
   deserve physical rollouts) but not as a **certifier** (which candidate
   confidently dominates). Physical paired rollouts remain the only
   dominance certificate.
2. The fix is structural, not more epochs: dominance is a paired
   quantity, so the model must see the pairing. Next slice should train a
   paired-difference head — same state, two actions, predict the joint
   outcome difference distribution — using the world-aligned sample pairs
   the dataset already contains. Alternatively (weaker), condition the
   scorer on the observable future stream so only handoff chance remains
   marginal.

## Horizon-2 degeneracy

At horizon 2 in these scenarios most joint heads are inert:
`soft_violation_gain`, `priority_*`, `survival` and `game_reward` are
tied across candidates at almost every root (taus computable on 0–1 of 18
roots). The informative branch vector today is effectively
{fill_gain, surface_total_variation_delta, center_of_mass_z_delta}. A
deeper horizon or terminal-connected labels (`leaf->terminal joint V`)
is needed before the multi-head joint framing pays off.

## Instrument findings (fed back into the tooling)

- `command_action.item_idx` is positional in the environment's current
  pool and shifts as items leave; the dataset joins the acting item by
  `selection.stable_item_index`. Anyone consuming manifests directly must
  do the same.
- Empty-board `board_fingerprint` values collide across scenarios: the
  same `puct-root-...` id appears in up to nine cells' step-0 records, so
  root ids alone are not cross-run state identities. The trainer excludes
  train-overlapping roots from held-out metrics; a fingerprint that
  includes container geometry would remove the collision at the source.

## Repro

```
python scripts/build_paired_joint_outcome_dataset.py \
  --run <cell_id>=<run_dir>/paired ... --output poc2-dataset.jsonl
python scripts/train_joint_outcome_scorer.py --dataset poc2-dataset.jsonl \
  --held-out-cell dual-shelf-mixed-original-game-20260822 \
  --held-out-cell single-preloaded-source-001-game-20260822 \
  --held-out-cell audit-cell-20260823 \
  --ensemble-size 3 --epochs 60 --dim 64 --output joint-outcome-scorer-poc2.json
```

## Verdict

PoC-2 splits: **ranking transfer to held-out roots is real** (fill tau
0.73, 89% zero-regret top picks), so a learned scorer can already cut
physical rollout budget by pruning candidates before rollout. **Joint
dominance certification does not transfer** with an unpaired predictive
distribution — the paired-difference model is the next required slice,
before any vector-search integration.
