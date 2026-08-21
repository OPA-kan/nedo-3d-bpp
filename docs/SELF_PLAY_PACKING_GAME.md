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
- The candidate generator produces a bounded proposal set, not mathematical
  legal moves. Before selection, every proposal is executed in an independent
  PyBullet environment reconstructed from the same item stream and accepted
  action prefix. Only proposals with all three authoritative status flags
  (`is_included`, `is_valid`, and `is_placed_safe`) enter the bounded legal set.
- Transport, containment, settling, and physical safety therefore remain hard
  constraints in the unchanged bundled PyBullet simulator.
- Soft and priority relationships remain legal actions. A mover pays `5` and
  the opponent receives `5` for each newly created violation. Existing
  violations are not charged again.
- A player with no physically safe move in the bounded proposal set loses `50`;
  the opponent gains `50`. This is explicitly bounded-set exhaustion, not proof
  that the mathematical action set is empty. Candidate recall remains a
  separate audit target.
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

Every transition retains the complete bounded legal set, its ranker metadata,
and the selected candidate. Physically rejected proposals and their simulator
status are retained in a separate legal-move audit as negative teacher data,
but can never be selected. A later search policy can therefore emit a
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

## Physical PUCT bootstrap

The next executable mode runs open-loop PUCT at every real Self-Play decision.
Each simulation reconstructs the current root in a fresh PyBullet environment,
uses the same bounded physically filtered action set, samples the stochastic
handoff rule, and backs up zero-sum return in the perspective of the player to
move at each visited node. The real move is sampled from the root visit policy.

Generation `pi0-puct0` is deliberately a cold start:

- `P` is uniform over the bounded legal set by default. The old rank prior is
  available only as a control because the executed-DAG audit found it too
  sticky at small budgets (16/19 oracle-root recovery versus 18/19 for uniform
  PUCT).
- `V` is zero at an unexpanded horizon leaf. This is explicit
  `zero_untrained`, not a claim that the state has zero production value.
- Terminal game reward and incremental soft/priority reward are the only backed
  up rewards. The hand-written packing `immediate_score` is not a value target.

After an episode, every captured state receives a policy target from MCTS root
visits and an undiscounted suffix-return target:

`G_t = final_reward[player_to_move_t] - reward_already_received_t`.

Terminal states have a value target but no policy target. Step-capped episodes
retain their observed return for diagnosis but mark it ineligible as a final
value target. These contracts make the output directly consumable by a later
P/V learner without pretending that the initial PUCT bootstrap is already an
AlphaZero-strength expert.

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
shows an isometric view of every container and item. Container wireframes use
the simulator's cut-corner ULD profile (`cut_x`, `cut_y`) rather than a
rectangular proxy, and show the always-present small shelf plus the optional
main shelf using the simulator's dimension formulas. Distinct colors identify
normal, soft, priority, and soft-plus-priority baggage. Playback overlays expose
the player to move, block length, chosen candidate rank, candidate count,
handoffs, incremental attribute violations, and—when search is active—the PUCT
simulation/horizon budget and root visit counts. CI generates one replay per
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
