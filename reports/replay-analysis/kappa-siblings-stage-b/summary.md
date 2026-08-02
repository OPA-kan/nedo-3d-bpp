# Stage B: within-state delta kappa does not predict settle survival

42 development states, 4 Q-band siblings each, 252 sibling
pairs, 3 final_holdout datasets skipped. Physical survival is the official
`is_placed_safe` from the committed candidate labels - real physics, no new
simulator run.

| outcome | rule | agree | disagree | decided | agreement rate |
| --- | --- | ---: | ---: | ---: | ---: |
| `physical_survival` | `raw` | 3 | 3 | 6 | 0.5 |
| `physical_survival` | `sum` | 6 | 6 | 12 | 0.5 |
| `physical_survival` | `max` | 6 | 6 | 12 | 0.5 |
| `physical_survival` | `product` | 6 | 6 | 12 | 0.5 |
| `rollout_placed` | `raw` | 5 | 0 | 5 | 1.0 |
| `rollout_placed` | `sum` | 7 | 0 | 7 | 1.0 |
| `rollout_placed` | `max` | 7 | 0 | 7 | 1.0 |
| `rollout_placed` | `product` | 7 | 0 | 7 | 1.0 |
| `rollout_volume` | `raw` | 5 | 0 | 5 | 1.0 |
| `rollout_volume` | `sum` | 7 | 0 | 7 | 1.0 |
| `rollout_volume` | `max` | 7 | 0 | 7 | 1.0 |
| `rollout_volume` | `product` | 7 | 0 | 7 | 1.0 |

## The physical channel is exactly chance

Agreement is 0.500 under every weighting - raw 3/6, and 6/12 for each of
sum, max and product. The sign of a within-state kappa difference carries
no information about which sibling survives its settle. This is the test
the whole line was pointing at, run against real validator labels, and it
is null.

It is also consistent rather than surprising. Stage A found capacity does
not explain placed-to-go because episodes end by topple; Stage A' found
weighting options by modelled survival made the state descriptor worse;
this finds the per-action differential does not predict survival either.
**Option space and physical survival are separate axes**, and no
rearrangement of an option count has reached the survival axis.

## The rollout agreement is near-circular and is not validation

`rollout_placed` and `rollout_volume` agree at 1.000 (5/5 raw, 7/7
weighted). That is not evidence that kappa predicts anything. Both the
rollout and kappa are computed from the same realised successor state and
both count how much still fits, so agreement between them is an internal
consistency check on two capacity measures, not a test against an outcome.
It is reported because it would have been alarming if they had disagreed.

## The sample is thin for a structural reason worth recording

Of 252 sibling pairs, **240 (95.2%) had identical physical survival** and
245 (97.2%) had identical rollout placed and volume, so they carry no sign
and are excluded. Sibling outcomes were 154 survivals to 14 failures.

Inside a 0.15 Q-band the short-horizon outcome is almost always the same
whichever sibling is chosen. That bounds how much any within-band reranking
can achieve at this horizon, independently of what quantity does the
ranking - and it is the same shape as the enforce band's own difficulty.

## Scope

- 6 to 12 decided pairs. Even a real effect of moderate size would not be
  resolvable here; this rules out a large effect, not a small one.
- Siblings come from a stratified candidate sample, not the full
  population, so the band is sampled rather than enumerated.
- Immediate survival is scored against the commanded successor, never the
  realised one, to avoid reading the failure back out of the state it
  produced.
