# The agent leaves dominating poses on the table

Scoring an unperturbed replay of `c000-k1` offline: at 10 of 17 steps a
legal alternative existed that was **strictly safer AND strictly higher
scoring** than the pose the agent took. Not a trade-off -- a dominated
choice, on the agent's own objective.

Instruments: `scripts/record_decisions.py` replays and writes down what
happened; `scripts/score_decisions.py` scores the record afterwards. The two
passes are separate because the single-pass version changed the run it was
measuring (see below).

## The record

```
step   P_rot  median  alts    pct  lam_flip  support  kind
   0  0.0061  0.1042  2456  0.283      0.00    0.000  settled
   1  0.0170  0.0157  1416  0.535      0.00    0.000  settled
   2  0.0287  0.1299  3065  0.300      0.00    0.000  release
   3  0.0003  0.0986  1757  0.128      0.00    0.000  release
   4  0.0056  0.1042  2459  0.009         -    1.000  settled
   5  0.1069  0.1020  2098  0.611      7.63    1.000  settled
   6  0.1069  0.1042  2300  0.614      3.34    1.000  settled
   7  0.0287  0.1299  1995  0.233      0.00    0.000  release
   8  0.0025  0.1069  1190  0.030      0.00    0.000  release
   9  0.0026  0.0923   802  0.000         -    0.000  release
  10  0.0056  0.1069  1455  0.005         -    1.000  settled
  11  0.1069  0.1060  1109  0.568      3.95    1.000  settled
  12  0.0062  0.1059  1141  0.009      0.00    0.000  release
  13  0.0027  0.1069   833  0.000         -    0.000  release
  14  0.1180  0.1083   824  0.606      0.00    1.000  settled
  15  0.0379  0.1039  1018  0.193      0.00    0.000  release
  16  0.2775  0.1016   827  0.963      0.00    0.000  release  FATAL
```

`lam_flip` is the smallest `lambda_rot` at which some strictly safer pose
outranks the chosen one under the shipped score
`Q - lambda_rot*P_rot - lambda_slide*P_slide` (shipped 1.0 and 0.5).

- **0.00 at 10 steps** -- a safer pose already outranked the chosen one at
  any weight, including zero. The choice was dominated.
- **`-` at 4 steps** -- no strictly safer pose existed; the agent was at or
  near the floor of the risk distribution.
- **3.3 to 7.6 at 3 steps** -- genuine trade-offs, where the risk weight
  would have to be 3-8x the shipped value to change the decision.

The fatal step is in the first group: `lambda_rot = 0.00`. The pose that
would have been promoted scored `P_rot 0.0835` against the chosen
`0.2775`, with `Q -1.0840` against `-1.1817`. Better on both. 112
alternatives outrank the chosen pose at the shipped weight.

## What this rules out

**It is not the risk weight.** A dominated choice cannot be fixed by
reweighting, because the alternative already wins at every weight. The
earlier reading -- that `Ranker.score`'s `2.0*support` outweighs a
`lambda_rot` of 1.0 -- was arithmetic done in my head and it does not
survive the measurement.

**It is not a missing gate.** `RELEASE_RISK_GATE_MODE` defaults to `off`
and `DEATH_BAND_FALLBACK` to `0`, so no hard `P_rot` filter is active; the
`0.5` threshold cited in earlier notes came from probe code, not the agent.

**It is not the candidate kind.** The fatal step is a `release_candidate`,
so it did pay the `P_rot` penalty and is comparable to the release
alternatives it was ranked against. Checked, not assumed --
`risk_adjusted_score` returns the score UNCHANGED for anything else.

What is left is coverage: within the 6.5 s budget the agent does not reach
poses that beat its own choice on its own objective.

## Two structural facts worth recording

**Every release candidate scores `support_ratio = 0`, every settled
candidate near 1.** `support_ratio` needs contact within `CONTACT_TOLERANCE`
(6 mm), and a release candidate is the pose sent BEFORE settling, so it
never registers contact. The `2.0*support` term is therefore worth a flat
+2.0 to settled poses and +0.0 to release poses, against a total `P_rot`
range of 0.81 at `lambda_rot` 1.0.

**8 of 17 decisions are settled candidates, which bypass risk scoring
entirely.** Roughly half the episode's choices never see `P_rot`.

Within release candidates for one item, `12*volume` and `2.0*support` are
both constant -- volume does not change with orientation and support is
always zero -- so `Q` varies only through `0.35*y - 0.12*|x| - 0.18*z*mass`,
a range far smaller than the risk term's. The risk signal is not being
outvoted there. The poses simply are not being found.

## Caveats

1. **The enumeration is a 5 cm grid with a heightmap drop; the agent's
   generator uses anchors and extreme points.** A dominating pose my grid
   finds may be structurally outside the agent's candidate space, which
   makes this an L1 generator gap rather than an L2 ranking failure. Either
   way it is coverage, not weights -- but which of the two is not settled
   here.
2. **`Ranker.score` may not be the complete decision rule.** Lookahead,
   cross-step retention and container routing also act. "Dominates on
   `Q_adjusted`" is not the same as "the agent should have chosen it".
3. **One case.** `c001-k1` and `m2-k15` cannot be decomposed by this
   instrument yet: both enumerate zero release alternatives at their fatal
   step.

## Why the two passes

`measure_risk_percentile.py` enumerated alternatives between the policy call
and the step, and that changed the episode. `c000-k1` ends after 21
placements with no topple under a plain replay and after 16 with a topple
under the scanning one. The policy deadline is re-taken from `perf_counter`
inside every `policy()` call so the scan steals no time, but it does hammer
`_cached_container_z_interval` (an `lru_cache` of 65536) and
`_PACKED_AABBS_CACHE` (cleared past 256 keys), and a wall-clock-bounded
search explores less from a cold cache.

The agent is also nondeterministic on its own: two runs of the plain harness
gave 21 placements with no topple and 16 with one. An earlier note claiming
reproducibility was reading a coincidence -- two scanning runs happened to
agree byte for byte. Placement counts are not comparable across harnesses or
across runs; the per-step quantities here are, because each compares a
choice against alternatives on the board it was actually made from.
