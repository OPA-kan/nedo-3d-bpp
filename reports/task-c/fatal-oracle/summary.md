# Task C fatal-snapshot exhaustive oracle

Date: 2026-08-02. Tool: `scripts/measure_anchor_recall.py` (no deadline,
`limit=sys.maxsize`, both anchor generators, live PyBullet settle validation).
Snapshots: the pre-action state of the step that ends each Task C episode.

The Task C baseline established that all four episodes die on the
fixed-coordinate fallback with `no_safe_action`. That label conflates at least
four different states, and they call for opposite fixes, so nothing should be
built on it until the fatal states are classified. This is that
classification.

The two cases split, one each way.

## c000-k1 step 21 — true infeasible

Exhaustive, both generators, no deadline, physics complete:

| generator | settled accepted | attempts | release accepted |
|---|---:|---:|---:|
| cartesian | 0 | 479,520 | 0 |
| support_plane | 0 | 14,142 | 0 |

`oracle_complete: true`, `physics_complete: true`,
`oracle_physical_settled_count: 0`, `oracle_release_count: 0`.

There is no safe placement for the arriving item in that state, under either
anchor space, with unlimited time. The search missed nothing. This state can
only be avoided earlier, which is exactly the claim the board value makes, and
the only class of fatal state where it is the relevant lever.

## c001-k1 step 18 — generator blindness, not a deadline

The oracle found 6 settled candidates and 54 release candidates, **all 60
physically safe** under live settle, none of which the anytime search
surfaced (`geometric_recall 0.0`, `anytime_settled_count 0`,
`anytime_release_count 0`).

Re-running both generators exhaustively on the saved snapshot, against the
same item that ended the episode (item 18, 0.65 x 0.45 x 0.25, 13 kg):

| generator | kind | accepted | attempts | exhaustive time |
|---|---|---:|---:|---:|
| **support_plane (shipped)** | settled | **0** | 12,562 | 2.1 s |
| **support_plane (shipped)** | release | **0** | 5,857 | 2.1 s |
| cartesian | settled | 6 | 399,975 | 19.6 s |
| cartesian | release | 54 | 31,953 | 5.1 s |

`ANCHOR_GENERATOR_MODE` ships as `support_plane`. Its entire anchor space is
exhausted in about 4.2 s, inside the 6.5 s budget, and contains **zero**
feasible placements at this state. The policy trace agrees: `units_completed`
reaches 12 of 12, so the search did not stop early -- it finished, empty, and
then emitted the poison fallback with budget still unspent.

So this is not the ordering failure or the depth/budget failure of the
proposed taxonomy. It is a fourth class: the shipped anchor space does not
contain the solution at all, so no reordering and no extra time can reach it.
All 6 settled oracle candidates carry `oracle_generators: ["cartesian"]`;
support_plane contributed none.

The cheapest consequence is directly measurable: an exhaustive cartesian
**release** scan costs 5.1 s at this state and the oracle's first accepted
release candidate appears 2.25 s into its scan, so a bounded cartesian scan
after support_plane comes back empty plausibly fits the remaining budget.
That is a hypothesis about cost, not a result; it has to be run.

## Classification

| snapshot | class | lever |
|---|---|---|
| c000-k1:21 | I. true infeasible | board value (prevention) only |
| c001-k1:18 | IV. generator blindness | generator fallback / anchor coverage |

Neither II (ordering) nor III (depth or budget) occurred in these two
snapshots. The per-unit progress audit added for this investigation
(`candidate_audit[].units`, audit-only) stays in place to classify future
snapshots, but it was not what separated these.

## Side observation

On the 54 physically safe release candidates at c001-k1:18 the threshold risk
gate reports `risk_gate_false_positive_rate: 1.0` -- it would reject every one
of them. The gate ships `off`, so it did not cause this death, and this is one
snapshot's selected-population figure, not a precision or recall estimate for
the gate.

## Scope

Two distinct fatal snapshots (c000-k1 repeats are bit-identical; c001-k1
repeats differ only in fill). The oracle replays deterministically from the
committed config, so the c001-k1 replay reproduces one trajectory and not
necessarily the exact recorded repeats. Physical safety is per-candidate live
settle at the same pre-action state, which is the correct counterfactual, but
it does not establish that the episode would have survived beyond that step.
