# Route-survival shadow telemetry

## Status

Experimental, shadow-only, and default-off with the enclosing
`FUTURE_OPTION_TIEBREAK` experiment. Enable the telemetry explicitly with
`FUTURE_OPTION_ROUTE_SHADOW=1`; the saved-snapshot evaluator does this only for
its feature arm. The route fields do not participate in
`FutureOptionValue.rank_key()`. Enabled shadow runs are diagnostic runs and may
still perturb a deadline-driven candidate stream through their measurement
cost; they are not action-equivalence evidence.

With the route flag off, corridor signatures, the route probe population, and
route revalidation are not computed. Existing future-option and production
paths therefore do not pay the shadow instrumentation cost.

## Question

For an immediate placement `a`, does the hypothetical next state preserve the
transport access of probes that the current state already accepted?

This is deliberately narrower than residual capacity. It measures whether a
placement destroys route access, not how much empty volume remains.

## Probe and classification contract

The normal future-option probe population remains unchanged. A separate,
corridor-stratified shadow population is retained at most once per
`(container, corridor class, item, orientation)` and traversed round-robin by
`(container, corridor class)`. This prevents the telemetry experiment from
changing the live future-option tuple.

Every route probe is already accepted by `PlacementCore` in the current state;
that accepted population is the denominator. After virtually applying the
candidate placement, each bounded probe is classified in this order:

1. `space_lost`: containment, static-geometry, or applicable support checks
   fail before the corridor check;
2. `route_lost`: all structural checks pass, but `transport_path_clear` fails;
3. `survived`: both structural and transport checks pass.

Release probes remain exempt from the settled-support check, matching the
existing release contract. The identity

```text
baseline = survived + route_lost + space_lost
```

is enforced by focused tests. Candidate, item, item-orientation, corridor-class,
and item-volume survival summaries are recorded. The fixed route-validation
budget defaults to 16 probes per hypothetical state and performs no PyBullet
call.

Because every denominator probe was already transport-valid and the only new
obstacle is the hypothetical placement, route revalidation is incremental. It
checks the new settled AABB directly against each probe's transport samples;
unchanged packed obstacles are not rescanned. This is an exact difference test,
not an approximate early reject.

## Verification

An actual-geometry unit case places a blocker that does not overlap a target
probe but intersects only its door-to-target sweep. The telemetry classifies
that probe as `route_lost`, proving the route-only channel is observable rather
than structurally unreachable in the implementation.

The committed saved-snapshot screen covered five states, 27 hypothetical
immediate placements, and 350 accepted route probes:

| outcome | count |
|---|---:|
| survived | 169 |
| space_lost | 181 |
| route_lost | 0 |

The states were `b000-k20` steps 9, 14, and 15; `b001-k20` step 15; and
`b001-k30` step 14. These bounded geometry-only samples therefore do not show
that the compared top/cohort placements create pure transport loss. They do
show substantial structural loss, but that is the already-observed capacity
channel and is not promoted into the ranker here.

One `b001-k20` evaluation had no denominator after excluding the hypothetically
placed item; its route probe population contained only that item. Empty
denominators remain visible rather than being reported as perfect survival.
The exact totals can vary at the deadline edge because the upstream candidate
stream is wall-clock bounded; the committed JSON files are the source for the
numbers above.

## Interpretation and next evidence

This is negative evidence against promoting route survival into live selection
from the present sample. It is not evidence that transport access never matters:
the screen is small, score/cohort conditioned, uses bounded probes, and does not
replay exact terminal `transport_invalid` decisions or physical settling.

The next useful measurement is targeted: restore the exact pre-action states
whose next-step failure was `transport_invalid`, then ask whether candidate
alternatives differ in `route_lost`. Broadening capacity-oriented probes is not
the next step. Until targeted evidence discriminates candidates, keep all route
fields shadow-only.

The reported post-cache terminal audit places `transport_invalid` at about 45%
of deaths, so the channel remains operationally important despite this sampled
negative result. A live adoption gate should require fewer
`transport_invalid` endings on the seven-case suite without a net placed-count
regression.
