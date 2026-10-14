# bench run: `stack:reports/wedge/ppo-stack-c1-s0-tower@offline_dry_run=true,last_resort_relax=true,no_cover_other_attribute=true,priority_cargo_first=true,offline_planner=rows,plan_variants=after-hard,plan_layouts=1,priority_is_structure=true,reserve_headroom_for_soft=true,soft_headroom_volume_share=0.75,soft_headroom_slack=0.05,plan_min_support=0.0,plan_standing=true,plan_replay_clearance=0.026,plan_replay_nudge=0.0,conservative_transport=false,count_first=true,plan_score_weights=1;0.5;0.5;3,plan_normal_in_priority_container=true,plan_priority_deep_first=true,cover_veto_ignores_shelf=true,soft_headroom_per_container=true,shadow_check=true,physics_resort=true,policy_budget_seconds=4.5,pocket_guard=true,count_mode=true,count_mode_strict=true,count_mode_min_support=0.25,resort_soft_structure=true,soft_is_structure=true,soft_structure_max_top=0.7,soft_structure_floor_share=0.35,shade_veto_area=0.15,resort_shade_step=0.1,level_key=true,phase_switch=true,phase_switch_resort_first=false,phase_switch_cover=true,grid_rescue=0.05,grid_rescue_seconds=1.0,rescue_deep_first=true,rescue_seal_area=0.2,rescue_order_gate=low,band_lift=0.003,band_lift_top=false,shadow_check=false,physics_resort=false,grid_rescue=0.0,pocket_guard=false,count_mode=false,phase_switch=false,deterministic_budgets=true,future_selector=true,future_selector_floor_only=true,future_selector_futures=6,future_selector_k=4`

| scene | placed | total | fill_volume | fill_shipped | fill_tolerant | com_z_ratio | priority_covered | priority_misrouted | soft_covered | shake_mean_shift | shake_topples | policy_time_max | over_budget_steps | end_reason | runtime_seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| c-hard2-s0008 | 45 | 90 | 34.121 | None | None | 0.4267 | 0 | 0 | 0 | None | None | 122.112 | 9 | declined | 679.06 |
| c-hard2-s0016 | 13 | 34 | 17.591 | None | None | 0.3018 | 0 | 0 | 0 | None | None | 12.268 | 4 | declined | 44.71 |
| c-hard2-s0024 | 15 | 30 | 33.929 | None | None | 0.3149 | 0 | 0 | 0 | None | None | 12.388 | 3 | declined | 38.1 |
| c-hard2-s0032 | 8 | 24 | 23.774 | None | None | 0.2836 | 0 | 0 | 0 | None | None | 5.946 | 1 | declined | 9.5 |
| c-hard2-s0040 | 21 | 82 | 20.16 | None | None | 0.3031 | 0 | 0 | 0 | None | None | 17.979 | 7 | declined | 82.21 |
| c-hard2-s0048 | 43 | 126 | 23.357 | None | None | 0.3072 | 0 | 0 | 0 | None | None | 201.852 | 17 | declined | 1506.59 |
| c-hard2-s0056 | 60 | 151 | 39.67 | None | None | 0.4462 | 0 | 0 | 0 | None | None | 144.412 | 11 | declined | 938.75 |
| c-hard2-s0064 | 20 | 58 | 33.458 | None | None | 0.3653 | 0 | 0 | 0 | None | None | 62.795 | 8 | declined | 307.64 |
| c-hard2-s0072 | 42 | 134 | 30.6 | None | None | 0.3235 | 0 | 0 | 0 | None | None | 106.404 | 13 | declined | 681.03 |
| c-hard2-s0080 | 58 | 212 | 24.334 | None | None | 0.3338 | 0 | 0 | 0 | None | None | 111.363 | 16 | declined | 985.23 |
| c-hard2-s0088 | 90 | 230 | 39.985 | None | None | 0.4317 | 0 | 0 | 0 | None | None | 153.798 | 23 | declined | 2393.09 |
| c-hard2-s0096 | 26 | 114 | 32.604 | None | None | 0.3695 | 0 | 0 | 0 | None | None | 111.946 | 9 | declined | 464.17 |
