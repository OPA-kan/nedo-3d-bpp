# Lookahead sample-simulator comparison

- Timestamp: `2026-07-28T07:34:05+00:00`
- Git SHA: `0d2e59bdc2e63ad57eb410276a45ca57f77d5f63`
- Config: `/home/runner/work/nedo-3d-bpp/nedo-3d-bpp/simulator/configs/sample_config.json`
- Run ID: `30338524490`
- Scope: bundled simulator proxy; not a SIGNATE leaderboard score

## Mode summary

| mode | process | physics | placed | mean fill | residual feasible | CoG z | surface TV | max policy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| weighted | 0 | FAIL | 18 | 12.745110 | 1.000 | 0.662 | 0.0195 | 6.510s |
| depth2 | 0 | FAIL | 18 | 12.745110 | 1.000 | 0.662 | 0.0201 | 6.510s |
| pool_resilience | 0 | FAIL | 18 | 12.745110 | 1.000 | 0.662 | 0.0195 | 6.510s |

## Case history

### weighted

| case | fill | placed | volume | residual feasible | CoG z | surface TV | valid | safe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 000 | 21.577369 | 14/41 | 1.1645 | - | 0.627 | 0.0275 | False | False |
| 001 | 3.912850 | 4/42 | 0.2315 | 1.000 | 0.697 | 0.0115 | True | False |

#### weighted / 000 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | search | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|
| 0 | 1 | 0.1134 | 0.972 | - | 0.175 | 0.567 | 0.000/0.056 | release_candidate | 0.052m/0.0deg | envelope:848 | 12/12 | PASS |
| 1 | 2 | 0.2268 | 0.943 | - | 0.310 | 0.567 | 0.000/0.113 | candidate | 0.000m/0.0deg | envelope:2504 | 12/12 | PASS |
| 2 | 3 | 0.3402 | 0.915 | - | 0.445 | 0.568 | 0.000/0.169 | candidate | 0.000m/0.0deg | envelope:4170 | 12/12 | PASS |
| 3 | 4 | 0.4536 | 0.887 | - | 0.377 | 0.318 | 0.050/0.175 | release_candidate | 0.052m/0.0deg | envelope:6803 | 12/12 | PASS |
| 4 | 5 | 0.5267 | 0.869 | - | 0.386 | 0.224 | 0.082/0.179 | candidate | 0.000m/0.0deg | envelope:7221 | 12/12 deadline | PASS |
| 5 | 6 | 0.5999 | 0.850 | - | 0.357 | 0.258 | 0.082/0.216 | release_candidate | 0.052m/0.1deg | envelope:5138 | 12/12 deadline | PASS |
| 6 | 7 | 0.6730 | 0.832 | - | 0.364 | 0.285 | 0.082/0.252 | release_candidate | 0.052m/0.0deg | envelope:5971 | 12/12 deadline | PASS |
| 7 | 8 | 0.7461 | 0.814 | - | 0.416 | 0.335 | 0.082/0.289 | release_candidate | 0.052m/0.0deg | envelope:6821 | 12/12 deadline | PASS |
| 8 | 9 | 0.8192 | 0.796 | - | 0.459 | 0.336 | 0.082/0.325 | release_candidate | 0.052m/0.0deg | envelope:9454 | 12/12 deadline | PASS |
| 9 | 10 | 0.8924 | 0.777 | - | 0.504 | 0.362 | 0.082/0.361 | release_candidate | 0.052m/0.0deg | envelope:9892 | 12/12 deadline | PASS |
| 10 | 11 | 0.9655 | 0.759 | - | 0.561 | 0.384 | 0.082/0.398 | release_candidate | 0.052m/0.0deg | envelope:13670 | 12/12 deadline | PASS |
| 11 | 12 | 1.0386 | 0.741 | - | 0.570 | 0.342 | 0.112/0.404 | release_candidate | 0.052m/0.0deg | envelope:21961 | 12/12 deadline | PASS |
| 12 | 13 | 1.1117 | 0.723 | - | 0.598 | 0.307 | 0.141/0.412 | release_candidate | 0.052m/0.0deg | envelope:23151 | 12/12 deadline | PASS |
| 13 | 14 | 1.1645 | 0.709 | - | 0.627 | 0.324 | 0.141/0.438 | release_candidate | 0.052m/0.0deg | envelope:20050 | 12/12 deadline | PASS |
| 14 | 14 | 1.1645 | 0.709 | - | 0.627 | 0.324 | 0.141/0.438 | fixed_fallback | - | envelope:47096 | 24/12 deadline | FAIL |

#### weighted / 001 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | search | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|
| 0 | 1 | 0.0528 | 0.987 | 1.000 | 0.980 | 0.696 | 0.000/0.026 | candidate | 0.051m/0.0deg | envelope:12045 | 120/120 | PASS |
| 1 | 2 | 0.1056 | 0.974 | - | 0.980 | 0.577 | 0.000/0.052 | candidate | 0.051m/0.0deg | envelope:27667 | 120/120 deadline | PASS |
| 2 | 3 | 0.1584 | 0.961 | - | 0.980 | 0.385 | 0.013/0.064 | candidate | 0.051m/0.0deg | envelope:23497 | 120/120 deadline | PASS |
| 3 | 4 | 0.2315 | 0.943 | - | 0.697 | 0.178 | 0.046/0.067 | release_candidate | 0.052m/0.0deg | envelope:22357 | 120/120 deadline | PASS |
| 4 | 4 | 0.2315 | 0.943 | - | 0.697 | 0.178 | 0.046/0.067 | release_candidate | 0.638m/90.0deg | envelope:20080 | 120/120 deadline | FAIL |

### depth2

| case | fill | placed | volume | residual feasible | CoG z | surface TV | valid | safe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 000 | 21.577369 | 14/41 | 1.1645 | - | 0.627 | 0.0287 | False | False |
| 001 | 3.912850 | 4/42 | 0.2315 | 1.000 | 0.697 | 0.0115 | True | False |

#### depth2 / 000 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | search | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|
| 0 | 1 | 0.1134 | 0.972 | - | 0.175 | 0.567 | 0.000/0.056 | release_candidate | 0.052m/0.0deg | envelope:848 | 12/12 | PASS |
| 1 | 2 | 0.2268 | 0.943 | - | 0.310 | 0.567 | 0.000/0.113 | candidate | 0.000m/0.0deg | envelope:2504 | 12/12 | PASS |
| 2 | 3 | 0.3402 | 0.915 | - | 0.445 | 0.568 | 0.000/0.169 | candidate | 0.000m/0.0deg | envelope:4170 | 12/12 | PASS |
| 3 | 4 | 0.4536 | 0.887 | - | 0.377 | 0.318 | 0.050/0.175 | release_candidate | 0.052m/0.0deg | envelope:6803 | 12/12 | PASS |
| 4 | 5 | 0.5267 | 0.869 | - | 0.386 | 0.224 | 0.082/0.179 | candidate | 0.000m/0.0deg | envelope:7203 | 12/12 deadline | PASS |
| 5 | 6 | 0.5999 | 0.850 | - | 0.357 | 0.258 | 0.082/0.216 | release_candidate | 0.052m/0.1deg | envelope:5138 | 12/12 deadline | PASS |
| 6 | 7 | 0.6730 | 0.832 | - | 0.364 | 0.285 | 0.082/0.252 | release_candidate | 0.052m/0.0deg | envelope:5965 | 12/12 deadline | PASS |
| 7 | 8 | 0.7461 | 0.814 | - | 0.416 | 0.335 | 0.082/0.289 | release_candidate | 0.052m/0.0deg | envelope:6805 | 12/12 deadline | PASS |
| 8 | 9 | 0.8192 | 0.796 | - | 0.459 | 0.336 | 0.082/0.325 | release_candidate | 0.052m/0.0deg | envelope:9454 | 12/12 deadline | PASS |
| 9 | 10 | 0.8924 | 0.777 | - | 0.504 | 0.362 | 0.082/0.361 | release_candidate | 0.052m/0.0deg | envelope:9892 | 12/12 deadline | PASS |
| 10 | 11 | 0.9655 | 0.759 | - | 0.561 | 0.384 | 0.082/0.398 | release_candidate | 0.052m/0.0deg | envelope:13661 | 12/12 deadline | PASS |
| 11 | 12 | 1.0386 | 0.741 | - | 0.591 | 0.343 | 0.111/0.406 | release_candidate | 0.052m/0.0deg | envelope:21889 | 12/12 deadline | PASS |
| 12 | 13 | 1.1117 | 0.723 | - | 0.598 | 0.307 | 0.141/0.412 | release_candidate | 0.052m/0.0deg | envelope:25117 | 12/12 deadline | PASS |
| 13 | 14 | 1.1645 | 0.709 | - | 0.627 | 0.324 | 0.141/0.438 | release_candidate | 0.052m/0.0deg | envelope:19942 | 12/12 deadline | PASS |
| 14 | 14 | 1.1645 | 0.709 | - | 0.627 | 0.324 | 0.141/0.438 | fixed_fallback | - | envelope:47304 | 24/12 deadline | FAIL |

#### depth2 / 001 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | search | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|
| 0 | 1 | 0.0528 | 0.987 | 1.000 | 0.980 | 0.696 | 0.000/0.026 | candidate | 0.051m/0.0deg | envelope:12045 | 120/120 | PASS |
| 1 | 2 | 0.1056 | 0.974 | - | 0.980 | 0.577 | 0.000/0.052 | candidate | 0.051m/0.0deg | envelope:28630 | 120/120 deadline | PASS |
| 2 | 3 | 0.1584 | 0.961 | - | 0.980 | 0.385 | 0.013/0.064 | candidate | 0.051m/0.0deg | envelope:23811 | 120/120 deadline | PASS |
| 3 | 4 | 0.2315 | 0.943 | - | 0.697 | 0.178 | 0.046/0.067 | release_candidate | 0.052m/0.0deg | envelope:22407 | 120/120 deadline | PASS |
| 4 | 4 | 0.2315 | 0.943 | - | 0.697 | 0.178 | 0.046/0.067 | release_candidate | 0.638m/90.0deg | envelope:20080 | 120/120 deadline | FAIL |

### pool_resilience

| case | fill | placed | volume | residual feasible | CoG z | surface TV | valid | safe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 000 | 21.577369 | 14/41 | 1.1645 | - | 0.627 | 0.0275 | False | False |
| 001 | 3.912850 | 4/42 | 0.2315 | 1.000 | 0.697 | 0.0115 | True | False |

#### pool_resilience / 000 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | search | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|
| 0 | 1 | 0.1134 | 0.972 | - | 0.175 | 0.567 | 0.000/0.056 | release_candidate | 0.052m/0.0deg | envelope:848 | 12/12 | PASS |
| 1 | 2 | 0.2268 | 0.943 | - | 0.310 | 0.567 | 0.000/0.113 | candidate | 0.000m/0.0deg | envelope:2504 | 12/12 | PASS |
| 2 | 3 | 0.3402 | 0.915 | - | 0.445 | 0.568 | 0.000/0.169 | candidate | 0.000m/0.0deg | envelope:4170 | 12/12 | PASS |
| 3 | 4 | 0.4536 | 0.887 | - | 0.377 | 0.318 | 0.050/0.175 | release_candidate | 0.052m/0.0deg | envelope:6803 | 12/12 | PASS |
| 4 | 5 | 0.5267 | 0.869 | - | 0.386 | 0.224 | 0.082/0.179 | candidate | 0.000m/0.0deg | envelope:7221 | 12/12 deadline | PASS |
| 5 | 6 | 0.5999 | 0.850 | - | 0.357 | 0.258 | 0.082/0.216 | release_candidate | 0.052m/0.1deg | envelope:5144 | 12/12 deadline | PASS |
| 6 | 7 | 0.6730 | 0.832 | - | 0.364 | 0.285 | 0.082/0.252 | release_candidate | 0.052m/0.0deg | envelope:5965 | 12/12 deadline | PASS |
| 7 | 8 | 0.7461 | 0.814 | - | 0.416 | 0.335 | 0.082/0.289 | release_candidate | 0.052m/0.0deg | envelope:6821 | 12/12 deadline | PASS |
| 8 | 9 | 0.8192 | 0.796 | - | 0.459 | 0.336 | 0.082/0.325 | release_candidate | 0.052m/0.0deg | envelope:9454 | 12/12 deadline | PASS |
| 9 | 10 | 0.8924 | 0.777 | - | 0.504 | 0.362 | 0.082/0.361 | release_candidate | 0.052m/0.0deg | envelope:9892 | 12/12 deadline | PASS |
| 10 | 11 | 0.9655 | 0.759 | - | 0.561 | 0.384 | 0.082/0.398 | release_candidate | 0.052m/0.0deg | envelope:13670 | 12/12 deadline | PASS |
| 11 | 12 | 1.0386 | 0.741 | - | 0.570 | 0.342 | 0.112/0.404 | release_candidate | 0.052m/0.0deg | envelope:21961 | 12/12 deadline | PASS |
| 12 | 13 | 1.1117 | 0.723 | - | 0.598 | 0.307 | 0.141/0.412 | release_candidate | 0.052m/0.0deg | envelope:23181 | 12/12 deadline | PASS |
| 13 | 14 | 1.1645 | 0.709 | - | 0.627 | 0.324 | 0.141/0.438 | release_candidate | 0.052m/0.0deg | envelope:20417 | 12/12 deadline | PASS |
| 14 | 14 | 1.1645 | 0.709 | - | 0.627 | 0.324 | 0.141/0.438 | fixed_fallback | - | envelope:47076 | 24/12 deadline | FAIL |

#### pool_resilience / 001 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | search | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|
| 0 | 1 | 0.0528 | 0.987 | 1.000 | 0.980 | 0.696 | 0.000/0.026 | candidate | 0.051m/0.0deg | envelope:12045 | 120/120 | PASS |
| 1 | 2 | 0.1056 | 0.974 | - | 0.980 | 0.577 | 0.000/0.052 | candidate | 0.051m/0.0deg | envelope:29338 | 120/120 deadline | PASS |
| 2 | 3 | 0.1584 | 0.961 | - | 0.980 | 0.385 | 0.013/0.064 | candidate | 0.051m/0.0deg | envelope:23822 | 120/120 deadline | PASS |
| 3 | 4 | 0.2315 | 0.943 | - | 0.697 | 0.178 | 0.046/0.067 | release_candidate | 0.052m/0.0deg | envelope:22773 | 120/120 deadline | PASS |
| 4 | 4 | 0.2315 | 0.943 | - | 0.697 | 0.178 | 0.046/0.067 | release_candidate | 0.638m/90.0deg | envelope:20104 | 120/120 deadline | FAIL |

## Interpretation

At least one mode's physical validity failed. Fill and placed comparisons are diagnostic history, not a valid competition result.
