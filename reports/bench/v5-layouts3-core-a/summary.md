# bench run: `stack:reports/wedge/ppo-stack-c1-s0-tower@offline_dry_run=true,last_resort_relax=true,no_cover_other_attribute=true,priority_cargo_first=true,offline_planner=rows,plan_variants=after-hard,plan_layouts=3,priority_is_structure=true,reserve_headroom_for_soft=true,soft_headroom_volume_share=0.75,soft_headroom_slack=0.05,plan_min_support=0.0,plan_standing=true`

| scene | placed | total | fill_volume | fill_shipped | fill_tolerant | com_z_ratio | priority_covered | priority_misrouted | soft_covered | shake_mean_shift | shake_topples | policy_time_max | over_budget_steps | end_reason | runtime_seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a-c2-s0001 | 42 | 82 | 37.023 | 25.436 | 34.606 | 0.3642 | 0 | 0 | 0 | 0.0325 | 0 | 6.133 | 0 | declined | 244.7 |
| a-c2-s0002 | 31 | 82 | 30.158 | 19.141 | 27.651 | 0.4017 | 0 | 0 | 0 | 0.0554 | 1 | 4.528 | 0 | declined | 208.51 |
| a-c2-s0003 | 35 | 82 | 37.537 | 26.217 | 36.887 | 0.3868 | 0 | 0 | 0 | 0.0746 | 4 | 4.719 | 0 | declined | 222.75 |
| a-c2-s0004 | 49 | 82 | 38.851 | 27.865 | 38.851 | 0.3406 | 0 | 0 | 0 | 0.0229 | 0 | 6.438 | 0 | declined | 207.67 |
| a-c2-s0005 | 45 | 82 | 38.632 | 28.248 | 38.073 | 0.3822 | 0 | 0 | 0 | 0.0284 | 0 | 6.175 | 0 | declined | 256.32 |
| a-c2-s0006 | 30 | 82 | 27.756 | 18.078 | 25.34 | 0.3435 | 0 | 0 | 0 | 0.0575 | 1 | 4.451 | 0 | declined | 200.81 |
| a-c2-s0007 | 38 | 82 | 35.665 | 25.577 | 33.339 | 0.3827 | 0 | 0 | 0 | 0.0358 | 0 | 5.181 | 0 | declined | 234.79 |
| a-c2-s0008 | 40 | 82 | 35.458 | 24.822 | 34.9 | 0.3558 | 0 | 0 | 0 | 0.0424 | 0 | 5.268 | 0 | declined | 228.78 |
| a-c2-s0009 | 30 | 82 | 27.407 | 18.082 | 27.407 | 0.2976 | 0 | 0 | 0 | 0.0215 | 0 | 4.399 | 0 | settle | 192.37 |
| a-c2-s0010 | 41 | 82 | 39.388 | 26.179 | 35.597 | 0.3764 | 0 | 0 | 0 | 0.036 | 0 | 5.647 | 0 | declined | 243.93 |
| a-c2-s0011 | 47 | 82 | 36.323 | 25.337 | 36.323 | 0.3102 | 0 | 0 | 0 | 0.0187 | 0 | 3.736 | 0 | declined | 200.59 |
| a-c2-s0012 | 49 | 82 | 39.835 | 28.29 | 39.276 | 0.3849 | 0 | 0 | 0 | 0.027 | 0 | 6.178 | 0 | declined | 271.7 |
