# CPU verification report

- Timestamp: `2026-08-23T17:14:58+00:00`
- Git SHA: `22d9e561c5467121241fe46da377159a9e50bf01`
- Python: `3.12.3 (main, Mar  3 2026, 12:15:18) [GCC 13.3.0]`
- Platform: `Linux-6.18.44-fc-v21-x86_64-with-glibc2.39`
- Processor: `x86_64`

## Unit tests

- Status: `PASS`
- Runtime: `58.971 s`
- Command: `python -m unittest discover -s tests -v`

## Simulator

- Status: `SKIPPED`

## Captured output

<details><summary>unit tests (tail; full log: reports/raw/unit-tests.log)</summary>

```text
test_incumbent_best_never_swaps (test_visible_tree_search.DecisionRuleTests.test_incumbent_best_never_swaps) ... ok
test_missing_scores_stand (test_visible_tree_search.DecisionRuleTests.test_missing_scores_stand) ... ok
test_within_tie_band_stands (test_visible_tree_search.DecisionRuleTests.test_within_tie_band_stands) ... ok
test_empty_board_drop_height_is_the_floor (test_visible_tree_search.HeightmapTests.test_empty_board_drop_height_is_the_floor) ... ok
test_footprint_outside_the_interior_returns_none (test_visible_tree_search.HeightmapTests.test_footprint_outside_the_interior_returns_none) ... ok
test_packed_cargo_is_part_of_the_surface (test_visible_tree_search.HeightmapTests.test_packed_cargo_is_part_of_the_surface) ... ok
test_stamp_raises_drop_height_over_the_footprint_only (test_visible_tree_search.HeightmapTests.test_stamp_raises_drop_height_over_the_footprint_only) ... ok
test_default_mode_is_off_and_constants_are_preregistered (test_visible_tree_search.KnobAndConstantsTests.test_default_mode_is_off_and_constants_are_preregistered) ... ok
test_expired_deadline_returns_incumbent_with_budget_exhausted (test_visible_tree_search.SearchTests.test_expired_deadline_returns_incumbent_with_budget_exhausted) ... ok
test_item_receptivity_is_capped (test_visible_tree_search.SearchTests.test_item_receptivity_is_capped) ... ok
test_roots_deduplicate_by_action (test_visible_tree_search.SearchTests.test_roots_deduplicate_by_action) ... ok
test_single_root_expands_and_never_proposes_itself (test_visible_tree_search.SearchTests.test_single_root_expands_and_never_proposes_itself) ... ok
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
Ran 1360 tests in 55.324s

OK (skipped=18)
```
</details>
