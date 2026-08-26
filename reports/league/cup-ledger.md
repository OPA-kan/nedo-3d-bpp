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

| 002 | 2026-08-26 | 32890092906 | pi2-pref-w6 プリフヒバリ | 000: 409,421,439,443 · 001: 401,419 | 32925104549 | 17 | 0.82-0.95 | five-horse field incl ジ・アーモンド (current-agent, ジ系列, named at this cup), 4-head dominance rule (surface excluded); standings job crashed on missing post-shake heads for its 5 non-genuine episodes, fixed and recomputed locally from the same run's artifacts (no re-run) — see `reports/league/diversity-cup-002.md`; ジ・アーモンド mined 0/19 strict pairs and missed candidate support on 132/164 steps |

| 003 | 2026-08-26 | 32890092906 | pi2-pref-w6 プリフヒバリ | 000: 449,457,461,463 · 001: 431,433 | pending | pending | pending | preregistered five-horse field incl current-agent |

Pool allocation note: primes used so far: 401, 409, 419, 421, 431, 433
(cup 001; note 000/001 sides used are what the row lists — a prime may
be reused on the OTHER source only if the ledger shows it was never
run on that source).

Methodology boundary: Cup 001's fork verdicts (strict pairs, novel
board rate) were decided under the original 5-head dominance rule,
which included `surface_total_variation_delta`. From Cup 002 onward
that axis is excluded from the dominance decision (design:
`reports/self-play-packing/diversity-cup-design.md`, "Cup 002+
amendment: surface_total_variation drops out of the fork dominance
rule"). Cup 001's numbers are not directly comparable to Cup 002+.
