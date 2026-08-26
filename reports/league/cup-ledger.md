# Diversity Cup ledger

Rolling preregistration for cup events (design:
`reports/self-play-packing/diversity-cup-design.md`, hosting procedure:
`reports/league/cup-hosting-runbook.md`). **Append the row BEFORE
dispatching** — the row is the preregistration. Streams must be fresh,
never-reused primes from the 401-599 pool; never eval variants, never
season-wave primes. Fill the result columns after the standings
artifact is read.

| cup | date | vs model (learning run) | champion | streams (000/001 primes) | run | strict pairs | novel board rate | notes |
|---|---|---|---|---|---|---|---|---|
| 001 | 2026-08-26 | 32890092906 | pi2-pref-w6 プリフヒバリ | 000: 401,419,431,433 · 001: 409,421 | 32920552027 | 15 | 0.81-0.84 | inaugural; 94/94 disagreements forked (budget never binding), strict rate 16%; race tables almost all incomparable |

| 002 | 2026-08-26 | 32890092906 | pi2-pref-w6 プリフヒバリ | 000: 409,421,439,443 · 001: 401,419 | 32925104549 | 17 | 0.82-0.95 | five-horse field incl ジ・アーモンド (current-agent, ジ系列, named at this cup); **mined under the OLD 5-head rule** (episodes dispatched 03:04:57Z on `88fc535`, before the surface-exclusion fix `1087667` at 05:27:29Z — corrected in the row below, this row's own earlier text was wrong); standings job crashed on missing post-shake heads for ジ・アーモンド's 5 non-genuine episodes, fixed and recomputed locally from the same run's artifacts (no re-run) — see `reports/league/diversity-cup-002.md`; ジ・アーモンド mined 0/19 strict pairs and missed candidate support on 132/164 steps |
| 003 アーモンドビレッジ | 2026-08-26 | 32890092906 | pi2-pref-w6 プリフヒバリ | 000: 449,457,461,463 · 001: 431,433 | 32935678296 | 56 | 0.79-0.96 | first cup run entirely under the **4-head dominance rule** (surface excluded, fix `1087667`); dispatched via the one-click `host-diversity-cup.yml` host, which auto-drew fresh primes and preregistered this row; standings succeeded cleanly this time (no crash) — see `reports/league/diversity-cup-003.md`; ジ・アーモンド mined 11/19 strict pairs (vs 0/19 in Cup 002) but reached genuine termination in 0/6 cells (worse than Cup 002's 1/6) |

Pool allocation note: primes used so far — 000: 401, 409, 419, 421,
431, 433, 439, 443, 449, 457, 461, 463 · 001: 401, 409, 419, 421, 431,
433 (a prime may be reused on the OTHER source only if the ledger
shows it was never run on that source).

Methodology boundary: Cup 001 AND Cup 002's fork verdicts (strict
pairs, novel board rate) were both decided under the original 5-head
dominance rule, which included `surface_total_variation_delta` — Cup
002's episodes ran two hours before the exclusion fix landed, despite
what an earlier version of this ledger said. **Cup 003 is the first
cup scored entirely under the 4-head rule** (design:
`reports/self-play-packing/diversity-cup-design.md`, "Cup 002+
amendment: surface_total_variation drops out of the fork dominance
rule"; fix commit `1087667`). Cup 001/002 numbers are not directly
comparable to Cup 003+; the strict-pairs jump (17 -> 56 pairs, same
6-cell format and champion) is itself evidence the axis was
suppressing real dominance verdicts.
