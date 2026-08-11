# State-model training

- Verdict: **state_model_beats_incumbent**
- Corpus: 4955 rows, 130 boards, 8 cases
- Positives from: `all`
- Split: `leave_one_case_out`, 2 seeds, 200 epochs

| model | mean within-state AUC | pooled AUC | top-1 safe rate |
|---|---:|---:|---:|
| incumbent | 0.733 | 0.715 | 0.882 |
| phi_mlp | 0.767 | 0.769 | 0.844 |
| candidate_mlp | 0.842 | 0.843 | 0.969 |
| set_attention | 0.835 | 0.839 | 0.961 |

## settle regression (R^2 against a held-out constant)

| target | phi_mlp | candidate_mlp | set_attention |
|---|---:|---:|---:|
| delta_theta_deg | 0.272 | 0.275 | 0.337 |
| d_norm | 0.215 | 0.343 | 0.390 |

Same protocol as scripts/audit_learnability.py, so these numbers sit beside its linear and lookup arms. phi_mlp isolates model capacity on the eight scalars; candidate_mlp adds the action's own geometry and its container; set_attention adds attention over the placed items and the pool and is the only arm that can see a neighbour. A win by candidate_mlp over phi_mlp means the features were the constraint; a win by set_attention over candidate_mlp means the board is. The corpus is small, so read the ordering of the arms, not the third decimal.
