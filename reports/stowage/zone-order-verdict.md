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
scenario                control   floor   zone_doctrine        zone_reversed
m-dual-full-stream       37.500  14.000   +3.500  within       -5.500  within
m-dual-shelf-mixed       39.333   5.000   -7.000  CLEARS       -1.000  within
m-single-empty-noshelf   24.667   5.000   -1.667  within       +0.000  within
m-single-empty-shelf     20.000   0.000  -13.000  CLEARS       +1.000  CLEARS*
```

`single-empty-shelf` goes from 20 placements to 7, and `fill` follows it
down, 21.4 to 6.6, clearing a floor of 5.3. On `dual-shelf-mixed` fill falls
22.0 to 18.2 but the floor there is 5.0, so that one is **within** — an
earlier version of this table called it cleared, which was the retired floor
rule speaking.

> **Deltas revised 2026-08-06 (audit).** The table above was first published
> against `base_null` alone with `|base - base_null|` as the floor, which
> double-counts the same two observations. It is now the pooled `base +
> base_null` control, matching `scripts/summarize_ablation.py` as shipped.
> Every verdict is unchanged in direction and in mark; only the magnitudes
> move, by half the base/base_null gap. Regenerate with
> `python scripts/summarize_ablation.py --root reports/stowage/raw`.

## and the stability proxies move the same way

```
scenario                metric               floor   zone_doctrine
m-dual-full-stream      shake_items_toppled  1.000   +1.833  CLEARS
m-dual-full-stream      shake_max_shift      0.581   +0.654  CLEARS
m-single-empty-noshelf  shake_items_toppled  0.000   +2.000  CLEARS
m-single-empty-noshelf  shake_max_shift      0.083   +0.418  CLEARS
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
