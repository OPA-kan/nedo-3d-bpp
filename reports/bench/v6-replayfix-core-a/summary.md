# bench run: `stack:reports/wedge/ppo-stack-c1-s0-tower@offline_dry_run=true,last_resort_relax=true,no_cover_other_attribute=true,priority_cargo_first=true,offline_planner=rows,plan_variants=after-hard,plan_layouts=3,priority_is_structure=true,reserve_headroom_for_soft=true,soft_headroom_volume_share=0.75,soft_headroom_slack=0.05,plan_min_support=0.0,plan_standing=false`

| scene | placed | total | fill_volume | fill_shipped | fill_tolerant | com_z_ratio | priority_covered | priority_misrouted | soft_covered | shake_mean_shift | shake_topples | policy_time_max | over_budget_steps | end_reason | runtime_seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a-c2-s0001 | 48 | 82 | 39.754 | 29.268 | 39.754 | 0.3823 | 0 | 0 | 0 | 0.0226 | 0 | 5.049 | 0 | declined | 174.79 |
| a-c2-s0002 | 33 | 82 | 33.161 | 22.583 | 33.161 | 0.3091 | 0 | 0 | 0 | 0.0223 | 0 | 0.003 | 0 | transport | 159.79 |
| a-c2-s0003 | 34 | 82 | 37.483 | 25.905 | 37.483 | 0.3171 | 0 | 0 | 0 | 0.0292 | 0 | 0.003 | 0 | transport | 154.33 |
| a-c2-s0004 | 52 | 82 | 40.976 | 29.99 | 40.976 | 0.3694 | 0 | 0 | 0 | 0.0167 | 0 | 4.701 | 0 | declined | 177.42 |
| a-c2-s0005 | 52 | 82 | 42.485 | 32.256 | 42.485 | 0.3764 | 0 | 0 | 0 | 0.022 | 0 | 4.992 | 0 | declined | 171.26 |
| a-c2-s0006 | 44 | 82 | 40.143 | 29.658 | 40.143 | 0.3808 | 0 | 0 | 0 | 0.0457 | 0 | 3.198 | 0 | declined | 173.12 |
| a-c2-s0007 | 50 | 82 | 43.841 | 32.049 | 43.282 | 0.3728 | 0 | 0 | 0 | 0.0171 | 0 | 4.859 | 0 | declined | 177.97 |
| a-c2-s0008 | 51 | 82 | 43.087 | 32.101 | 43.087 | 0.3547 | 0 | 0 | 0 | 0.021 | 0 | 4.159 | 0 | declined | 182.4 |
| a-c2-s0009 | 50 | 82 | 44.229 | 32.996 | 44.229 | 0.3774 | 0 | 0 | 0 | 0.0253 | 0 | 4.749 | 0 | declined | 172.73 |
| a-c2-s0010 | 34 | 82 | 35.81 | 24.232 | 35.81 | 0.3142 | 0 | 0 | 0 | 0.0292 | 0 | 0.003 | 0 | transport | 153.56 |
| a-c2-s0011 | 48 | 82 | 38.27 | 27.285 | 38.27 | 0.3341 | 0 | 0 | 0 | 0.0248 | 0 | 4.952 | 0 | declined | 181.21 |
| a-c2-s0012 | 50 | 82 | 41.594 | 31.016 | 41.594 | 0.3603 | 1 | 0 | 0 | 0.0225 | 0 | 4.771 | 0 | declined | 182.99 |
