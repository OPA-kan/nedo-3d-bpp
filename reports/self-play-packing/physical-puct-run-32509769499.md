# Physical PUCT Self-Play pilot: run 32509769499

## Decision

The per-real-move physical PUCT pipeline is executable end to end. It is not
yet evidence that search improves packing quality: with six simulations, three
root actions, horizon two, uniform `P`, and zero untrained `V`, the root visit
policy stayed uniform in this game.

## Contract exercised

- one `single-empty-noshelf` scenario, shared environment/game seeds
- paired rank-0 control and PUCT arm
- exact PyBullet filtering before policy selection
- six fresh-PyBullet simulations at every real PUCT decision
- maximum physical horizon two
- uniform cold-start prior and zero leaf value
- visit-count policy target at every non-terminal state
- player-to-move suffix return `G_t` after episode completion
- standalone rank-0 and PUCT HTML replays

## Results

| Metric | rank-0 | PUCT |
| --- | ---: | ---: |
| placements | 10 | 10 |
| terminal | no retained candidate | no retained candidate |
| selected physical failures | 0 | 0 |
| handoffs | 3 | 3 |
| non-rank-0 actions | 0 | 5 |
| attribute violations | 0 | 1 priority |
| game reward, player 0 | +50 | +45 |
| fill score | 9.5477 | 9.4348 |
| shake peak kinetic energy | 7.6709 | 3.2056 |

The PUCT arm produced 10 search decisions, 60 physical simulations, 43
expanded nodes, 10 policy targets, and 11 eligible value targets including the
terminal state. Its 10 root policies all had visit counts `2,2,2`; mean entropy
was `ln(3) = 1.098612`. Later edge Q values did detect attribute and bounded
terminal differences, but the six-simulation budget was exhausted immediately
after equal root coverage, so those differences could not alter visit counts.

The return contract behaved as intended. The priority violation reduced the
PUCT arm's player-0 episode reward from `+50` to `+45`; states before that event
received `G_t=+45`, the next player-0 state received the remaining `+50`, and
the terminal player-1 state received `G_t=-50` with no policy target.

## Interpretation

This run passes the infrastructure gate: each Self-Play move can invoke bounded
physical search, execute only a filtered legal candidate, expose the improved
policy surface as root visits, continue into the policy-induced state
distribution, and emit `(state, pi, G_t)` plus a replay.

It does not pass the policy-improvement gate. This cold-start configuration is
uniform exploration, not a useful expert. The next informative experiment must
give PUCT enough revisit budget (at least beyond one equal second visit per
root action) and compare budget/horizon variants on multiple fixed paired
seeds. A learned or measured leaf `V` should be added only after this search
budget audit, so compute effects are not confused with value-model effects.

## Evidence

- Actions: https://github.com/OPA-kan/nedo-3d-bpp/actions/runs/32509769499
- implementation commits: `53e669d`, `3d113e6`
- raw artifact: `self-play-physical-puct-32509769499`
