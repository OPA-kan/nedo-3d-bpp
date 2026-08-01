# CPU verification report

- Timestamp: `2026-08-01T21:06:38+00:00`
- Git SHA: `ab423670dd28fb9617f5c6aba65b62da936d8f74`
- Python: `3.12.3 (main, Mar  3 2026, 12:15:18) [GCC 13.3.0]`
- Platform: `Linux-6.18.5-x86_64-with-glibc2.39`
- Processor: `x86_64`

## Unit tests

- Status: `PASS`
- Runtime: `5.161 s`
- Command: `python -m unittest discover -s tests -v`

## Simulator

- Status: `SKIPPED`

## Captured output

<details><summary>unit tests (tail; full log: reports/raw/unit-tests.log)</summary>

```text
test_rollout_enforce_is_the_shipped_baseline_plus_selection (test_run_risk_ablation.ArmEnvironmentTests.test_rollout_enforce_is_the_shipped_baseline_plus_selection) ... ok
test_rollout_shadow_is_the_shipped_baseline_plus_telemetry (test_run_risk_ablation.ArmEnvironmentTests.test_rollout_shadow_is_the_shipped_baseline_plus_telemetry) ... ok
test_counts_rescue_and_protocol_fallback_separately (test_run_risk_ablation.PolicyTraceSummaryTests.test_counts_rescue_and_protocol_fallback_separately) ... ok
test_rollout_shadow_summary_counts_discrimination_and_cost (test_run_risk_ablation.PolicyTraceSummaryTests.test_rollout_shadow_summary_counts_discrimination_and_cost) ... ok
test_cross_step_telemetry_is_preserved_in_compact_summary (test_run_risk_ablation.SummarizeTests.test_cross_step_telemetry_is_preserved_in_compact_summary) ... ok
test_development_and_full_suite_totals_are_separate (test_run_risk_ablation.SummarizeTests.test_development_and_full_suite_totals_are_separate) ... ok
test_failed_processes_excluded (test_run_risk_ablation.SummarizeTests.test_failed_processes_excluded) ... ok
test_no_off_arm_gives_no_paired_diff (test_run_risk_ablation.SummarizeTests.test_no_off_arm_gives_no_paired_diff) ... ok
test_paired_diff_vs_off (test_run_risk_ablation.SummarizeTests.test_paired_diff_vs_off) ... ok
test_rescue_is_paired_against_shipped_base (test_run_risk_ablation.SummarizeTests.test_rescue_is_paired_against_shipped_base) ... ok
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
Ran 310 tests in 4.864s

OK (skipped=3)
```
</details>
