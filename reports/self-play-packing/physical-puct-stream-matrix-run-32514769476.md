# Zero-value PUCT 24-step control

Run: [GitHub Actions 32514769476](https://github.com/OPA-kan/nedo-3d-bpp/actions/runs/32514769476)

## Physical result

All 16 paired jobs succeeded across four scenarios and four item-stream
families. The exact PyBullet legal filter reported no selected-action failure.

- fill wins/ties/losses: `5/3/8`
- mean fill-score delta: `-0.102367`
- mean placed-count delta: `-0.0625`
- mean soft/priority violation delta: `-0.8125`
- mean CoM-z delta: `-0.015567` (lower)
- mean raw terminal shake-KE delta: `+13.663055`

The H2 search with zero leaf value reduces attribute violations but does not
improve fill or placed count on average. It is not a score-improving agent.

## Teacher result

Extending from 12 to 24 steps removed the terminal censoring that blocked the
value contract:

- 16 independent scenario/stream trajectory groups
- 136 unique model-visible states
- 190 policy rows
- 23 rows where physical search Q discriminated between visited candidates
- 206 terminal suffix-return rows
- zero Ranker `score`, `rank`, `selection`, or search `prior` leakage in the
  exported P/V dataset

The first fixed-alpha, leave-one-trajectory-group-out value bootstrap found
weak but insufficient board signal. Board set summaries reached Pearson
`0.264527` and return-sign accuracy `0.577670`, but RMSE `50.847199` was worse
than the phase/count baseline `50.157025`. The value model is not ready to be
used as a PUCT leaf evaluator.

## Next comparison

The follow-up collection uses the same deterministic physics and adds only
the AlphaZero-style diversity controls: two independent game seeds per
scenario/stream and root prior mixing
`P' = 0.75 P + 0.25 Dirichlet(0.3)`. It also evaluates both arms after replay
to the same placed count, reporting shake KE per item and per unit mass.
