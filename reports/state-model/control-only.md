# State-model training

- Verdict: **state_model_beats_incumbent**
- Corpus: 2610 rows, 118 boards, 8 cases
- Positives from: `control`
- Split: `leave_one_case_out`, 2 seeds, 200 epochs

| model | mean within-state AUC | pooled AUC | top-1 safe rate |
|---|---:|---:|---:|
| incumbent | 0.742 | 0.719 | 0.861 |
| phi_mlp | 0.768 | 0.776 | 0.746 |
| candidate_mlp | 0.849 | 0.847 | 0.896 |
| set_attention | 0.841 | 0.842 | 0.887 |

## settle regression (R^2 against a held-out constant)

| target | phi_mlp | candidate_mlp | set_attention |
|---|---:|---:|---:|
| delta_theta_deg | 0.234 | 0.242 | 0.270 |
| d_norm | 0.187 | 0.357 | 0.363 |

Same protocol as scripts/audit_learnability.py, so these numbers sit beside its linear and lookup arms. phi_mlp isolates model capacity on the eight scalars; candidate_mlp adds the action's own geometry and its container; set_attention adds attention over the placed items and the pool and is the only arm that can see a neighbour. A win by candidate_mlp over phi_mlp means the features were the constraint; a win by set_attention over candidate_mlp means the board is. The corpus is small, so read the ordering of the arms, not the third decimal.
