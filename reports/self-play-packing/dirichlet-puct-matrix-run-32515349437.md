# Dirichlet PUCT self-play matrix

Run: [GitHub Actions 32515349437](https://github.com/OPA-kan/nedo-3d-bpp/actions/runs/32515349437)

## What changed

Physics remained deterministic. Relative to the 16-pair zero-noise control,
collection added two independent game seeds per scenario/stream and mixed
root priors as `P' = 0.75 P + 0.25 Dirichlet(0.3)`. Early moves sampled the
root visit policy and moves from step 6 onward were greedy.

## Physical result

All 32 paired jobs and the aggregate job succeeded.

- unique rank-0 trajectories: `16`
- unique MCTS trajectories: `32`
- fill wins/ties/losses: `20/0/12`
- mean fill-score delta: `+0.521186`
- mean placed-count delta: `+0.21875`
- mean soft/priority violation delta: `-0.59375`
- mean CoM-z delta: `+0.020644` (worse)
- selected-action physics failures: `0`

The positive mean is seed-sensitive. Seed `20260822` averaged `-0.429302`
fill with 5/16 wins, while `20260823` averaged `+1.471675` with 15/16 wins.
The matrix therefore demonstrates useful exploration, not a stable improved
policy.

## Matched-count stability

Both arms were independently replayed to the smaller final placed count and
shaken there, so this comparison does not reward or punish an arm merely for
placing more items.

- mean KE/item delta: `+0.377733`
- median KE/item delta: `+0.037135`
- KE/item better/tie/worse: `9/0/23`
- mean KE/mass delta: `+0.037429`
- shifted-fraction worse/better: `16/4`
- toppled-fraction worse/better: `1/0`

One large KE outlier dominates the mean, but the median and direction count
also say that the searched boards are usually less stable at equal item
count. Stability must remain a separate gate; raw terminal KE must not be
folded into one uncalibrated scalar reward.

## Teacher result

- 32 independent trajectory groups
- 265 unique model-visible states
- 389 policy rows
- 370 non-uniform visit targets after root noise
- 58 rows where physical search Q discriminated visited candidates
- 421 eligible terminal suffix-return rows
- zero forbidden Ranker score/rank/selection or search-prior leakage

Noise successfully expands the state distribution, but non-uniform policy
rows are not automatically physics-informed rows. The Q-discriminating count
is the relevant search-signal audit.

The fixed leave-one-trajectory-group-out value bootstrap remains below its
gate. Board summaries improve return-sign accuracy to `0.615202` and have
Pearson `0.177533`, but RMSE `60.657601` is worse than phase/count RMSE
`49.487844`. No value model should be injected into live PUCT from this audit.

The policy bootstrap also remains below its gate. Across all 389 decisions,
candidate geometry has cross-entropy `1.087381`, slightly worse than uniform
`1.087013`. Restricting the same MCTS policy target to the 58 rows where
physical search Q actually discriminates candidates still gives `1.098960`,
worse than uniform `1.098612`. Thus the failure is not explained solely by
Dirichlet-dominated rows; the current representation and sample count do not
generalize the search correction to held-out trajectories.

## Verdict

The AlphaZero-style collection mechanism is operational and creates genuinely
different on-policy trajectories. It has produced a promising positive-fill
cohort, but no score-improving deployable agent has been established. The next
search teacher must first become less sparse and less seed-sensitive, for
example by deeper/better-valued search or substantially more independent
on-policy groups. Any later P/V model must be selected with trajectory-group
holdout, then tested noise-free and greedy on fresh scenario/stream/game groups
with the matched stability gate enforced.
