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
