# Loading order over zones: refuted

The corridor measurement said the loss was reachability — at the board
`dual-shelf-mixed` stops on, 62.9% of the poses where the space is free and
the item fits are refused only by `transport_path_clear`, and they sit deep
while the legal ones sit by the door. The obvious remedy was to fill the
far zones before they are spent: shelf top, then deep, then centre, then
under the shelf.

Measured with the shipped agent, four scenarios, four arms, three repeats,
serial (48 jobs). `base_null` is `base` re-run under a different name and
carries the noise floor; `zone_reversed` points the same machinery the other
way so a win cannot be attributed to "some zone bonus helps".

**The doctrine is worse, and it clears the floor in the wrong direction.**

## placed — the gate, and the component that amplifies

```
scenario                floor   zone_doctrine        zone_reversed
m-dual-full-stream     14.000   +2.000  within       -7.000  within
m-dual-shelf-mixed      5.000   -8.667  CLEARS       -2.667  within
m-single-empty-noshelf  5.000   -2.333  within       -0.667  within
m-single-empty-shelf    0.000  -13.000  CLEARS       +1.000  CLEARS*
```

`single-empty-shelf` goes from 20 placements to 7. `fill` follows it down,
21.4 to 6.6, and on `dual-shelf-mixed` 23.4 to 18.2 (both clear the floor).

## and the stability proxies move the same way

```
scenario                metric               floor   zone_doctrine
m-dual-full-stream      shake_items_toppled  1.000   +1.667  CLEARS
m-dual-full-stream      shake_max_shift      0.367   +0.533  CLEARS
m-single-empty-noshelf  shake_items_toppled  0.000   +2.000  CLEARS
m-single-empty-noshelf  shake_max_shift      0.082   +0.406  CLEARS
m-single-empty-shelf    com_z                0.011   +0.099  CLEARS
```

Doctrine raises the centre of mass on the shelf scenes and topples more
items on the shelf-less ones. That is the mechanism: filling deep and high
first builds tall stacks against the far wall with little under them, and a
single unsafe placement ends the episode outright — the simulator sets
`terminated` directly on `is_placed_safe == False`.

`zone_reversed` sits at base almost everywhere. So the loss is not "the
agent uses the wrong order"; the shipped order is already better than either
alternative tested here.

## What this does and does not overturn

Still standing, all of it geometric and independently measured:

- 62.9% of the free-and-fits poses at a terminal board are corridor-blocked,
  concentrated deep
- neighbour gaps are 47–178 mm against a forced clearance of 26 mm, with
  52/57 in x and 51/53 in y wider than forced
- 0.958 m3 sits under the main shelf; deliberate greedy filling puts 6 items
  and 30.5% of the volume there, and the agent puts zero

What is refuted is that reordering **when** zones are filled recovers any of
it. The deep space is not merely unclaimed — reaching it early costs
stability, and stability is what keeps the episode alive long enough to place
anything at all.

## A weakness in this run's floor, stated rather than buried

`* ` on `single-empty-shelf`: `base` and `base_null` returned identical
values across all three repeats, so the floor computes to 0.000 and any
difference "clears" it. A zero floor is not infinite resolution — it is
three repeats agreeing, which at n=3 is weak evidence about the spread.
The doctrine verdict there does not rest on it (−13 placed on a 20-placement
baseline is far outside anything three repeats could hide), but
`zone_reversed +1.000 CLEARS` on the same line should be read as noise.

## Knob left in, default off

`ZONE_ORDER` stays in `agent/agent.py` at `off`, with `doctrine` and
`reversed` reachable, so this result stays reproducible instead of becoming
a claim about deleted code.
