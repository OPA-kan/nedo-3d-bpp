# Lookahead sample-simulator comparison

- Timestamp: `2026-07-28T07:12:41+00:00`
- Git SHA: `68395b38f360e72b296eb9dca5809842ae7e0bb2`
- Config: `/home/runner/work/nedo-3d-bpp/nedo-3d-bpp/simulator/configs/sample_config.json`
- Run ID: `30337216417`
- Scope: bundled simulator proxy; not a SIGNATE leaderboard score

## Mode summary

| mode | process | physics | placed | mean fill | residual feasible | CoG z | surface TV | max policy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| weighted | 0 | FAIL | 19 | 10.300148 | 1.000 | 0.825 | 0.0322 | 6.520s |
| depth2 | 0 | FAIL | 19 | 10.300148 | 1.000 | 0.825 | 0.0322 | 6.521s |
| pool_resilience | 0 | FAIL | 19 | 10.300148 | 1.000 | 0.825 | 0.0322 | 6.522s |

## Case history

### weighted

| case | fill | placed | volume | residual feasible | CoG z | surface TV | valid | safe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 000 | 12.774596 | 12/41 | 1.0386 | - | 0.730 | 0.0473 | False | False |
| 001 | 7.825700 | 7/42 | 0.3691 | 1.000 | 0.921 | 0.0171 | False | False |

#### weighted / 000 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | search | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|
| 0 | 1 | 0.1134 | 0.972 | - | 0.415 | 0.780 | 0.000/0.056 | release_candidate | 0.052m/0.0deg | envelope:692 | 6/6 | PASS |
| 1 | 2 | 0.2268 | 0.943 | - | 0.415 | 0.781 | 0.000/0.113 | release_candidate | 0.052m/0.1deg | envelope:1908 | 6/6 | PASS |
| 2 | 3 | 0.3402 | 0.915 | - | 0.415 | 0.523 | 0.027/0.142 | release_candidate | 0.052m/0.0deg | envelope:3769 | 6/6 | PASS |
| 3 | 4 | 0.4536 | 0.887 | - | 0.415 | 0.392 | 0.055/0.170 | release_candidate | 0.052m/0.0deg | envelope:5941 | 6/6 | PASS |
| 4 | 5 | 0.5267 | 0.869 | - | 0.500 | 0.377 | 0.063/0.199 | candidate | 0.051m/0.0deg | envelope:7304 | 6/6 | PASS |
| 5 | 6 | 0.5999 | 0.850 | - | 0.581 | 0.424 | 0.063/0.236 | candidate | 0.000m/0.0deg | envelope:11923 | 6/6 | PASS |
| 6 | 7 | 0.6730 | 0.832 | - | 0.644 | 0.465 | 0.063/0.272 | candidate | 0.000m/0.0deg | envelope:19746 | 6/6 | PASS |
| 7 | 8 | 0.7461 | 0.814 | - | 0.693 | 0.421 | 0.079/0.292 | candidate | 0.000m/0.0deg | envelope:24100 | 6/6 | PASS |
| 8 | 9 | 0.8192 | 0.796 | - | 0.733 | 0.391 | 0.093/0.315 | candidate | 0.000m/0.0deg | envelope:29639 | 6/6 | PASS |
| 9 | 10 | 0.8924 | 0.777 | - | 0.693 | 0.364 | 0.108/0.335 | release_candidate | 0.052m/0.0deg | envelope:33287 | 6/6 | PASS |
| 10 | 11 | 0.9655 | 0.759 | - | 0.695 | 0.341 | 0.124/0.356 | candidate | 0.000m/0.0deg | envelope:31941 | 6/6 deadline | PASS |
| 11 | 12 | 1.0386 | 0.741 | - | 0.730 | 0.285 | 0.160/0.356 | candidate | 0.051m/0.0deg | envelope:33435 | 6/6 deadline | PASS |
| 12 | 12 | 1.0386 | 0.741 | - | 0.730 | 0.285 | 0.160/0.356 | fixed_fallback | - | envelope:51112 | 12/6 deadline | FAIL |

#### weighted / 001 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | search | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|
| 0 | 1 | 0.0528 | 0.987 | 1.000 | 0.980 | 0.696 | 0.000/0.026 | candidate | 0.051m/0.0deg | envelope:8297 | 60/60 | PASS |
| 1 | 2 | 0.1056 | 0.974 | 1.000 | 0.980 | 0.577 | 0.000/0.052 | candidate | 0.051m/0.0deg | envelope:23450 | 60/60 | PASS |
| 2 | 3 | 0.1584 | 0.961 | 1.000 | 0.980 | 0.271 | 0.024/0.053 | candidate | 0.051m/0.0deg | envelope:35656 | 60/60 | PASS |
| 3 | 4 | 0.2112 | 0.948 | - | 1.060 | 0.373 | 0.024/0.079 | candidate | 0.000m/0.0deg | envelope:49852 | 60/60 deadline | PASS |
| 4 | 5 | 0.2640 | 0.935 | - | 1.092 | 0.390 | 0.024/0.105 | candidate | 0.000m/0.0deg | envelope:53861 | 60/60 deadline | PASS |
| 5 | 6 | 0.3168 | 0.922 | - | 1.113 | 0.268 | 0.048/0.106 | candidate | 0.000m/0.0deg | envelope:62201 | 60/60 deadline | PASS |
| 6 | 7 | 0.3691 | 0.909 | - | 0.921 | 0.230 | 0.060/0.118 | fixed_fallback | 0.097m/0.1deg | envelope:105620 | 120/60 deadline | PASS |
| 7 | 7 | 0.3691 | 0.909 | - | 0.921 | 0.230 | 0.060/0.118 | fixed_fallback | - | envelope:118080 | 120/60 deadline | FAIL |

### depth2

| case | fill | placed | volume | residual feasible | CoG z | surface TV | valid | safe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 000 | 12.774596 | 12/41 | 1.0386 | - | 0.730 | 0.0473 | False | False |
| 001 | 7.825700 | 7/42 | 0.3691 | 1.000 | 0.921 | 0.0171 | False | False |

#### depth2 / 000 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | search | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|
| 0 | 1 | 0.1134 | 0.972 | - | 0.415 | 0.780 | 0.000/0.056 | release_candidate | 0.052m/0.0deg | envelope:692 | 6/6 | PASS |
| 1 | 2 | 0.2268 | 0.943 | - | 0.415 | 0.781 | 0.000/0.113 | release_candidate | 0.052m/0.1deg | envelope:1908 | 6/6 | PASS |
| 2 | 3 | 0.3402 | 0.915 | - | 0.415 | 0.523 | 0.027/0.142 | release_candidate | 0.052m/0.0deg | envelope:3769 | 6/6 | PASS |
| 3 | 4 | 0.4536 | 0.887 | - | 0.415 | 0.392 | 0.055/0.170 | release_candidate | 0.052m/0.0deg | envelope:5941 | 6/6 | PASS |
| 4 | 5 | 0.5267 | 0.869 | - | 0.500 | 0.377 | 0.063/0.199 | candidate | 0.051m/0.0deg | envelope:7304 | 6/6 | PASS |
| 5 | 6 | 0.5999 | 0.850 | - | 0.581 | 0.424 | 0.063/0.236 | candidate | 0.000m/0.0deg | envelope:11923 | 6/6 | PASS |
| 6 | 7 | 0.6730 | 0.832 | - | 0.644 | 0.465 | 0.063/0.272 | candidate | 0.000m/0.0deg | envelope:19746 | 6/6 | PASS |
| 7 | 8 | 0.7461 | 0.814 | - | 0.693 | 0.421 | 0.079/0.292 | candidate | 0.000m/0.0deg | envelope:24100 | 6/6 | PASS |
| 8 | 9 | 0.8192 | 0.796 | - | 0.733 | 0.391 | 0.093/0.315 | candidate | 0.000m/0.0deg | envelope:29639 | 6/6 | PASS |
| 9 | 10 | 0.8924 | 0.777 | - | 0.693 | 0.364 | 0.108/0.335 | release_candidate | 0.052m/0.0deg | envelope:33287 | 6/6 | PASS |
| 10 | 11 | 0.9655 | 0.759 | - | 0.695 | 0.341 | 0.124/0.356 | candidate | 0.000m/0.0deg | envelope:32235 | 6/6 deadline | PASS |
| 11 | 12 | 1.0386 | 0.741 | - | 0.730 | 0.285 | 0.160/0.356 | candidate | 0.051m/0.0deg | envelope:33435 | 6/6 deadline | PASS |
| 12 | 12 | 1.0386 | 0.741 | - | 0.730 | 0.285 | 0.160/0.356 | fixed_fallback | - | envelope:51161 | 12/6 deadline | FAIL |

#### depth2 / 001 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | search | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|
| 0 | 1 | 0.0528 | 0.987 | 1.000 | 0.980 | 0.696 | 0.000/0.026 | candidate | 0.051m/0.0deg | envelope:8297 | 60/60 | PASS |
| 1 | 2 | 0.1056 | 0.974 | 1.000 | 0.980 | 0.577 | 0.000/0.052 | candidate | 0.051m/0.0deg | envelope:23450 | 60/60 | PASS |
| 2 | 3 | 0.1584 | 0.961 | 1.000 | 0.980 | 0.271 | 0.024/0.053 | candidate | 0.051m/0.0deg | envelope:35656 | 60/60 | PASS |
| 3 | 4 | 0.2112 | 0.948 | - | 1.060 | 0.373 | 0.024/0.079 | candidate | 0.000m/0.0deg | envelope:51071 | 60/60 deadline | PASS |
| 4 | 5 | 0.2640 | 0.935 | - | 1.092 | 0.390 | 0.024/0.105 | candidate | 0.000m/0.0deg | envelope:54411 | 60/60 deadline | PASS |
| 5 | 6 | 0.3168 | 0.922 | - | 1.113 | 0.268 | 0.048/0.106 | candidate | 0.000m/0.0deg | envelope:63133 | 60/60 deadline | PASS |
| 6 | 7 | 0.3691 | 0.909 | - | 0.921 | 0.230 | 0.060/0.118 | fixed_fallback | 0.097m/0.1deg | envelope:112904 | 120/60 deadline | PASS |
| 7 | 7 | 0.3691 | 0.909 | - | 0.921 | 0.230 | 0.060/0.118 | fixed_fallback | - | envelope:122630 | 120/60 deadline | FAIL |

### pool_resilience

| case | fill | placed | volume | residual feasible | CoG z | surface TV | valid | safe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 000 | 12.774596 | 12/41 | 1.0386 | - | 0.730 | 0.0473 | False | False |
| 001 | 7.825700 | 7/42 | 0.3691 | 1.000 | 0.921 | 0.0171 | False | False |

#### pool_resilience / 000 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | search | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|
| 0 | 1 | 0.1134 | 0.972 | - | 0.415 | 0.780 | 0.000/0.056 | release_candidate | 0.052m/0.0deg | envelope:692 | 6/6 | PASS |
| 1 | 2 | 0.2268 | 0.943 | - | 0.415 | 0.781 | 0.000/0.113 | release_candidate | 0.052m/0.1deg | envelope:1908 | 6/6 | PASS |
| 2 | 3 | 0.3402 | 0.915 | - | 0.415 | 0.523 | 0.027/0.142 | release_candidate | 0.052m/0.0deg | envelope:3769 | 6/6 | PASS |
| 3 | 4 | 0.4536 | 0.887 | - | 0.415 | 0.392 | 0.055/0.170 | release_candidate | 0.052m/0.0deg | envelope:5941 | 6/6 | PASS |
| 4 | 5 | 0.5267 | 0.869 | - | 0.500 | 0.377 | 0.063/0.199 | candidate | 0.051m/0.0deg | envelope:7304 | 6/6 | PASS |
| 5 | 6 | 0.5999 | 0.850 | - | 0.581 | 0.424 | 0.063/0.236 | candidate | 0.000m/0.0deg | envelope:11923 | 6/6 | PASS |
| 6 | 7 | 0.6730 | 0.832 | - | 0.644 | 0.465 | 0.063/0.272 | candidate | 0.000m/0.0deg | envelope:19746 | 6/6 | PASS |
| 7 | 8 | 0.7461 | 0.814 | - | 0.693 | 0.421 | 0.079/0.292 | candidate | 0.000m/0.0deg | envelope:24100 | 6/6 | PASS |
| 8 | 9 | 0.8192 | 0.796 | - | 0.733 | 0.391 | 0.093/0.315 | candidate | 0.000m/0.0deg | envelope:29639 | 6/6 | PASS |
| 9 | 10 | 0.8924 | 0.777 | - | 0.693 | 0.364 | 0.108/0.335 | release_candidate | 0.052m/0.0deg | envelope:33287 | 6/6 | PASS |
| 10 | 11 | 0.9655 | 0.759 | - | 0.695 | 0.341 | 0.124/0.356 | candidate | 0.000m/0.0deg | envelope:31941 | 6/6 deadline | PASS |
| 11 | 12 | 1.0386 | 0.741 | - | 0.730 | 0.285 | 0.160/0.356 | candidate | 0.051m/0.0deg | envelope:33338 | 6/6 deadline | PASS |
| 12 | 12 | 1.0386 | 0.741 | - | 0.730 | 0.285 | 0.160/0.356 | fixed_fallback | - | envelope:51165 | 12/6 deadline | FAIL |

#### pool_resilience / 001 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | search | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|---|
| 0 | 1 | 0.0528 | 0.987 | 1.000 | 0.980 | 0.696 | 0.000/0.026 | candidate | 0.051m/0.0deg | envelope:8297 | 60/60 | PASS |
| 1 | 2 | 0.1056 | 0.974 | 1.000 | 0.980 | 0.577 | 0.000/0.052 | candidate | 0.051m/0.0deg | envelope:23450 | 60/60 | PASS |
| 2 | 3 | 0.1584 | 0.961 | 1.000 | 0.980 | 0.271 | 0.024/0.053 | candidate | 0.051m/0.0deg | envelope:35656 | 60/60 | PASS |
| 3 | 4 | 0.2112 | 0.948 | - | 1.060 | 0.373 | 0.024/0.079 | candidate | 0.000m/0.0deg | envelope:51074 | 60/60 deadline | PASS |
| 4 | 5 | 0.2640 | 0.935 | - | 1.092 | 0.390 | 0.024/0.105 | candidate | 0.000m/0.0deg | envelope:54162 | 60/60 deadline | PASS |
| 5 | 6 | 0.3168 | 0.922 | - | 1.113 | 0.268 | 0.048/0.106 | candidate | 0.000m/0.0deg | envelope:63161 | 60/60 deadline | PASS |
| 6 | 7 | 0.3691 | 0.909 | - | 0.921 | 0.230 | 0.060/0.118 | fixed_fallback | 0.097m/0.1deg | envelope:112484 | 120/60 deadline | PASS |
| 7 | 7 | 0.3691 | 0.909 | - | 0.921 | 0.230 | 0.060/0.118 | fixed_fallback | - | envelope:122577 | 120/60 deadline | FAIL |

## Interpretation

At least one mode's physical validity failed. Fill and placed comparisons are diagnostic history, not a valid competition result.
