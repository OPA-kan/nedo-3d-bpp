# bench run: `stack:reports/wedge/ppo-stack-c1-s0-tower@offline_dry_run=true,last_resort_relax=true,no_cover_other_attribute=true,priority_cargo_first=true,offline_planner=rows,plan_variants=after-hard,plan_layouts=1,priority_is_structure=true,reserve_headroom_for_soft=true,soft_headroom_volume_share=0.75,soft_headroom_slack=0.05,plan_min_support=0.0,plan_standing=true`

| scene | placed | total | fill_volume | fill_shipped | fill_tolerant | com_z_ratio | priority_covered | priority_misrouted | soft_covered | shake_mean_shift | shake_topples | policy_time_max | over_budget_steps | end_reason | runtime_seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a-c1s-s0001 | 24 | 41 | 39.317 | 27.184 | 39.317 | 0.404 | 0 | 0 | 0 | 0.0579 | 0 | 3.609 | 0 | declined | 95.48 |
| a-c1s-s0002 | 20 | 41 | 40.107 | 28.274 | 40.107 | 0.4111 | 0 | 0 | 0 | 0.0393 | 0 | 2.834 | 0 | declined | 73.31 |
| a-c1s-s0003 | 22 | 41 | 40.816 | 29.794 | 40.816 | 0.3639 | 0 | 0 | 0 | 0.0169 | 0 | 3.173 | 0 | declined | 55.43 |
| a-c1s-s0004 | 23 | 41 | 38.359 | 23.764 | 36.4 | 0.3717 | 0 | 0 | 0 | 0.0266 | 0 | 3.083 | 0 | declined | 90.8 |
| a-c1s-s0005 | 25 | 41 | 37.659 | 26.637 | 37.659 | 0.3646 | 0 | 0 | 0 | 0.0311 | 0 | 3.953 | 0 | declined | 69.47 |
| a-c1s-s0006 | 21 | 41 | 39.033 | 28.011 | 39.033 | 0.345 | 0 | 0 | 0 | 0.0178 | 0 | 2.973 | 0 | declined | 60.59 |
| a-c1s-s0007 | 21 | 41 | 38.347 | 27.326 | 38.347 | 0.3385 | 0 | 0 | 0 | 0.0155 | 0 | 2.868 | 0 | declined | 58.36 |
| a-c1s-s0008 | 22 | 41 | 35.651 | 24.629 | 35.651 | 0.3513 | 0 | 0 | 0 | 0.0219 | 0 | 3.002 | 0 | declined | 63.63 |
| a-c1s-s0009 | 22 | 41 | 40.323 | 29.302 | 40.323 | 0.3524 | 0 | 0 | 0 | 0.0167 | 0 | 2.775 | 0 | declined | 56.5 |
| a-c1s-s0010 | 22 | 41 | 39.952 | 28.93 | 39.952 | 0.3531 | 0 | 0 | 0 | 0.0176 | 0 | 2.961 | 0 | declined | 57.3 |
| a-c1s-s0011 | 23 | 41 | 36.395 | 25.373 | 36.395 | 0.3368 | 0 | 0 | 0 | 0.0295 | 0 | 3.64 | 0 | declined | 68.31 |
| a-c1s-s0012 | 22 | 41 | 37.797 | 26.775 | 37.797 | 0.3526 | 0 | 0 | 0 | 0.022 | 0 | 3.179 | 0 | declined | 65.04 |
