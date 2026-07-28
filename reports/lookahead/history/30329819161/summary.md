# Lookahead sample-simulator comparison

- Timestamp: `2026-07-28T04:55:03+00:00`
- Git SHA: `f405c3ad7fe7ffbf4030fc75b31e406cb9ece840`
- Config: `/home/runner/work/nedo-3d-bpp/nedo-3d-bpp/simulator/configs/sample_config.json`
- Run ID: `30329819161`
- Scope: bundled simulator proxy; not a SIGNATE leaderboard score

## Mode summary

| mode | process | physics | placed | mean fill | residual feasible | CoG z | surface TV | max policy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| weighted | 0 | FAIL | 14 | 9.890238 | 0.400 | 0.877 | 0.0179 | 6.557s |
| depth2 | 0 | FAIL | 14 | 9.890238 | 0.400 | 0.877 | 0.0179 | 6.549s |
| pool_resilience | 0 | FAIL | 14 | 9.890238 | 0.400 | 0.877 | 0.0179 | 6.519s |

## Case history

### weighted

| case | fill | placed | volume | residual feasible | CoG z | surface TV | valid | safe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 000 | 11.954776 | 7/41 | 0.5522 | 0.000 | 0.844 | 0.0192 | False | False |
| 001 | 7.825700 | 7/42 | 0.3691 | 0.800 | 0.911 | 0.0166 | False | False |

#### weighted / 000 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | surface TV | flat edges | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0 | 1 | 0.0731 | 0.982 | - | 0.970 | 0.0060 | 0.991 | PASS |
| 1 | 2 | 0.1865 | 0.953 | - | 0.976 | 0.0085 | 0.988 | PASS |
| 2 | 3 | 0.2597 | 0.935 | - | 1.048 | 0.0100 | 0.988 | PASS |
| 3 | 4 | 0.3328 | 0.917 | - | 1.092 | 0.0122 | 0.984 | PASS |
| 4 | 5 | 0.4059 | 0.899 | - | 0.920 | 0.0139 | 0.976 | PASS |
| 5 | 6 | 0.4790 | 0.880 | - | 0.841 | 0.0155 | 0.976 | PASS |
| 6 | 7 | 0.5522 | 0.862 | - | 0.844 | 0.0192 | 0.973 | PASS |
| 7 | 7 | 0.5522 | 0.862 | - | 0.844 | 0.0192 | 0.973 | FAIL |

#### weighted / 001 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | surface TV | flat edges | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0 | 1 | 0.0528 | 0.987 | 1.000 | 0.980 | 0.0080 | 0.986 | PASS |
| 1 | 2 | 0.1056 | 0.974 | 1.000 | 0.980 | 0.0093 | 0.983 | PASS |
| 2 | 3 | 0.1584 | 0.961 | 1.000 | 0.980 | 0.0111 | 0.977 | PASS |
| 3 | 4 | 0.2112 | 0.948 | 1.000 | 1.040 | 0.0124 | 0.977 | PASS |
| 4 | 5 | 0.2640 | 0.935 | - | 1.076 | 0.0142 | 0.977 | PASS |
| 5 | 6 | 0.3168 | 0.922 | 0.000 | 1.100 | 0.0162 | 0.974 | PASS |
| 6 | 7 | 0.3691 | 0.909 | - | 0.911 | 0.0166 | 0.970 | PASS |
| 7 | 7 | 0.3691 | 0.909 | - | 0.911 | 0.0166 | 0.970 | FAIL |

### depth2

| case | fill | placed | volume | residual feasible | CoG z | surface TV | valid | safe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 000 | 11.954776 | 7/41 | 0.5522 | 0.000 | 0.844 | 0.0192 | False | False |
| 001 | 7.825700 | 7/42 | 0.3691 | 0.800 | 0.911 | 0.0166 | False | False |

#### depth2 / 000 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | surface TV | flat edges | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0 | 1 | 0.0731 | 0.982 | - | 0.970 | 0.0060 | 0.991 | PASS |
| 1 | 2 | 0.1865 | 0.953 | - | 0.976 | 0.0085 | 0.988 | PASS |
| 2 | 3 | 0.2597 | 0.935 | - | 1.048 | 0.0100 | 0.988 | PASS |
| 3 | 4 | 0.3328 | 0.917 | - | 1.092 | 0.0122 | 0.984 | PASS |
| 4 | 5 | 0.4059 | 0.899 | - | 0.920 | 0.0139 | 0.976 | PASS |
| 5 | 6 | 0.4790 | 0.880 | - | 0.841 | 0.0155 | 0.976 | PASS |
| 6 | 7 | 0.5522 | 0.862 | - | 0.844 | 0.0192 | 0.973 | PASS |
| 7 | 7 | 0.5522 | 0.862 | - | 0.844 | 0.0192 | 0.973 | FAIL |

#### depth2 / 001 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | surface TV | flat edges | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0 | 1 | 0.0528 | 0.987 | 1.000 | 0.980 | 0.0080 | 0.986 | PASS |
| 1 | 2 | 0.1056 | 0.974 | 1.000 | 0.980 | 0.0093 | 0.983 | PASS |
| 2 | 3 | 0.1584 | 0.961 | 1.000 | 0.980 | 0.0111 | 0.977 | PASS |
| 3 | 4 | 0.2112 | 0.948 | 1.000 | 1.040 | 0.0124 | 0.977 | PASS |
| 4 | 5 | 0.2640 | 0.935 | - | 1.076 | 0.0142 | 0.977 | PASS |
| 5 | 6 | 0.3168 | 0.922 | 0.000 | 1.100 | 0.0162 | 0.974 | PASS |
| 6 | 7 | 0.3691 | 0.909 | - | 0.911 | 0.0166 | 0.970 | PASS |
| 7 | 7 | 0.3691 | 0.909 | - | 0.911 | 0.0166 | 0.970 | FAIL |

### pool_resilience

| case | fill | placed | volume | residual feasible | CoG z | surface TV | valid | safe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 000 | 11.954776 | 7/41 | 0.5522 | 0.000 | 0.844 | 0.0192 | False | False |
| 001 | 7.825700 | 7/42 | 0.3691 | 0.800 | 0.911 | 0.0166 | False | False |

#### pool_resilience / 000 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | surface TV | flat edges | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0 | 1 | 0.0731 | 0.982 | - | 0.970 | 0.0060 | 0.991 | PASS |
| 1 | 2 | 0.1865 | 0.953 | - | 0.976 | 0.0085 | 0.988 | PASS |
| 2 | 3 | 0.2597 | 0.935 | - | 1.048 | 0.0100 | 0.988 | PASS |
| 3 | 4 | 0.3328 | 0.917 | - | 1.092 | 0.0122 | 0.984 | PASS |
| 4 | 5 | 0.4059 | 0.899 | - | 0.920 | 0.0139 | 0.976 | PASS |
| 5 | 6 | 0.4790 | 0.880 | - | 0.841 | 0.0155 | 0.976 | PASS |
| 6 | 7 | 0.5522 | 0.862 | - | 0.844 | 0.0192 | 0.973 | PASS |
| 7 | 7 | 0.5522 | 0.862 | - | 0.844 | 0.0192 | 0.973 | FAIL |

#### pool_resilience / 001 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | surface TV | flat edges | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 0 | 1 | 0.0528 | 0.987 | 1.000 | 0.980 | 0.0080 | 0.986 | PASS |
| 1 | 2 | 0.1056 | 0.974 | 1.000 | 0.980 | 0.0093 | 0.983 | PASS |
| 2 | 3 | 0.1584 | 0.961 | 1.000 | 0.980 | 0.0111 | 0.977 | PASS |
| 3 | 4 | 0.2112 | 0.948 | 1.000 | 1.040 | 0.0124 | 0.977 | PASS |
| 4 | 5 | 0.2640 | 0.935 | - | 1.076 | 0.0142 | 0.977 | PASS |
| 5 | 6 | 0.3168 | 0.922 | 0.000 | 1.100 | 0.0162 | 0.974 | PASS |
| 6 | 7 | 0.3691 | 0.909 | - | 0.911 | 0.0166 | 0.970 | PASS |
| 7 | 7 | 0.3691 | 0.909 | - | 0.911 | 0.0166 | 0.970 | FAIL |

## Interpretation

At least one mode's physical validity failed. Fill and placed comparisons are diagnostic history, not a valid competition result.
