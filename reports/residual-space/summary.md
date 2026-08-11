# Residual space: what predicts observed afterstate difference

- Verdict: **hand_made_proxy_holds** (best: `command_proxy`)
- 162978 within-board pairs from 182 boards, 8 cases
- Truth: `gower_distance_over_observed_x_plus_in_container_frame`

| predictor | mean within-board Spearman | pooled Spearman | world frame (old) |
|---|---:|---:|---:|
| command_proxy | 0.848 | 0.851 | 0.841 |
| command_proxy_identity_only | 0.749 | 0.768 | 0.790 |
| command_proxy_geometry_only | 0.712 | 0.699 | 0.667 |
| candidate_mlp | 0.477 | 0.461 | 0.487 |
| set_attention | 0.504 | 0.422 | 0.500 |
| geometry_versus_geometry | 0.691 | — | 0.663 |

## on one footing: each half of the truth, separately

The full sum's own ordering is 0.917 correlated with its occupancy half and 0.422 with its consumption half, so a verdict read off the sum was mostly a verdict about occupancy without saying so.

| predictor | vs occupancy (settled where) | vs consumption (which item) |
|---|---:|---:|
| command_proxy | 0.709 | 0.385 |
| command_proxy_identity_only | 0.530 | 0.579 |
| command_proxy_geometry_only | 0.667 | 0.155 |
| candidate_mlp | 0.491 | 0.175 |
| set_attention | 0.502 | 0.165 |

The consumption column is not prediction. The proxy carries `pool_index` and `item_index` verbatim, so its agreement there is definitional and a learned arm has to earn what the proxy is handed. The occupancy column is where the item actually settled -- the part physics decides -- and it is what the verdict is read from.

Pairs are formed inside a board, so this measures ordering of candidate-versus-candidate residual difference, not how different two boards are. Truth is the same Gower distance the acceptance guard reports, on observed x_plus. Every predictor is available before the replay, which is the expensive step -- so a learned winner would also mean a portfolio can be spread out without settling every overdrawn candidate first. A win for command_proxy means the fourteen hand-made fields already do the job. Read the decomposition before the headline: the proxy and the truth share their four categorical fields, so command_proxy_identity_only is how much of the agreement is tautological, and geometry_versus_geometry is the only comparison with no shared terms on either side. The truth is now scored with settled positions in their own container's frame; the world-frame column is the same trained embeddings scored the way every measurement before 2026-08-11 read them, so the gap between the two is the coordinate frame and nothing else.
