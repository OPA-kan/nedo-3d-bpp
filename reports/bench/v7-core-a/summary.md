# bench run: `stack:reports/wedge/ppo-stack-c1-s0-tower@offline_dry_run=true,last_resort_relax=true,no_cover_other_attribute=true,priority_cargo_first=true,offline_planner=rows,plan_variants=after-hard,plan_layouts=3,priority_is_structure=true,reserve_headroom_for_soft=true,soft_headroom_volume_share=0.75,soft_headroom_slack=0.05,plan_min_support=0.0,plan_standing=false`

| scene | placed | total | fill_volume | fill_shipped | fill_tolerant | com_z_ratio | priority_covered | priority_misrouted | soft_covered | shake_mean_shift | shake_topples | policy_time_max | over_budget_steps | end_reason | runtime_seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a-c1-s0001 | 28 | 41 | 43.014 | 32.064 | 43.014 | 0.3672 | 0 | 0 | 0 | 0.0225 | 0 | 2.346 | 0 | declined | 72.47 |
| a-c1-s0002 | 21 | 41 | 37.141 | 25.479 | 35.794 | 0.323 | 0 | 0 | 0 | 0.0291 | 0 | 2.56 | 0 | declined | 58.19 |
| a-c1-s0003 | 21 | 41 | 42.135 | 29.995 | 42.135 | 0.3457 | 1 | 0 | 0 | 0.028 | 0 | 2.554 | 0 | declined | 61.48 |
| a-c1-s0004 | 25 | 41 | 39.734 | 28.785 | 39.734 | 0.33 | 1 | 0 | 0 | 0.024 | 0 | 2.65 | 0 | declined | 60.87 |
| a-c1-s0005 | 29 | 41 | 45.768 | 29.557 | 45.768 | 0.4156 | 0 | 0 | 0 | 0.0378 | 0 | 2.604 | 0 | declined | 103.67 |
| a-c1-s0006 | 22 | 41 | 42.156 | 28.698 | 42.156 | 0.3546 | 0 | 0 | 0 | 0.0246 | 0 | 2.493 | 0 | declined | 61.81 |
| a-c1-s0007 | 21 | 41 | 38.237 | 27.287 | 38.237 | 0.3103 | 0 | 0 | 0 | 0.0212 | 0 | 1.754 | 0 | declined | 60.74 |
| a-c1-s0008 | 25 | 41 | 42.054 | 31.25 | 41.38 | 0.3698 | 0 | 0 | 0 | 0.027 | 0 | 2.586 | 0 | declined | 63.78 |
| a-c1-s0009 | 23 | 41 | 45.588 | 33.448 | 45.588 | 0.3725 | 0 | 0 | 0 | 0.0207 | 0 | 2.533 | 0 | declined | 53.07 |
| a-c1-s0010 | 25 | 41 | 46.574 | 33.117 | 46.574 | 0.3724 | 1 | 0 | 0 | 0.0243 | 0 | 2.235 | 0 | declined | 63.39 |
| a-c1-s0011 | 25 | 41 | 39.393 | 29.263 | 39.393 | 0.3583 | 0 | 0 | 0 | 0.023 | 0 | 2.647 | 0 | declined | 75.85 |
| a-c1-s0012 | 21 | 41 | 38.601 | 27.652 | 38.601 | 0.3078 | 0 | 0 | 0 | 0.0273 | 0 | 2.038 | 0 | declined | 55.21 |
