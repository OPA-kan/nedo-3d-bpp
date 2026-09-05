# Candidate space — first probe: wall clearance

The agreement study said the analytic model forbids about half of what the
competition allows, and one named reason was the 16 mm wall clearance
against the official 5 mm (`outside-container`: 48 of 48 such probes were
accepted by the physics).  The cheapest test of "more candidate space helps"
is therefore to lower `inclusion_clearance`, which needs no new generator.

Arm `ladder-stable@inclusion_clearance=0.008` on the 48-scene core suite,
physics once and analytic once (`stable-vs-wall8-core.md`,
`stable-wall8-analytic-vs-physics.md`).

| metric | ladder-stable | +8 mm wall clearance | diff, 95 % CI |
|---|---:|---:|---|
| placed_count | 21.77 | 21.35 | −0.42 [−1.69, +0.75] |
| fill_volume | 23.80 | 23.78 | −0.02 [−1.35, +1.32] |
| fill_evaluator_shipped | 14.40 | 13.93 | −0.47 [−1.49, +0.56] |
| com_z_above_floor_ratio | 0.336 | 0.329 | −0.007 |
| inclusion failures in physics | 0 | 0 | |
| settle deaths | 2 | 1 | |

* **The physics accepts every 8 mm pose.**  No episode ended in
  `inclusion` or `transport`, so the 16 mm figure was conservative by at
  least 8 mm, as the probes said.
* **It buys nothing.**  Placed count and fill are flat with wide intervals;
  the per-layout means are +0.5 / +0.9 on one container and −1.8 / −1.3 on
  two, which is the usual chaotic scatter of a re-routed sequence, not a
  direction.  The `evaluator_shipped` fill drifts down, as it must: boxes
  settled nearer the wall are the ones the −0.005 margin discards.
* The one topple is a `priority-edge` standing pose (0.40 × 0.24 × 0.55 m,
  tipping ratio 2.3) on a terrace, again the loaded-stack class.

Wall clearance is not the lever.  The remaining half of the forbidden space
is the released drop — `no-support` was 724/736 accepted — and that needs a
generator, not a knob.
