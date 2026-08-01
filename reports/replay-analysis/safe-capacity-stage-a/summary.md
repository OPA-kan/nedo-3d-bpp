# Stage A': risk-weighted kappa (negative, and not a resolution problem)

42 development snapshots (3 final_holdout datasets skipped, RELEASE_RISK_PROTOCOL 3.1). Terminal channels: physical 17, terminal 25, fallback 0. Y_1/Y_2/Y_3 positives: 8 / 14 / 16.

| rule | mean | sd | distinct | Spearman vs T_physical | AUC vs Y_1 | AUC vs Y_2 | AUC vs Y_3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `raw` | 19.786 | 3.979 | 12 | 0.5032 | 0.4908 | 0.5982 | 0.6274 |
| `sum` | 15.384 | 3.749 | 37 | 0.2514 | 0.4706 | 0.5179 | 0.524 |
| `max` | 16.853 | 3.621 | 37 | 0.2514 | 0.4669 | 0.5612 | 0.5673 |
| `product` | 15.928 | 3.666 | 37 | 0.2142 | 0.4743 | 0.5306 | 0.5361 |

Spearman is over the 17 uncensored snapshots; AUC is over all 42.

## Verdict: risk weighting does not help, and all three rules agree

Weighting an option by its modelled survival makes the relation to the
physical label **worse**, not better, under every combination rule:
Spearman 0.503 -> 0.251 / 0.251 / 0.214 and AUC(Y_3) 0.627 -> 0.524 /
0.567 / 0.536. The union-bound, max and independence rules land in the same
place, so by the agreement criterion this is robust and not an artefact of
one combination choice. No new hypothesis about the combination rule is
needed, because none of them separates.

## The motivating diagnosis was wrong, which makes the negative stronger

This experiment was justified by 'raw kappa failed because it saturated'.
That does not hold for this counting. The constant-class fraction is 0.0
for **raw** as well as for every weighted rule: no per-class descriptor is
constant across snapshots, and raw kappa takes 12 distinct totals. The
constant 0.113 in Stage A was `release_cap_volume`, the largest acceptable
class volume - a different quantity from an independent-option count.

So raw kappa here has adequate resolution and still fails. Weighting adds
resolution (12 -> 37 distinct totals) and *loses* signal. The problem is
not that the instrument cannot tell states apart.

## Mechanism

- Release options are 48.4% of independent options on average (0.089 to
  1.000 across snapshots), so the weighting has real scope to act.
- The models are not degenerate: P_rot mean 0.245 (sd 0.135, range
  0.015-0.722), P_slide mean 0.152 (sd 0.144, range 0.001-0.763) over 184
  modelled class-observations.
- But the net effect is close to a uniform shrink:
  `kappa_product / kappa_raw` is 0.810 mean with sd 0.110. The weighting
  contributes variation that is not aligned with the outcome - it dilutes
  rather than sharpens.

The reason is structural rather than a modelling defect. **An episode fails
from the action the policy actually takes, not from the average safety of
the option pool.** kappa^safe averages survival over options the policy will
mostly never select, so per-option risk cannot aggregate into a state
descriptor that predicts a failure caused by one specific selected action.

## Do not read raw kappa's 0.503 as predictive power

It is the Stage A confound again. Spearman(kappa_raw, step) = -0.367 and
Spearman(step, T_physical) = -0.342: both quantities decline with step, so
a positive rank correlation between them appears without either informing
the other. Absolute state descriptors keep failing for the same reason, and
this is the third measurement to show it.

The conclusion is therefore about where to look, not which weight to use:
the within-state per-action differential (Stage B) is the only form left
that these confounds do not reach.

## Scope

- 42 snapshots, 17 with an uncensored physical failure. Small.
- `sum(w_j)` is an expected count of safe options, not an episode survival
  probability; nothing here estimates the latter.
- Settled options carry weight 1.0 because both calibrated models are
  release-specific. A settled-survival model would change the instrument,
  not just its numbers.
- Y_h is exact rather than censored, but T_physical is defined only on the
  17 failing episodes, and Spearman is reported on those alone.
