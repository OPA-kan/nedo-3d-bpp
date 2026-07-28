# Lookahead sample-simulator comparison

- Timestamp: `2026-07-28T07:57:15+00:00`
- Git SHA: `b32e2f80906d4f625359eed4f1772b55bab3ff5b`
- Config: `/home/runner/work/nedo-3d-bpp/nedo-3d-bpp/simulator/configs/sample_config.json`
- Run ID: `30340049061`
- Scope: bundled simulator proxy; not a SIGNATE leaderboard score

## Mode summary

| mode | process | physics | placed | mean fill | residual feasible | CoG z | surface TV | max policy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| weighted | 0 | FAIL | 19 | 12.994050 | 1.000 | 0.701 | 0.0245 | 6.304s |
| depth2 | 0 | FAIL | 19 | 12.994050 | 1.000 | 0.701 | 0.0245 | 6.302s |
| pool_resilience | 0 | FAIL | 19 | 12.994050 | 1.000 | 0.701 | 0.0245 | 6.304s |

## Case history

### weighted

| case | fill | placed | volume | residual feasible | CoG z | surface TV | valid | safe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 000 | 22.075251 | 15/41 | 1.2173 | - | 0.705 | 0.0375 | True | False |
| 001 | 3.912850 | 4/42 | 0.2315 | 1.000 | 0.697 | 0.0115 | True | False |

#### weighted / 000 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | search | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|
| 0 | 1 | 0.1134 | 0.972 | - | 1.125 | 0.429 | 0.006/0.050 | candidate | 0.051m/0.0deg | envelope:848 | 12/12 | PASS |
| 1 | 2 | 0.2268 | 0.943 | - | 1.052 | -0.069 | 0.062/0.050 | candidate | 0.051m/0.0deg | envelope:2203 | 12/12 | PASS |
| 2 | 3 | 0.3402 | 0.915 | - | 1.118 | -0.236 | 0.119/0.050 | candidate | 0.000m/0.0deg | envelope:4603 | 12/12 | PASS |
| 3 | 4 | 0.4536 | 0.887 | - | 0.882 | -0.035 | 0.119/0.107 | release_candidate | 0.052m/0.0deg | envelope:6269 | 12/12 | PASS |
| 4 | 5 | 0.5267 | 0.869 | - | 0.814 | 0.060 | 0.119/0.143 | candidate | 0.000m/0.0deg | envelope:11769 | 12/12 | PASS |
| 5 | 6 | 0.5999 | 0.850 | - | 0.823 | 0.149 | 0.119/0.179 | candidate | 0.000m/0.0deg | envelope:16758 | 12/12 | PASS |
| 6 | 7 | 0.6730 | 0.832 | - | 0.831 | 0.170 | 0.119/0.216 | candidate | 0.000m/0.0deg | envelope:24593 | 12/12 | PASS |
| 7 | 8 | 0.7461 | 0.814 | - | 0.761 | 0.203 | 0.119/0.252 | release_candidate | 0.052m/0.1deg | envelope:32887 | 12/12 deadline | PASS |
| 8 | 9 | 0.8192 | 0.796 | - | 0.704 | 0.143 | 0.155/0.252 | release_candidate | 0.052m/0.1deg | envelope:14846 | 12/12 deadline | PASS |
| 9 | 10 | 0.8924 | 0.777 | - | 0.658 | 0.090 | 0.191/0.253 | release_candidate | 0.052m/0.0deg | envelope:14894 | 12/12 deadline | PASS |
| 10 | 11 | 0.9655 | 0.759 | - | 0.638 | 0.121 | 0.191/0.289 | release_candidate | 0.052m/0.0deg | envelope:14040 | 12/12 deadline | PASS |
| 11 | 12 | 1.0386 | 0.741 | - | 0.640 | 0.148 | 0.191/0.325 | release_candidate | 0.052m/0.0deg | envelope:14219 | 12/12 deadline | PASS |
| 12 | 13 | 1.1117 | 0.723 | - | 0.659 | 0.171 | 0.191/0.362 | release_candidate | 0.052m/0.0deg | envelope:14857 | 12/12 deadline | PASS |
| 13 | 14 | 1.1645 | 0.709 | - | 0.679 | 0.195 | 0.191/0.388 | release_candidate | 0.052m/0.0deg | envelope:14526 | 12/12 deadline | PASS |
| 14 | 15 | 1.2173 | 0.696 | - | 0.705 | 0.211 | 0.191/0.415 | release_candidate | 0.052m/0.0deg | envelope:26574 | 12/12 deadline | PASS |
| 15 | 15 | 1.2173 | 0.696 | - | 0.705 | 0.212 | 0.192/0.415 | release_candidate | 0.871m/90.3deg | envelope:34553 | 12/12 deadline | FAIL |

#### weighted / 001 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | search | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|
| 0 | 1 | 0.0528 | 0.987 | 1.000 | 0.980 | 0.696 | 0.000/0.026 | candidate | 0.051m/0.0deg | envelope:12045 | 120/120 | PASS |
| 1 | 2 | 0.1056 | 0.974 | 1.000 | 0.980 | 0.577 | 0.000/0.052 | candidate | 0.051m/0.0deg | envelope:31418 | 120/120 | PASS |
| 2 | 3 | 0.1584 | 0.961 | - | 0.980 | 0.385 | 0.013/0.064 | candidate | 0.051m/0.0deg | envelope:25569 | 120/120 deadline | PASS |
| 3 | 4 | 0.2315 | 0.943 | - | 0.697 | 0.178 | 0.046/0.067 | release_candidate | 0.052m/0.0deg | envelope:23193 | 120/120 deadline | PASS |
| 4 | 4 | 0.2315 | 0.943 | - | 0.697 | 0.178 | 0.046/0.067 | release_candidate | 0.638m/90.0deg | envelope:20516 | 120/120 deadline | FAIL |

### depth2

| case | fill | placed | volume | residual feasible | CoG z | surface TV | valid | safe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 000 | 22.075251 | 15/41 | 1.2173 | - | 0.705 | 0.0375 | True | False |
| 001 | 3.912850 | 4/42 | 0.2315 | 1.000 | 0.697 | 0.0115 | True | False |

#### depth2 / 000 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | search | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|
| 0 | 1 | 0.1134 | 0.972 | - | 1.125 | 0.429 | 0.006/0.050 | candidate | 0.051m/0.0deg | envelope:848 | 12/12 | PASS |
| 1 | 2 | 0.2268 | 0.943 | - | 1.052 | -0.069 | 0.062/0.050 | candidate | 0.051m/0.0deg | envelope:2203 | 12/12 | PASS |
| 2 | 3 | 0.3402 | 0.915 | - | 1.118 | -0.236 | 0.119/0.050 | candidate | 0.000m/0.0deg | envelope:4603 | 12/12 | PASS |
| 3 | 4 | 0.4536 | 0.887 | - | 0.882 | -0.035 | 0.119/0.107 | release_candidate | 0.052m/0.0deg | envelope:6269 | 12/12 | PASS |
| 4 | 5 | 0.5267 | 0.869 | - | 0.814 | 0.060 | 0.119/0.143 | candidate | 0.000m/0.0deg | envelope:11769 | 12/12 | PASS |
| 5 | 6 | 0.5999 | 0.850 | - | 0.823 | 0.149 | 0.119/0.179 | candidate | 0.000m/0.0deg | envelope:16758 | 12/12 | PASS |
| 6 | 7 | 0.6730 | 0.832 | - | 0.831 | 0.170 | 0.119/0.216 | candidate | 0.000m/0.0deg | envelope:24593 | 12/12 | PASS |
| 7 | 8 | 0.7461 | 0.814 | - | 0.761 | 0.203 | 0.119/0.252 | release_candidate | 0.052m/0.1deg | envelope:34331 | 12/12 deadline | PASS |
| 8 | 9 | 0.8192 | 0.796 | - | 0.704 | 0.143 | 0.155/0.252 | release_candidate | 0.052m/0.1deg | envelope:14856 | 12/12 deadline | PASS |
| 9 | 10 | 0.8924 | 0.777 | - | 0.658 | 0.090 | 0.191/0.253 | release_candidate | 0.052m/0.0deg | envelope:14895 | 12/12 deadline | PASS |
| 10 | 11 | 0.9655 | 0.759 | - | 0.638 | 0.121 | 0.191/0.289 | release_candidate | 0.052m/0.0deg | envelope:14044 | 12/12 deadline | PASS |
| 11 | 12 | 1.0386 | 0.741 | - | 0.640 | 0.148 | 0.191/0.325 | release_candidate | 0.052m/0.0deg | envelope:14247 | 12/12 deadline | PASS |
| 12 | 13 | 1.1117 | 0.723 | - | 0.659 | 0.171 | 0.191/0.362 | release_candidate | 0.052m/0.0deg | envelope:14889 | 12/12 deadline | PASS |
| 13 | 14 | 1.1645 | 0.709 | - | 0.679 | 0.195 | 0.191/0.388 | release_candidate | 0.052m/0.0deg | envelope:14526 | 12/12 deadline | PASS |
| 14 | 15 | 1.2173 | 0.696 | - | 0.705 | 0.211 | 0.191/0.415 | release_candidate | 0.052m/0.0deg | envelope:26554 | 12/12 deadline | PASS |
| 15 | 15 | 1.2173 | 0.696 | - | 0.705 | 0.212 | 0.192/0.415 | release_candidate | 0.871m/90.3deg | envelope:34578 | 12/12 deadline | FAIL |

#### depth2 / 001 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | search | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|
| 0 | 1 | 0.0528 | 0.987 | 1.000 | 0.980 | 0.696 | 0.000/0.026 | candidate | 0.051m/0.0deg | envelope:12045 | 120/120 | PASS |
| 1 | 2 | 0.1056 | 0.974 | 1.000 | 0.980 | 0.577 | 0.000/0.052 | candidate | 0.051m/0.0deg | envelope:31418 | 120/120 | PASS |
| 2 | 3 | 0.1584 | 0.961 | - | 0.980 | 0.385 | 0.013/0.064 | candidate | 0.051m/0.0deg | envelope:25624 | 120/120 deadline | PASS |
| 3 | 4 | 0.2315 | 0.943 | - | 0.697 | 0.178 | 0.046/0.067 | release_candidate | 0.052m/0.0deg | envelope:23233 | 120/120 deadline | PASS |
| 4 | 4 | 0.2315 | 0.943 | - | 0.697 | 0.178 | 0.046/0.067 | release_candidate | 0.638m/90.0deg | envelope:20527 | 120/120 deadline | FAIL |

### pool_resilience

| case | fill | placed | volume | residual feasible | CoG z | surface TV | valid | safe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 000 | 22.075251 | 15/41 | 1.2173 | - | 0.705 | 0.0375 | True | False |
| 001 | 3.912850 | 4/42 | 0.2315 | 1.000 | 0.697 | 0.0115 | True | False |

#### pool_resilience / 000 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | search | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|
| 0 | 1 | 0.1134 | 0.972 | - | 1.125 | 0.429 | 0.006/0.050 | candidate | 0.051m/0.0deg | envelope:848 | 12/12 | PASS |
| 1 | 2 | 0.2268 | 0.943 | - | 1.052 | -0.069 | 0.062/0.050 | candidate | 0.051m/0.0deg | envelope:2203 | 12/12 | PASS |
| 2 | 3 | 0.3402 | 0.915 | - | 1.118 | -0.236 | 0.119/0.050 | candidate | 0.000m/0.0deg | envelope:4603 | 12/12 | PASS |
| 3 | 4 | 0.4536 | 0.887 | - | 0.882 | -0.035 | 0.119/0.107 | release_candidate | 0.052m/0.0deg | envelope:6269 | 12/12 | PASS |
| 4 | 5 | 0.5267 | 0.869 | - | 0.814 | 0.060 | 0.119/0.143 | candidate | 0.000m/0.0deg | envelope:11769 | 12/12 | PASS |
| 5 | 6 | 0.5999 | 0.850 | - | 0.823 | 0.149 | 0.119/0.179 | candidate | 0.000m/0.0deg | envelope:16758 | 12/12 | PASS |
| 6 | 7 | 0.6730 | 0.832 | - | 0.831 | 0.170 | 0.119/0.216 | candidate | 0.000m/0.0deg | envelope:24593 | 12/12 | PASS |
| 7 | 8 | 0.7461 | 0.814 | - | 0.761 | 0.203 | 0.119/0.252 | release_candidate | 0.052m/0.1deg | envelope:30602 | 12/12 deadline | PASS |
| 8 | 9 | 0.8192 | 0.796 | - | 0.704 | 0.143 | 0.155/0.252 | release_candidate | 0.052m/0.1deg | envelope:14846 | 12/12 deadline | PASS |
| 9 | 10 | 0.8924 | 0.777 | - | 0.658 | 0.090 | 0.191/0.253 | release_candidate | 0.052m/0.0deg | envelope:14860 | 12/12 deadline | PASS |
| 10 | 11 | 0.9655 | 0.759 | - | 0.638 | 0.121 | 0.191/0.289 | release_candidate | 0.052m/0.0deg | envelope:14039 | 12/12 deadline | PASS |
| 11 | 12 | 1.0386 | 0.741 | - | 0.640 | 0.148 | 0.191/0.325 | release_candidate | 0.052m/0.0deg | envelope:14221 | 12/12 deadline | PASS |
| 12 | 13 | 1.1117 | 0.723 | - | 0.659 | 0.171 | 0.191/0.362 | release_candidate | 0.052m/0.0deg | envelope:14857 | 12/12 deadline | PASS |
| 13 | 14 | 1.1645 | 0.709 | - | 0.679 | 0.195 | 0.191/0.388 | release_candidate | 0.052m/0.0deg | envelope:14526 | 12/12 deadline | PASS |
| 14 | 15 | 1.2173 | 0.696 | - | 0.705 | 0.211 | 0.191/0.415 | release_candidate | 0.052m/0.0deg | envelope:26514 | 12/12 deadline | PASS |
| 15 | 15 | 1.2173 | 0.696 | - | 0.705 | 0.212 | 0.192/0.415 | release_candidate | 0.871m/90.3deg | envelope:34549 | 12/12 deadline | FAIL |

#### pool_resilience / 001 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | search | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|
| 0 | 1 | 0.0528 | 0.987 | 1.000 | 0.980 | 0.696 | 0.000/0.026 | candidate | 0.051m/0.0deg | envelope:12045 | 120/120 | PASS |
| 1 | 2 | 0.1056 | 0.974 | 1.000 | 0.980 | 0.577 | 0.000/0.052 | candidate | 0.051m/0.0deg | envelope:31418 | 120/120 | PASS |
| 2 | 3 | 0.1584 | 0.961 | - | 0.980 | 0.385 | 0.013/0.064 | candidate | 0.051m/0.0deg | envelope:25602 | 120/120 deadline | PASS |
| 3 | 4 | 0.2315 | 0.943 | - | 0.697 | 0.178 | 0.046/0.067 | release_candidate | 0.052m/0.0deg | envelope:23223 | 120/120 deadline | PASS |
| 4 | 4 | 0.2315 | 0.943 | - | 0.697 | 0.178 | 0.046/0.067 | release_candidate | 0.638m/90.0deg | envelope:20516 | 120/120 deadline | FAIL |

## Interpretation

At least one mode's physical validity failed. Fill and placed comparisons are diagnostic history, not a valid competition result.
