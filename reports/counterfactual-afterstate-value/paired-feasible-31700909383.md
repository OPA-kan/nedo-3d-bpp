# Paired feasible-item audit — run 31700909383

- All eight conditions completed physical replay successfully.
- `all-visible` and `live-cap` used the same root fingerprint in every pair.
- The pool-10 control was unchanged: 8 feasible items in both arms.
- Every pool-over-10 condition had feasible items outside the live cap (7/7).
- Feasible-item gains were +10, +19, +16, +10, +16, +10, and +10.
- The score-ordered best safe candidate changed under cap 20 in every pool-over-10 condition (7/7); four of seven all-visible best candidates were recovered exactly.

The feasible-count target itself is rejected as a state-value teacher because
it nearly saturates at the visible pool size. The paired result instead
supports a new acting intervention: retain cap 10 before six placed items and
raise it to 20 from the measured mid/late band onward. This is implemented as
the opt-in `late_item_cap20` ablation arm. It is an agent candidate with an
expected internal selection-score improvement, not yet an established episode
or competition-score improvement.
