# Direct post-shake instrument: gate adjudication

Protocol: `reports/hazard/post-shake-direct-protocol.md`. Instrument: `scripts/postshake_capture.py` (recorder) and `scripts/run_test_capture.py` (entry point). No clone, no reconstruction: these are the numbers the bundled shake itself produced.

## Gates

| gate | threshold | measured | result |
|---|---|---|---|
| G1a wrapped-vs-unwrapped shake equal | all episodes | 41/41 | pass |
| G1a exactly two `_live_poses` calls per shake | all episodes | 41/41 | pass |
| G1a span | >= 6 episodes, >= 3 configs, both arms | 41 episodes, 7 configs, arms ['base', 'quiet_guard'] | pass |
| G2 pre-shake capture == last safe step counts | >= 95% | 41/41 = 100.0% | pass |
| G3 no reimplementation of the attribute contract | structural | `tests/test_postshake_capture.py` | see test run |
| stream sufficiency | >= 40 episodes, >= 5 configs, both arms | 41 episodes, 7 configs, arms ['base', 'quiet_guard'] | pass |

## Verdict: **pass**

## Payload: what the shake does to attribute coverage

- episodes with pre and post capture: 41
- episodes whose soft coverage changed across the shake: 2
- episodes whose priority coverage changed across the shake: 4

| arm | episodes | soft clean pre | soft clean post | priority clean pre | priority clean post |
|---|---:|---:|---:|---:|---:|
| base | 20 | 0.9808 | 0.9850 | 0.7500 | 0.7222 |
| quiet_guard | 21 | 0.9857 | 0.9738 | 0.7639 | 0.7361 |
