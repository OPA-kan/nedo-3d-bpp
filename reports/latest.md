# CPU verification report

- Timestamp: `2026-08-02T08:54:33+00:00`
- Git SHA: `8ae002f3744c121ec953c9f17630a4e9e1df55b4`
- Python: `3.12.3 (main, Mar  3 2026, 12:15:18) [GCC 13.3.0]`
- Platform: `Linux-6.18.5-x86_64-with-glibc2.39`
- Processor: `x86_64`

## Unit tests

- Status: `PASS`
- Runtime: `5.809 s`
- Command: `python -m unittest discover -s tests -v`

## Simulator

- Status: `SKIPPED`

## Captured output

<details><summary>unit tests (tail; full log: reports/raw/unit-tests.log)</summary>

```text
Both models are release-specific; a settled weight would be made up. ... ok
test_the_union_bound_rule_never_goes_negative (test_safe_capacity.SurvivalWeightTests.test_the_union_bound_rule_never_goes_negative) ... ok
test_an_unknown_mode_is_refused (test_stream_variants.ModeTests.test_an_unknown_mode_is_refused) ... ok
test_index_is_reassigned_positionally (test_stream_variants.PermuteTests.test_index_is_reassigned_positionally) ... ok
test_non_dimensional_attributes_travel_with_the_item (test_stream_variants.PermuteTests.test_non_dimensional_attributes_travel_with_the_item) ... ok
test_the_multiset_is_preserved_exactly (test_stream_variants.PermuteTests.test_the_multiset_is_preserved_exactly) ... ok
test_the_same_seed_reproduces_the_same_stream (test_stream_variants.PermuteTests.test_the_same_seed_reproduces_the_same_stream) ... ok
test_the_source_list_is_not_mutated (test_stream_variants.PermuteTests.test_the_source_list_is_not_mutated) ... ok
test_length_is_preserved_but_content_may_drift (test_stream_variants.ResampleTests.test_length_is_preserved_but_content_may_drift) ... ok
test_only_whole_source_items_appear (test_stream_variants.ResampleTests.test_only_whole_source_items_appear) ... ok
test_builds_online_pool_case_without_mutating_source (test_task_b_config.TaskBConfigTests.test_builds_online_pool_case_without_mutating_source) ... ok
test_rejects_pool_larger_than_item_stream (test_task_b_config.TaskBConfigTests.test_rejects_pool_larger_than_item_stream) ... ok
test_supports_largest_planned_pool (test_task_b_config.TaskBConfigTests.test_supports_largest_planned_pool) ... ok
test_builds_compact_case_table (test_task_b_summary.TaskBSummaryTests.test_builds_compact_case_table) ... ok
test_confusion_matrix_is_labelled_as_selection_conditioned (test_task_b_summary.TaskBSummaryTests.test_confusion_matrix_is_labelled_as_selection_conditioned) ... ok
test_counts_shadow_rejection_that_physically_succeeds (test_task_b_summary.TaskBSummaryTests.test_counts_shadow_rejection_that_physically_succeeds) ... ok
test_records_coverage_and_starvation_failure_mode (test_task_b_summary.TaskBSummaryTests.test_records_coverage_and_starvation_failure_mode) ... ok
test_selected_confusion_matrix_covers_all_four_cells (test_task_b_summary.TaskBSummaryTests.test_selected_confusion_matrix_covers_all_four_cells) ... ok
test_separates_physical_labels_from_the_composite (test_task_b_summary.TaskBSummaryTests.test_separates_physical_labels_from_the_composite) ... ok
test_trace_is_partitioned_by_init_for_each_case (test_task_b_summary.TaskBSummaryTests.test_trace_is_partitioned_by_init_for_each_case) ... ok
test_compact_aggregate_is_saved_by_run_id_on_the_live_trunk (test_task_b_workflow.TaskBAggregatePersistenceTests.test_compact_aggregate_is_saved_by_run_id_on_the_live_trunk) ... ok
test_only_the_aggregate_job_gets_write_permission (test_task_b_workflow.TaskBAggregatePersistenceTests.test_only_the_aggregate_job_gets_write_permission) ... ok
test_push_conflicts_fetch_rebase_and_retry (test_task_b_workflow.TaskBAggregatePersistenceTests.test_push_conflicts_fetch_rebase_and_retry) ... ok
test_reusable_workflow_caller_grants_write_permission (test_task_b_workflow.TaskBAggregatePersistenceTests.test_reusable_workflow_caller_grants_write_permission) ... ok
test_enforce_matrix_covers_requested_eight_cases_and_three_repeats (test_visible_pool_rollout_workflow.VisiblePoolRolloutWorkflowTests.test_enforce_matrix_covers_requested_eight_cases_and_three_repeats) ... ok

----------------------------------------------------------------------
Ran 405 tests in 5.471s

OK
```
</details>
