# Search headroom: is the surrender ending a full board or an unsearched one?

> **WITHDRAWN 2026-08-18, before it ran, as largely redundant.** The
> question below was already measured. `reports/anchor-recall/phase-structure.md`
> crossed 51 anchor-recall oracle states with their decision-time
> telemetry and split exactly this: **P1 deadline-miss 17** (reachable
> settled candidates exist, none accepted) against **P3 true-empty 8**,
> with P2 generator-hole zero. So roughly two thirds of no-candidate
> states are un-searched rather than full, and the answer did not need
> a new 7-hour physical stream.
>
> Worse, the live consequence has already been tested twice and failed
> twice. `VACUUM_SETTLED_CUTOFF` turned that phase detector into an
> in-flight early stop and failed all four preregistered gates
> (`reports/vacuum-cutoff/verdict.md`). `LAST_RESORT_RELAXATION_SECONDS`
> spent extra effort in precisely the zero-accepted regime, passed
> development, and failed fresh-permutation confirmation
> (`reports/last-resort/`). "Reachable candidates exist" is therefore
> already known NOT to convert into placed by either detecting the
> state or spending more effort in it.
>
> This protocol is kept, unrun, as the record of a wrong turn:
> `docs/AGENT_OPERATIONS.md` §0.2 says "導出しない、照会する" -- query
> the ledger, do not reconstruct measured facts from prose -- and this
> was written without doing that. The instrument it motivated
> (`POLICY_BUDGET_SECONDS` as a registered knob) is harmless and stays,
> default-inert; the stream it asked for is not worth spending.
>
> What is NOT answered by the prior work, and would need its own
> preregistration if anyone reopens this: the phase split was measured
> on the anchor-recall oracle's 51 states, before the quiet-guard
> adoption, and P1 says candidates were reachable by an ORACLE, not
> that the shipped search would reach them given more wall clock.

Preregistration, written before the diagnostic runs. This is a
MEASUREMENT protocol, not a candidate for adoption: every treatment
value here is unshippable by construction (see "Why nothing here can
ship").

## The question

`death-budget-is-search-starvation-not-physics` establishes that 57.6%
of recorded episodes (38 of 66) end in surrender: the deadline search
accepted nothing, found no candidate for ANY item after a mean 7371
attempts, and the agent emitted the fixed protocol fallback, which is a
knowingly transport-invalid action. Those episodes carry the HIGHEST
mean placed fraction of any ending (0.5052), so they are late boards
that were going well.

Two readings fit that evidence and they imply opposite strategies.

- **H_full.** The board really is finished. No legal pose remains for
  any visible item, the search would have found nothing given any
  budget, and `num_placed_items ~ 0.5` is close to the true ceiling for
  this packing style. A learned proposer cannot conjure poses that do
  not exist.
- **H_unsearched.** Legal poses remain but the 6.5 s deadline expires
  before the search reaches them. The ceiling is an artifact of search
  throughput, and a proposer that reaches good candidates immediately
  converts those 38 episodes into longer ones.

Since every official component tracks `num_placed_items` above r = 0.96
(`reports/official/placed-regression.md`), the answer sets the value of
rung 3 before rung 3 is built. That is the point of running it.

## The instrument

`POLICY_BUDGET_SECONDS`, the agent's online policy deadline, was a
source literal (6.5) and is now a registered env knob with that same
default, `axis: timing`, `semantic: true`,
`offline_optimizer: false`. Default behaviour is unchanged: both
`component_sha256` and `behaviour_sha256` are unmoved by the change.

## Why nothing here can ship

The evaluation platform fixes `policy_timeout` (8.0 s on the harder
task set), a timeout substitutes `env.action_space.sample()`, and the
official feedback already reports a max policy time of 6.992 s against
that ceiling. Any budget above the default is therefore unshippable.
The knob is registered `offline_optimizer: false` precisely so the
offline proposal oracle cannot "discover" that more time scores better.
No adoption may follow from this protocol -- only a decision about
where to spend effort.

## Design

Paired by config. Arms:

- `control`: `POLICY_BUDGET_SECONDS=6.5` (shipped default)
- `headroom`: `POLICY_BUDGET_SECONDS=32.5` (5x)

7 development configs (b000-k15, b000-k20, b000-k40, b001-k20,
b001-k30, c000-k1, c001-k1) x 2 arms x 1 replicate, arms run as
concurrent pairs so wall-clock load is symmetric -- the search is time
budgeted and asymmetric load would be the confound this whole protocol
is about. Extended to a second replicate only if the first is
ambiguous under the decision rule below, and that extension is declared
here rather than chosen after seeing the result.

## Measurements

Per episode: `placed_fraction`, terminal cause via
`scripts/analyze_death_budget.py`, and the fatal step's search
diagnostics.

## Decision rule, fixed in advance

Let `d` = mean `placed_fraction`(headroom) - mean
`placed_fraction`(control), paired over configs.

- `d < 0.02` -> **H_full stands.** The boards are genuinely finished at
  ~0.5. A faster proposer cannot buy placed by finding candidates
  sooner, rung 3's justification collapses to whatever it can do for
  the 42.4% physical channel, and the campaign should say so plainly
  rather than build it.
- `d >= 0.05` -> **H_unsearched stands.** Real headroom exists, its
  size bounds what a proposer reaching those candidates within 6.5 s
  could capture, and rung 3 is justified with a measured target rather
  than a hope.
- `0.02 <= d < 0.05` -> ambiguous. Run the second replicate, then read
  the surrender share alongside `d`: if the surrender share falls
  materially while `d` stays small, the extra time is finding poses
  that do not survive, which is a different finding and gets written up
  as one.

Secondary, reported either way: the shift in the cause distribution,
and whether the headroom arm's surrender episodes still report "no
candidate for any item".

## What a pass does NOT license

A positive result does not license shipping any budget change, does not
license retuning any shipped constant, and does not by itself validate
a proposer. It licenses building one and gives it a target to beat.
