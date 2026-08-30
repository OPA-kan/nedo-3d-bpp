# Diversity Cup ledger

Rolling preregistration for cup events (design:
`reports/self-play-packing/diversity-cup-design.md`, hosting procedure:
`reports/league/cup-hosting-runbook.md`). **Append the row BEFORE
dispatching** — the row is the preregistration. Streams must be fresh,
never-reused primes from the 401-799 pool; never eval variants, never
season-wave primes. Fill the result columns after the standings
artifact is read.

| cup | date | vs model (learning run) | champion | streams (000/001 primes) | run | strict pairs | novel board rate | notes |
|---|---|---|---|---|---|---|---|---|
| 001 | 2026-08-26 | 32890092906 | pi2-pref-w6 プリフヒバリ | 000: 401,419,431,433 · 001: 409,421 | 32920552027 | 15 | 0.81-0.84 | inaugural; 94/94 disagreements forked (budget never binding), strict rate 16%; race tables almost all incomparable |

| 002 | 2026-08-26 | 32890092906 | pi2-pref-w6 プリフヒバリ | 000: 409,421,439,443 · 001: 401,419 | 32925104549 | 17 | 0.82-0.95 | five-horse field incl ジ・アーモンド (current-agent, ジ系列, named at this cup); **mined under the OLD 5-head rule** (episodes dispatched 03:04:57Z on `88fc535`, before the surface-exclusion fix `1087667` at 05:27:29Z — corrected in the row below, this row's own earlier text was wrong); standings job crashed on missing post-shake heads for ジ・アーモンド's 5 non-genuine episodes, fixed and recomputed locally from the same run's artifacts (no re-run) — see `reports/league/diversity-cup-002.md`; ジ・アーモンド mined 0/19 strict pairs and missed candidate support on 132/164 steps |
| 003 | 2026-08-26 | 32890092906 | pi2-pref-w6 プリフヒバリ | 000: 449,457,461,463 · 001: 431,433 | 32935678296 | 56 | 0.79-0.96 | 「アーモンドビレッジ」; first cup run entirely under the **4-head dominance rule** (surface excluded, fix `1087667`); dispatched via the one-click `host-diversity-cup.yml` host, which auto-drew fresh primes and preregistered this row; standings succeeded cleanly this time (no crash) — see `reports/league/diversity-cup-003.md`; ジ・アーモンド mined 11/19 strict pairs (vs 0/19 in Cup 002) but reached genuine termination in 0/6 cells (worse than Cup 002's 1/6) |

| 004 | 2026-08-26 | 32890092906 | pi2-pref-w6 プリフヒバリ | 000: 467,479,487,491 · 001: 439,443 | 32947834246 | 53 | 0.81-0.95 | run's own GitHub Actions title misreads "Diversity Cup 003" (cosmetic leftover of the `d681aaa` ledger bug; course is genuinely fresh, this row is correctly 004); ジ・アーモンド mined 6/15 strict pairs (down from 11/19 in Cup 003) and again reached genuine termination in 0/6 cells — see `reports/league/diversity-cup-004.md` |

| 005 | 2026-08-30 | 32890092906 | pi2-pref-w6 プリフヒバリ | 000: 499,503,509,521 · 001: 449,457 | 33291140628 | 75 | 0.83-0.96 | five-horse field incl ジ・アーモンド; 144 disagreements, 143 forks, 75 strict pairs; maximum terminal fill 38.8154 (ジ・アーモンド, 25 placed, non-genuine selected-action failure) — see `reports/league/diversity-cup-005.md` |

| 006 | 2026-08-30 | 32890092906 | pi2-pref-w6 プリフヒバリ | 000: 523,541,547,557 · 001: 461,463 | 33294741331 | 78 | 0.82-0.96 | first cup with rule-alpha@7908b09 (debut: 0/6 genuine termination, `rule_alpha_declined` x5 + 1 selected_action_failure, 105/105 candidate-support misses); ジ・アーモンド 0/6 genuine termination for a fifth straight cup; maximum terminal fill 41.857 (ジ・アーモンド, 26 placed, non-genuine selected_action_failure); pairs **corrected 79 -> 78** (rule-alpha 17 -> 16) — one fork was a one-horse race, not strict dominance; root cause fixed in `run_terminal_rollout_policy.pair_fork_winner` — see `reports/league/diversity-cup-006.md` |

| 007 | 2026-08-30 | 32890092906 | pi2-pref-w6 プリフヒバリ | 000: 563,569,571,577 · 001: 467,479 | 33297401046 | 83 | 0.78-0.95 | still rule-alpha@7908b09 (dispatched from `3b95cfc`, before the `f54abbc` vendor — Cup 008 is the first on `803fd6f`); largest harvest yet; **rule-alpha the most efficient miner in the field** (18 strict from 22 forks = 82%, 78261 pairs/M step-equiv, and 12 actor wins to 6 champion — the only winning record vs the champion); ジ・アーモンド collapsed to 3/14 strict (21%) and 0/6 genuine termination for a sixth straight cup; maximum terminal fill 36.069 (ジ・アーモンド, 23 placed, non-genuine selected_action_failure); **first cup collected under the one-horse-race fix — zero one-sided verdicts, analyzer/builder/jsonl all agree at 83** — see `reports/league/diversity-cup-007.md` |

| 008 | 2026-08-30 | 32890092906 | pi2-pref-w6 プリフヒバリ | 000: 587,593,599,601 · 001: 487,491 | 33299902464 | 71 | 0.79-0.96 | first cup on the extended 401-799 pool and **first on rule-alpha@803fd6f**; rule-alpha took the cup's maximum terminal fill for the first time (39.917, 23 placed, single-empty-noshelf-000-599, beating ジ・アーモンド's 32.575 in the same cell — not an all-time record, Cup 006's 41.857 stands) and holds the best strict rate by far (8/11 = 73%, 7-1 vs the champion); ジ・アーモンド 0/6 genuine termination for a seventh straight cup; **exposed the candidate-support mismatch — rule-alpha 89/89 = 100% of its executed actions absent from the candidate provider's set, ジ・アーモンド 78%, the three rule studs 0%** — so Cup 009 is deliberately deferred while the candidate set is fixed — see `reports/league/diversity-cup-008.md` |

Pool allocation note: primes used so far (regenerated from the table
above) — 000 (32): 401, 409, 419, 421, 431, 433, 439, 443, 449, 457, 461, 463, 467, 479, 487, 491, 499, 503, 509, 521, 523, 541, 547, 557, 563, 569, 571, 577, 587, 593, 599, 601 · 001 (16): 401, 409, 419, 421, 431, 433, 439, 443, 449, 457, 461, 463, 467, 479, 487, 491 (a prime may be reused on the OTHER source only if the ledger shows
it was never run on that source).

**Pool extension 401-599 → 401-799 (2026-08-30, after Cup 007).**
After Cup 007 the original pool held 31 primes per source and source
000 was down to three (587, 593, 599) against a four-cell requirement,
so `host_diversity_cup.allocate_course` raised "stream pool exhausted
for source 000: need 4, have 3" and Cup 008 could not be hosted at
all. Coordinated and resolved by extending the pool with primes
601-799 (30 more per source, 61 each now), which remain disjoint from
the frozen eval variants (all ≤ 197) and every season-1 wave prime
(all ≤ 379) — verified by scanning every prime referenced anywhere in
the repository, whose maximum was 599.

**The window lives in two places and they must move together:** the
pool block in `build_scenario_matrix.STREAM_VARIANTS`, and
`host_diversity_cup.CUP_PRIME_RANGE` (which previously hard-coded
`401 <= p <= 599` inline). A prime added to the first but outside the
second is silently never drawn. The single-use-per-source rule is
unchanged — never reuse a prime on a source that has already run it.

rule-alpha vendor note (2026-08-30): rule-alpha is developed on
`claude/rule-alpha-layer-1-ch78oi`, an **orphan branch that shares no
history with this one** (empty merge-base; it carries no
`reports/league` and no `scripts/`). It is therefore vendored
file-by-file, never merged — merging it would delete the league. Cups
006 and 007 raced `rule-alpha@7908b09` (vendored by `f8464ff`). After
Cup 007 was dispatched, `803fd6f` was vendored: the five modules
`config/diagnostics/layer1/terrain/visualize` plus
`tests/test_rule_alpha.py` are taken from the branch, while
`rule_alpha/_reuse.py` deliberately keeps the **trunk's** shim — the
branch's production helper already carries the 2 cm floor release, the
Cup trunk's does not, and the shim supplies it without altering the
shipped agent. Taking the branch's `_reuse.py` would silently drop
that release. Cup 008 onward races the newer actor.

Candidate-support mismatch (2026-08-30, after Cup 008). Cup 009 was
deliberately deferred to fix the candidate set first. `ad2a68a` unions a
rule-alpha proposal family into the inference-side candidate provider
(`scripts/rule_alpha_proposals.py`, off by default behind
`--union-rule-alpha`). On dual-empty-permute-000-607 seed 42 the generic
provider contained rule-alpha's executed move on 0 of 31 boards and the
family on 31 of 31, with the two sets **never overlapping**; running the
same episode with the union and with `add_exact_agent_candidate` turned
OFF gave bit-identical results to leaving it on, so the mining-time
injection is now a provable no-op and teacher and inference share one
action space. Strict pairs on that cell went 3 -> 10 and the head-to-head
against the champion flipped 0-3 to 6-4, though the fork budget became
binding (12 of 25 disagreements forked) so the yield figure understates
it. Lifting the fork budget to 40 then forked all 25 disagreements and took
strict pairs to **23** (3 in the baseline) at a 92% strict rate, with the
head-to-head against the champion at 16-7 to rule-alpha versus 0-3
before -- same episode, same physics, same actor play throughout.
`adba8f9` additionally recovers each item's discarded 2nd..kth Layer 1
candidates via a trunk-only `ranked_observer` hook in
`layer1.choose_for_item` (**re-apply it on the next rule_alpha vendor**;
`RuleAlphaProposer` raises rather than silently narrowing if it is
gone), which widens the family 2.5x for ~2% more proposer time and is
the only source of same-item diversity -- the thing that matters on a
one-item pool. Full measurement, cost profile and caveats:
`reports/candidate-support/rule-alpha-union-20260830.md`.

Hosting bug (2026-08-26): the row above for Cup 003 briefly read
"003 アーモンドビレッジ" in the `cup` column. `scripts/host_diversity_cup.py`'s
`next_cup_id()` matches `^\|\s*(\d{3})\s*\|` — a bare 3-digit id with
nothing else in that cell — so the nickname suffix made the regex miss
that row entirely; the next `host-diversity-cup.yml` run (course
000:467,479,487,491 · 001:439,443, run `32947834246`) recomputed
`next_id` from only rows 001/002 and re-dispatched as "Diversity Cup
003" again — a second, colliding "003". The **course itself was
unaffected** (`used_primes()` reads the streams column with a separate
regex and correctly saw all of 001-003's primes as used, so the new
course is genuinely fresh, not a reused/duplicate one) — only the
ledger row number and the dispatched run's display title were wrong.
Fixed here by moving the nickname out of the `cup` column into notes
and renumbering that row 004. Lesson: never put anything but the bare
`NNN` id in the `cup` column; a nickname belongs in notes or in the
per-cup report title only.

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
