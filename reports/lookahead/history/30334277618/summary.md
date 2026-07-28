# Lookahead sample-simulator comparison

- Timestamp: `2026-07-28T06:22:00+00:00`
- Git SHA: `149559b04664a6ad71289404717ef8affc69e93b`
- Config: `/home/runner/work/nedo-3d-bpp/nedo-3d-bpp/simulator/configs/sample_config.json`
- Run ID: `30334277618`
- Scope: bundled simulator proxy; not a SIGNATE leaderboard score

## Mode summary

| mode | process | physics | placed | mean fill | residual feasible | CoG z | surface TV | max policy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| weighted | 0 | FAIL | 26 | 14.163902 | 1.000 | 0.713 | 0.0410 | 9.873s |
| depth2 | 0 | FAIL | 26 | 14.163902 | 1.000 | 0.713 | 0.0410 | 10.009s |
| pool_resilience | 0 | FAIL | 26 | 14.163902 | 1.000 | 0.713 | 0.0410 | 9.954s |

## Case history

### weighted

| case | fill | placed | volume | residual feasible | CoG z | surface TV | valid | safe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 000 | 12.774596 | 13/41 | 1.1117 | - | 0.698 | 0.0504 | False | False |
| 001 | 15.553209 | 13/42 | 0.8893 | 1.000 | 0.729 | 0.0316 | False | False |

#### weighted / 000 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|
| 0 | 1 | 0.1134 | 0.972 | - | 0.415 | 0.780 | 0.000/0.056 | release_candidate | 0.052m/0.0deg | envelope:692 | PASS |
| 1 | 2 | 0.2268 | 0.943 | - | 0.415 | 0.781 | 0.000/0.113 | release_candidate | 0.052m/0.1deg | envelope:1908 | PASS |
| 2 | 3 | 0.3402 | 0.915 | - | 0.415 | 0.523 | 0.027/0.142 | release_candidate | 0.052m/0.0deg | envelope:3769 | PASS |
| 3 | 4 | 0.4536 | 0.887 | - | 0.415 | 0.392 | 0.055/0.170 | release_candidate | 0.052m/0.0deg | envelope:5941 | PASS |
| 4 | 5 | 0.5267 | 0.869 | - | 0.500 | 0.377 | 0.063/0.199 | candidate | 0.051m/0.0deg | envelope:7304 | PASS |
| 5 | 6 | 0.5999 | 0.850 | - | 0.581 | 0.424 | 0.063/0.236 | candidate | 0.000m/0.0deg | envelope:11923 | PASS |
| 6 | 7 | 0.6730 | 0.832 | - | 0.644 | 0.465 | 0.063/0.272 | candidate | 0.000m/0.0deg | envelope:19746 | PASS |
| 7 | 8 | 0.7461 | 0.814 | - | 0.693 | 0.421 | 0.079/0.292 | candidate | 0.000m/0.0deg | envelope:24100 | PASS |
| 8 | 9 | 0.8192 | 0.796 | - | 0.733 | 0.391 | 0.093/0.315 | candidate | 0.000m/0.0deg | envelope:29639 | PASS |
| 9 | 10 | 0.8924 | 0.777 | - | 0.693 | 0.364 | 0.108/0.335 | release_candidate | 0.052m/0.0deg | envelope:33287 | PASS |
| 10 | 11 | 0.9655 | 0.759 | - | 0.702 | 0.352 | 0.115/0.365 | candidate | 0.000m/0.0deg | envelope:37392 | PASS |
| 11 | 12 | 1.0386 | 0.741 | - | 0.737 | 0.285 | 0.151/0.365 | candidate | 0.051m/0.0deg | envelope:47856 | PASS |
| 12 | 13 | 1.1117 | 0.723 | - | 0.698 | 0.227 | 0.187/0.365 | release_candidate | 0.052m/0.0deg | envelope:36519 | PASS |
| 13 | 13 | 1.1117 | 0.723 | - | 0.698 | 0.227 | 0.187/0.365 | - | 0.052m/0.0deg | - | FAIL |

#### weighted / 001 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|
| 0 | 1 | 0.0528 | 0.987 | 1.000 | 0.980 | 0.696 | 0.000/0.026 | candidate | 0.051m/0.0deg | envelope:8297 | PASS |
| 1 | 2 | 0.1056 | 0.974 | 1.000 | 0.980 | 0.577 | 0.000/0.052 | candidate | 0.051m/0.0deg | envelope:23450 | PASS |
| 2 | 3 | 0.1584 | 0.961 | 1.000 | 0.980 | 0.271 | 0.024/0.053 | candidate | 0.051m/0.0deg | envelope:35656 | PASS |
| 3 | 4 | 0.2112 | 0.948 | - | 1.060 | 0.373 | 0.024/0.079 | candidate | 0.000m/0.0deg | envelope:39200 | PASS |
| 4 | 5 | 0.2640 | 0.935 | - | 1.092 | 0.390 | 0.024/0.105 | candidate | 0.000m/0.0deg | envelope:48772 | PASS |
| 5 | 6 | 0.3371 | 0.917 | - | 0.892 | 0.277 | 0.055/0.109 | release_candidate | 0.052m/0.0deg | envelope:54472 | PASS |
| 6 | 7 | 0.4103 | 0.899 | - | 0.770 | 0.128 | 0.091/0.109 | release_candidate | 0.052m/0.0deg | envelope:53926 | PASS |
| 7 | 8 | 0.4834 | 0.881 | - | 0.763 | 0.025 | 0.126/0.109 | candidate | 0.000m/0.0deg | envelope:47784 | PASS |
| 8 | 9 | 0.5968 | 0.853 | - | 0.655 | -0.071 | 0.179/0.112 | release_candidate | 0.052m/0.0deg | envelope:46964 | PASS |
| 9 | 10 | 0.6699 | 0.835 | - | 0.631 | -0.107 | 0.212/0.114 | candidate | 0.000m/0.0deg | envelope:52219 | PASS |
| 10 | 11 | 0.7430 | 0.816 | - | 0.637 | -0.148 | 0.248/0.114 | candidate | 0.000m/0.0deg | envelope:53771 | PASS |
| 11 | 12 | 0.8162 | 0.798 | - | 0.686 | -0.168 | 0.284/0.114 | candidate | 0.000m/0.0deg | envelope:41720 | PASS |
| 12 | 13 | 0.8893 | 0.780 | - | 0.729 | -0.201 | 0.320/0.114 | candidate | 0.000m/0.0deg | envelope:64307 | PASS |
| 13 | 13 | 0.8893 | 0.780 | - | 0.729 | -0.201 | 0.320/0.114 | fixed_fallback | 0.000m/0.0deg | envelope:49857 | FAIL |

### depth2

| case | fill | placed | volume | residual feasible | CoG z | surface TV | valid | safe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 000 | 12.774596 | 13/41 | 1.1117 | - | 0.698 | 0.0504 | False | False |
| 001 | 15.553209 | 13/42 | 0.8893 | 1.000 | 0.729 | 0.0316 | False | False |

#### depth2 / 000 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|
| 0 | 1 | 0.1134 | 0.972 | - | 0.415 | 0.780 | 0.000/0.056 | release_candidate | 0.052m/0.0deg | envelope:692 | PASS |
| 1 | 2 | 0.2268 | 0.943 | - | 0.415 | 0.781 | 0.000/0.113 | release_candidate | 0.052m/0.1deg | envelope:1908 | PASS |
| 2 | 3 | 0.3402 | 0.915 | - | 0.415 | 0.523 | 0.027/0.142 | release_candidate | 0.052m/0.0deg | envelope:3769 | PASS |
| 3 | 4 | 0.4536 | 0.887 | - | 0.415 | 0.392 | 0.055/0.170 | release_candidate | 0.052m/0.0deg | envelope:5941 | PASS |
| 4 | 5 | 0.5267 | 0.869 | - | 0.500 | 0.377 | 0.063/0.199 | candidate | 0.051m/0.0deg | envelope:7304 | PASS |
| 5 | 6 | 0.5999 | 0.850 | - | 0.581 | 0.424 | 0.063/0.236 | candidate | 0.000m/0.0deg | envelope:11923 | PASS |
| 6 | 7 | 0.6730 | 0.832 | - | 0.644 | 0.465 | 0.063/0.272 | candidate | 0.000m/0.0deg | envelope:19746 | PASS |
| 7 | 8 | 0.7461 | 0.814 | - | 0.693 | 0.421 | 0.079/0.292 | candidate | 0.000m/0.0deg | envelope:24100 | PASS |
| 8 | 9 | 0.8192 | 0.796 | - | 0.733 | 0.391 | 0.093/0.315 | candidate | 0.000m/0.0deg | envelope:29639 | PASS |
| 9 | 10 | 0.8924 | 0.777 | - | 0.693 | 0.364 | 0.108/0.335 | release_candidate | 0.052m/0.0deg | envelope:33287 | PASS |
| 10 | 11 | 0.9655 | 0.759 | - | 0.702 | 0.352 | 0.115/0.365 | candidate | 0.000m/0.0deg | envelope:37392 | PASS |
| 11 | 12 | 1.0386 | 0.741 | - | 0.737 | 0.285 | 0.151/0.365 | candidate | 0.051m/0.0deg | envelope:47856 | PASS |
| 12 | 13 | 1.1117 | 0.723 | - | 0.698 | 0.227 | 0.187/0.365 | release_candidate | 0.052m/0.0deg | envelope:36519 | PASS |
| 13 | 13 | 1.1117 | 0.723 | - | 0.698 | 0.227 | 0.187/0.365 | - | 0.052m/0.0deg | - | FAIL |

#### depth2 / 001 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|
| 0 | 1 | 0.0528 | 0.987 | 1.000 | 0.980 | 0.696 | 0.000/0.026 | candidate | 0.051m/0.0deg | envelope:8297 | PASS |
| 1 | 2 | 0.1056 | 0.974 | 1.000 | 0.980 | 0.577 | 0.000/0.052 | candidate | 0.051m/0.0deg | envelope:23450 | PASS |
| 2 | 3 | 0.1584 | 0.961 | 1.000 | 0.980 | 0.271 | 0.024/0.053 | candidate | 0.051m/0.0deg | envelope:35656 | PASS |
| 3 | 4 | 0.2112 | 0.948 | - | 1.060 | 0.373 | 0.024/0.079 | candidate | 0.000m/0.0deg | envelope:39200 | PASS |
| 4 | 5 | 0.2640 | 0.935 | - | 1.092 | 0.390 | 0.024/0.105 | candidate | 0.000m/0.0deg | envelope:48772 | PASS |
| 5 | 6 | 0.3371 | 0.917 | - | 0.892 | 0.277 | 0.055/0.109 | release_candidate | 0.052m/0.0deg | envelope:54472 | PASS |
| 6 | 7 | 0.4103 | 0.899 | - | 0.770 | 0.128 | 0.091/0.109 | release_candidate | 0.052m/0.0deg | envelope:53926 | PASS |
| 7 | 8 | 0.4834 | 0.881 | - | 0.763 | 0.025 | 0.126/0.109 | candidate | 0.000m/0.0deg | envelope:47784 | PASS |
| 8 | 9 | 0.5968 | 0.853 | - | 0.655 | -0.071 | 0.179/0.112 | release_candidate | 0.052m/0.0deg | envelope:46964 | PASS |
| 9 | 10 | 0.6699 | 0.835 | - | 0.631 | -0.107 | 0.212/0.114 | candidate | 0.000m/0.0deg | envelope:52219 | PASS |
| 10 | 11 | 0.7430 | 0.816 | - | 0.637 | -0.148 | 0.248/0.114 | candidate | 0.000m/0.0deg | envelope:43119 | PASS |
| 11 | 12 | 0.8162 | 0.798 | - | 0.686 | -0.168 | 0.284/0.114 | candidate | 0.000m/0.0deg | envelope:41720 | PASS |
| 12 | 13 | 0.8893 | 0.780 | - | 0.729 | -0.201 | 0.320/0.114 | candidate | 0.000m/0.0deg | envelope:64307 | PASS |
| 13 | 13 | 0.8893 | 0.780 | - | 0.729 | -0.201 | 0.320/0.114 | - | 0.000m/0.0deg | - | FAIL |

### pool_resilience

| case | fill | placed | volume | residual feasible | CoG z | surface TV | valid | safe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 000 | 12.774596 | 13/41 | 1.1117 | - | 0.698 | 0.0504 | False | False |
| 001 | 15.553209 | 13/42 | 0.8893 | 1.000 | 0.729 | 0.0316 | False | False |

#### pool_resilience / 000 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|
| 0 | 1 | 0.1134 | 0.972 | - | 0.415 | 0.780 | 0.000/0.056 | release_candidate | 0.052m/0.0deg | envelope:692 | PASS |
| 1 | 2 | 0.2268 | 0.943 | - | 0.415 | 0.781 | 0.000/0.113 | release_candidate | 0.052m/0.1deg | envelope:1908 | PASS |
| 2 | 3 | 0.3402 | 0.915 | - | 0.415 | 0.523 | 0.027/0.142 | release_candidate | 0.052m/0.0deg | envelope:3769 | PASS |
| 3 | 4 | 0.4536 | 0.887 | - | 0.415 | 0.392 | 0.055/0.170 | release_candidate | 0.052m/0.0deg | envelope:5941 | PASS |
| 4 | 5 | 0.5267 | 0.869 | - | 0.500 | 0.377 | 0.063/0.199 | candidate | 0.051m/0.0deg | envelope:7304 | PASS |
| 5 | 6 | 0.5999 | 0.850 | - | 0.581 | 0.424 | 0.063/0.236 | candidate | 0.000m/0.0deg | envelope:11923 | PASS |
| 6 | 7 | 0.6730 | 0.832 | - | 0.644 | 0.465 | 0.063/0.272 | candidate | 0.000m/0.0deg | envelope:19746 | PASS |
| 7 | 8 | 0.7461 | 0.814 | - | 0.693 | 0.421 | 0.079/0.292 | candidate | 0.000m/0.0deg | envelope:24100 | PASS |
| 8 | 9 | 0.8192 | 0.796 | - | 0.733 | 0.391 | 0.093/0.315 | candidate | 0.000m/0.0deg | envelope:29639 | PASS |
| 9 | 10 | 0.8924 | 0.777 | - | 0.693 | 0.364 | 0.108/0.335 | release_candidate | 0.052m/0.0deg | envelope:33287 | PASS |
| 10 | 11 | 0.9655 | 0.759 | - | 0.702 | 0.352 | 0.115/0.365 | candidate | 0.000m/0.0deg | envelope:37392 | PASS |
| 11 | 12 | 1.0386 | 0.741 | - | 0.737 | 0.285 | 0.151/0.365 | candidate | 0.051m/0.0deg | envelope:47856 | PASS |
| 12 | 13 | 1.1117 | 0.723 | - | 0.698 | 0.227 | 0.187/0.365 | release_candidate | 0.052m/0.0deg | envelope:36519 | PASS |
| 13 | 13 | 1.1117 | 0.723 | - | 0.698 | 0.227 | 0.187/0.365 | - | 0.052m/0.0deg | - | FAIL |

#### pool_resilience / 001 per-step diagnostics

| step | placed | volume | empty ratio | residual feasible | CoG z | depth center | front/back | kind | settle d/angle | top rejection | physical |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|---|
| 0 | 1 | 0.0528 | 0.987 | 1.000 | 0.980 | 0.696 | 0.000/0.026 | candidate | 0.051m/0.0deg | envelope:8297 | PASS |
| 1 | 2 | 0.1056 | 0.974 | 1.000 | 0.980 | 0.577 | 0.000/0.052 | candidate | 0.051m/0.0deg | envelope:23450 | PASS |
| 2 | 3 | 0.1584 | 0.961 | 1.000 | 0.980 | 0.271 | 0.024/0.053 | candidate | 0.051m/0.0deg | envelope:35656 | PASS |
| 3 | 4 | 0.2112 | 0.948 | - | 1.060 | 0.373 | 0.024/0.079 | candidate | 0.000m/0.0deg | envelope:39200 | PASS |
| 4 | 5 | 0.2640 | 0.935 | - | 1.092 | 0.390 | 0.024/0.105 | candidate | 0.000m/0.0deg | envelope:48772 | PASS |
| 5 | 6 | 0.3371 | 0.917 | - | 0.892 | 0.277 | 0.055/0.109 | release_candidate | 0.052m/0.0deg | envelope:54472 | PASS |
| 6 | 7 | 0.4103 | 0.899 | - | 0.770 | 0.128 | 0.091/0.109 | release_candidate | 0.052m/0.0deg | envelope:53926 | PASS |
| 7 | 8 | 0.4834 | 0.881 | - | 0.763 | 0.025 | 0.126/0.109 | candidate | 0.000m/0.0deg | envelope:47784 | PASS |
| 8 | 9 | 0.5968 | 0.853 | - | 0.655 | -0.071 | 0.179/0.112 | release_candidate | 0.052m/0.0deg | envelope:46964 | PASS |
| 9 | 10 | 0.6699 | 0.835 | - | 0.631 | -0.107 | 0.212/0.114 | candidate | 0.000m/0.0deg | envelope:52219 | PASS |
| 10 | 11 | 0.7430 | 0.816 | - | 0.637 | -0.148 | 0.248/0.114 | candidate | 0.000m/0.0deg | envelope:43119 | PASS |
| 11 | 12 | 0.8162 | 0.798 | - | 0.686 | -0.168 | 0.284/0.114 | candidate | 0.000m/0.0deg | envelope:41720 | PASS |
| 12 | 13 | 0.8893 | 0.780 | - | 0.729 | -0.201 | 0.320/0.114 | candidate | 0.000m/0.0deg | envelope:64307 | PASS |
| 13 | 13 | 0.8893 | 0.780 | - | 0.729 | -0.201 | 0.320/0.114 | fixed_fallback | 0.000m/0.0deg | envelope:49857 | FAIL |

## Interpretation

At least one mode's physical validity failed. Fill and placed comparisons are diagnostic history, not a valid competition result.
