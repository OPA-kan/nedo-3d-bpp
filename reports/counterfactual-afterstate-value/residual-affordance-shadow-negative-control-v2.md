# Residual-affordance shadow negative-control v2

This protocol is frozen after runs `32380902237` and `32381957502` failed the
original exact cross-process action-hash gate and before any v2 episode is
launched. It does not reinterpret either historical wave as a pass.

## Why the control changes

Run `32381957502` showed multiple action hashes among repeats of the identical
base arm. Exact hashes from independent wall-clock-bounded PyBullet processes
therefore combine two questions: whether shadow code changes the selected
action and whether two physical runs enter the same timing-dependent search
basin. The first is the causal no-op contract; the second is environmental
variation. V2 measures them separately.

## Frozen gates

1. **Same-call decision invariance.** At every residual-affordance observation,
   snapshot the selected action and the full deduplicated retained portfolio
   immediately before scoring. Both must be value-identical after scoring. At
   least 50 observations are required; missing fields, one selected-action
   mutation, or one portfolio mutation fails.
2. **Attribute safety.** Every unrestricted increase in direct or stack-aware
   soft/priority coverage or priority routing must be blocked. The guarded
   proposal must have zero contract regressions.
3. **Reach.** At least five guarded action changes must remain among at least
   50 observed decisions.
4. **Physical footprint.** For each of the five development cases, both arms
   need at least three successful repeats. For placed, fill, policy time,
   priority/soft clean ratios, shake displacement/energy/shift/topple channels,
   and terminal inclusion/validity/safety, the shadow-arm mean must remain
   within one full simultaneous-base repeat spread of the base mean. Missing
   metrics fail; no weighted proxy total is formed.
5. **Cross-process hashes are diagnostic only.** They remain in the report to
   expose trajectory diversity, but cannot override gates 1--4 in either
   direction.

`scripts/evaluate_residual_affordance_shadow_gate.py` is the sole executable
adjudicator. Passing v2 licenses preparation of a separately preregistered
guarded enforce canary. It does not license an official submission or make an
official-score improvement claim.
