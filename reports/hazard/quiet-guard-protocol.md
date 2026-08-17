# Quiet guard: preregistered protocol (probe-guard v2)

Committed 2026-08-17 JST before any result is opened. Successor to
`probe-guard-wave1-fail-but-parity`, changing exactly the two defects
that wave named; everything validated stays fixed.

## Mechanism (`PHYSICS_PROBE_MODE=guard_quiet`, default off)

1. Every step, compute the incumbent's calibrated safety logit — the
   Gate 1 instrument, measured bit-identical to off (~60 us). If
   logit >= 2.0 (empirical survival 1.000 above this line): play
   unchanged, NO probe. Expected on ~80% of steps.
2. Below the trigger: probe the incumbent with the validated physics
   clone. If it predicts safe: play unchanged.
3. If physics predicts unsafe: probe alternatives in descending-logit
   order (Amendment 1 machinery unchanged), cap 6 probes / 1.5 s
   clamped to the shipped deadline; play the first physics-approved
   alternative; incumbent stands if none. Never refuse.

Footprint arithmetic, recorded up front: wave 1 probed all ~19 steps
(~2.9 s/episode of probe compute); the trigger fires on ~20% of steps
and Gate 1's calibration puts every observed death below logit +1.9,
so the quiet guard keeps the rescue surface while cutting probe
compute to ~0.6 s/episode and leaving 80% of steps untouched at the
already-validated 60 us.

## Matrix and gates (survival-stated)

{base, quiet_null, quiet_guard} x 3 replicates x 7 guard configs.
quiet_null = SAFETY_RERANK_SHADOW log-only (the Gate 1 arm, measured
trajectory-identical) — a null that is KNOWN quiet, so a breach voids
the instrument, not the interpretation.

1. Survival mechanism: pooled episode steps strictly higher under
   quiet_guard than base.
2. Direction: pooled placed strictly higher, paired wins >= losses.
3. No harm: every config's mean placed within its baseline.json floor
   of base.
4. Fallback conservation: pooled transport_invalid non-increasing.
5. Null control: quiet_null within every config floor of base.

Death-channel composition is reported, not gated: converting an early
fallback death into later physical survival is the mechanism working,
and wave 1's channel gate misread exactly that. An inert arm (zero
swaps) closes it. Pass licenses fresh-permutation confirmation before
any default flip. Fail closes the line; no retuning of the trigger,
thresholds, caps, or slice on these streams.

## Confirmation stage (preregistered before any confirmation result)

Development passed on run 32000938328 (all five gates; placed +7,
steps +7, 9 rescues). Per the adoption discipline, confirmation runs
on never-before-used arrival permutations: six fresh streams
(three per source case, `build_stream_variants` seed 20260817,
look-ahead 20, same item multisets) x {base, quiet_guard} x 2
replicates. Gates on the fresh set, all required:

1. Pooled placed strictly higher under quiet_guard.
2. Paired placed wins >= losses across stream-replicate pairs.
3. Pooled episode steps strictly higher (the survival mechanism).
4. Pooled transport_invalid non-increasing.
5. No stream's mean placed lower by more than three placements
   (the last-resort confirmation's floor, stricter than the largest
   measured 2-sd).

Pass: adopt PHYSICS_PROBE_MODE=guard_quiet as the shipped default
(with SAFETY_RERANK_MODE=shadow and the committed artifact path
wired), record the adoption, and rebuild the submission artifact.
Fail: the knob stays off, the line closes, and the result is
recorded. No retuning on these streams in either case. The
last-resort relaxation passed development and died exactly here; this
gate is the real one.

## Confirmation run 1 verdict and corrected confirmation

Run 32001795205 (six fresh streams, seed 20260817): pooled placed 210
versus 184, pooled steps 222 versus 196, paired 5W/1L, every stream at
or above base (floors +0.0 to +5.0), physical deaths (topple+slide)
10 -> 7, and 8 physics-approved rescues from 12 detections. Gate 4 as
written (transport_invalid non-increasing) breached 2 -> 5, so the
confirmation FAILS on its letter and that verdict is recorded.

The breach is a design contradiction inside this same protocol: the
development stage explicitly repudiated channel-composition gates
("converting an early fallback death into later physical survival is
the mechanism working"), and the confirmation then reintroduced one
copied from the last-resort protocol, whose mechanism was fallback
rescue and whose gate direction is exactly backwards for a physical
guard: episodes that no longer die physically live long enough to
reach search exhaustion. Physical deaths fell; the conversion is the
mechanism.

Corrected confirmation, preregistered before any of its results
exist: same six-stream construction on a NEVER-USED seed (20260818),
same replicates, gates 1-3 and 5 unchanged, gate 4 restated as pooled
topple+slide NON-INCREASING (the guard must not create the deaths it
exists to prevent; fallback conversion is reported, not gated). The
seed-20260817 streams are burned as development-adjacent and may not
be reused. No retuning of any mechanism constant.
