# bench run: `stack:reports/wedge/ppo-stack-c1-s0-tower@offline_dry_run=true,last_resort_relax=true,no_cover_other_attribute=true,priority_cargo_first=true,offline_planner=rows,plan_variants=after-hard,priority_is_structure=true,reserve_headroom_for_soft=true,soft_headroom_volume_share=0.75,soft_headroom_slack=0.05,plan_min_support=0.0`

| scene | placed | total | fill_volume | fill_shipped | fill_tolerant | com_z_ratio | priority_covered | priority_misrouted | soft_covered | shake_mean_shift | shake_topples | policy_time_max | over_budget_steps | end_reason | runtime_seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a-c1-s0001 | 27 | 41 | 42.157 | None | None | 0.3702 | 0 | 0 | 0 | None | None | 1.447 | 0 | declined | 33.47 |
| a-c1s-s0001 | 27 | 41 | 43.219 | None | None | 0.4001 | 0 | 0 | 0 | None | None | 2.403 | 0 | declined | 52.94 |
| a-c2-s0001 | 54 | 82 | 43.836 | None | None | 0.3633 | 0 | 0 | 0 | None | None | 2.28 | 0 | declined | 112.49 |
| a-c2p-s0001 | 39 | 82 | 31.937 | None | None | 0.3119 | 0 | 0 | 0 | None | None | 3.072 | 0 | declined | 89.05 |
| a-c1-s0002 | 24 | 41 | 40.694 | None | None | 0.3244 | 0 | 0 | 0 | None | None | 0.955 | 0 | declined | 30.83 |
| a-c1s-s0002 | 25 | 41 | 47.488 | None | None | 0.4034 | 0 | 0 | 0 | None | None | 1.712 | 0 | declined | 44.01 |
| a-c2-s0002 | 52 | 82 | 43.469 | None | None | 0.3618 | 0 | 0 | 0 | None | None | 2.408 | 0 | declined | 99.79 |
| a-c2p-s0002 | 39 | 82 | 31.996 | None | None | 0.345 | 0 | 0 | 0 | None | None | 2.307 | 0 | declined | 62.49 |
| a-c1-s0003 | 26 | 41 | 44.799 | None | None | 0.3713 | 0 | 0 | 0 | None | None | 1.148 | 0 | declined | 24.84 |
| a-c1s-s0003 | 22 | 41 | 40.816 | None | None | 0.3653 | 0 | 0 | 0 | None | None | 1.114 | 0 | declined | 28.29 |
| a-c2-s0003 | 46 | 82 | 39.367 | None | None | 0.323 | 0 | 0 | 0 | None | None | 2.366 | 0 | declined | 101.96 |
| a-c2p-s0003 | 37 | 82 | 31.688 | None | None | 0.2992 | 0 | 0 | 0 | None | None | 1.996 | 0 | declined | 94.91 |
| a-c1-s0004 | 25 | 41 | 39.941 | None | None | 0.3417 | 0 | 0 | 0 | None | None | 1.382 | 0 | declined | 30.38 |
| a-c1s-s0004 | 23 | 41 | 38.359 | None | None | 0.3722 | 0 | 0 | 0 | None | None | 1.899 | 0 | declined | 52.66 |
| a-c2-s0004 | 51 | 82 | 40.15 | None | None | 0.355 | 0 | 0 | 0 | None | None | 2.901 | 0 | declined | 127.22 |
| a-c2p-s0004 | 38 | 82 | 31.837 | None | None | 0.3359 | 0 | 0 | 0 | None | None | 3.173 | 0 | declined | 88.29 |
| a-c1-s0005 | 29 | 41 | 45.768 | None | None | 0.4161 | 0 | 0 | 0 | None | None | 1.52 | 0 | declined | 47.86 |
| a-c1s-s0005 | 25 | 41 | 37.659 | None | None | 0.3659 | 0 | 0 | 0 | None | None | 1.602 | 0 | declined | 32.24 |
| a-c2-s0005 | 49 | 82 | 40.064 | None | None | 0.3395 | 0 | 0 | 0 | None | None | 2.966 | 0 | declined | 95.71 |
| a-c2p-s0005 | 37 | 82 | 30.717 | None | None | 0.3261 | 0 | 0 | 0 | None | None | 2.875 | 0 | declined | 58.82 |
| a-c1-s0006 | 28 | 41 | 47.8 | None | None | 0.404 | 0 | 0 | 0 | None | None | 1.317 | 0 | declined | 29.9 |
| a-c1s-s0006 | 21 | 41 | 39.033 | None | None | 0.3456 | 0 | 0 | 0 | None | None | 0.984 | 0 | declined | 32.37 |
| a-c2-s0006 | 49 | 82 | 42.907 | None | None | 0.3576 | 0 | 0 | 0 | None | None | 1.834 | 0 | declined | 105.57 |
| a-c2p-s0006 | 37 | 82 | 31.812 | None | None | 0.3214 | 0 | 0 | 0 | None | None | 2.871 | 0 | declined | 82.08 |
| a-c1-s0007 | 23 | 41 | 39.367 | None | None | 0.3224 | 0 | 0 | 0 | None | None | 0.987 | 0 | declined | 30.34 |
| a-c1s-s0007 | 21 | 41 | 38.347 | None | None | 0.3394 | 0 | 0 | 0 | None | None | 1.26 | 0 | declined | 33.01 |
| a-c2-s0007 | 45 | 82 | 40.168 | None | None | 0.3424 | 0 | 0 | 0 | None | None | 2.512 | 0 | declined | 102.77 |
