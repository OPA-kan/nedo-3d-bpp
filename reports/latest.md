# CPU verification report

- Timestamp: `2026-08-01T17:42:49+09:00`
- Git SHA: `3b06959ca6bcdba3989c2ed94a3f64805af1a8ee`
- Python: `3.12.13 (main, Mar  3 2026, 15:01:35) [MSC v.1944 64 bit (AMD64)]`
- Platform: `Windows-11-10.0.26200-SP0`
- Processor: `Intel64 Family 6 Model 186 Stepping 3, GenuineIntel`

## Unit tests

- Status: `PASS`
- Runtime: `8.469 s`
- Command: `python -m unittest discover -s tests -v`

## Simulator

- Status: `SKIPPED`

## Captured output

<details><summary>unit tests (tail; full log: reports/raw/unit-tests.log)</summary>

```text
test_non_string_command_rejected (test_run_queue.PlanValidationTests.test_non_string_command_rejected) ... ok
test_valid_plan_loads (test_run_queue.PlanValidationTests.test_valid_plan_loads) ... ok
test_queue_runs_records_and_resumes (test_run_queue.QueueExecutionTests.test_queue_runs_records_and_resumes) ... ok
test_stop_on_failure_halts_queue (test_run_queue.QueueExecutionTests.test_stop_on_failure_halts_queue) ... ok
test_timeout_is_recorded (test_run_queue.QueueExecutionTests.test_timeout_is_recorded) ... ok
test_future_option_keeps_shipped_risk_and_enables_only_tiebreak (test_run_risk_ablation.ConfigureArmEnvironmentTests.test_future_option_keeps_shipped_risk_and_enables_only_tiebreak) ... ok
test_other_arms_cannot_inherit_future_option_flag (test_run_risk_ablation.ConfigureArmEnvironmentTests.test_other_arms_cannot_inherit_future_option_flag) ... ok
test_failed_processes_excluded (test_run_risk_ablation.SummarizeTests.test_failed_processes_excluded) ... ok
test_future_option_is_paired_against_shipped_base (test_run_risk_ablation.SummarizeTests.test_future_option_is_paired_against_shipped_base) ... ok
test_no_off_arm_gives_no_paired_diff (test_run_risk_ablation.SummarizeTests.test_no_off_arm_gives_no_paired_diff) ... ok
test_paired_diff_vs_off (test_run_risk_ablation.SummarizeTests.test_paired_diff_vs_off) ... ok
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

----------------------------------------------------------------------
Ran 288 tests in 7.843s

OK (skipped=3)
```
</details>
