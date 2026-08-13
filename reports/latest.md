# CPU verification report

- Timestamp: `2026-08-13T16:20:27+09:00`
- Git SHA: `e15447ac692f10d967ed3f2c2e29db22b625f59e`
- Python: `3.12.13 (main, Mar  3 2026, 15:01:35) [MSC v.1944 64 bit (AMD64)]`
- Platform: `Windows-11-10.0.26200-SP0`
- Processor: `Intel64 Family 6 Model 186 Stepping 3, GenuineIntel`

## Unit tests

- Status: `PASS`
- Runtime: `88.153 s`
- Command: `python -m unittest discover -s tests -v`

## Simulator

- Status: `SKIPPED`

## Captured output

<details><summary>unit tests (tail; full log: reports/raw/unit-tests.log)</summary>

```text
Only the CENTRE shelf is flag-controlled; conflating the two is ... ok
test_outside_the_band_the_official_drop_height_returns (test_transport_plane_contract.TransportPlaneContractTests.test_outside_the_band_the_official_drop_height_returns)
Beyond 50 mm above the plane the 80 mm lift applies again, which ... ok
test_resting_planes_match_the_small_shelf_faces (test_transport_plane_contract.TransportPlaneContractTests.test_resting_planes_match_the_small_shelf_faces)
The official reason for the planes: the small shelf always ... ok
test_shelf_plane_suppresses_the_lift_without_a_shelf (test_transport_plane_contract.TransportPlaneContractTests.test_shelf_plane_suppresses_the_lift_without_a_shelf)
A bottom just above the shelf plane is a direct approach even ... ok
test_the_floor_plane_is_also_unconditional (test_transport_plane_contract.TransportPlaneContractTests.test_the_floor_plane_is_also_unconditional) ... ok
test_the_same_pose_behaves_identically_with_a_shelf (test_transport_plane_contract.TransportPlaneContractTests.test_the_same_pose_behaves_identically_with_a_shelf) ... ok
test_transport_samples_use_the_same_plane_logic (test_transport_plane_contract.TransportPlaneContractTests.test_transport_samples_use_the_same_plane_logic)
Both transport builders must agree; the sampled path is the one ... ok
test_enforce_matrix_covers_requested_eight_cases_and_three_repeats (test_visible_pool_rollout_workflow.VisiblePoolRolloutWorkflowTests.test_enforce_matrix_covers_requested_eight_cases_and_three_repeats) ... ok
test_a_shelf_container_has_no_deep_floor_zone (test_zone_order.ZoneClassificationTests.test_a_shelf_container_has_no_deep_floor_zone) ... ok
test_a_shelfless_container_has_only_deep_and_centre (test_zone_order.ZoneClassificationTests.test_a_shelfless_container_has_only_deep_and_centre) ... ok
test_a_tall_floor_pose_by_the_door_is_not_shelf_top (test_zone_order.ZoneClassificationTests.test_a_tall_floor_pose_by_the_door_is_not_shelf_top)
The defect this exists for. Classifying on the pose's TOP made a tall ... ok
test_resting_on_the_shelf_is_shelf_top (test_zone_order.ZoneClassificationTests.test_resting_on_the_shelf_is_shelf_top) ... ok
test_under_the_shelf_is_its_own_zone (test_zone_order.ZoneClassificationTests.test_under_the_shelf_is_its_own_zone) ... ok
test_an_unknown_mode_is_refused_at_import (test_zone_order.ZoneScoreTests.test_an_unknown_mode_is_refused_at_import) ... ok
test_doctrine_ranks_the_shelf_top_above_under_the_shelf (test_zone_order.ZoneScoreTests.test_doctrine_ranks_the_shelf_top_above_under_the_shelf) ... ok
test_off_by_default_leaves_the_score_untouched (test_zone_order.ZoneScoreTests.test_off_by_default_leaves_the_score_untouched) ... ok
test_reversed_inverts_it (test_zone_order.ZoneScoreTests.test_reversed_inverts_it) ... ok
test_the_bonus_span_is_three_units (test_zone_order.ZoneScoreTests.test_the_bonus_span_is_three_units) ... ok
test_the_span_must_clear_the_support_term (test_zone_order.ZoneScoreTests.test_the_span_must_clear_the_support_term)
Why the default bonus is 1.0 and not 0.5. ... ok

----------------------------------------------------------------------
Ran 843 tests in 86.173s

OK (skipped=5)
```
</details>
