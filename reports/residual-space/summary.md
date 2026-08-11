# Residual space: what predicts observed afterstate difference

- Verdict: **hand_made_proxy_holds** (best: `command_proxy`)
- 105108 within-board pairs from 130 boards, 8 cases
- Truth: `gower_distance_over_observed_x_plus`

| predictor | mean within-board Spearman | pooled Spearman |
|---|---:|---:|
| command_proxy | 0.839 | 0.841 |
| candidate_mlp | 0.432 | 0.395 |
| set_attention | 0.472 | 0.415 |

Pairs are formed inside a board, so this measures ordering of candidate-versus-candidate residual difference, not how different two boards are. Truth is the same Gower distance the acceptance guard reports, on observed x_plus. Every predictor is available before the replay, which is the expensive step -- so a learned winner would also mean a portfolio can be spread out without settling every overdrawn candidate first. A win for command_proxy means the fourteen hand-made fields already do the job.
