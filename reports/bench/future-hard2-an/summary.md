# bench run: `stack:reports/wedge/ppo-stack-c1-s0-tower@offline_dry_run=true,last_resort_relax=true,no_cover_other_attribute=true,priority_cargo_first=true,offline_planner=rows,plan_variants=after-hard,plan_layouts=1,priority_is_structure=true,reserve_headroom_for_soft=true,soft_headroom_volume_share=0.75,soft_headroom_slack=0.05,plan_min_support=0.0,plan_standing=true,plan_replay_clearance=0.026,plan_replay_nudge=0.0,conservative_transport=false,count_first=true,plan_score_weights=1;0.5;0.5;3,plan_normal_in_priority_container=true,plan_priority_deep_first=true,cover_veto_ignores_shelf=true,soft_headroom_per_container=true,shadow_check=true,physics_resort=true,policy_budget_seconds=4.5,pocket_guard=true,count_mode=true,count_mode_strict=true,count_mode_min_support=0.25,resort_soft_structure=true,soft_is_structure=true,soft_structure_max_top=0.7,soft_structure_floor_share=0.35,shade_veto_area=0.15,resort_shade_step=0.1,level_key=true,phase_switch=true,phase_switch_resort_first=false,phase_switch_cover=true,grid_rescue=0.05,grid_rescue_seconds=1.0,rescue_deep_first=true,rescue_seal_area=0.2,rescue_order_gate=low,band_lift=0.003,band_lift_top=false,shadow_check=false,physics_resort=false,grid_rescue=0.0,pocket_guard=false,count_mode=false,phase_switch=false,deterministic_budgets=true,future_selector=true`

| scene | placed | total | fill_volume | fill_shipped | fill_tolerant | com_z_ratio | priority_covered | priority_misrouted | soft_covered | shake_mean_shift | shake_topples | policy_time_max | over_budget_steps | end_reason | runtime_seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| c-hard2-s0004 | 8 | 42 | 10.429 | None | None | 0.222 | 0 | 0 | 0 | None | None | 1.585 | 0 | declined | 5.05 |
| c-hard2-s0012 | 30 | 60 | 32.488 | None | None | 0.4014 | 0 | 0 | 0 | None | None | 37.277 | 21 | declined | 473.4 |
| c-hard2-s0020 | 27 | 86 | 20.343 | None | None | 0.255 | 0 | 0 | 0 | None | None | 44.591 | 16 | declined | 482.44 |
| c-hard2-s0028 | 20 | 26 | 45.696 | None | None | 0.4508 | 0 | 0 | 0 | None | None | 9.993 | 7 | declined | 71.19 |
| c-hard2-s0036 | 60 | 164 | 24.903 | None | None | 0.2712 | 0 | 0 | 0 | None | None | 53.458 | 19 | declined | 674.35 |
| c-hard2-s0044 | 12 | 70 | 13.168 | None | None | 0.2078 | 0 | 0 | 0 | None | None | 6.252 | 2 | declined | 21.27 |
| c-hard2-s0052 | 26 | 82 | 33.741 | None | None | 0.3676 | 0 | 0 | 0 | None | None | 33.568 | 17 | declined | 328.67 |
| c-hard2-s0060 | 65 | 190 | 30.483 | None | None | 0.3502 | 1 | 8 | 0 | None | None | 73.886 | 42 | declined | 1530.69 |
| c-hard2-s0068 | 39 | 159 | 14.702 | None | None | 0.2563 | 0 | 0 | 0 | None | None | 25.833 | 15 | declined | 192.53 |
| c-hard2-s0076 | 15 | 42 | 31.732 | None | None | 0.3228 | 0 | 0 | 0 | None | None | 8.2 | 3 | declined | 30.39 |
| c-hard2-s0084 | 28 | 120 | 22.313 | None | None | 0.2805 | 0 | 0 | 0 | None | None | 27.883 | 8 | declined | 187.72 |
| c-hard2-s0092 | 27 | 152 | 28.738 | None | None | 0.291 | 0 | 0 | 0 | None | None | 20.587 | 6 | declined | 112.03 |
