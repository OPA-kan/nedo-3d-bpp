# Lookahead sample-simulator comparison

- Timestamp: `2026-07-28T05:32:58+00:00`
- Git SHA: `32da81638d9cd7942ca99c211433cdd7ad079256`
- Config: `/home/runner/work/nedo-3d-bpp/nedo-3d-bpp/simulator/configs/sample_config.json`
- Run ID: `30331700531`
- Scope: bundled simulator proxy; not a SIGNATE leaderboard score

## Mode summary

| mode | process | physics | placed | mean fill | residual feasible | CoG z | surface TV | max policy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| weighted | 0 | FAIL | 14 | 9.890238 | 0.800 | 0.877 | 0.0179 | 6.595s |
| depth2 | 0 | FAIL | 14 | 9.890238 | 0.800 | 0.877 | 0.0179 | 6.585s |
| pool_resilience | 0 | FAIL | 14 | 9.890238 | 0.800 | 0.877 | 0.0179 | 6.545s |

## Case history

### weighted

| case | fill | placed | volume | residual feasible | CoG z | surface TV | valid | safe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 000 | 11.954776 | 7/41 | 0.5522 | - | 0.844 | 0.0192 | False | False |
| 001 | 7.825700 | 7/42 | 0.3691 | 0.800 | 0.911 | 0.0166 | False | False |

#### weighted / 000 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | top rejection | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 0 | 1 | 0.0731 | 0.982 | - | 0.970 | 0.502 | 0.000/0.036 | containment:568 | PASS |
| 1 | 2 | 0.1865 | 0.953 | - | 0.976 | -0.148 | 0.056/0.036 | containment:1822 | PASS |
| 2 | 3 | 0.2597 | 0.935 | - | 1.048 | 0.035 | 0.056/0.073 | containment:3210 | PASS |
| 3 | 4 | 0.3328 | 0.917 | - | 1.092 | -0.080 | 0.093/0.073 | containment:4263 | PASS |
| 4 | 5 | 0.4059 | 0.899 | - | 0.920 | -0.065 | 0.111/0.091 | containment:13276 | PASS |
| 5 | 6 | 0.4790 | 0.880 | - | 0.841 | -0.055 | 0.129/0.109 | containment:12067 | PASS |
| 6 | 7 | 0.5522 | 0.862 | - | 0.844 | -0.028 | 0.132/0.142 | containment:17279 | PASS |
| 7 | 7 | 0.5522 | 0.862 | - | 0.844 | -0.028 | 0.132/0.142 | containment:49192 | FAIL |

#### weighted / 001 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | top rejection | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 0 | 1 | 0.0528 | 0.987 | 1.000 | 0.980 | 0.696 | 0.000/0.026 | containment:8297 | PASS |
| 1 | 2 | 0.1056 | 0.974 | 1.000 | 0.980 | 0.577 | 0.000/0.052 | containment:23450 | PASS |
| 2 | 3 | 0.1584 | 0.961 | 1.000 | 0.980 | 0.271 | 0.024/0.053 | containment:35656 | PASS |
| 3 | 4 | 0.2112 | 0.948 | 1.000 | 1.040 | 0.318 | 0.024/0.079 | containment:45436 | PASS |
| 4 | 5 | 0.2640 | 0.935 | - | 1.076 | 0.186 | 0.048/0.080 | containment:68376 | PASS |
| 5 | 6 | 0.3168 | 0.922 | 0.000 | 1.100 | 0.249 | 0.048/0.106 | containment:63204 | PASS |
| 6 | 7 | 0.3691 | 0.909 | - | 0.911 | 0.214 | 0.060/0.118 | containment:104430 | PASS |
| 7 | 7 | 0.3691 | 0.909 | - | 0.911 | 0.214 | 0.060/0.118 | containment:106962 | FAIL |

### depth2

| case | fill | placed | volume | residual feasible | CoG z | surface TV | valid | safe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 000 | 11.954776 | 7/41 | 0.5522 | - | 0.844 | 0.0192 | False | False |
| 001 | 7.825700 | 7/42 | 0.3691 | 0.800 | 0.911 | 0.0166 | False | False |

#### depth2 / 000 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | top rejection | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 0 | 1 | 0.0731 | 0.982 | - | 0.970 | 0.502 | 0.000/0.036 | containment:568 | PASS |
| 1 | 2 | 0.1865 | 0.953 | - | 0.976 | -0.148 | 0.056/0.036 | containment:1822 | PASS |
| 2 | 3 | 0.2597 | 0.935 | - | 1.048 | 0.035 | 0.056/0.073 | containment:3210 | PASS |
| 3 | 4 | 0.3328 | 0.917 | - | 1.092 | -0.080 | 0.093/0.073 | containment:4263 | PASS |
| 4 | 5 | 0.4059 | 0.899 | - | 0.920 | -0.065 | 0.111/0.091 | containment:13276 | PASS |
| 5 | 6 | 0.4790 | 0.880 | - | 0.841 | -0.055 | 0.129/0.109 | containment:12067 | PASS |
| 6 | 7 | 0.5522 | 0.862 | - | 0.844 | -0.028 | 0.132/0.142 | containment:17279 | PASS |
| 7 | 7 | 0.5522 | 0.862 | - | 0.844 | -0.028 | 0.132/0.142 | containment:49192 | FAIL |

#### depth2 / 001 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | top rejection | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 0 | 1 | 0.0528 | 0.987 | 1.000 | 0.980 | 0.696 | 0.000/0.026 | containment:8297 | PASS |
| 1 | 2 | 0.1056 | 0.974 | 1.000 | 0.980 | 0.577 | 0.000/0.052 | containment:23450 | PASS |
| 2 | 3 | 0.1584 | 0.961 | 1.000 | 0.980 | 0.271 | 0.024/0.053 | containment:35656 | PASS |
| 3 | 4 | 0.2112 | 0.948 | 1.000 | 1.040 | 0.318 | 0.024/0.079 | containment:45436 | PASS |
| 4 | 5 | 0.2640 | 0.935 | - | 1.076 | 0.186 | 0.048/0.080 | containment:68376 | PASS |
| 5 | 6 | 0.3168 | 0.922 | 0.000 | 1.100 | 0.249 | 0.048/0.106 | containment:63204 | PASS |
| 6 | 7 | 0.3691 | 0.909 | - | 0.911 | 0.214 | 0.060/0.118 | containment:103102 | PASS |
| 7 | 7 | 0.3691 | 0.909 | - | 0.911 | 0.214 | 0.060/0.118 | containment:106962 | FAIL |

### pool_resilience

| case | fill | placed | volume | residual feasible | CoG z | surface TV | valid | safe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 000 | 11.954776 | 7/41 | 0.5522 | - | 0.844 | 0.0192 | False | False |
| 001 | 7.825700 | 7/42 | 0.3691 | 0.800 | 0.911 | 0.0166 | False | False |

#### pool_resilience / 000 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | top rejection | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 0 | 1 | 0.0731 | 0.982 | - | 0.970 | 0.502 | 0.000/0.036 | containment:568 | PASS |
| 1 | 2 | 0.1865 | 0.953 | - | 0.976 | -0.148 | 0.056/0.036 | containment:1822 | PASS |
| 2 | 3 | 0.2597 | 0.935 | - | 1.048 | 0.035 | 0.056/0.073 | containment:3210 | PASS |
| 3 | 4 | 0.3328 | 0.917 | - | 1.092 | -0.080 | 0.093/0.073 | containment:4263 | PASS |
| 4 | 5 | 0.4059 | 0.899 | - | 0.920 | -0.065 | 0.111/0.091 | containment:13276 | PASS |
| 5 | 6 | 0.4790 | 0.880 | - | 0.841 | -0.055 | 0.129/0.109 | containment:12067 | PASS |
| 6 | 7 | 0.5522 | 0.862 | - | 0.844 | -0.028 | 0.132/0.142 | containment:17279 | PASS |
| 7 | 7 | 0.5522 | 0.862 | - | 0.844 | -0.028 | 0.132/0.142 | containment:49192 | FAIL |

#### pool_resilience / 001 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | top rejection | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 0 | 1 | 0.0528 | 0.987 | 1.000 | 0.980 | 0.696 | 0.000/0.026 | containment:8297 | PASS |
| 1 | 2 | 0.1056 | 0.974 | 1.000 | 0.980 | 0.577 | 0.000/0.052 | containment:23450 | PASS |
| 2 | 3 | 0.1584 | 0.961 | 1.000 | 0.980 | 0.271 | 0.024/0.053 | containment:35656 | PASS |
| 3 | 4 | 0.2112 | 0.948 | 1.000 | 1.040 | 0.318 | 0.024/0.079 | containment:45436 | PASS |
| 4 | 5 | 0.2640 | 0.935 | - | 1.076 | 0.186 | 0.048/0.080 | containment:68376 | PASS |
| 5 | 6 | 0.3168 | 0.922 | 0.000 | 1.100 | 0.249 | 0.048/0.106 | containment:63204 | PASS |
| 6 | 7 | 0.3691 | 0.909 | - | 0.911 | 0.214 | 0.060/0.118 | containment:103102 | PASS |
| 7 | 7 | 0.3691 | 0.909 | - | 0.911 | 0.214 | 0.060/0.118 | containment:106962 | FAIL |

## Interpretation

At least one mode's physical validity failed. Fill and placed comparisons are diagnostic history, not a valid competition result.
