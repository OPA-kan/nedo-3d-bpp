# bench run: `stack:reports/wedge/ppo-stack-c1-s0-tower@last_resort_relax=true,no_cover_other_attribute=true,priority_cargo_first=true,offline_planner=rows,plan_variants=after-hard,priority_is_structure=true,reserve_headroom_for_soft=true,soft_headroom_volume_share=0.75,soft_headroom_slack=0.05`

| scene | placed | total | fill_volume | fill_shipped | fill_tolerant | com_z_ratio | priority_covered | priority_misrouted | soft_covered | shake_mean_shift | shake_topples | policy_time_max | over_budget_steps | end_reason | runtime_seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a-c1-s0001 | 23 | 41 | 37.554 | 26.604 | 37.554 | 0.3194 | 1 | 0 | 0 | 0.0339 | 0 | 1.678 | 0 | declined | 12.46 |
| a-c1s-s0001 | 22 | 41 | 34.593 | 23.571 | 34.593 | 0.3281 | 0 | 0 | 0 | 0.0288 | 0 | 1.793 | 0 | declined | 12.14 |
| a-c2-s0001 | 50 | 82 | 40.613 | 29.628 | 40.613 | 0.3461 | 0 | 0 | 0 | 0.0236 | 0 | 4.215 | 0 | declined | 48.25 |
| a-c2p-s0001 | 46 | 82 | 38.822 | 26.128 | 38.173 | 0.347 | 0 | 0 | 0 | 0.0253 | 0 | 5.351 | 0 | declined | 52.5 |
