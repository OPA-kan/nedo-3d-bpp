# bench run: `stack:reports/wedge/ppo-stack-c1-s0-tower@offline_dry_run=true,last_resort_relax=true,no_cover_other_attribute=true,priority_cargo_first=true,offline_planner=rows,plan_variants=after-hard,plan_layouts=1,priority_is_structure=true,reserve_headroom_for_soft=true,soft_headroom_volume_share=0.75,soft_headroom_slack=0.05,plan_min_support=0.0,plan_standing=false`

| scene | placed | total | fill_volume | fill_shipped | fill_tolerant | com_z_ratio | priority_covered | priority_misrouted | soft_covered | shake_mean_shift | shake_topples | policy_time_max | over_budget_steps | end_reason | runtime_seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a-c1-s0001 | 23 | 41 | 37.749 | 26.799 | 37.749 | 0.3084 | 0 | 0 | 0 | 0.0253 | 0 | 2.256 | 0 | declined | 39.88 |
| a-c1-s0002 | 25 | 41 | 45.44 | 34.49 | 45.44 | 0.3563 | 0 | 0 | 0 | 0.0281 | 0 | 1.245 | 0 | declined | 35.76 |
| a-c1-s0003 | 25 | 41 | 43.847 | 32.898 | 43.847 | 0.3775 | 0 | 0 | 0 | 0.0232 | 0 | 1.883 | 0 | declined | 39.57 |
| a-c1-s0004 | 22 | 41 | 36.0 | 25.05 | 36.0 | 0.3064 | 1 | 0 | 0 | 0.0283 | 0 | 1.088 | 0 | declined | 36.04 |
| a-c1-s0005 | 29 | 41 | 45.768 | 29.557 | 45.768 | 0.4156 | 0 | 0 | 0 | 0.0373 | 0 | 1.747 | 0 | declined | 61.42 |
| a-c1-s0006 | 20 | 41 | 37.915 | 26.965 | 37.915 | 0.333 | 0 | 0 | 0 | 0.0204 | 0 | 1.477 | 0 | declined | 36.09 |
| a-c1-s0007 | 21 | 41 | 38.237 | 27.287 | 38.237 | 0.307 | 0 | 0 | 0 | 0.0247 | 0 | 1.105 | 0 | declined | 36.38 |
| a-c1-s0008 | 24 | 41 | 40.748 | 29.798 | 40.748 | 0.3194 | 0 | 0 | 0 | 0.0243 | 0 | 1.646 | 0 | declined | 34.12 |
| a-c1-s0009 | 21 | 41 | 40.766 | 29.817 | 40.766 | 0.3368 | 1 | 0 | 0 | 0.0273 | 0 | 1.598 | 0 | declined | 31.69 |
| a-c1-s0010 | 25 | 41 | 42.931 | 31.982 | 42.931 | 0.3411 | 0 | 0 | 0 | 0.0262 | 0 | 1.346 | 0 | declined | 35.6 |
| a-c1-s0011 | 29 | 41 | 45.331 | 28.105 | 45.331 | 0.4096 | 0 | 0 | 0 | 0.0381 | 0 | 1.585 | 0 | declined | 58.17 |
| a-c1-s0012 | 21 | 41 | 38.601 | 27.652 | 38.601 | 0.3078 | 0 | 0 | 0 | 0.0273 | 0 | 1.321 | 0 | declined | 33.64 |
