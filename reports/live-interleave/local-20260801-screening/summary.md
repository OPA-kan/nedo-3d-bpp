# Live scan interleave: development screening (rejected)

Local Linux, PyBullet 3.2.7, one repeat per cell, five development
configurations, `base` versus `live_interleave4`.

| case | base placed | il4 placed | d | base fill | il4 fill | d |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `b000-k15` | 17 | 14 | -3 | 23.119 | 12.655 | -10.464 |
| `b000-k20` | 16 | 12 | -4 | 17.287 | 12.804 | -4.483 |
| `b000-k40` | 14 | 19 | +5 | 19.525 | 25.603 | +6.078 |
| `b001-k20` | 18 | 17 | -1 | 20.989 | 19.708 | -1.281 |
| `b001-k30` | 18 | 18 | +0 | 23.822 | 21.225 | -2.597 |
| **total** | **83** | **80** | **-3** | **104.742** | **91.995** | **-12.747** |

## Verdict

Rejected as a live default. `LIVE_SEARCH_INTERLEAVE` stays 1.

## The result is not noise-shaped, it is starvation-shaped

One configuration gains and the rest lose, and the winner is the one the
ledger already identifies as search-starved. `b000-k40` gains +5 placed /
+6.078 fill; `b000-k15` and `b000-k20` lose 3 and 4.

This is the same signature `aabb-cache-guard-mixed` recorded for the
packed-AABB cache: +10 placed on `b000-k40` where starvation was binding,
-12 on `b000-k20`. Two independent coverage interventions - one that
enlarges the candidate set, one that only reorders it - now produce the
same per-configuration pattern.

The search diagnostics rule out the obvious alternative. The interleave
did not make the search worse at finding candidates: it is
deadline-limited on most steps in both arms and the unit completion
ratio does not fall (`b000-k15` 0.285 -> 0.330, `b000-k40` 0.202 ->
0.153 with 33% more units in play), and no episode ended in a
no-candidate branch that the base arm avoided. What changed is which
candidate a truncated search settles on, and therefore which trajectory
is taken.

So the constraint is the one already on the books: with the known-defective
utility (`Ranker` volume dead vote, `q + gamma*q` lookahead), changing
which candidates the search surfaces reshuffles trajectories rather than
improving them. Selection quality is blocking for coverage work, not the
other way round.

## Scope and what this does not say

- **One repeat per cell.** The b000 cases run in a deterministic
  environment; the b001 cases carry timing nondeterminism, so their two
  small deltas (-1, 0) are the least trustworthy rows here.
- **The local totals are not comparable to the registered baseline.** Local
  base is placed 83 / fill 104.742 against the registered
  development baseline of 88 / 114.6. The search is deadline-limited, so
  absolute totals are machine-dependent. Only base-vs-arm inside this run
  is meaningful, and a deadline-sensitive change is exactly the kind that
  a slower or faster machine would size differently.
- **This rejects the interleave as an unconditional default, not the
  coverage hole as a target.** The hole is measured and real
  (`rollout-endgame-silence-is-a-scan-order-hole`). The `b000-k40` gain is
  the hole being closed where closing it helps.
- A targeted form - interleave only when the search is actually starving -
  is a different design, not a tuning of this one, and is untested.
