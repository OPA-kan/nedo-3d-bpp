# bench run: `stack:reports/wedge/ppo-stack-c1-s0-tower@offline_dry_run=true,last_resort_relax=true,no_cover_other_attribute=true,priority_cargo_first=true,offline_planner=rows,plan_variants=after-hard,plan_layouts=3,priority_is_structure=true,reserve_headroom_for_soft=true,soft_headroom_volume_share=0.75,soft_headroom_slack=0.05,plan_min_support=0.0,plan_standing=false`

| scene | placed | total | fill_volume | fill_shipped | fill_tolerant | com_z_ratio | priority_covered | priority_misrouted | soft_covered | shake_mean_shift | shake_topples | policy_time_max | over_budget_steps | end_reason | runtime_seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a-c1-s0001 | 28 | 41 | 43.014 | None | None | 0.3687 | 0 | 0 | 0 | None | None | 2.15 | 0 | declined | 58.96 |
| a-c1s-s0001 | 26 | 41 | 40.627 | None | None | 0.3881 | 0 | 0 | 0 | None | None | 2.27 | 0 | declined | 61.18 |
| a-c2-s0001 | 48 | 82 | 39.754 | None | None | 0.3838 | 0 | 0 | 0 | None | None | 4.218 | 0 | declined | 151.64 |
