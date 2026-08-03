# The Task C wall is the anchor parameterisation, not the board

Date: 2026-08-02. This retracts the central conclusion of
`reports/task-c/ceiling/summary.md`.

## What was claimed

> Every chain terminates on a **true dead end**: the oracle enumerated the
> whole anchor space of both generators and found zero physically safe
> placements. Not a budget, not a cap.

The first sentence was accurate about the anchor space and wrong about the
board. **The anchor space is a sampling of the placement space**, and the
sampling misses valid placements.

## The measurement

Both methods run against the identical replay of c001-k1 to step 20 — same
rescue (step 18, oracle rank 0), 20 packed items, arriving item 20 at
0.65 x 0.45 x 0.25:

| method | valid placements found |
|---|---:|
| both anchor generators, exhaustive, no deadline | **0** |
| dense 2.5 cm grid over the same support levels | **16** |

All 16 pass the agent's own `Geometry.rejection_reason`, and **all 16 are
physically safe** under live settle: 2.04–4.86 degrees, 5.76–9.20 cm
displacement. They sit in one pocket at level 0.687, y = −0.600, sampled
across x, so this is roughly two distinct placements rather than sixteen
independent options. One is enough to falsify a dead end.

## What closes the board, from a rejection tally

475,422 probes at that state, one reason each:

| reason | share |
|---|---:|
| containment | 78.4% |
| static_geometry | 21.2% |
| support | 0.3% |
| **corridor** | **0.1%** |
| accepted | 0.003% |

This refutes the corridor hypothesis outright. Transport access is not what
closes the board — 0.1% of probes fail on it. The board closes because
placements either leave the container or hit packed geometry, which is what
"the shape is used up" looks like, but at a resolution the generators do not
sample.

## Retractions

1. **The search ceiling result is withdrawn.** "Perfect search reaches 20 of
   42 and then the board is genuinely stuck" does not follow. The ceiling is
   unknown, not measured.
2. **The board-value case is not established by it.** The argument that the
   remaining ~20 items belong to the board-value class rested on the ceiling
   being real.
3. **The three-way classification of fatal states needs re-checking.**
   c000-k1:21 was called truly infeasible on the same kind of evidence and has
   not been re-tested; its replay cannot reach the step because that case dies
   by a physics failure of its own pick, which the rescue path does not cover.
4. **The pocket-margin gate was calibrated against a false wall.** Stage 1
   called the arriving class marginally alive at this state, and given 16
   valid placements exist that was arguably correct; the stage-2 "fix" made it
   wrong. The gate has to be rebuilt on a state whose status is established
   independently of the generators.

## What stands, and is now stronger

Anchor coverage is the binding constraint in Task C endgames, repeatedly and
at more than one scale:

| state | blind | sees it |
|---|---|---|
| c001-k1:18 | support_plane (shipped) | cartesian: 6 settled + 54 release, all safe |
| c001-k1:20 | **both generators** | 2.5 cm grid: 16, all safe |

The anchor fallback was the one intervention that survived physics, and it
works by changing the anchor space. This measurement says that direction has
more room in it than the ceiling result implied — not less.

## Scope

One state, one case. The 16 placements are one pocket. Whether a finer
generator would pay for itself inside the 6.5 s budget is not addressed here;
this establishes that the placements exist, not that they are reachable
cheaply.
