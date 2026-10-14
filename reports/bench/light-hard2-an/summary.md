# bench run: `stack:reports/wedge/ppo-stack-c1-s0-tower@offline_dry_run=true,last_resort_relax=true,no_cover_other_attribute=true,priority_cargo_first=true,offline_planner=rows,plan_variants=after-hard,plan_layouts=1,priority_is_structure=true,reserve_headroom_for_soft=true,soft_headroom_volume_share=0.75,soft_headroom_slack=0.05,plan_min_support=0.0,plan_standing=true,plan_replay_clearance=0.026,plan_replay_nudge=0.0,conservative_transport=false,count_first=true,plan_score_weights=1;0.5;0.5;3,plan_normal_in_priority_container=true,plan_priority_deep_first=true,cover_veto_ignores_shelf=true,soft_headroom_per_container=true,shadow_check=true,physics_resort=true,policy_budget_seconds=4.5,pocket_guard=true,count_mode=true,count_mode_strict=true,count_mode_min_support=0.25,resort_soft_structure=true,soft_is_structure=true,soft_structure_max_top=0.7,soft_structure_floor_share=0.35,shade_veto_area=0.15,resort_shade_step=0.1,level_key=true,phase_switch=true,phase_switch_resort_first=false,phase_switch_cover=true,grid_rescue=0.05,grid_rescue_seconds=1.0,rescue_deep_first=true,rescue_seal_area=0.2,rescue_order_gate=low,band_lift=0.003,band_lift_top=false,shadow_check=false,physics_resort=false,grid_rescue=0.0,pocket_guard=false,count_mode=false,phase_switch=false,deterministic_budgets=true`

| scene | placed | total | fill_volume | fill_shipped | fill_tolerant | com_z_ratio | priority_covered | priority_misrouted | soft_covered | shake_mean_shift | shake_topples | policy_time_max | over_budget_steps | end_reason | runtime_seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| c-hard2-s0003 | 20 | 40 | 37.156 | None | None | 0.4341 | 0 | 0 | 0 | None | None | 0.359 | 0 | declined | 5.19 |
| c-hard2-s0006 | 16 | 66 | 13.925 | None | None | 0.2408 | 0 | 0 | 0 | None | None | 0.196 | 0 | declined | 2.37 |
| c-hard2-s0009 | 47 | 104 | 28.397 | None | None | 0.3362 | 0 | 0 | 0 | None | None | 2.025 | 0 | declined | 23.13 |
| c-hard2-s0012 | 32 | 60 | 33.852 | None | None | 0.4183 | 0 | 0 | 0 | None | None | 1.666 | 0 | declined | 12.74 |
| c-hard2-s0015 | 14 | 28 | 33.226 | None | None | 0.3876 | 0 | 0 | 0 | None | None | 0.504 | 0 | declined | 3.13 |
| c-hard2-s0018 | 39 | 74 | 39.447 | None | None | 0.4044 | 0 | 0 | 0 | None | None | 0.946 | 0 | declined | 16.18 |
| c-hard2-s0021 | 37 | 100 | 24.162 | None | None | 0.3923 | 0 | 0 | 0 | None | None | 1.795 | 0 | declined | 15.72 |
| c-hard2-s0024 | 15 | 30 | 33.929 | None | None | 0.3149 | 0 | 0 | 0 | None | None | 0.784 | 0 | declined | 4.09 |
| c-hard2-s0027 | 21 | 56 | 25.711 | None | None | 0.3358 | 0 | 0 | 0 | None | None | 1.034 | 0 | declined | 7.29 |
| c-hard2-s0030 | 58 | 156 | 27.361 | None | None | 0.3244 | 0 | 0 | 0 | None | None | 2.841 | 0 | declined | 31.56 |
| c-hard2-s0033 | 35 | 84 | 30.57 | None | None | 0.3888 | 0 | 0 | 0 | None | None | 1.057 | 0 | declined | 17.4 |
| c-hard2-s0036 | 60 | 164 | 24.903 | None | None | 0.2729 | 0 | 0 | 0 | None | None | 2.807 | 0 | declined | 40.37 |
| c-hard2-s0039 | 15 | 42 | 23.718 | None | None | 0.3773 | 0 | 0 | 0 | None | None | 0.587 | 0 | declined | 2.84 |
| c-hard2-s0042 | 50 | 108 | 29.376 | None | None | 0.3728 | 0 | 0 | 0 | None | None | 2.693 | 0 | declined | 19.58 |
| c-hard2-s0045 | 71 | 104 | 40.79 | None | None | 0.45 | 0 | 0 | 0 | None | None | 1.676 | 0 | declined | 41.67 |
| c-hard2-s0048 | 39 | 126 | 20.418 | None | None | 0.3073 | 0 | 0 | 0 | None | None | 2.683 | 0 | declined | 12.84 |
| c-hard2-s0051 | 23 | 46 | 44.176 | None | None | 0.4248 | 0 | 0 | 0 | None | None | 0.691 | 0 | declined | 7.06 |
| c-hard2-s0054 | 44 | 116 | 31.637 | None | None | 0.4079 | 0 | 0 | 0 | None | None | 1.459 | 0 | declined | 20.32 |
| c-hard2-s0057 | 36 | 82 | 33.924 | None | None | 0.3792 | 0 | 0 | 0 | None | None | 1.23 | 0 | declined | 13.07 |
| c-hard2-s0060 | 61 | 190 | 28.602 | None | None | 0.3286 | 0 | 9 | 0 | None | None | 3.284 | 0 | declined | 29.02 |
| c-hard2-s0063 | 35 | 110 | 31.939 | None | None | 0.343 | 0 | 0 | 0 | None | None | 2.278 | 0 | declined | 11.28 |
| c-hard2-s0066 | 27 | 71 | 32.373 | None | None | 0.348 | 0 | 0 | 0 | None | None | 1.293 | 0 | declined | 9.89 |
| c-hard2-s0069 | 12 | 76 | 12.037 | None | None | 0.1767 | 0 | 0 | 0 | None | None | 0.125 | 0 | declined | 1.05 |
| c-hard2-s0072 | 38 | 134 | 28.154 | None | None | 0.2932 | 0 | 0 | 0 | None | None | 1.096 | 0 | declined | 14.67 |
| c-hard2-s0075 | 49 | 216 | 19.34 | None | None | 0.2913 | 0 | 0 | 0 | None | None | 4.205 | 0 | declined | 23.19 |
| c-hard2-s0078 | 41 | 96 | 37.333 | None | None | 0.4319 | 0 | 0 | 0 | None | None | 1.716 | 0 | declined | 18.62 |
| c-hard2-s0081 | 50 | 122 | 40.725 | None | None | 0.4363 | 0 | 0 | 0 | None | None | 1.645 | 0 | declined | 27.6 |
| c-hard2-s0084 | 30 | 120 | 24.196 | None | None | 0.2985 | 0 | 0 | 0 | None | None | 1.538 | 0 | declined | 14.11 |
| c-hard2-s0087 | 34 | 89 | 40.579 | None | None | 0.3867 | 0 | 0 | 0 | None | None | 1.093 | 0 | declined | 10.89 |
| c-hard2-s0090 | 33 | 124 | 48.675 | None | None | 0.4253 | 0 | 0 | 0 | None | None | 1.037 | 0 | declined | 8.45 |
| c-hard2-s0093 | 14 | 210 | 10.422 | None | None | 0.2414 | 0 | 0 | 0 | None | None | 0.216 | 0 | declined | 1.71 |
| c-hard2-s0096 | 26 | 114 | 32.604 | None | None | 0.3695 | 0 | 0 | 0 | None | None | 1.775 | 0 | declined | 9.51 |
