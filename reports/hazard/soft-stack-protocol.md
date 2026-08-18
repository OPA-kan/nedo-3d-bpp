# Stack-aware soft coverage: shadow first, then a dominance tie-break

Preregistration. Written before the shadow wave runs and before any
selector exists.

## The finding this comes from

`soft-proxy-is-contact-only-and-therefore-inert`
(`reports/official/soft-rule-gap.md`): the agent charges an ordinary
item against a soft one only on DIRECT CONTACT, and on 42 recorded
terminal states that predicate fires on 0.19 soft items per episode and
is identically zero on 34 of 42. The soft axis has never carried a
gradient. Under a stack-aware reading the same states give 2.24 violated
soft items and 5.45 violating pairs per episode, and the local ratio
falls from 98.14 to 33.42 against an official `soft_item_score` of
19.65.

The official rule is NOT identified by that work and is not assumed
here. What is established is narrower and sufficient to act on: the
shipped predicate is inert, so anything built on it cannot move.

## Why a shadow first, and not an arm

The attribute filter (`attribute-filter-protocol.md`) was preregistered,
waved and closed inert -- 0 filtered across 16 swaps. That verdict cost
a wave and taught nothing, because the intervention had no reach and
nobody checked its reach beforehand. The same mistake is available here
and this protocol refuses it: **no selector is built until a log-only
shadow shows the intervention would have something to act on.**

## Stage 1 -- shadow (log-only, no behaviour change)

`multi_axis_candidate_record` now records
`priority_cover_violations_stack` and `soft_cover_violations_stack`
beside the shipped columns, for every retained Top-K candidate.
`multi_axis_dominates` fixes its own axis tuple, so the added columns
change no verdict; a test pins that. The record only runs under
`MULTI_AXIS_SELECTOR_MODE` in {shadow, enforce}, default off, and the
shadow mode is already established as behaviour-neutral (run
31360283401: every reported case metric inside the pooled control
spread). `behaviour_sha256` is unmoved.

Wave: >= 5 configs x 2 replicates, `MULTI_AXIS_SELECTOR_MODE=shadow`,
otherwise shipped defaults.

**Reach measurements**, declared now so they cannot be chosen after
seeing them. Over all decisions with more than one retained candidate:

- `R1` the fraction of decisions where some retained candidate has
  STRICTLY FEWER stack-aware soft violations than the chosen one;
- `R2` the fraction where such a candidate ALSO has an `adjusted_score`
  no worse than the chosen one -- the dominance-eligible fraction, which
  is the reach of the Stage 2 rule;
- `R3` the same for priority;
- `R4` the same counts under the SHIPPED contact reading, as the
  negative control. R4 is expected near zero; if it is not, the inert
  verdict for the attribute filter needs revisiting rather than this.

**Entry gate for Stage 2: `R2 >= 0.05`.** Below that the rule cannot
reach 5% of decisions and no arm is built, the line is closed as
measured-inert-with-a-reason, and the shadow columns stay as telemetry.
The threshold is set here, before the number exists.

## Stage 2 -- dominance tie-break (only if the gate passes)

`docs/AGENT_OPERATIONS.md` §5.1 forbids inventing a free coefficient,
and §5 says the reliable move is to design so the trade cannot happen
structurally -- "係数もゼロで済む". So Stage 2 introduces NO weight:

> Among the retained Top-K, if a candidate's `adjusted_score` is no
> worse than the incumbent's and its stack-aware soft violation count is
> strictly lower, play it. Otherwise the incumbent stands.

Selling score for soft is impossible by construction rather than by
tuning, so there is no lambda to fit and no ablation ladder to run. The
knob is `SOFT_STACK_TIEBREAK`, default off.

### Stage 2 gates (frozen)

- **P, primary.** Pooled placed must be non-inferior to the shipped
  default on the same streams, with paired per-stream losses not
  exceeding wins, against the `reports/benchmarks/baseline.json` floors.
- **S.** Pooled `shake_max_shift` and `shake_peak_kinetic_energy` must
  not worsen, per §5 -- reported beside placed, and a worsening blocks
  adoption even if placed rises. Read on pooled paired runs only, never
  a single case.
- **C.** Post-shake soft coverage from the now-validated direct
  instrument (`post-shake-instrument-passes-rung3-labels-unblocked`)
  must not worsen. This is the axis the change is FOR; if it does not
  move here, the mechanism is not doing what it claims.
- **N, negative control.** An arm identical but preferring the candidate
  with strictly MORE stack-aware violations must do worse on C. If it
  does not, the tie-break is not acting through the mechanism claimed
  and nothing is adopted whatever C says.
- **Confirmation.** Fresh never-used permutations, new seed, no
  retuning, same gates -- the last-resort precedent.

## What no result here licenses

- No hard attribute gate. `release attribute hard reject` is closed on
  placed cost and a wider predicate costs more, not less.
- No claim about the official rule. Even a Stage 2 pass would show that
  a stack-aware tie-break helps our own measurable coverage, not that
  the official scorer reads the rule that way.
- No change to the bundled diagnostic. `simulator/` stays untouched.
