# Future-option tie-break

## Status

Experimental and default-off. Enable with:

```text
FUTURE_OPTION_TIEBREAK=1
```

This experiment does not change `Ranker.score`, the live release-risk terms,
or the settled-before-release contract.

## Selection contract

The Task B decision is split into four stages:

1. Run the existing candidate generator and live score, but retain at most one
   immediate representative per visible item. This prevents a single item
   from occupying the whole global top-K.
2. Keep representatives whose `Q_live` is within `FUTURE_OPTION_Q_BAND`
   (default `0.15`) of the best immediate representative.
3. For each member of that cohort, virtually apply the same settled proxy used
   by the current lookahead and revalidate a fixed number of already-generated
   probes from the current visible pool, excluding the placed item.
4. Select lexicographically by:

```text
feasible_items
feasible_item_orientations
distinct_support_regions
valid_probe_candidates
Q_live
```

The first three fields prevent raw anchor multiplicity from masquerading as
future flexibility. `valid_probe_candidates` is explicitly a count inside a
fixed sample; it is not the complete next-state candidate population.

## Budget and observability

The default future validation budget is 32 candidates per hypothetical state.
The future loop has no PyBullet call and no wall-clock cutoff. The preceding
live generator remains the existing deadline-driven search; consequently the
probe population at the edge of that deadline can still vary between runs.
If an evaluation reaches the policy reserve, the implementation returns the
best immediate `Q_live` representative instead of comparing a partial cohort.

`candidate_diagnostics.future_option_tiebreak` records the shortlist, cohort,
Q gaps, all four value components, per-hypothetical runtime, total future
runtime, selection change, and deadline abort status.

## Saved-snapshot measurement

Run:

```powershell
python3 scripts/evaluate_future_option.py `
  --snapshot <step-state.json> `
  --repeats 3 `
  --output-dir reports/future-option/<name>
```

On the saved `b000-k20` step-9 observation, the current baseline selected item
5 in all three fresh runs. The feature admitted the previously starved item 17
on all runs and changed the choice to item 17 or 21 in all three runs. Total
policy time was 5.81--5.91 seconds; the fixed-work future stage itself was
0.80--0.89 seconds. This is geometry-only evidence. It neither reproduces the
historical item-28 action nor establishes a better PyBullet trajectory.

## Adoption gate

`.github/workflows/future-option-ablation.yml` compares `base` against
`future-option` on five development configurations:

- `b000-k15`
- `b000-k20`
- `b000-k40`
- `b001-k20`
- `b001-k30`

The workflow stores compact paired placed/fill summaries in
`reports/future-option/history/<run_id>/`. Do not enable the feature by default
unless that episode-level guard gives an explained non-regression result.
