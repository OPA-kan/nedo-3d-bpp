Status: Historical / superseded

This report describes an early failure mode around commit 9b300f0.
Its root-cause conclusion was superseded by later measurements:
current dominant failures are release candidates that pass transport
validation but undergo large displacement and approximately 90-degree
rotation during settle.

Do not use this report as the current implementation state.

# CPU verification report

- Timestamp: `2026-07-30T15:52:01+00:00`
- Git SHA: `d3986a96640e0091b45d6ef26cba438ecfd0c264`
- Python: `3.12.3 (main, Mar  3 2026, 12:15:18) [GCC 13.3.0]`
- Platform: `Linux-6.18.5-x86_64-with-glibc2.39`
- Processor: `x86_64`

## Unit tests

- Status: `PASS`
- Runtime: `1.451 s`
- Command: `python -m unittest discover -s tests -v`

## Simulator

- Status: `FAIL (physics validation)`
- Runtime: `257.522 s`
- Command: `python scripts/run_test.py --config-path /home/user/nedo-3d-bpp/simulator/configs/sample_config.json --module-path  --result-dir /home/user/nedo-3d-bpp/reports/raw --result-fname evaluation_results.json`

### Evaluation JSON

```json
{
  "000": {
    "evaluation": {
      "fill_score": 27.269317310610287,
      "num_placed_items": 0.5365853658536586
    },
    "message": "ok",
    "status": "success",
    "place_states": {
      "is_included": true,
      "is_valid": false,
      "is_placed_safe": false
    },
    "time_results": {
      "optimization": 149.20761195699993,
      "policy": 4.436066207000067
    }
  },
  "001": {
    "evaluation": {
      "fill_score": 18.22476656291685,
      "num_placed_items": 0.47619047619047616
    },
    "message": "ok",
    "status": "success",
    "place_states": {
      "is_included": true,
      "is_valid": false,
      "is_placed_safe": false
    },
    "time_results": {
      "optimization": 0,
      "policy": 6.652955311999904
    }
  }
}
```

## Captured output

<details><summary>unit tests</summary>

```text
test_empty_container_yields_floor_candidates (test_agent.FloorPlacementRegressionTests.test_empty_container_yields_floor_candidates) ... ok
test_floor_action_passes_official_inclusion_margin (test_agent.FloorPlacementRegressionTests.test_floor_action_passes_official_inclusion_margin) ... ok
test_policy_emits_action_for_empty_official_container (test_agent.FloorPlacementRegressionTests.test_policy_emits_action_for_empty_official_container) ... ok
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
test_transport_sampling_covers_validator_margin (test_agent.GeometryContractTests.test_transport_sampling_covers_validator_margin) ... ok
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
Ran 33 tests in 1.202s

OK
```
</details>

<details><summary>simulator</summary>

```text
argv[0]=
Perform Optimization!
transport item 3
place item 3
transport item 33
place item 33
transport item 5
place item 5
transport item 9
place item 9
transport item 11
place item 11
transport item 19
place item 19
transport item 20
place item 20
transport item 22
place item 22
transport item 23
place item 23
transport item 4
place item 4
transport item 0
place item 0
transport item 35
place item 35
transport item 39
place item 39
transport item 6
place item 6
transport item 10
place item 10
transport item 12
place item 12
transport item 18
place item 18
transport item 24
place item 24
transport item 27
place item 27
transport item 29
place item 29
transport item 32
place item 32
transport item 36
place item 36
transport item 38
collision: 38 and 33 at (np.float32(0.0), np.float32(-0.6856154), np.float32(0.18)), distance 0.00841145810527224
item 38 not packable. removed.
item 3 not inside (hit boundary plane), [ 3.06598284e-05 -5.84809825e-01 -1.53003066e+00 -1.33519017e+00
 -6.18651904e-01 -1.39606303e+00 -1.39369672e-02]
item 33 not inside (hit boundary plane), [-1.30964152e-06 -5.84813896e-01 -1.52999869e+00 -1.33518610e+00
 -6.18672821e-01 -8.07892084e-01 -6.02107916e-01]
item 5 not inside (hit boundary plane), [ 4.75944192e-06 -5.57786817e-01 -1.53000476e+00 -1.36221318e+00
 -6.36848712e-01 -1.39539301e+00 -1.46069872e-02]
item 9 not inside (hit boundary plane), [-4.83570710e-05 -5.56561541e-01 -1.52995164e+00 -1.36343846e+00
 -6.37712224e-01 -7.15928155e-01 -6.94071845e-01]
close env.
closed runner.
argv[0]=
transport item 2
place item 2
transport item 5
place item 5
transport item 6
place item 6
transport item 10
place item 10
transport item 1
place item 1
transport item 3
place item 3
transport item 4
place item 4
transport item 12
place item 12
transport item 11
place item 11
transport item 13
place item 13
transport item 14
place item 14
transport item 17
place item 17
transport item 19
place item 19
transport item 21
place item 21
transport item 0
place item 0
transport item 7
place item 7
transport item 25
place item 25
transport item 26
place item 26
transport item 8
place item 8
transport item 28
place item 28
transport item 9
collision: 9 and 10 at (np.float32(0.0), np.float32(-0.76), np.float32(0.185)), distance -0.1245822400095003
collision: 9 and 13 at (np.float32(0.0), np.float32(-0.76), np.float32(0.185)), distance -6.620928798033794e-05
item 9 not packable. removed.
item 2 not inside (hit boundary plane), [ 2.05925760e-05 -6.24446393e-01 -1.52002059e+00 -1.27555361e+00
 -5.96559352e-01 -1.45647984e+00 -1.35201648e-02]
item 5 not inside (hit boundary plane), [ 1.70860708e-05 -5.96632720e-01 -1.52001709e+00 -1.30336728e+00
 -6.15505921e-01 -1.45458127e+00 -1.54187323e-02]
item 6 not inside (hit boundary plane), [ 2.00754805e-05 -6.25717372e-01 -1.52002008e+00 -1.27428263e+00
 -5.95694062e-01 -9.79615848e-01 -4.90384152e-01]
item 10 not inside (hit boundary plane), [ 3.15775042e-06 -6.24481104e-01 -1.52000316e+00 -1.27551890e+00
 -5.96548475e-01 -5.00417155e-01 -9.69582845e-01]
item 1 not inside (hit boundary plane), [ 1.68487280e-05 -4.76741558e-02 -1.52001685e+00 -1.85232584e+00
 -9.89403938e-01 -7.77890356e-01 -6.92109644e-01]
item 11 not inside (hit boundary plane), [ 7.47644426e-06 -4.77882464e-02 -1.52000748e+00 -1.85221175e+00
 -9.89333092e-01 -1.08539560e-01 -1.36146044e+00]
close env.
closed runner.
pybullet build time: Jul 30 2026 15:27:10
pybullet build time: Jul 30 2026 15:27:10
pybullet build time: Jul 30 2026 15:27:10
```
</details>
