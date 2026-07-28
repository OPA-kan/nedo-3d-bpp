# CPU verification report

- Timestamp: `2026-07-28T09:46:24+09:00`
- Git SHA: `7b2b4853df393c3d715f578a48b6abc0a55cf660`
- Python: `3.12.13 (main, Mar  3 2026, 15:01:35) [MSC v.1944 64 bit (AMD64)]`
- Platform: `Windows-11-10.0.26200-SP0`
- Processor: `Intel64 Family 6 Model 186 Stepping 3, GenuineIntel`

## Unit tests

- Status: `PASS`
- Runtime: `6.731 s`
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
test_missing_or_empty_evaluation_fails (test_run_checks.EvaluationStatusTests.test_missing_or_empty_evaluation_fails) ... ok
test_process_success_does_not_hide_physics_failure (test_run_checks.EvaluationStatusTests.test_process_success_does_not_hide_physics_failure) ... ok
test_valid_safe_cases_pass (test_run_checks.EvaluationStatusTests.test_valid_safe_cases_pass) ... ok

----------------------------------------------------------------------
Ran 29 tests in 6.003s

OK
```
</details>
