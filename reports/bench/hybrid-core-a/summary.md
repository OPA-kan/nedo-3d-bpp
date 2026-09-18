# bench run: `stack:reports/wedge/ppo-stack-c1-s0-tower@offline_dry_run=true,last_resort_relax=true,no_cover_other_attribute=true,priority_cargo_first=true,offline_planner=rows,plan_variants=after-hard,priority_is_structure=true,reserve_headroom_for_soft=true,soft_headroom_volume_share=0.75,soft_headroom_slack=0.05,plan_min_support=0.0`

| scene | placed | total | fill_volume | fill_shipped | fill_tolerant | com_z_ratio | priority_covered | priority_misrouted | soft_covered | shake_mean_shift | shake_topples | policy_time_max | over_budget_steps | end_reason | runtime_seconds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a-c2p-s0001 | 40 | 82 | 33.344 | 21.403 | 32.695 | 0.3095 | 0 | 0 | 0 | 0.0194 | 0 | 4.86 | 0 | declined | 186.83 |
| a-c2p-s0002 | 38 | 82 | 30.588 | 18.796 | 30.588 | 0.3212 | 0 | 0 | 0 | 0.0177 | 0 | 4.424 | 0 | declined | 135.61 |
| a-c2p-s0003 | 38 | 82 | 33.095 | 22.067 | 31.796 | 0.3199 | 0 | 0 | 0 | 0.0234 | 0 | 4.528 | 0 | declined | 178.25 |
| a-c2p-s0004 | 45 | 82 | 37.178 | 25.886 | 37.178 | 0.3654 | 0 | 0 | 0 | 0.0227 | 0 | 5.954 | 0 | declined | 195.91 |
| a-c2p-s0005 | 37 | 82 | 30.717 | 18.936 | 29.165 | 0.3245 | 0 | 0 | 0 | 0.0197 | 0 | 4.519 | 0 | declined | 116.48 |
| a-c2p-s0006 | 37 | 82 | 31.812 | 21.085 | 31.163 | 0.3177 | 0 | 0 | 0 | 0.0198 | 0 | 4.264 | 0 | declined | 159.42 |
| a-c2p-s0007 | 37 | 82 | 31.609 | 20.624 | 31.609 | 0.3315 | 0 | 0 | 0 | 0.0183 | 0 | 4.434 | 0 | declined | 170.54 |
| a-c2p-s0008 | 34 | 82 | 26.276 | 15.897 | 25.626 | 0.2822 | 0 | 0 | 0 | 0.0202 | 0 | 4.527 | 0 | declined | 129.97 |
| a-c2p-s0009 | 36 | 82 | 28.141 | 17.413 | 27.491 | 0.2577 | 0 | 1 | 0 | 0.0205 | 0 | 4.548 | 0 | declined | 173.26 |
| a-c2p-s0010 | 34 | 82 | 27.635 | 16.65 | 27.635 | 0.2644 | 0 | 0 | 0 | 0.023 | 0 | 4.424 | 0 | declined | 157.66 |
| a-c2p-s0011 | 39 | 82 | 30.62 | 20.063 | 29.292 | 0.324 | 0 | 0 | 0 | 0.0204 | 0 | 4.715 | 0 | declined | 173.62 |
| a-c2p-s0012 | 38 | 82 | 31.695 | 20.139 | 30.052 | 0.3019 | 0 | 0 | 0 | 0.0386 | 0 | 5.1 | 0 | declined | 155.19 |
