# Every remaining place is on top of soft or priority cargo

A reading of the section drawings observed that usable space is
`fits AND reachable AND supportable`, and that the instruments were showing
two of the three. Following that up produced a complete mechanism for how
these episodes die, and it is not the one the earlier reports proposed.

## The rule that does it

`support_surfaces()` admits the floor, the shelves, and packed items -- but
only plain ones:

```python
for box, is_soft, is_prioritized in packed_aabbs_local(container):
    if not is_soft and not is_prioritized:
        surfaces.append(box)
```

At the board `c000-k1` ends on: 16 packed items, 5 soft, 3 priority, so 8 of
16 tops are support surfaces (11 total with the floor and two shelves).

## The asymmetry

Neither contract matches the published rule, and they miss it in opposite
directions:

| | on soft / priority tops |
|---|---|
| competition rule | penalised only when the covering item has a DIFFERENT attribute; same-attribute stacking is free |
| settled path | refuses everything -- those tops are not support surfaces, so `support_ratio < MIN_SUPPORT_RATIO` |
| release path | allows everything -- no support test at all, and `RELEASE_ATTRIBUTE_GUARD` defaults to `off` |

`release_rejection_reason` tests containment, static geometry, the corridor,
and the attribute guard when it is on. It never calls `has_stable_support`.

## What that produces

At the fatal board of `c000-k1`, of the 950 legal release candidates the
deadline-free oracle enumerates:

```
rest-height support ratio   min 0.000  median 0.000  max 0.359
clearing MIN_SUPPORT_RATIO 0.55:   0 of 950
the pose that toppled:             0.0055
```

Every remaining legal pose rests on soft or priority cargo. The settled path
would refuse all 950 for support; the release path accepts them; the agent
takes the best-scoring one and physics ends the episode.

This also connects to the two worst official components. Covering a soft or
priority item with a different-attribute item is exactly what
`placement_score` and `soft_item_score` penalise, and those sit at 16.95 and
21.30 against a 100 scale in the best submission.

## The instrument bug this went through, and its control

The first version measured support on `settled_proxy_candidate`, which
computes `proxy_z = max(containment_minimum_z, rest_height + h/2)`.
Containment demands 16 mm of clearance from every plane and `support_ratio`
wants contact within `CONTACT_TOLERANCE` = 6 mm, so the containment term
always wins and a floor pose scores support 0. A control caught it: the same
item on an EMPTY container floor scored **0.0000** where it must score 1.

Fixed by building the proxy at `release_rest_height` directly, which is the
height the item comes to rest at rather than the lowest legally-releasable
one. The control now returns **1.0000**.

The conclusion above survived the fix -- 0 of 950 either way -- but it
survived for a different reason than the broken metric was reporting, and
one claim did not survive at all. **Retracted: "c000-k1 ends with 80 columns
still taking the item, so it did not end for lack of room."** Those 80
columns are all unsupported. There was nowhere left that would hold
anything.

## Terminations now separate rather than average

Recorded per episode by `classify_termination`:

```
dual-shelf-mixed   transport_exhaustion     supported 0, blocked 19
dual-full-stream   stability_termination    c0 blocked 31, c1 supported 29
c000-k1            stability_termination    supported 0, unsupported 80
```

Three episodes, two distinct causes. Scoring them as one "space utilisation
failure" mixes a board that ran out of corridor with a board that ran out of
support.

## What is testable next, and with what

`RELEASE_ATTRIBUTE_GUARD` already exists with modes `off` / `priority` /
`all`, defaulting to `off`. Turning it on refuses release poses whose
settled proxy rests on a protected top. That is the exact population above.

Two competing predictions, and they are separable:

* it prevents the topple deaths and the placement/soft penalties, or
* it removes the last legal poses and simply ends episodes sooner

The second is a real risk: at that board every legal pose was on protected
cargo, so a guard would have left none. That is an argument for the
`priority` mode over `all`, and for measuring both.

Measure with the same harness as the zone-order run -- `base`, `base_null`,
and the guard arms, three repeats, serial. The zone-order verdict is the
precedent for why: without `base_null` and repeats, arm differences here are
not readable.
