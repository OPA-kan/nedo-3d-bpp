# Last-resort relaxation

## The problem this solves

The competition environment terminates the episode the moment an action
fails any of its three checks (inclusion, transport path, settle safety).
The shipped protocol fallback, entered when the deadline search accepts
zero candidates, emits a fixed coordinate `(0, 0, 0.25)` that fails the
transport check by construction. Firing it is therefore certain episode
death, and it is the leading death channel: transport_invalid endings were
5 of 12 base episodes in paired run `31941364445` and 45% of endings in
the earlier terminal-failure audit. Every death forfeits the entire
remaining stream — at placed fraction ~0.5 that is roughly twenty items.

## The algorithm

`LAST_RESORT_RELAXATION_SECONDS` (default 0, off) arms the following,
strictly inside the zero-accepted regime:

1. The normal deadline search runs unchanged. If it accepts any
   candidate, nothing below executes.
2. Otherwise, instead of emitting the fixed coordinate, rescan the same
   prioritized units down a **clearance ladder**: the self-imposed
   settled-item clearance is set to the official transport clearance,
   then half of it, then zero. The first rung that yields any candidate
   wins; within that rung the best risk-adjusted score is chosen. The
   knob value is the total wall-clock budget, split evenly across rungs.
3. If even the zero rung yields nothing, the fixed coordinate is emitted
   as before.

The decision-theoretic argument is one line: at a zero-accepted state the
status quo action has survival probability exactly 0, so emitting *any*
candidate — even one that may fail the environment's own trajectory
check — has expected value greater than or equal to the status quo, and
the ladder ordering maximizes the emitted candidate's validity odds.
The guard being relaxed exists to improve average-case safety; at a
certain-death state the average-case argument carries no weight. This is
the "recovery policy" pattern from safe RL (a separate policy that takes
over only in constraint-violating regions, cf. Recovery RL, Thananjeyan
et al. 2021) transplanted to a deterministic packing search, and the
ladder mirrors constraint-relaxation hierarchies standard in packing
heuristics since lexicographic feasibility restoration in GRASP/EMS
constructive methods (Parreño et al. 2008).

## What it is not

- It is not a search-budget change: outside the zero-accepted regime the
  policy is bit-identical (default off; `behaviour_sha256` unchanged).
- It is not the rejected rescue scan (which reserved deadline from every
  step) nor the rejected static hard risk gate (which refused actions):
  this only ever *adds* an action where the alternative was a known-dead
  one, and never refuses anything.
- It cannot help where death is intrinsic. c001-k1's certified ceiling is
  the worked example: the rescue fires, emits a real candidate, the
  environment still rejects the trajectory, and the episode ends exactly
  where it would have — zero cost, zero gain. The wins must come from
  multi-item pools where some other item still has an environment-valid
  placement.

## Evidence trail

- Mechanism confirmed live: on c001-k1 the step-21 fixed fallback becomes
  a `last_resort_relaxation` action (real coordinates, env-rejected, same
  ending) — the no-loss half of the exchange.
- At that same state the zero rung yields 305 geometric candidates in
  five seconds, so the ladder has material to work with when the board
  is not intrinsically dead.
- Adoption is gated by the paired A/B in
  `reports/last-resort/protocol.md`, sized against the measured
  instrument floor in `reports/benchmarks/baseline.json`, plus an
  independent fresh-permutation confirmation per repository precedent.
