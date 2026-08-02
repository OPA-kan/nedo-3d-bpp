# CPU verification report

- Timestamp: `2026-08-02T04:54:58+00:00`
- Git SHA: `039a43d04b3368ca54c4f3553d5ea9174ed73d21`
- Python: `3.12.3 (main, Mar  3 2026, 12:15:18) [GCC 13.3.0]`
- Platform: `Linux-6.18.5-x86_64-with-glibc2.39`
- Processor: `x86_64`

## Unit tests

- Status: `PASS`
- Runtime: `10.586 s`
- Command: `python -m unittest discover -s tests -v`

## Simulator

- Status: `SKIPPED`

## Captured output

<details><summary>unit tests (tail; full log: reports/raw/unit-tests.log)</summary>

```text
test_arm_environment_preserves_legacy_and_enables_bounded (test_task_a_rollout.TaskARolloutTests.test_arm_environment_preserves_legacy_and_enables_bounded) ... ok
test_base_arm_does_not_inherit_the_adopted_default (test_task_a_rollout.TaskARolloutTests.test_base_arm_does_not_inherit_the_adopted_default)
The regression this guards: once bounded128 became the shipped ... ok
test_builder_forces_task_a_contract_without_mutating_source (test_task_a_rollout.TaskARolloutTests.test_builder_forces_task_a_contract_without_mutating_source) ... ok
test_default_arm_measures_the_shipped_submission (test_task_a_rollout.TaskARolloutTests.test_default_arm_measures_the_shipped_submission) ... ok
test_summary_reads_isolated_rows (test_task_a_rollout.TaskARolloutTests.test_summary_reads_isolated_rows) ... ok
test_unknown_arm_is_rejected (test_task_a_rollout.TaskARolloutTests.test_unknown_arm_is_rejected) ... ok
test_matrix_contrasts_the_shipped_path_against_legacy (test_task_a_rollout_workflow.TaskARolloutWorkflowTests.test_matrix_contrasts_the_shipped_path_against_legacy)
Post-ADR-002 the treatment arm is the shipped default, so the ... ok
test_workflow_freezes_adoption_matrix_and_budgets (test_task_a_rollout_workflow.TaskARolloutWorkflowTests.test_workflow_freezes_adoption_matrix_and_budgets) ... ok
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
Ran 402 tests in 8.094s

OK
```
</details>
