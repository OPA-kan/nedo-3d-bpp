# One changed placement: flips, H against crossings (cf_flip.py)

H: share of distinct alternatives that turn a miss into a crossing; X (crossings branched the same way): share that turn a crossing into a miss.

| group | split | | distinct branches | flips | flip share | mean margin change |
|---|---|---|---:|---:|---:|---:|
| H | all |  | 187 | 26 | 0.14 | -0.77 |
| H | by kind | a pose the ladder vetoed | 28 | 5 | 0.18 | +0.39 |
| H | by kind | another rung's best | 4 | 1 | 0.25 | -6.00 |
| H | by kind | ladder pick (vetoed downstream) | 15 | 1 | 0.07 | -1.87 |
| H | by kind | most usable surface left | 41 | 10 | 0.24 | +0.73 |
| H | by kind | next in the rung | 9 | 1 | 0.11 | -7.78 |
| H | by kind | veto (agent's next answer) | 90 | 8 | 0.09 | -0.70 |
| H | by lead | lead 1-3 | 45 | 5 | 0.11 | +0.31 |
| H | by lead | lead 4-9 | 61 | 12 | 0.20 | +0.54 |
| H | by lead | lead >= 10 | 81 | 9 | 0.11 | -2.36 |
| X | all |  | 71 | 19 | 0.27 | +0.23 |
| X | by kind | a pose the ladder vetoed | 10 | 3 | 0.30 | -0.10 |
| X | by kind | ladder pick (vetoed downstream) | 4 | 2 | 0.50 | -0.75 |
| X | by kind | most usable surface left | 23 | 10 | 0.43 | +1.09 |
| X | by kind | next in the rung | 3 | 0 | 0.00 | +0.67 |
| X | by kind | veto (agent's next answer) | 31 | 4 | 0.13 | -0.23 |
| X | by lead | lead 1-3 | 8 | 0 | 0.00 | +2.75 |
| X | by lead | lead 4-9 | 31 | 13 | 0.42 | -0.23 |
| X | by lead | lead >= 10 | 32 | 6 | 0.19 | +0.03 |
