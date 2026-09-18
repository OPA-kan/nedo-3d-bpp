# bench run: `stack:reports/wedge/ppo-stack-c1-s0-tower@last_resort_relax=true,no_cover_other_attribute=true,priority_cargo_first=true,offline_planner=rows,plan_variants=after-hard,priority_is_structure=true,reserve_headroom_for_soft=true,soft_headroom_volume_share=0.75,soft_headroom_slack=0.05,plan_min_support=0.0`

| scene | placed | total | fill_volume | fill_shipped | fill_tolerant | com_z_ratio | priority_covered | priority_misrouted | soft_covered | shake_mean_shift | shake_topples | policy_time_max | over_budget_steps | end_reason | runtime_seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a-c1-s0001 | 25 | 41 | 40.809 | 29.86 | 40.809 | 0.3627 | 1 | 0 | 0 | 0.0357 | 0 | 1.594 | 0 | declined | 12.74 |
| a-c1s-s0001 | 22 | 41 | 35.399 | 24.378 | 35.399 | 0.3363 | 0 | 0 | 0 | 0.03 | 0 | 2.596 | 0 | declined | 16.66 |
| a-c2-s0001 | 52 | 82 | 42.508 | 31.522 | 42.508 | 0.3539 | 2 | 0 | 0 | 0.0154 | 0 | 4.902 | 0 | declined | 62.91 |
| a-c2p-s0001 | 44 | 82 | 37.476 | 25.534 | 36.826 | 0.3371 | 0 | 0 | 0 | 0.0183 | 0 | 5.584 | 0 | declined | 50.37 |
