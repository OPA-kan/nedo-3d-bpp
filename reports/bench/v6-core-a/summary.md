# bench run: `stack:reports/wedge/ppo-stack-c1-s0-tower@offline_dry_run=true,last_resort_relax=true,no_cover_other_attribute=true,priority_cargo_first=true,offline_planner=rows,plan_variants=after-hard,plan_layouts=3,priority_is_structure=true,reserve_headroom_for_soft=true,soft_headroom_volume_share=0.75,soft_headroom_slack=0.05,plan_min_support=0.0,plan_standing=false`

| scene | placed | total | fill_volume | fill_shipped | fill_tolerant | com_z_ratio | priority_covered | priority_misrouted | soft_covered | shake_mean_shift | shake_topples | policy_time_max | over_budget_steps | end_reason | runtime_seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a-c1-s0001 | 23 | 41 | 37.749 | 26.799 | 37.749 | 0.3084 | 0 | 0 | 0 | 0.0253 | 0 | 3.539 | 0 | declined | 75.81 |
| a-c1-s0002 | 19 | 41 | 35.345 | 25.029 | 35.345 | 0.372 | 0 | 0 | 0 | 0.0244 | 0 | 2.638 | 0 | declined | 82.44 |
| a-c1-s0003 | 11 | 41 | 27.596 | 14.451 | 27.596 | 0.2664 | 0 | 0 | 0 | 0.0374 | 0 | 2.527 | 0 | declined | 65.0 |
| a-c1-s0004 | 22 | 41 | 36.0 | 25.05 | 36.0 | 0.3064 | 1 | 0 | 0 | 0.0283 | 0 | 1.717 | 0 | declined | 64.47 |
| a-c1-s0005 | 29 | 41 | 45.768 | 29.557 | 45.768 | 0.4156 | 0 | 0 | 0 | 0.0373 | 0 | 2.696 | 0 | declined | 109.29 |
| a-c1-s0006 | 15 | 41 | 32.538 | 20.398 | 32.538 | 0.3408 | 0 | 0 | 0 | 0.0357 | 0 | 2.475 | 0 | declined | 74.77 |
| a-c1-s0007 | 21 | 41 | 38.237 | 27.287 | 38.237 | 0.307 | 0 | 0 | 0 | 0.0247 | 0 | 1.778 | 0 | declined | 66.1 |
| a-c1-s0008 | 18 | 41 | 33.497 | 23.367 | 33.497 | 0.3288 | 0 | 0 | 0 | 0.0445 | 0 | 2.787 | 0 | declined | 77.37 |
| a-c1-s0009 | 16 | 41 | 35.197 | 23.057 | 35.197 | 0.3438 | 0 | 0 | 0 | 0.0188 | 0 | 2.443 | 0 | declined | 64.6 |
| a-c1-s0010 | 15 | 41 | 32.538 | 20.398 | 32.538 | 0.3408 | 0 | 0 | 0 | 0.0357 | 0 | 2.467 | 0 | declined | 73.72 |
| a-c1-s0011 | 16 | 41 | 28.833 | 18.703 | 28.833 | 0.3389 | 0 | 0 | 0 | 0.0312 | 0 | 3.107 | 0 | declined | 87.46 |
| a-c1-s0012 | 21 | 41 | 38.601 | 27.652 | 38.601 | 0.3078 | 0 | 0 | 0 | 0.0273 | 0 | 2.125 | 0 | declined | 59.1 |
