# bench run: `stack:reports/wedge/ppo-stack-c1-s0-tower@offline_dry_run=true,last_resort_relax=true,no_cover_other_attribute=true,priority_cargo_first=true,offline_planner=rows,plan_variants=after-hard,plan_layouts=1,priority_is_structure=true,reserve_headroom_for_soft=true,soft_headroom_volume_share=0.75,soft_headroom_slack=0.05,plan_min_support=0.0,plan_standing=true,plan_replay_clearance=0.026,plan_replay_nudge=0.0,conservative_transport=false,count_first=true,plan_score_weights=1;0.5;0.5;3,plan_normal_in_priority_container=true,plan_priority_deep_first=true,cover_veto_ignores_shelf=true,soft_headroom_per_container=true,shadow_check=true,physics_resort=true,policy_budget_seconds=4.5,pocket_guard=true,count_mode=true,count_mode_strict=true,count_mode_min_support=0.25,resort_soft_structure=true,soft_is_structure=true,soft_structure_max_top=0.7,soft_structure_floor_share=0.35,shade_veto_area=0.15,resort_shade_step=0.1,level_key=true,phase_switch=true,phase_switch_resort_first=false,phase_switch_cover=true,grid_rescue=0.05,grid_rescue_seconds=1.0,rescue_deep_first=true,rescue_seal_area=0.2,rescue_order_gate=low,band_lift=0.003,band_lift_top=false,shadow_check=false,physics_resort=false,grid_rescue=0.0,pocket_guard=false,count_mode=false,phase_switch=false,deterministic_budgets=true,future_selector=true,future_selector_diverse=true,future_selector_futures=3,future_selector_k=4`

| scene | placed | total | fill_volume | fill_shipped | fill_tolerant | com_z_ratio | priority_covered | priority_misrouted | soft_covered | shake_mean_shift | shake_topples | policy_time_max | over_budget_steps | end_reason | runtime_seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| c-hard2-s0007 | 12 | 41 | 14.041 | None | None | 0.2059 | 0 | 0 | 0 | None | None | 8.308 | 3 | declined | 27.81 |
| c-hard2-s0015 | 15 | 28 | 34.464 | None | None | 0.3911 | 0 | 0 | 0 | None | None | 7.816 | 3 | declined | 40.44 |
| c-hard2-s0023 | 53 | 106 | 31.022 | None | None | 0.39 | 0 | 0 | 0 | None | None | 39.402 | 31 | declined | 738.81 |
| c-hard2-s0031 | 56 | 122 | 33.658 | None | None | 0.4314 | 0 | 0 | 0 | None | None | 42.043 | 34 | declined | 680.17 |
| c-hard2-s0039 | 15 | 42 | 23.718 | None | None | 0.3334 | 0 | 0 | 0 | None | None | 6.544 | 6 | declined | 53.76 |
| c-hard2-s0047 | 51 | 116 | 31.095 | None | None | 0.433 | 0 | 0 | 0 | None | None | 41.611 | 28 | declined | 596.11 |
| c-hard2-s0055 | 17 | 58 | 32.176 | None | None | 0.3443 | 0 | 0 | 0 | None | None | 8.757 | 3 | declined | 39.57 |
| c-hard2-s0063 | 34 | 110 | 31.352 | None | None | 0.3712 | 0 | 0 | 0 | None | None | 22.888 | 19 | declined | 227.84 |
| c-hard2-s0071 | 27 | 120 | 20.416 | None | None | 0.3152 | 0 | 0 | 0 | None | None | 23.517 | 18 | declined | 251.65 |
| c-hard2-s0079 | 31 | 57 | 41.081 | None | None | 0.4204 | 0 | 0 | 0 | None | None | 16.138 | 11 | declined | 118.7 |
| c-hard2-s0087 | 33 | 89 | 39.569 | None | None | 0.3609 | 0 | 0 | 0 | None | None | 36.112 | 22 | declined | 461.44 |
| c-hard2-s0095 | 20 | 104 | 30.738 | None | None | 0.3628 | 0 | 0 | 0 | None | None | 13.562 | 8 | declined | 91.02 |
