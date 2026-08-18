# State-dependent risk pricing: the entry gate, and nothing past it

Preregistration. This is `HANDOFF.md` "Next engineering task" item 3,
whose entry condition the handoff already fixed and which this protocol
does not get to soften:

> re-derive the 57-death postmortem with candidate alternatives and
> show that at fatal steps a materially lower-P accepted alternative
> existed. Without that, the lever is empty; a global lambda raise is
> already refuted (lambda=2 loses everywhere).

Nothing here designs a lambda form. The only question is whether the
lever exists.

## Why this line and not another

The measurement budget is explicit that a line burning episodes without
a shipping-change candidate must justify itself or move. This session
has spent 113 episodes across four lines with zero such candidates. The
soft lines earned theirs -- three durable negatives that close an axis --
and the post-shake lines bought a validated instrument at a high price.
None of them can now produce a change.

This one can. `terminal-failure-channels` records that within topples
the rotation model mostly saw it coming (KNOWN 6, AMBIGUOUS 17, MISSED
5 of 28), so the remainder is pricing rather than perception, and a
state-dependent lambda is the ledger's own named lever for it. The
death budget puts the physical channels at 42.4% of endings, which is
the minority but is also the only channel the shipped physics probe
already touches.

## Instrument: existing telemetry, no agent change

`MULTI_AXIS_SELECTOR_MODE=shadow` already records, for every retained
candidate at every decision, `rotation_probability`, `slide_probability`,
`support_ratio`, `support_center_margin` and both scores. It is
established behaviour-neutral (run 31360283401: every reported case
metric inside the pooled control spread), and this session's own
soft-stack wave confirms the columns are present.

The harness row already carries `terminal_channel`, so the fatal step of
each physically-dead episode is identifiable without new instrumentation.

## Data

The gate needs deaths, not episodes. Physical deaths ran at 6 of 14 in
the soft-stack wave and 5 of 14 in the soft-generation wave, so roughly
40%. Target **>= 40 physical deaths**, which is about 100 episodes: 7
development configs x 7 replicates, `multi_axis_shadow` arm, serial.
Collection stops when 40 deaths are in hand or the configs are
exhausted, whichever comes first, and the count reached is reported
either way.

## Measurement, fixed now

At each fatal step -- the last decision of an episode whose
`terminal_channel` is `topple` or `slide` -- over the retained
candidates:

- **E1** the fraction of fatal steps where some retained alternative had
  a strictly lower `rotation_probability` (for topples) or
  `slide_probability` (for slides) than the played choice;
- **E2** the same, requiring the margin to be **materially** lower,
  fixed here as an absolute drop of at least **0.10** in the relevant
  probability, so "materially" is a number and not a judgement made
  after seeing the data;
- **E3** for the E2 hits, the score the alternative gives up
  (`adjusted_score` difference), because a lever that only reaches
  alternatives the ranker hates is not reachable by reweighting;
- **E4** negative control: the same counts at a random non-fatal step
  of the same episodes. If E2 is no higher at fatal steps than at
  ordinary ones, the signal is not about death and the lever is empty
  regardless of E2's absolute value.

## Entry gate

**E2 >= 0.30 AND E2(fatal) > E4(non-fatal).** Below either, the lever is
declared empty and item 3 is closed with the measurement recorded, as
the handoff's own wording requires. Above both, a lambda form may be
designed -- in a separate preregistration, with its own gates, and
subject to `AGENT_OPERATIONS.md` §5.1: a coefficient is admissible only
if externally determined or chosen by a preregistered ablation with the
losing values recorded.

Passing this gate licenses a design, not an adoption, and not a default
change.

## What this cannot become

No lambda is fitted on this stream. No threshold above may move after
the numbers exist. The retained-candidate scope is stated rather than
quietly widened: if the answer depends on alternatives the policy never
retained, that is a different lever with a different protocol.
