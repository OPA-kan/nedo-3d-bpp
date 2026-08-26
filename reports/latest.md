# CPU verification report

- Timestamp: `2026-08-26T11:35:08+00:00`
- Git SHA: `5e4aa00f23a362b2ca5d516bcf21434b787953bd`
- Python: `3.11.15 (main, Mar  3 2026, 09:26:23) [GCC 13.3.0]`
- Platform: `Linux-6.18.44-fc-v21-x86_64-with-glibc2.39`
- Processor: `x86_64`

## Unit tests

- Status: `PASS`
- Runtime: `11.067 s`
- Command: `python -m unittest discover -s tests -v`

## Simulator

- Status: `SKIPPED`

## Captured output

<details><summary>unit tests</summary>

```text
test_coordinate_round_trip_only_offsets_world_x (test_agent.GeometryContractTests.test_coordinate_round_trip_only_offsets_world_x) ... ok
test_float32_action_preserves_more_than_official_5mm_inclusion_margin (test_agent.GeometryContractTests.test_float32_action_preserves_more_than_official_5mm_inclusion_margin) ... ok
test_float32_transport_clearance_preserves_official_15mm_margin (test_agent.GeometryContractTests.test_float32_transport_clearance_preserves_official_15mm_margin) ... ok
test_floating_item_is_rejected (test_agent.GeometryContractTests.test_floating_item_is_rejected) ... ok
test_floor_direct_rest_transport_stays_at_contact_height (test_agent.GeometryContractTests.test_floor_direct_rest_transport_stays_at_contact_height) ... ok
test_lateral_clearance_guards_15mm_and_allows_vertical_contact (test_agent.GeometryContractTests.test_lateral_clearance_guards_15mm_and_allows_vertical_contact) ... ok
test_official_shelf_key_is_supported (test_agent.GeometryContractTests.test_official_shelf_key_is_supported) ... ok
test_offline_order_places_hard_items_before_soft_and_priority (test_agent.GeometryContractTests.test_offline_order_places_hard_items_before_soft_and_priority) ... ok
test_packed_dimensions_use_settled_quaternion (test_agent.GeometryContractTests.test_packed_dimensions_use_settled_quaternion) ... ok
test_pool_of_40_stays_below_online_time_limit (test_agent.GeometryContractTests.test_pool_of_40_stays_below_online_time_limit) ... ok
test_priority_item_is_routed_to_priority_container (test_agent.GeometryContractTests.test_priority_item_is_routed_to_priority_container) ... ok
test_shelf_action_target_is_lifted_above_direct_rest_threshold (test_agent.GeometryContractTests.test_shelf_action_target_is_lifted_above_direct_rest_threshold) ... ok
test_shelf_boxes_are_derived_from_simulator_dimensions (test_agent.GeometryContractTests.test_shelf_boxes_are_derived_from_simulator_dimensions) ... ok
test_shelf_top_is_support_but_mid_shelf_is_collision (test_agent.GeometryContractTests.test_shelf_top_is_support_but_mid_shelf_is_collision) ... ok
test_shelf_transport_sweep_uses_lifted_action_plus_start_height (test_agent.GeometryContractTests.test_shelf_transport_sweep_uses_lifted_action_plus_start_height) ... ok
test_soft_and_priority_items_are_not_future_support_surfaces (test_agent.GeometryContractTests.test_soft_and_priority_items_are_not_future_support_surfaces) ... ok
test_transport_clearance_uses_3d_closest_distance (test_agent.GeometryContractTests.test_transport_clearance_uses_3d_closest_distance) ... ok
test_transport_sweeps_include_official_y_then_x_legs (test_agent.GeometryContractTests.test_transport_sweeps_include_official_y_then_x_legs) ... ok
test_dry_run_places_simple_sequence_with_common_core (test_agent.OfflineOptimizationTests.test_dry_run_places_simple_sequence_with_common_core) ... ok
test_dry_run_result_uses_failure_first_lexicographic_order (test_agent.OfflineOptimizationTests.test_dry_run_result_uses_failure_first_lexicographic_order) ... ok
test_init_states_keeps_clean_container_templates (test_agent.OfflineOptimizationTests.test_init_states_keeps_clean_container_templates) ... ok
test_optimize_generates_pair_macro_candidates (test_agent.OfflineOptimizationTests.test_optimize_generates_pair_macro_candidates) ... ok
test_optimize_is_deterministic_and_returns_a_permutation (test_agent.OfflineOptimizationTests.test_optimize_is_deterministic_and_returns_a_permutation) ... ok
test_optimize_never_returns_worse_than_constructive_seed (test_agent.OfflineOptimizationTests.test_optimize_never_returns_worse_than_constructive_seed) ... ok
test_pair_macro_neighbor_keeps_internal_order_and_permutation (test_agent.OfflineOptimizationTests.test_pair_macro_neighbor_keeps_internal_order_and_permutation) ... ok
test_pair_macro_records_executable_order_layout_and_signature (test_agent.OfflineOptimizationTests.test_pair_macro_records_executable_order_layout_and_signature) ... ok
test_a_long_soft_bag_still_lies_flat (test_rule_alpha.ClassificationTest.test_a_long_soft_bag_still_lies_flat) ... ok
test_elongation_uses_max_over_median (test_rule_alpha.ClassificationTest.test_elongation_uses_max_over_median) ... ok
test_floor_policy_maximises_footprint_shelf_policy_minimises_it (test_rule_alpha.ClassificationTest.test_floor_policy_maximises_footprint_shelf_policy_minimises_it) ... ok
test_four_cargo_classes (test_rule_alpha.ClassificationTest.test_four_cargo_classes) ... ok
test_structural_policy_buys_height (test_rule_alpha.ClassificationTest.test_structural_policy_buys_height) ... ok
test_tipping_bands_follow_the_spec (test_rule_alpha.ClassificationTest.test_tipping_bands_follow_the_spec) ... ok
test_chamfer_is_a_bottom_edge_bevel_not_a_top_corner (test_rule_alpha.DerivedGeometryTest.test_chamfer_is_a_bottom_edge_bevel_not_a_top_corner) ... ok
test_floor_limit_is_independent_of_item_height (test_rule_alpha.DerivedGeometryTest.test_floor_limit_is_independent_of_item_height)
The binding corner is the bottom one, so a tall box gains nothing. ... ok
test_planes_match_the_simulator_mesh (test_rule_alpha.DerivedGeometryTest.test_planes_match_the_simulator_mesh)
The analytic cross section must equal the simulator's own planes. ... ok
test_connected_components_counts_islands (test_rule_alpha.DiagnosticsTest.test_connected_components_counts_islands) ... ok
test_interior_hole_is_separated_from_open_free_space (test_rule_alpha.DiagnosticsTest.test_interior_hole_is_separated_from_open_free_space) ... ok
test_largest_rectangle (test_rule_alpha.DiagnosticsTest.test_largest_rectangle) ... ok
test_reachable_from_boundary_finds_enclosed_cells (test_rule_alpha.DiagnosticsTest.test_reachable_from_boundary_finds_enclosed_cells) ... ok
test_every_placement_is_valid_against_the_board_before_it (test_rule_alpha.EpisodeTest.test_every_placement_is_valid_against_the_board_before_it) ... ok
test_layer_one_stays_on_floor_and_shelves (test_rule_alpha.EpisodeTest.test_layer_one_stays_on_floor_and_shelves) ... ok
test_no_plain_floor_placement_stands_on_a_small_face (test_rule_alpha.EpisodeTest.test_no_plain_floor_placement_stands_on_a_small_face) ... ok
test_something_gets_placed (test_rule_alpha.EpisodeTest.test_something_gets_placed) ... ok
test_step_log_round_trips_as_jsonl (test_rule_alpha.EpisodeTest.test_step_log_round_trips_as_jsonl) ... ok
test_summary_carries_the_required_diagnostics (test_rule_alpha.EpisodeTest.test_summary_carries_the_required_diagnostics) ... ok
test_tall_poses_always_have_a_wall_or_a_backing_item (test_rule_alpha.EpisodeTest.test_tall_poses_always_have_a_wall_or_a_backing_item) ... ok
test_lift_stays_inside_the_validator_direct_rest_window (test_rule_alpha.FloorLiftTest.test_lift_stays_inside_the_validator_direct_rest_window) ... ok
test_settled_floor_pose_would_fail_the_official_margin (test_rule_alpha.FloorLiftTest.test_settled_floor_pose_would_fail_the_official_margin)
Documents why placements are commanded above the floor. ... ok
test_reuse_bridge_loads_the_production_helpers (test_rule_alpha.ProductionPolicyUntouchedTest.test_reuse_bridge_loads_the_production_helpers) ... ok
test_rule_alpha_is_not_imported_by_the_production_agent (test_rule_alpha.ProductionPolicyUntouchedTest.test_rule_alpha_is_not_imported_by_the_production_agent) ... ok
test_plain_hard_prefers_the_normal_container_but_may_use_the_priority_one (test_rule_alpha.RoutingTest.test_plain_hard_prefers_the_normal_container_but_may_use_the_priority_one) ... ok
test_priority_and_soft_priority_prefer_the_priority_container (test_rule_alpha.RoutingTest.test_priority_and_soft_priority_prefer_the_priority_container) ... ok
test_soft_only_never_enters_a_priority_container (test_rule_alpha.RoutingTest.test_soft_only_never_enters_a_priority_container) ... ok
test_a_mere_overhang_is_not_slope_infill (test_rule_alpha.SlopeGateTest.test_a_mere_overhang_is_not_slope_infill) ... ok
test_a_real_pocket_box_is_slope_infill (test_rule_alpha.SlopeGateTest.test_a_real_pocket_box_is_slope_infill) ... ok
test_bevel_is_too_steep_to_rest_on (test_rule_alpha.SlopeGateTest.test_bevel_is_too_steep_to_rest_on) ... ok
test_no_floor_resting_box_can_reach_the_pocket (test_rule_alpha.SlopeGateTest.test_no_floor_resting_box_can_reach_the_pocket)
The negative finding the README states: the wedge is unreachable ... ok
test_missing_or_empty_evaluation_fails (test_run_checks.EvaluationStatusTests.test_missing_or_empty_evaluation_fails) ... ok
test_process_success_does_not_hide_physics_failure (test_run_checks.EvaluationStatusTests.test_process_success_does_not_hide_physics_failure) ... ok
test_valid_safe_cases_pass (test_run_checks.EvaluationStatusTests.test_valid_safe_cases_pass) ... ok

----------------------------------------------------------------------
Ran 60 tests in 10.843s

OK
```
</details>
