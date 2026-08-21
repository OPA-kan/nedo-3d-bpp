# Residual-affordance guarded-enforce canary v1

This development protocol is frozen after shadow negative-control v3 run
`32436768825` passed and before the first guarded-enforce episode is launched.
It tests whether the frozen residual-affordance action model improves the
executed trajectory. It does not change model weights, feature scales, or the
five-axis soft/priority guard.

## Arms and population

Run three repeats of `base` and `residual_affordance_enforce` on each of the
five frozen development cases: `b000-k15`, `b000-k20`, `b000-k40`,
`b001-k20`, and `b001-k30`. Both arms use the same code and configuration;
the enforce arm alone executes the guarded proposal after ordinary selection
is frozen. At least 15 successful episodes per arm are required.

## Frozen gates

No weighted total is formed and improvement on one axis cannot compensate for
regression on another.

1. **Causal reach.** At least five guarded proposals must actually be
   executed. The trace must contain zero guarded soft/priority contract
   regressions.
2. **Trajectory value.** Mean placed, fill, and completed steps must each be
   no worse than simultaneous base. At least one of placed or fill must be
   strictly better.
3. **Special attributes.** Mean priority-clean and soft-clean ratios must each
   be no worse than simultaneous base.
4. **Physical veto.** Mean shake maximum shift, peak kinetic energy, shifted
   items, toppled items, and shifted fraction must each be no worse than base.
5. **Terminal validity.** Mean inclusion, validity, and placed-safe rates must
   each be no worse than base.

Missing arms, metrics, or repeats fail closed. Cross-process action hashes are
diagnostic only. A PASS licenses an unchanged replication wave on unseen
scenarios; it does not license an official submission. Only a replicated PASS
may support the claim that the learned residual-space policy improves
trajectory value.

`scripts/evaluate_residual_affordance_enforce_canary.py` is the sole
executable adjudicator.
