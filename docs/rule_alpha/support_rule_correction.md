# The 0.6 support ratio is ours, not the competition's

Measured, not read: `scripts/rule_alpha_bridge_probe.py` drives the official
`GroundHandlingEnv` directly with a hand-built stream and reports what it
accepts.

## What the official acceptance path actually is

`simulator/src/ground_handling/env.py` steps through

    check_inclusion  ->  check_transport_path  ->  place_item

and **none of the three tests support**.  `place_item` warps the item to the
target pose, runs `settle_wait_step` (300) of physics, and accepts it unless it
moved more than `displacement_threshold` (**0.30 m**) or rotated more than
`angle_displacement_threshold` (**45 deg**).  That is the whole rule.

`MIN_SUPPORT_RATIO = 0.6` in `agent/agent.py` is **rule-alpha's own** proxy for
"will it stay put", and `Geometry.support_metrics` makes it stricter still by
scoring the *single largest* contact patch (`ratio = max_area / item_area`)
rather than the union of contacts.

## Bridges are legal

Two piers with a gap, a deck across them.  Single contact is deliberately far
under 0.6; the union is what actually holds it up.

| gap | deck dx | single contact | union | included | path | **settled safe** |
|---|---|---|---|---|---|---|
| 0.20 | 0.80 | 0.38 | 0.75 | yes | yes | **yes** |
| 0.35 | 0.95 | 0.32 | 0.63 | yes | yes | **yes** |
| 0.50 | 1.10 | 0.27 | 0.55 | yes | yes | **yes** |
| 0.65 | 1.25 | 0.24 | 0.48 | yes | yes | **yes** |

Every one is accepted.  The current rule would have refused all four.

## The real cantilever limit is 0.50, and beyond it "safe" stops meaning "where you put it"

One pier, a 0.70 x 0.45 x 0.22 deck on top overhanging by a fraction of its own
width.  `drift` is the distance from the commanded pose to the settled pose.

| overhang / width | implied support | **settled safe** | drift | where it landed |
|---|---|---|---|---|
| 0.25 | 0.75 | yes | 0.020 | exactly as commanded |
| 0.40 | 0.60 | yes | 0.020 | exactly as commanded |
| **0.50** | 0.50 | yes | 0.020 | exactly as commanded |
| 0.60 | 0.40 | **no** | — | tipped, removed |
| 0.70 | 0.30 | yes | **0.133** | slid down 0.128 m |
| 0.80 | 0.20 | yes | **0.094** | slid down 0.091 m |

Two things fall out.

**A clean cantilever reaches half the box width, not 0.4 of it.**  Up to and
including `o/w = 0.50` the box settles 0.020 m below the commanded pose — which
is exactly the release lift — and does not move laterally at all.
`wedge_overhang_fraction = 0.25` is **half** of what the simulator actually
allows cleanly.

**Past that, acceptance is not the right question.**  At 0.70 and 0.80 the
placement is *accepted* and the box is somewhere else: it slid off the pier and
landed roughly 0.1 m lower.  `is_placed_safe` only means "moved less than
0.30 m".  A planner that trusts it builds a plateau that is not there.  The
criterion Layer 2 needs is **drift**, not acceptance.

The 0.50 figure is for a wide flat deck (0.70 x 0.45 x 0.22) — the shape a
wedge-bridge wants.  A taller, narrower box has its centre of mass higher and
should be expected to tip sooner; that is not measured here and should not be
assumed.

## What this corrects

An earlier report in this branch said the staircase reach was bounded by "the
official 0.6 support floor, which allows `o <= 0.4w`".  There is no official
support floor.  The bound was self-imposed, and the measured clean limit is
`o <= 0.5w`.

That matters for the staircase conclusion.  The slope-tracking condition was
`dx/dz >= 1.1/f`: at `f = 0.25` that is 4.4 and essentially no cargo qualifies,
but at the measured `f = 0.50` it is **2.2** — and the four steps actually
placed in `08-slope-exploitation` had `dx/dz` of 1.66, 2.25, 2.61 and 2.82.
Three of the four would track the slope under the real limit.  The earlier
finding, "the material to follow the chamfer does not exist", was measured
against a constraint that is not the competition's.

The separate finding still stands on its own terms: raising `f` from 0.25 to
0.35 recovered more wedge area and packed *worse* over twelve scenarios.  But
that A/B moved one number inside a rule set built around the wrong bound, and
is worth re-running now that the bound is known.
