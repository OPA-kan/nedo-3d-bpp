# Safety rerank: preregistered development protocol (Gate 2)

Committed before any paired episode result is opened. Licensed by the
Gate 1 calibration pass (`safety-shadow-calibration-pass`: pooled
surviving-over-fatal AUC 0.933, monotone bands, every fatal placement a
release_candidate, model conservative below logit 0).

## Mechanism

`SAFETY_RERANK_MODE` (default `off`) with the artifact path in
`SAFETY_RERANK_SHADOW`. After every live selection decision is frozen
(the multi-axis lesson: computing earlier changes wall-clock budgets
and fails the physical negative control), the incumbent
placement-core decision and each retained top-K candidate are scored
with the exported safety ranker — at most `LOOKAHEAD_TOP_K + 1` = 4
forward passes of a 64-wide numpy MLP per step.

Swap rule, fixed here from the calibration table and never retuned on
development results:

- **Trigger**: act only when the incumbent logit is below **2.0**
  (empirical survival is 1.000 at or above logit 2 in the calibration
  wave; 13 of 14 fatal logits sat below +1.9).
- **Escape**: an alternative must itself clear logit 2.0 AND exceed the
  incumbent by at least **2.0** logits.
- **Q-conservation**: an alternative must give up no more than **15%**
  of the incumbent's immediate score (the min-q collapse showed
  unpriced score sacrifices compound into placed losses).
- Among eligible alternatives, highest logit wins, score breaking ties.
- **Never refuse**: with no eligible alternative the incumbent stands
  unchanged (the vacuum-cutoff lesson: this classifier is licensed to
  substitute, not to veto).

`shadow` mode runs the identical scoring on every step and logs the
would-swap verdict without changing the action; `enforce` executes the
swap and stamps `action_source=safety_rerank`.

## Matrix

`safety-rerank-ablation.yml`: arms {base, safety_null, safety_rerank}
x replicates {0,1,2} x the seven guard configs (b000-k15/k20/k40,
b001-k20/k30, c000-k1, c001-k1).

- `base`: knobs off.
- `safety_null` (physical negative control): `SAFETY_RERANK_MODE=shadow`
  — the full scoring compute on the hot path, zero behavioral effect.
  If this arm moves off base, the wave is confounded and void.
- `safety_rerank`: `SAFETY_RERANK_MODE=enforce`.

## Predeclared gates (development; all required to advance)

Sized against `reports/benchmarks/baseline.json` (paired 3v3 resolves
2.2-7.1 placements; sd 0 on b001-k30 and c001-k1).

1. **Mechanism**: pooled topple+slide endings strictly lower under
   `safety_rerank` than base — this is the channel the model was shown
   to rank, so the mechanism must move it.
2. **Direction**: pooled placed strictly higher under `safety_rerank`,
   and across case-replicate pairs placed wins >= losses.
3. **No harm**: no config's mean placed lower than base by more than
   its single-episode resolvable (2 sd where sd > 0; one placement
   where sd = 0).
4. **Fallback conservation**: pooled transport_invalid endings
   non-increasing (a swap must not push episodes into fixed-fallback
   death).
5. **Negative control**: `safety_null` within each config's resolvable
   floor of base on mean placed. Failure voids the wave regardless of
   the enforce arm's numbers.

Also recorded (not gated): swap counts per arm (`triggered`,
`would_swap`, `enforced` from the `safety_rerank` trace events), placed
and channel deltas conditioned on episodes where at least one swap
fired. An enforce arm that never fires cannot pass gate 1-2 and closes
the arm as inert on these streams.

Passing is development evidence only; adoption additionally requires
Gate 3 — an independent confirmation on fresh arrival-order
permutations under these same gates (six never-before-used streams,
same construction as `last-resort-confirmation.yml`). Failing any gate
closes the arm with the knob at `off` and the result is recorded
either way. No retuning of the trigger, margin, or Q-conservation
constants on any of these streams.
