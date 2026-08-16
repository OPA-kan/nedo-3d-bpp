# Fatal-case branch labels: one death is suicide, the other is fate

Actions run `31938388838` extended the branch-label instrument to the two
certified-fatal pool-1 cases at steps 2–20 (`top_candidates` sibling mode:
the only choice axis with one visible item is where it goes), with the new
per-sibling support-surface ledger, and re-ran the five Task B configs as
an independent replication of run `31931772512`.

"Suicide" is used here as an operational claim, not a metaphor: a death is
self-inflicted to the extent that (1) before some freezing step, siblings
of the policy's own choice existed whose branches physically reach a
strictly better final outcome, and (2) something measurable separates
them. Otherwise the death is intrinsic.

## c001-k1: intrinsic — not suicide

In 0 of 9 measurable states does any sibling beat the policy's choice on
final placed (1 of 9 on fill, gap 1.3 fill points). Sibling outcomes do
differ — you can still lose placements by deviating — but the control is
at the per-state ceiling everywhere from step 2 on. This extends the
step-18 choice-invariant-ceiling certification back to the start of the
episode: on this trajectory the 21-placed ceiling was never avoidable by
any measured placement choice. The policy is not killing itself here.

## c000-k1: avoidable, and the ranker points the wrong way

In 6 of 8 measurable states a strictly better sibling existed. The
counterfactual gaps are large: a single different placement of the same
item at step 8 ends the episode 6 placements higher (0.146 of the
41-item stream), and at step 16 five placements higher. On these decided
pairs the live q ordering is significantly inverted: the higher-q sibling
reaches the better ending in only 3/17 pairs on final placed
(`p=0.0127`) and 3/18 on final fill (`p=0.0075`). Among the policy's own
top-3 spatially distinct candidates on this case, preferring higher q is
systematically the wrong tiebreak.

The support-surface ledger is directional but unproven as the mechanism:
the better sibling has the higher usable-support delta in 4/4 comparable
fill pairs (`p=0.125`) and the smaller footprint in 7/10, both short of
significance. What is established is avoidability plus ordering
inversion, not yet the surface-bookkeeping explanation.

## The b-config replication weakens the global concordance claim

The fresh identical-protocol run gives fill 24/41 and placed 13/32
against yesterday's 27/39 and 19/30. Pooled over both independent runs:
fill 51/80 (`p=0.0183`), placed 32/62 (`p=0.90`). The corrected reading
of `scale-31931772512` is therefore: the live ordering is mildly
concordant with final fill, carries no measurable signal on final
placed, and the episode-level instrument is deadline-sensitive enough
that single-run significance must not be quoted alone.

## Combined picture

The ordering question is regime-dependent, echoing the `settled_share`
regime result: on multi-item pools the immediate ordering is fine to
mildly helpful; in the fatal single-item regime of c000-k1 it is
significantly anti-predictive, and that is exactly where large avoidable
losses sit. The 0.267-vs-0.5 one-episode suggestion was directionally
right about the wrong place. Caveats: one fatal case per verdict; pairs
within a state share history; sibling construction differs between modes
(same-item top candidates versus cross-item class-diverse); support
thresholds in the ledger are geometric approximations.

Next decisions this licenses: a scoped selection experiment on the
pool-1 fatal regime (e.g. deviate from the q tiebreak among retained
top candidates only there), preregistered at episode level; and a
mechanism-first look at what the 3/17 pairs share before proposing any
new score term. It does not license touching the live ranker globally.

## Causality probe: the inversion does not compose sequentially

The mechanism audit found no single axis behind the inverted pairs — the
micro q-differences (mostly |dq| <= 0.055) point the wrong way through
different components at different steps. `scripts/run_tiebreak_probe.py`
therefore tested the naive causal reading directly on c000-k1, with the
shipped agent untouched: at every step, deterministically reconstruct
the spatially distinct top-3 candidates (budget 4096) and force either
the highest-q member (control for the reconstruction itself) or the
lowest-q member (the inversion), against the unmodified live policy.

| arm | steps | final placed | final fill |
|---|---:|---:|---:|
| live_base | 24 | 0.561 (23) | 26.10 |
| offline_top_q | 19 | 0.439 (18) | 16.16 |
| offline_min_q | 11 | 0.244 (10) | 6.96 |

Two conclusions, both negative and both load-bearing. First, wholesale
inversion is catastrophic: taking the low-q member at every step ends the
episode at 11 steps with 10 placements. The observational advantage of
lower-q siblings is a **single-deviation** property — each better branch
was completed by the shipped policy — and it does not survive being made
the policy. Second, even the top-q arm loses five placements to the live
policy despite agreeing with it on 16 of 19 steps: the deterministic
budget-4096 reconstruction is not the live deadline search, so any
selector experiment built on offline reconstruction has a built-in
handicap that must be controlled exactly this way.

Single local Linux machine, one episode per arm, no repeats —
directional development evidence. What survives: the avoidable losses
on c000-k1 are real but harvesting them requires a *selective*, 
state-conditional deviation at the right decision points, which returns
the problem to the still-missing regime detector. Do not implement a
global or per-step q-inversion; this probe is the evidence.
