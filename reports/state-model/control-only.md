# State-model training

- Verdict: **state_model_beats_incumbent**
- Corpus: 2926 rows, 130 boards, 8 cases
- Positives from: `control`
- Split: `leave_one_case_out`, 2 seeds, 200 epochs

| model | mean within-state AUC | pooled AUC | top-1 safe rate |
|---|---:|---:|---:|
| incumbent | 0.745 | 0.723 | 0.874 |
| phi_mlp | 0.768 | 0.777 | 0.757 |
| candidate_mlp | 0.851 | 0.852 | 0.882 |
| set_attention | 0.841 | 0.841 | 0.874 |

## settle regression (R^2 against a held-out constant)

| target | phi_mlp | candidate_mlp | set_attention |
|---|---:|---:|---:|
| delta_theta_deg | 0.249 | 0.269 | 0.299 |
| d_norm | 0.182 | 0.373 | 0.373 |

Same protocol as scripts/audit_learnability.py, so these numbers sit beside its linear and lookup arms. phi_mlp isolates model capacity on the eight scalars; candidate_mlp adds the action's own geometry and its container; set_attention adds attention over the placed items and the pool and is the only arm that can see a neighbour. A win by candidate_mlp over phi_mlp means the features were the constraint; a win by set_attention over candidate_mlp means the board is. The corpus is small, so read the ordering of the arms, not the third decimal.
