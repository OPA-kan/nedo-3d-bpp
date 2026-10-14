# bench run: `stack:reports/wedge/ppo-stack-c1-s0-tower@offline_dry_run=true,last_resort_relax=true,no_cover_other_attribute=true,priority_cargo_first=true,offline_planner=rows,plan_variants=after-hard,plan_layouts=1,priority_is_structure=true,reserve_headroom_for_soft=true,soft_headroom_volume_share=0.75,soft_headroom_slack=0.05,plan_min_support=0.0,plan_standing=true,plan_replay_clearance=0.026,plan_replay_nudge=0.0,conservative_transport=false,count_first=true,plan_score_weights=1;0.5;0.5;3,plan_normal_in_priority_container=true,plan_priority_deep_first=true,cover_veto_ignores_shelf=true,soft_headroom_per_container=true,shadow_check=true,physics_resort=true,policy_budget_seconds=4.5,pocket_guard=true,count_mode=true,count_mode_strict=true,count_mode_min_support=0.25,resort_soft_structure=true,soft_is_structure=true,soft_structure_max_top=0.7,soft_structure_floor_share=0.35,shade_veto_area=0.15,resort_shade_step=0.1,level_key=true,phase_switch=true,phase_switch_resort_first=false,phase_switch_cover=true,grid_rescue=0.05,grid_rescue_seconds=1.0,rescue_deep_first=true,rescue_seal_area=0.2,rescue_order_gate=low,band_lift=0.003,band_lift_top=false,shadow_check=false,physics_resort=false,grid_rescue=0.0,pocket_guard=false,count_mode=false,phase_switch=false,deterministic_budgets=true`

| scene | placed | total | fill_volume | fill_shipped | fill_tolerant | com_z_ratio | priority_covered | priority_misrouted | soft_covered | shake_mean_shift | shake_topples | policy_time_max | over_budget_steps | end_reason | runtime_seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| c-c1-s0001 | 19 | 41 | 26.552 | None | None | 0.3099 | 0 | 0 | 0 | None | None | 0.434 | 0 | declined | 3.1 |
| c-c2-s0001 | 39 | 82 | 28.951 | None | None | 0.3538 | 0 | 0 | 0 | None | None | 0.904 | 0 | declined | 10.56 |
| c-c1-s0002 | 17 | 41 | 29.761 | None | None | 0.3807 | 0 | 0 | 0 | None | None | 0.359 | 0 | declined | 2.66 |
| c-c2-s0002 | 38 | 82 | 31.156 | None | None | 0.3232 | 0 | 0 | 0 | None | None | 0.925 | 0 | declined | 8.86 |
| c-c1-s0003 | 15 | 41 | 26.646 | None | None | 0.3154 | 0 | 0 | 0 | None | None | 0.407 | 0 | declined | 2.15 |
| c-c2-s0003 | 30 | 82 | 26.732 | None | None | 0.3564 | 0 | 0 | 0 | None | None | 0.611 | 0 | declined | 6.4 |
| c-c1-s0004 | 20 | 41 | 28.483 | None | None | 0.3272 | 0 | 0 | 0 | None | None | 0.454 | 0 | declined | 3.35 |
| c-c2-s0004 | 36 | 82 | 26.903 | None | None | 0.3584 | 0 | 0 | 0 | None | None | 1.2 | 0 | declined | 10.42 |
| c-c1-s0005 | 21 | 41 | 31.173 | None | None | 0.3533 | 0 | 0 | 0 | None | None | 0.548 | 0 | declined | 3.78 |
| c-c2-s0005 | 41 | 82 | 29.69 | None | None | 0.3427 | 0 | 0 | 0 | None | None | 1.041 | 0 | declined | 10.63 |
| c-c1-s0006 | 15 | 41 | 22.414 | None | None | 0.2762 | 0 | 0 | 0 | None | None | 0.403 | 0 | declined | 2.17 |
| c-c2-s0006 | 32 | 82 | 25.619 | None | None | 0.3458 | 0 | 0 | 0 | None | None | 0.94 | 0 | declined | 7.8 |
| c-c1-s0007 | 18 | 41 | 30.585 | None | None | 0.3845 | 0 | 0 | 0 | None | None | 0.47 | 0 | declined | 3.25 |
| c-c2-s0007 | 35 | 82 | 28.612 | None | None | 0.3307 | 0 | 0 | 0 | None | None | 1.082 | 0 | declined | 9.28 |
| c-c1-s0008 | 22 | 41 | 33.639 | None | None | 0.3777 | 0 | 0 | 0 | None | None | 0.497 | 0 | declined | 4.42 |
| c-c2-s0008 | 47 | 82 | 36.145 | None | None | 0.3778 | 0 | 0 | 0 | None | None | 0.974 | 0 | declined | 15.18 |
| c-c1-s0009 | 19 | 41 | 31.931 | None | None | 0.3169 | 0 | 0 | 0 | None | None | 0.669 | 0 | declined | 3.6 |
| c-c2-s0009 | 33 | 82 | 28.482 | None | None | 0.3341 | 0 | 0 | 0 | None | None | 0.779 | 0 | declined | 8.93 |
| c-c1-s0010 | 19 | 41 | 32.688 | None | None | 0.3615 | 0 | 0 | 0 | None | None | 0.528 | 0 | declined | 3.18 |
| c-c2-s0010 | 33 | 82 | 27.78 | None | None | 0.3258 | 0 | 0 | 0 | None | None | 1.079 | 0 | declined | 9.75 |
| c-c1-s0011 | 14 | 41 | 23.284 | None | None | 0.3043 | 0 | 0 | 0 | None | None | 0.538 | 0 | declined | 2.39 |
| c-c2-s0011 | 35 | 82 | 25.214 | None | None | 0.3495 | 0 | 0 | 0 | None | None | 1.115 | 0 | declined | 9.24 |
| c-c1-s0012 | 21 | 41 | 34.384 | None | None | 0.3734 | 0 | 0 | 0 | None | None | 0.372 | 0 | declined | 3.28 |
| c-c2-s0012 | 50 | 82 | 38.971 | None | None | 0.3832 | 0 | 0 | 0 | None | None | 1.034 | 0 | declined | 18.39 |
