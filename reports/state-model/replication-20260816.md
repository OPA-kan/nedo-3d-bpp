# State-model training

- Verdict: **state_model_beats_incumbent**
- Corpus: 7764 rows, 189 boards, 8 cases
- Positives from: `all`
- Split: `leave_one_case_out`, 2 seeds, 200 epochs

| model | mean within-state AUC | pooled AUC | top-1 safe rate |
|---|---:|---:|---:|
| incumbent | 0.705 | 0.691 | 0.849 |
| phi_mlp | 0.731 | 0.746 | 0.787 |
| candidate_mlp | 0.825 | 0.824 | 0.968 |
| set_attention | 0.818 | 0.823 | 0.968 |

## settle regression (R^2 against a held-out constant)

| target | phi_mlp | candidate_mlp | set_attention |
|---|---:|---:|---:|
| delta_theta_deg | 0.243 | 0.265 | 0.319 |
| d_norm | 0.187 | 0.303 | 0.363 |

Same protocol as scripts/audit_learnability.py, so these numbers sit beside its linear and lookup arms. phi_mlp isolates model capacity on the eight scalars; candidate_mlp adds the action's own geometry and its container; set_attention adds attention over the placed items and the pool and is the only arm that can see a neighbour. A win by candidate_mlp over phi_mlp means the features were the constraint; a win by set_attention over candidate_mlp means the board is. The corpus is small, so read the ordering of the arms, not the third decimal.
