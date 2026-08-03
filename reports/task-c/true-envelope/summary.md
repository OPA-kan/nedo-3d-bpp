# Anchor envelope from the container: first Task C ablation

Date: 2026-08-02. Local 4 vCPU, `run_queue --parallel 3`, 3 repeats per cell,
arm `base` versus `true_envelope` (`ANCHOR_TRUE_ENVELOPE=1`).

## Result

| case | arm | placed | fill | fixed-coordinate deaths |
|---|---|---|---:|---|
| c000-k1 | base | 19, 19, 19 | 13.529 | 0/3 |
| c000-k1 | **true_envelope** | **23, 23, 23** | **26.099** | 3/3 |
| c001-k1 | base | 18, 18, 18 | 22.256 | 3/3 |
| c001-k1 | **true_envelope** | **21, 21, 21** | **25.366** | 3/3 |

+4 placed and +12.570 fill on c000-k1, +3 and +3.110 on c001-k1. Every cell is
deterministic across its three repeats and the arms do not overlap.

This is the largest effect measured on Task C, and it is the only intervention
today that is not a heuristic: it removes a disagreement between two pieces of
the same codebase about the same container.

## Why it works, in one line

`inside_container` and `container_z_interval` use the container's real
half-spaces. The anchor envelope used a box formula that subtracts a thickness
from both y sides, while the AKE/AKN-derived containers have y planes at
`[-W/2, +W/2 - t]`. The low-y side was one thickness too tight, for every item,
every orientation, and both generators, because they carried separate copies of
the same formula.

On the state previously certified as a true dead end, both generators run
exhaustively return 0 candidates with the box bound and **33 with the true
bound, all 33 physically safe**.

## What this does not establish

- **Task B is unmeasured.** The guard does not reproduce on this box
  (`task-b-guard-not-reproducible-off-ci`), so adoption needs CI. The search
  space is strictly wider, which costs attempts per unit inside the same 6.5 s
  budget; whether that trade is positive on pools of 10-40 is exactly what the
  guard has to answer.
- Two cases, one machine, Task C only.
- The fix widens where the search looks and changes nothing about what it
  accepts, so it cannot admit an illegal placement -- but it can change which
  legal placement is chosen, and every downstream number moves with the
  trajectory.

## Two observations worth recording

**c000-k1's death channel moved back to the fixed-coordinate fallback** (0/3 to
3/3). The episode now travels four placements further and then reaches a state
with no candidate, so the poison fallback fires where previously the episode
ended on a physics failure. The fallback problem is not solved by this; it is
relocated.

**Fill rose despite the band being wall-adjacent.** Official QA records that
items flush against container walls earn no fill credit
(`wall-flush-fill-exclusion`), and the band this fix opens is exactly the
wall-adjacent one. Fill still rose 93% on c000-k1, so the gain is dominated by
the additional placements the opened band enables downstream rather than by the
wall-hugging items themselves. Not a concern, but it is the reason the fill
gain is not proportional to the placed gain across the two cases.
