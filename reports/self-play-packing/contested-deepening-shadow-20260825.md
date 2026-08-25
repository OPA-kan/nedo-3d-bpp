# Contested deepening: measured, and rejected as the production default

Date: 2026-08-25. Instrument: `deadline_physical_rollout.py` contested
phase (commit `e92eb90`) — after the common-depth phase hits its depth
cap with budget left, only the candidates still on the checkpoint
Pareto frontier keep advancing, in lockstep among themselves, until the
frontier resolves, the budget guard trips, or the extra-step cap (6) is
reached. Same 46 hard roots / 16 interventions as the three-arm shadow.

## Runs

| arm | run | reproduction | live IV recovery | mean s | p95 s | ≤10 s | achieved depths |
|---|---|---:|---:|---:|---:|---:|---|
| ranker_next, contested 0 (baseline) | `32803397418` | 35/46 | 6/16 | 5.74 | 8.47 | 45/46 | H≤3 |
| **ranker_next, contested 6** | `32810925906` | **34/46** | **6/16** | 6.33 | 9.09 | 45/46 | H4: 8, H5: 3 |
| geometry, contested 0 (baseline) | `32802777408` | 34/46 | 6/16 | 5.77 | 8.56 | 45/46 | H≤3 |
| **geometry, contested 6** | `32810936004` | **32/46** | **6/16** | 6.49 | 9.06 | 45/46 | H4: 7, H5: 3, H6: 2 |

## What the deepening actually did, per root

- ranker_next arm: 13 roots ran contested rounds (17 rounds total).
  **Zero interventions converted.** One flip, harmful: `…045ed72b`
  (non-intervention) was decided correctly at H3; one contested round
  *resolved* the frontier to the wrong action.
- geometry arm: 14 roots, 22 rounds. Zero conversions; three flips, all
  harmful or neutral (`…8b471fb4`, `…045ed72b` correct→wrong;
  `…bb6f8fa7` changed its pick and stayed wrong).
- Stop reasons (ranker arm): 18 resolved, 15 predicted_deadline,
  3 all-terminal, 10 never entered (phase-1 deadline stop). The
  conservative first-round estimate (sized from 3-session rounds)
  blocked several contested roots from even one extra round — but where
  rounds *did* run, they were harmful-to-neutral, so loosening that
  guard is not indicated by this data.

## Verdict

The conversion hypothesis from the three-arm shadow — that the 5–6
in-support interventions rejected at H ≤ 3 would convert if the
contested pair were read deeper — is **refuted at H4–H6 under the 10 s
SLA**: conversion stayed exactly 6/16 in both arms while reproduction
dropped by 1–2. Bounded rank-0 continuations at these depths do not
converge toward the terminal ordering; where they resolve the frontier,
they sometimes resolve it away from the terminal answer. This
replicates, now at n=13–14 contested roots, the single-root H3→H4
vanishing-advantage result (run `32469901132`) and the serial-MCTS
depth degradation reported by Zhao et al.

**Production default reverts to `ranker_next` + contested 0**
(35/46 reproduction, 6/16 recovery, p95 8.47 s). The contested phase
stays in the library and the workflow as an off-by-default, fully
instrumented option.

## What the remaining headroom now needs

Not +1–3 bounded steps. The unconverted interventions need
terminal-connected information: either much deeper selective reading
(the budget cannot buy it inside 10 s) or an estimator at the
checkpoint — which is exactly the frozen roadmap's item 10, V as a
**same-budget challenger** (never a mainline revival): at identical
wall-clock, does `checkpoint + V(s_H)` order the contested pair better
than `checkpoint` alone? The wave-2 cohort (24 cells, collecting) is
the prerequisite either way — n=16 interventions cannot separate any
of these arms.
