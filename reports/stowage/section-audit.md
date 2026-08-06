# Stowage sections, and what the pictures changed

Everything about the packing had been read through summary statistics. These
are the boards themselves: orthographic sections cut through three episodes
the shipped agent played, drawn from the container's published half-spaces
and the item AABBs the simulator reports after settling.

Instruments, all committed:

| script | what it produces |
|---|---|
| `scripts/dump_packing_geometry.py` | replays a case to termination and dumps container planes, shelf AABBs, and settled items |
| `scripts/render_sections.py` | half-space -> section polygon (Sutherland-Hodgman), shared by the page builder |
| `scripts/build_sections_page.py` | profile / deck plans / transverse stations as a self-contained HTML sheet |
| `scripts/space_audit.py` | 25 mm voxel decomposition of where the free volume goes |
| `scripts/space_pockets.py` | erodes the free region by each published type -- how many item-sized pockets remain |

## What the sections settled

**The container is not the box the dimensions imply.** 15.3% of
`length x width x height` lies outside the seven half-spaces -- the chamfer
wedge at low x plus wall clearance -- and no policy can reach it. The two
side walls are not at the same `|y|`: the `+y` plane sits one wall thickness
inboard of `-width/2`.

**Shelves.** Container 1 of the dual scenarios carries a main shelf at
`z 0.81..0.86` spanning `y 0.05..0.71`. Items sitting at `z ~ 0.85` in an
otherwise sparse container are resting on it, not floating; this was checked
against the shelf AABBs rather than inferred.

## Where the free volume goes

Three dumps, five containers, 25 mm voxels, as a fraction of the space
inside the envelope:

| | |
|---|---|
| stowed items | 33.2% |
| shelf plates | 1.2% |
| free, nothing above it | 44.2% |
| free, built over | 21.4% |

Per container the split is uneven, and the shelf containers are the worst:

```
c000-k1/c0           stowed 39.9%  open 43.3%  built over 16.2%
dual-shelf-mixed/c0  stowed 33.0%  open 52.3%  built over 14.0%
dual-shelf-mixed/c1  stowed 24.8%  open 44.0%  built over 29.3%   shelf
dual-full-stream/c0  stowed 44.2%  open 39.4%  built over 15.7%
dual-full-stream/c1  stowed 25.2%  open 42.1%  built over 30.8%   shelf
```

Eroding the open region by each published type (25 cm dedup lattice, resting
on solid) leaves, at the moment the agent stops:

```
                    suitcase_L  medium  small  duffel  cardboard  backpack  daypack
c000-k1/c0                  10      19     26      37         14        21       46
dual-shelf-mixed/c0         23      29     40      47         18        34       53
dual-shelf-mixed/c1         27      30     49      55         17        41       73
dual-full-stream/c0          3      12     24      18         19        18       43
dual-full-stream/c1          9      11     25      29          8        11       55
```

This table is an UPPER BOUND. It is 5 cm voxel geometry and applies none of:
inclusion clearance, lateral clearance against settled items, the transport
corridor, the support ratio, or the risk gate.

## The under-shelf hypothesis: rejected

Zero items sit under the main shelf in all three episodes, in a volume of
roughly 1 m3. Forcing a placement there on an empty container is accepted by
physics (`is_included` / `is_valid` / `is_placed_safe` all true), so it is
not a legality wall. At the board the agent stops on, no legal pose exists
there at all -- 0 candidates clear the contract, 0 rejections by physics --
so the volume closes during the episode, which made it an ordering question.

Filling it first does not help:

```
prefill = 0   ->  0 seeded, agent 36, total 36
prefill = 3   ->  2 seeded, agent 34, total 36
prefill = 6   ->  2 seeded, agent 34, total 36
```

The volume is fungible. Seeding it displaces placements the agent would have
made elsewhere, one for one. `dual-shelf-mixed`, n = 1 per arm.

## What actually ends the episode

Read from the simulator, not inferred (`simulator/src/ground_handling/env.py`):

```python
is_placed_safe = self.validator.place_item(...)
if is_placed_safe:
    ...
else:
    ## 失敗: エピソード終了
    terminated = True
```

A single unsafe placement terminates the run. The item is not removed and
play continued -- the episode is over.

And Task C shows **one item at a time**: `visible pool = 1` at every step of
`c000-k1`, no lookahead.

So `c000-k1` publishes 41 items, the agent places 16-22 depending on how much
search budget the deadline gives it, and then one drop topples and the run
ends -- with 34 slots for the pending item still clearing both the geometry
contract and the risk gate.

That reframes the 44%. It is not primarily a packing-efficiency loss. The
episode dies with half the container and half the stream unused, so filling
space only pays once the agent survives long enough to use it.

## Caveat carried with these numbers

The `16 placed` figure above came from a run sharing the machine with two
other replays; the same case reaches 22 unloaded. The agent is
deadline-driven, so CPU contention changes the trajectory -- the failure
mode this repo has already recorded twice. The structural facts (34 slots at
the terminal board, stop-by-topple, pool size 1) are read off the final
state and the simulator source; the step counts are not comparable across
loads.

## Regenerating the drawings

The dumps these sections are drawn from are committed under
`reports/stowage/dumps/` (68 KB). Until the 2026-08-06 audit they existed
only in a scratchpad, and the page's entry point had its input paths
hardcoded to `scripts/packing-*.json`, where no dump is ever written — the
figures could not be redrawn by anyone, including their author.

```
python scripts/make_stowage_page.py OUT.html \
    reports/stowage/dumps/packing-c000.json \
    reports/stowage/dumps/packing-dual-shelf-mixed.json \
    reports/stowage/dumps/packing-dual-full-stream.json
```

To rebuild a dump from scratch instead:

```
python scripts/dump_packing_geometry.py CONFIG.json CASE_ID OUT.json
```
