# Self-Play exact legal-move filter run 32506261250

Source: GitHub Actions run `32506261250`, commit `20a6702`, 2026-08-22
JST. All four Linux/PyBullet play jobs and the critical-replay aggregation
completed successfully.

## Contract

`PlacementCore.top_candidates` supplies a bounded proposal set. Before either
player selects a move, every proposal is executed in a fresh
`GroundHandlingEnv` reconstructed from the same item order and accepted action
prefix. Only proposals for which `is_included`, `is_valid`, and
`is_placed_safe` are all true enter the bounded legal set. Rejected proposals
and their status flags remain in the manifest as negative audit data.

An empty bounded legal set is not evidence that the mathematical action set is
empty. Candidate recall remains a separate measurement problem.

## Result

| measure | all arms | temperature arm |
|---|---:|---:|
| games | 12 | 8 |
| captured decision states | 192 | 127 |
| unique model-visible states (within scenario/arm) | 180 | 115 |
| handoffs | 50 | 34 |
| non-rank-0 actions | 38 | 38 |
| candidate proposals | 558 | 372 |
| physically legal proposals | 546 | 363 |
| prefilter rejections | 12 | 9 |
| selected-action physical failures | 0 | 0 |
| new soft/priority violations | 14 | 9 |

The exact filter rejected 12/558 proposals (2.15%). The prior unfiltered
matrix, run `32501468765`, ended 4/12 games in `selected_action_failure`; this
run ended 0/12 games that way while preserving essentially the same exploration
coverage (temperature: 127 states, 115 unique model-visible states, 38
non-rank-0 actions, and 34 handoffs).

Terminal counts were three `no_safe_retained_candidate`, five
`no_retained_candidate`, and four `max_steps`. The first means every proposed
Top-K action failed authoritative physics; the second means the bounded
generator proposed nothing. Both are candidate-set exhaustion labels, not
proof of global infeasibility.

## Verdict

**PASS for the bounded legal-move precision gate on this deterministic
matrix.** Unsafe proposals are now useful negative examples rather than moves
that corrupt a game trajectory. The game remains useful as a diverse,
replayable state-distribution engine.

**HOLD for candidate recall and P/V strength.** The filter cannot recover a
safe action that the proposal generator never emitted, and this run does not
show that game returns predict or improve the original packing score. The next
learning step should train/search over the recorded bounded legal sets while
keeping candidate recall and fresh single-agent score as independent gates.

## Replay artifact

The aggregate Actions artifact is
`self-play-matrix-critical-32506261250`. It contains six standalone HTML
replays and `critical/index.html`. The replay HUD reports the selected rank,
`legal X of Y`, and the number of proposals filtered by PyBullet at each move.
