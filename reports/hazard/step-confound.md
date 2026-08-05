# The afterstate features were a clock

Every ranking of the afterstate features on this corpus has been measuring
how late in the episode a board is, not how good it is. The label is
`1` when the episode ends within a horizon of that step, so step index is a
predictor by construction -- and the features that scored best all rise
monotonically with step index too.

Instrument: `scripts/measure_step_confound.py`, tested in
`tests/test_measure_step_confound.py`. It reports each feature's raw AUC,
its AUC after the within-case linear step trend and level are removed, and
the within-step AUC, which is the only contrast free of the confound by
construction.

## The reading

231 rows, 32 positives, 8 scenario-matrix cases.

**Step index on its own scores AUC 0.832.**

```
feature                      raw  residual   |residual - 0.5|
roughness                  0.848     0.439              0.061
occupancy_mean             0.838     0.549              0.049
placed (a step counter)    0.800     0.421              0.079
R_min_type                 0.097     0.370              0.130
R_cardboard                0.087     0.363              0.137
R_suitcase_large           0.121     0.379              0.121
R_daypack_small            0.178     0.307              0.193
floor_fraction_free        0.222     0.726              0.226
occupancy_max              0.696     0.197              0.303
headroom_deficit           0.329     0.214              0.286
largest_free_span          0.330     0.440              0.060
```

`roughness` and `occupancy_mean` -- the two features that dominated every
previous analysis here, including the "occupancy_mean alone scores 0.944"
result that retired the fitted six-feature model -- fall to chance once the
clock is removed. `placed`, a literal step counter, falls to chance too,
which is the sanity check that the residualisation works.

So the six-feature afterstate set is a clock. That also explains, without
any new hypothesis, why the regime gate added nothing to it and why three
value functions failed on it.

## What survives, and how far it can be trusted

The `R_c` family keeps a consistent residual across all seven published
types (0.307 to 0.379, all on the same side of 0.5), and `occupancy_max`,
`headroom_deficit` and `floor_fraction_free` get STRONGER after detrending,
which is a suppression effect.

None of it is confirmed, for two reasons stated here rather than discovered
later:

1. **Within-step pairs = 0, for every feature.** The corpus records one row
   per step, so the confound-free contrast has nothing to work with. The
   residual is the only available tool.
2. **Residualisation removes a LINEAR trend only.** A feature whose true
   dependence on step index is curved keeps part of the clock, so a
   surviving residual is an upper bound on real signal, never a proof of it.

At 32 positives the sign flips (`floor_fraction_free` 0.222 raw to 0.726
residual) are as likely to be small-sample artefacts as suppression.

## Instability, measured

The same script over the same eight scenes, run twice, does not agree on
which feature is best:

```
run 1 (245 rows)          run 2 (233 rows)
R_min_type      0.372     roughness       0.373
roughness       0.320     occupancy_mean  0.344
occupancy_mean  0.313     R_min_type      0.325
```

Row counts differ because the agent is deadline-driven and the two runs had
different CPU loads, which changes the trajectory. The earlier reading that
"R_min_type beats occupancy_mean" was not a finding.

## Consequence

Confirming any board feature needs contrasts at the SAME step: several
alternatives evaluated from one board, with the outcome of each. That is
what `scripts/measure_dead_end_branch.py` produces, expensively. No cheaper
substitute on this corpus can separate a board descriptor from a clock.

## A defect this found in the feature set

`covered_void` and `headroom_deficit` returned the same number to machine
precision (max absolute difference 3.3e-16, Spearman 1.0). The "new"
orthogonal feature was a rename: computed from the heightmap,
`mean(max_height - height)` IS the headroom deficit, and a heightmap holds
one number per column so it cannot express an overhang at all.

Fixed in `sealed_void_fraction`, which voxelises the settled AABBs and
returns two fractions, because the first version conflated them:

```
                         headroom_deficit  covered_void  covered_void_by_items
empty shelf container             0.00000       0.26826                0.00000
after one placement               0.58390       0.26826                0.04465
after four                        0.50921       0.26826                0.08559
```

On an empty shelf container 0.268 of the interior is already sealed -- by
the shelf. That is a property of the container, useful to L3 when choosing
between containers and useless as a description of what the packing did, so
`covered_void_by_items` reports only the part with settled items as the
ceiling.
