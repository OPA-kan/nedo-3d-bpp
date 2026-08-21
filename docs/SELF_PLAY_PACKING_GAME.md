# Self-Play Packing Game

## Purpose

This game is a state-distribution engine for the production packing agent. Its
job is to create physically valid, decision-relevant boards that a fixed
single-agent heuristic rarely visits. Game win rate is not the production
objective. Every production claim must eventually be re-evaluated under the
original single-agent packing score and fresh scenario streams.

## Version 0 contract

- Two players share one board, one item stream, one candidate generator, and
  exactly the same policy.
- A player places at least three items. After every later successful placement,
  control changes with probability `0.6`.
- Transport, containment, settling, and physical safety remain hard constraints
  in the unchanged bundled PyBullet simulator.
- Soft and priority relationships remain legal actions. A mover pays `5` and
  the opponent receives `5` for each newly created violation. Existing
  violations are not charged again.
- A player with no retained candidate loses `50`; the opponent gains `50`.
- A selected candidate rejected by physics is recorded separately as
  `selected_action_failure` and quarantined without a winner or terminal
  reward. It is a policy/retention failure, not evidence that the mathematical
  action set was empty.
- Exhausting the finite item stream after a safe placement is a draw. It is not
  attributed to the next player as a loss.
- All rewards are exactly zero-sum.

The implementation stores `player_to_move` and block-scheduling metadata beside
every pre-action decision snapshot. The game-state signature includes those scheduling fields,
because the game would otherwise not be Markov: the same board can have a
different handoff probability depending on the current block length. A separate
model-visible signature is computed from the existing physical tensor only, so
production transfer can discard the artificial game context.

Every transition also retains the complete bounded candidate set, its ranker
metadata, and the selected candidate. A later search policy can therefore emit a
distribution over the exact legal-action abstraction seen at that state instead
of reconstructing an unstable candidate list after the fact.

## Initial pilot

The first pilot intentionally uses the existing hand-coded candidate ranking in
two symmetric modes:

1. rank-0 control, which checks that the game wrapper itself does not invent
   diversity;
2. shared Top-K temperature sampling, which checks whether the game produces
   new handoff states without immediately degenerating into physical failure or
   attribute abuse.

This is not yet AlphaZero. It validates the game dynamics and produces replayable
handoff roots. The next gate is to run bounded physical search from those roots
and show that game-generated states contain planning signal. Only after that do
policy/value targets and search-follow generations become justified.

## Gates

The game may feed a P/V learner only if the pilot shows:

- exact zero-sum accounting and no handoff shorter than the minimum block;
- replayable, physically valid handoff snapshots;
- non-trivial board and model-visible state diversity;
- bounded selected-action failure and soft/priority violation rates;
- useful shallow-versus-deeper search disagreement on captured roots.

The eventual success criterion is stricter: a P/V model or search policy trained
with these states must improve fresh, unbiased, single-agent 3D-BPP evaluation.

## Visual replay

`scripts/render_self_play_replay.py` converts any saved game into a standalone
HTML replay. It needs no server or external JavaScript dependency. The canvas
shows an isometric view of every container and item, with distinct colors for
normal, soft, priority, and soft-plus-priority baggage. Playback overlays expose
the player to move, block length, chosen candidate rank, candidate count,
handoffs, and incremental attribute violations. CI generates one replay per
pilot game under `reports/self-play-packing/replays/` and includes them in the
normal Actions artifact.

## Scenario matrix and critical gallery

The scenario-matrix workflow runs the same rank-0 control and symmetric
exploration contract across four representative physical setups:

- one general container without a shelf;
- one general container with a shelf;
- two general containers with a shelf in only the second container;
- two pre-loaded containers with the second reserved for priority baggage.

The replay labels make these roles explicit as `GENERAL`, `PRIORITY`, and
`SHELF`; priority baggage is not placed on a separate hidden board.

Raw manifests and snapshots remain available for auditing, but the default
gallery is deliberately small. `scripts/select_critical_self_play_replays.py`
ranks games by selected-action physical rejection, newly created soft/priority
violations, deeper-ranked exploration, state novelty, and handoffs. It first
keeps the strongest game from every scenario, then fills the remaining slots
globally. CI emits the six selected standalone replays under
`reports/self-play-matrix/critical/`; open `index.html` to browse them.
