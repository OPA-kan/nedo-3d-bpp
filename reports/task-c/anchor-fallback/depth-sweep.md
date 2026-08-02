# Task C first-pass depth sweep, and a correction to how I read coverage

Date: 2026-08-02. Same box, `--parallel 3`, 3 repeats per cell, arms
`first_pass{16,32,64,128,256}` (base plus one variable).

## Correction: I read the wrong counter

`units_completed` counts units the search **exhausted**. `units_started`
counts units it **visited**. Coverage is the second one. I reported the first
as coverage in `post-fallback.md`, in the evidence entries
`task-c-post-fallback-terminal-is-a-coverage-gap` and
`task-c-after-first-pass-256`, and in two commit messages.

The correct numbers at every fatal state I examined:

| state | first pass | units_started | units_completed | units_total |
|---|---:|---:|---:|---:|
| c001-k1:19 | 64 | **24** | 4 | 12 |
| c001-k1:20 | 64 | **24** | 6-9 | 12 |
| c001-k1:19 | 256 | **24** | 2 | 12 |

24 is 12 units visited by each of the two search calls a policy step makes.
**Every unit was visited, every time.** The search is breadth-first by
construction -- it gives each unit a shallow pass before deepening any -- so
unit coverage was never the constraint and could not have been.

What I called a coverage gap is a **depth-within-unit** failure: all twelve
units were seen, and none was scanned far enough into its anchor order to
reach an accepted candidate before the deadline.

This also reverses the conclusion I drew about the right tool.
`LIVE_SEARCH_INTERLEAVE` permutes anchor order *within* a unit, so a
deadline-limited visit spreads across the grid instead of taking its prefix.
I ruled it out on the grounds that it does not address unit coverage. Unit
coverage is complete; the prefix problem is exactly what is left. It is the
indicated tool, not the excluded one.

## Sweep result

| case | depth | placed | fill | units_started | terminal source |
|---|---:|---|---:|---:|---|
| c000-k1 | 16 | 20, 20, 20 | 16.477 | 12 | placement_core |
| c000-k1 | 32 | 20, 20, 20 | 16.477 | 12 | placement_core |
| c000-k1 | 64 | 21, 21, 21 | 17.310 | 24 | fixed fallback |
| c000-k1 | 128 | 18, 18, 18 | 11.728 | 12 | placement_core |
| c000-k1 | 256 | 20, 20, 20 | 16.477 | 12 | placement_core |
| c001-k1 | 16 | 18, 18, 19 | 23.560 | 24 | fixed fallback |
| c001-k1 | 32 | 18, 18, 18 | 23.560 | 24 | fixed fallback |
| c001-k1 | 64 | 18, 18, 18 | 23.560 | 24 | fixed fallback |
| c001-k1 | 128 | 18, 18, 18 | 23.560 | 24 | fixed fallback |
| c001-k1 | 256 | 18, 18, 18 | 23.560 | 24 | fixed fallback |

**c001-k1: depth is a dead knob.** Identical placed, identical fill and the
same fixed-coordinate death at every depth from 16 to 256, with
`units_completed` at or past `units_total` throughout -- support_plane
exhausts its whole space and holds nothing, so no budget can help. That is the
blindness class behaving exactly as classified. The one exception is a single
depth-16 repeat that reached step 19 (placed 19); one repeat, not a result.

**c000-k1: non-monotonic and not readable.** 20, 20, 21, 18, 20 across the
ladder, and the death channel flips -- only depth 64 ends on the poison
fallback, every other depth ends on a real candidate that fails physically.
Each depth is internally deterministic over its three repeats while the values
jump between depths, which is trajectory sensitivity rather than a depth
response. Nothing here should be read as "depth D is better for c000-k1".

Neither case supports the hypothesis that a shallower first pass helps Task C.
It was built on the miscounted coverage figure and does not survive the
correction.

## Consistency with the trunk's own depth result

The trunk measured `first_pass64` against the 256 default on the Task B
development suite and found 64 clearly worse: placed -2.70 (p=0.039), fill
-2.95 (p=0.022) over ten pairs. Task C adds that on its two cases the knob is
either inert (c001-k1) or chaotic (c000-k1). Nothing in Task C argues for
moving the default, and Task B argues against it. The default stays 256.
