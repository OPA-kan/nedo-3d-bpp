# CPU verification report

- Timestamp: `2026-08-13T14:11:40+09:00`
- Git SHA: `b73693670c75b1ce9efa8cc28f913784d36da9b1`
- Python: `3.12.13 (main, Mar  3 2026, 15:01:35) [MSC v.1944 64 bit (AMD64)]`
- Platform: `Windows-11-10.0.26200-SP0`
- Processor: `Intel64 Family 6 Model 186 Stepping 3, GenuineIntel`

## Unit tests

- Status: `FAIL`
- Runtime: `75.978 s`
- Command: `python -m unittest discover -s tests -v`

## Simulator

- Status: `SKIPPED`

## Captured output

<details><summary>unit tests (tail; full log: reports/raw/unit-tests.log)</summary>

```text
test_the_bonus_span_is_three_units (test_zone_order.ZoneScoreTests.test_the_bonus_span_is_three_units) ... ok
test_the_span_must_clear_the_support_term (test_zone_order.ZoneScoreTests.test_the_span_must_clear_the_support_term)
Why the default bonus is 1.0 and not 0.5. ... ok

======================================================================
ERROR: test_queue_runs_records_and_resumes (test_run_queue.QueueExecutionTests.test_queue_runs_records_and_resumes)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\�哈���Y\Documents\Codex\2026-07-28\ne\work\nedo-counterfactual-graph\tests\test_run_queue.py", line 83, in test_queue_runs_records_and_resumes
    (queue_root / "test-plan" / "state.json").read_text()
  File "C:\Users\�哈���Y\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\Lib\pathlib.py", line 1028, in read_text
    return f.read()
           ^^^^^^^^
UnicodeDecodeError: 'cp932' codec can't decode byte 0x8e in position 297: illegal multibyte sequence

======================================================================
ERROR: test_timeout_is_recorded (test_run_queue.QueueExecutionTests.test_timeout_is_recorded)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "C:\Users\�哈���Y\Documents\Codex\2026-07-28\ne\work\nedo-counterfactual-graph\tests\test_run_queue.py", line 119, in test_timeout_is_recorded
    (queue_root / "test-plan" / "state.json").read_text()
  File "C:\Users\�哈���Y\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\Lib\pathlib.py", line 1028, in read_text
    return f.read()
           ^^^^^^^^
UnicodeDecodeError: 'cp932' codec can't decode byte 0x8e in position 315: illegal multibyte sequence

----------------------------------------------------------------------
Ran 832 tests in 74.562s

FAILED (errors=2, skipped=5)
```
</details>
