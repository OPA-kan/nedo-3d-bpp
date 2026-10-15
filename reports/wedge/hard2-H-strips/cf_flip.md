# One changed placement: flips, H against crossings (cf_flip.py)

H: share of distinct alternatives that turn a miss into a crossing; X (crossings branched the same way): share that turn a crossing into a miss.

| group | split | | distinct branches | flips | flip share | mean margin change |
|---|---|---|---:|---:|---:|---:|
| H | all |  | 170 | 26 | 0.15 | -0.96 |
| H | by kind | a pose the ladder vetoed | 25 | 5 | 0.20 | +0.28 |
| H | by kind | another rung's best | 3 | 1 | 0.33 | -8.00 |
| H | by kind | ladder pick (vetoed downstream) | 12 | 1 | 0.08 | -2.33 |
| H | by kind | most usable surface left | 38 | 10 | 0.26 | +0.53 |
| H | by kind | next in the rung | 7 | 1 | 0.14 | -10.71 |
| H | by kind | veto (agent's next answer) | 85 | 8 | 0.09 | -0.75 |
| H | by lead | lead 1-3 | 45 | 5 | 0.11 | +0.31 |
| H | by lead | lead 4-9 | 48 | 12 | 0.25 | +0.52 |
| H | by lead | lead >= 10 | 77 | 9 | 0.12 | -2.64 |
| X | all |  | 62 | 19 | 0.31 | +0.13 |
| X | by kind | a pose the ladder vetoed | 8 | 3 | 0.38 | -0.38 |
| X | by kind | ladder pick (vetoed downstream) | 4 | 2 | 0.50 | -0.75 |
| X | by kind | most usable surface left | 21 | 10 | 0.48 | +1.00 |
| X | by kind | next in the rung | 1 | 0 | 0.00 | +0.00 |
| X | by kind | veto (agent's next answer) | 28 | 4 | 0.14 | -0.25 |
| X | by lead | lead 1-3 | 8 | 0 | 0.00 | +2.75 |
| X | by lead | lead 4-9 | 31 | 13 | 0.42 | -0.23 |
| X | by lead | lead >= 10 | 23 | 6 | 0.26 | -0.30 |
