# Counterfactual teacher baseline replication

Two consecutive Linux physical matrices satisfied the complete source-state
and paired-action tensor contract. The root trajectories are physics-sensitive,
so the discovery/late row counts and directional denominators moved between
runs. Exact correct/total counts are retained instead of pooling them.

| Run | Split (discovery/late) | Axis | Immediate score | Action 1-NN | State+action 1-NN |
|---:|---:|---|---:|---:|---:|
| 31563029977 | 56 / 10 | fill | 4/7 | 6/7 | 6/7 |
| 31563029977 | 56 / 10 | CoG | 8/10 | 6/10 | 7/10 |
| 31563029977 | 56 / 10 | surface variation | 5/10 | 8/10 | 9/10 |
| 31563973521 | 58 / 8 | fill | 5/7 | 6/7 | 6/7 |
| 31563973521 | 58 / 8 | CoG | 6/8 | 4/8 | 5/8 |
| 31563973521 | 58 / 8 | surface variation | 4/8 | 7/8 | 7/8 |

The pairwise corpus and score-order counterexample replicate. Candidate-action
features beat immediate score on fill and surface in both runs. Adding the
source-state summary improves some cells by one decision, but not consistently;
it remains unproven that the current state summary adds value beyond the
candidate action. Neither run establishes generalization or live-policy gain.
