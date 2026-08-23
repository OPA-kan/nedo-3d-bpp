# Terminal probe: the depth ladder inverts the V-MCTS-0 verdict

Date: 2026-08-23 (Linux, PyBullet 3.2.7)
Probe data: `reports/self-play-paired-physical/vmcts0-terminal-probe-20260823/`
Instruments: `scripts/run_paired_terminal_probe.py`,
`scripts/evaluate_terminal_probe_ladder.py`

## What ran

For 20 searched roots (2 cells: `single-empty-noshelf-original`,
`dual-shelf-mixed-original`, seeds shared with the H1/H2 arms), every
sibling root candidate was executed after replaying the trajectory
prefix and then continued under the game loop's own rank-0 policy and
fresh-replay legal filter to genuine termination. All 60 probes reached
genuine terminals (no censoring; post-shake evaluation recorded).
Because both players follow rank-0, the exogenous handoff draws only
reassign the mover: one physical continuation per candidate covers all
paired worlds.

## Depth ladder: H2 was too shallow, exactly as suspected

Fill ordering Kendall tau against the realized terminal outcome
(roots with non-tied means):

| arm | tau vs terminal | tau vs each other |
|---|---|---|
| H1 measured delta | +0.333 (n=9) | tau(H1,H2) = +0.800 (n=10) |
| H2 measured delta | +0.111 (n=9) | |
| **H1 + V composite** | **+0.600 (n=10)** | |

The earlier H1-vs-H2 agreement (+0.889 on its 18 roots) was agreement
between two shallow measurements, not evidence about future value: both
collapse against the terminal reference, H2 hardest. The bounded second
physical step added no terminal-ordering information here — while the
V bootstrap, which the H2-referenced gate had scored as damage, roughly
doubles H1's terminal-ordering quality. **The V-MCTS-0 gate verdict was
an artifact of judging against a shallow reference.** Secondary heads
tell the same story (H1 vs terminal: surface TV +0.576, CoM +0.152).

## Within-root V validation: the global/local dissociation is total

V^pi_behavior leaf predictions against the realized suffix
(terminal minus after-action), per root:

| head | within-root pairwise acc. | within-root tau | global pearson (same probe set) |
|---|---|---|---|
| fill | 0.708 (17/24) | +0.394 | 0.983 |
| placed | 0.700 (14/20) | +0.400 | 0.979 |
| priority_covered | 1.000 (8/8) | +1.000 | 0.431 |
| surface TV | 0.600 (15/25) | +0.152 | 0.964 |
| soft_violation | 0.500 (7/14) | 0.000 | 0.853 |
| center_of_mass_z | 0.360 (9/25) | −0.333 | 0.944 |

Both failure directions of the global metric are on display: pearson
0.98 coexists with 0.71 sibling discrimination (fill), and pearson 0.43
coexists with perfect discrimination (priority_covered). Global
correlation was never the right yardstick; within-root pairwise
accuracy is now measured directly and becomes the V acceptance metric.

## Honest scope

- 20 roots, 2 scenarios, one environment seed; n per tau is 9–11.
  Direction is clear, magnitudes are not yet precise.
- The terminal reference is the rank-0 continuation — the same behavior
  policy V is defined over (`V^pi_behavior`), so this validates V on its
  own semantics and on the decision-relevant quantity under the current
  rank-0 execution. It does not measure V against optimal continuations.
- soft/priority events remain rare; several heads still carry few
  comparable roots.

## Consequences

1. The V-MCTS-0 "do not integrate V" verdict is **superseded in
   direction but not yet in license**: V + one physical step is the
   best terminal-ordering estimator measured so far, but integration
   still requires re-running the gate at scale with the *terminal*
   reference (more cells, more roots, both seeds) rather than H2.
2. Deeper bounded horizons (H4/H8) drop in priority but are not ruled
   out: depth-2 added nothing over depth-1 against terminal *on these
   roots*, but divergences that only appear around depth 4-8 (a corridor
   blocked five placements later) are exactly what search exists for. If
   the question returns, an H4 arm over the same 20 probed roots costs
   little and measures tau(H4, terminal) directly. For now the budget
   question is "physical step + V" vs "more replicas", not "how deep".
3. The probe machinery is cheap enough (~38 s/candidate, zero censoring)
   to become the standing reference arm: terminal probes on sampled
   roots should accompany every future gate instead of bounded-horizon
   proxies.
