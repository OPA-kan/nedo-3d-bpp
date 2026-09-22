# bench run: `stack:reports/wedge/ppo-stack-c1-s0-tower@offline_dry_run=true,last_resort_relax=true,no_cover_other_attribute=true,priority_cargo_first=true,offline_planner=rows,plan_variants=after-hard,plan_layouts=1,priority_is_structure=true,reserve_headroom_for_soft=true,soft_headroom_volume_share=0.75,soft_headroom_slack=0.05,plan_min_support=0.0,plan_standing=true,plan_replay_clearance=0.026,plan_replay_nudge=0.0,conservative_transport=false,count_first=true,plan_score_weights=1;0.5;0.5;3`

| scene | placed | total | fill_volume | fill_shipped | fill_tolerant | com_z_ratio | priority_covered | priority_misrouted | soft_covered | shake_mean_shift | shake_topples | policy_time_max | over_budget_steps | end_reason | runtime_seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a-c1s-s0001 | 24 | 41 | 39.317 | 27.184 | 39.317 | 0.404 | 0 | 0 | 0 | 0.0579 | 0 | 3.642 | 0 | declined | 94.41 |
| a-c1s-s0002 | 19 | 41 | 32.289 | 23.257 | 32.289 | 0.3516 | 0 | 0 | 0 | 0.0246 | 0 | 2.89 | 0 | declined | 78.57 |
| a-c1s-s0003 | 21 | 41 | 31.532 | 21.109 | 30.239 | 0.3447 | 1 | 0 | 0 | 0.0188 | 0 | 3.243 | 0 | declined | 67.32 |
| a-c1s-s0004 | 23 | 41 | 38.359 | 23.764 | 36.4 | 0.3717 | 0 | 0 | 0 | 0.0266 | 0 | 3.097 | 0 | declined | 89.52 |
| a-c1s-s0005 | 27 | 41 | 35.938 | 25.001 | 35.938 | 0.3341 | 0 | 0 | 0 | 0.0138 | 0 | 3.552 | 0 | declined | 77.52 |
| a-c1s-s0006 | 24 | 41 | 32.277 | 21.34 | 32.277 | 0.3144 | 0 | 0 | 0 | 0.0125 | 0 | 3.409 | 0 | declined | 69.89 |
| a-c1s-s0007 | 23 | 41 | 30.284 | 19.862 | 28.992 | 0.2834 | 0 | 0 | 0 | 0.0114 | 0 | 3.405 | 0 | declined | 62.19 |
| a-c1s-s0008 | 26 | 41 | 33.525 | 21.991 | 31.121 | 0.3421 | 0 | 0 | 0 | 0.0399 | 2 | 3.596 | 0 | declined | 68.08 |
| a-c1s-s0009 | 24 | 41 | 32.272 | 22.031 | 31.161 | 0.3081 | 0 | 0 | 0 | 0.0119 | 0 | 3.733 | 0 | declined | 61.87 |
| a-c1s-s0010 | 21 | 41 | 40.764 | 28.931 | 40.764 | 0.4116 | 0 | 0 | 0 | 0.0635 | 0 | 2.626 | 0 | declined | 72.26 |
| a-c1s-s0011 | 23 | 41 | 29.874 | 18.938 | 29.874 | 0.2737 | 0 | 0 | 0 | 0.0365 | 1 | 3.624 | 0 | declined | 68.44 |
| a-c1s-s0012 | 26 | 41 | 36.19 | 25.768 | 34.898 | 0.3353 | 0 | 0 | 0 | 0.0146 | 0 | 3.524 | 0 | declined | 61.88 |
