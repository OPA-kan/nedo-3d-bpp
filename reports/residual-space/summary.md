# Residual space: what predicts observed afterstate difference

- Verdict: **hand_made_proxy_holds** (best: `command_proxy`)
- 140456 within-board pairs from 171 boards, 8 cases
- Truth: `gower_distance_over_observed_x_plus_in_container_frame`

| predictor | mean within-board Spearman | pooled Spearman | world frame (old) |
|---|---:|---:|---:|
| command_proxy | 0.844 | 0.844 | 0.837 |
| command_proxy_identity_only | 0.747 | 0.766 | 0.787 |
| command_proxy_geometry_only | 0.708 | 0.691 | 0.665 |
| candidate_mlp | 0.460 | 0.424 | 0.469 |
| set_attention | 0.498 | 0.439 | 0.494 |
| geometry_versus_geometry | 0.686 | — | 0.658 |

Pairs are formed inside a board, so this measures ordering of candidate-versus-candidate residual difference, not how different two boards are. Truth is the same Gower distance the acceptance guard reports, on observed x_plus. Every predictor is available before the replay, which is the expensive step -- so a learned winner would also mean a portfolio can be spread out without settling every overdrawn candidate first. A win for command_proxy means the fourteen hand-made fields already do the job. Read the decomposition before the headline: the proxy and the truth share their four categorical fields, so command_proxy_identity_only is how much of the agreement is tautological, and geometry_versus_geometry is the only comparison with no shared terms on either side. The truth is now scored with settled positions in their own container's frame; the world-frame column is the same trained embeddings scored the way every measurement before 2026-08-11 read them, so the gap between the two is the coordinate frame and nothing else.
