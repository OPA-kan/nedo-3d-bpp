# The headroom is in the single-container cases, and it is enormous

Date: 2026-09-01. Derived from the 200-cell arena plus the eight
episodes that exhausted the item stream.

## A ceiling we can compute

`fill_percent_proxy = 100 × placed_volume / total_container_volume`, and
`total_container_volume` sums each container's own `volume` field — the
real chamfered envelope (4.007 m³ per container, against 4.669 m³ for
its bounding box). So the maximum fill any policy can reach on a case is
fixed by the stream: place every item.

| scenario | items | ceiling | completed | agent | champ-all | champ-union | rule-alpha |
|---|---|---|---|---|---|---|---|
| dual-preloaded-dedicated | 39 | 30.4 | **8** | 24.7 / 81% | 27.4 / 90% | 19.4 / 64% | 11.8 / 39% |
| dual-full-stream | 41 | 32.3 | 0 | 23.0 / 71% | 27.4 / 85% | 21.2 / 66% | 20.2 / 63% |
| dual-shelf-mixed | 41 | 32.3 | 0 | 30.1 / 93% | 30.4 / 94% | 25.7 / 80% | 23.8 / 74% |
| dual-empty | 41 | 32.4 | 0 | 30.0 / 93% | 31.2 / 96% | 26.6 / 82% | 22.9 / 70% |
| dual-dedicated-priority | 41 | 32.4 | 0 | 26.6 / 82% | 30.9 / 95% | 22.2 / 69% | 20.4 / 63% |
| **single-preloaded** | 38 | **59.4** | 0 | 30.9 / 52% | 34.2 / 58% | 24.9 / 42% | 23.5 / 40% |
| **single-empty-shelf** | 41 | **64.2** | 0 | 24.8 / 39% | 29.2 / 45% | 29.6 / 46% | 31.9 / 50% |
| **single-empty-noshelf** | 41 | **64.9** | 0 | 34.3 / 53% | 34.5 / 53% | 26.4 / 41% | 30.3 / 47% |

Two containers hold the same 41 items, so the dual ceilings sit near 32
and everyone is already at 81–96% of them: **1 to 6 fill points of
headroom**. One container doubles the density, the ceilings rise to
59–65, and nobody exceeds 58%: **25 to 35 fill points of headroom**.

**Five of the arena's eight scenarios are dual.** Most of what was
measured today was a contest for a few points near a ceiling.

Caveat on the single ceilings: unlike the dual ones, they are *upper
bounds*, not observed optima. On `dual-preloaded-dedicated` the ceiling
was reached eight times, so it is real. Packing 41 items into one
chamfered container at 65% volumetric density under physical stability
may not be achievable at all. The size of the gap is still the point.

## Why the eight completions happened

Every one is `dual-preloaded-dedicated`, all at fill 32.44 or 32.95 —
identical across different streams, which is itself the proof: fill
depends only on *which* items are placed, so equal fills mean all of
them. It is also the one scenario whose stream (39 items) fits inside
`--max-steps 40`.

The completed board is drawn at plan and elevation from the simulator's
settled poses:
https://claude.ai/code/artifact/11a69d5f-15e5-4b43-9be6-b96a9ec28774

It does not look like a solved packing problem. The stacks reach **94%
and 96% of the inner height** at 32.4% volumetric fill: tall columns
with the air beside them, not above them.

So "the stream was exhausted" is a reliability result, not a packing
one. Finishing means 39 consecutive placements without a rejection —
which the hand-coded agent manages 7 times in 200 episodes, while 141
end when its own move is judged unsafe.

## What every run has in common

At termination, by arm and reason, the container is between 67% and 90%
empty:

| arm | termination | n | mean fill | free |
|---|---|---|---|---|
| agent | stream_exhausted | 7 | 32.59 | 67% |
| agent | max_steps | 52 | 31.40 | 69% |
| agent | selected_action_failure | 141 | 26.61 | 73% |
| champ-all | max_steps | 14 | 31.61 | 68% |
| champ-all | no_safe_retained_candidate | 41 | 30.28 | 70% |
| rule-alpha | rule_alpha_declined | 121 | 28.18 | 72% |
| rule-alpha | selected_action_failure | 72 | 13.75 | 86% |
| champ | no_retained_candidate | 195 | 10.37 | 90% |

Nothing in this project has ever run out of room. Runs end because a
move was rejected, a generator ran dry, or the step cap hit.

## Next

The single-container scenarios hold essentially all of the remaining
opportunity, and they are also where `current-agent` self-terminates
100% of the time and where `champ-all` is the only arm that loses to
`rule-alpha`. Drawing the same plan and elevation for a single-container
episode would show directly what is being left on the floor.
