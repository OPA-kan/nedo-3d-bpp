# Rescue scan contract

The rescue scan is an ablation for the observed
`unsafe_protocol_fallback` failure channel. It is disabled by default with
`RESCUE_SCAN_ENABLED=0`.

When enabled, the online policy reserves the final 0.9 seconds of its
6.5-second internal budget. The normal closed-loop search and Ranker run
unchanged before that reserve. Rescue runs only if both normal selection
paths returned no validated candidate.

The rescue population is every visible pool item, ordered round-robin across
normal, soft, and priority classes. For each item it searches release units
before settled units, in fixed batches of 32 attempted anchors and with a
global budget of 512 attempts. Candidate generation, static geometry checks,
the shipped risk model, and Ranker are reused without changed thresholds.
The best validated settled incumbent wins; if none exists, the best validated
release incumbent wins.

If rescue also returns no candidate, the internal result remains
`no_safe_action` and the simulator API still receives the explicitly unsafe
fixed-coordinate protocol fallback. The fixed action is not described as a
safe fallback.

## Controls

- `RESCUE_SCAN_ENABLED` (default `0`)
- `RESCUE_SCAN_RESERVE_SECONDS` (default `0.9`)
- `RESCUE_SCAN_ATTEMPT_BUDGET` (default `512`)
- `RESCUE_SCAN_ATTEMPTS_PER_UNIT` (default `32`)

## Preliminary static replay

On the 37 checked-in replay snapshots at step 10 or later, the rescue scan
returned a statically validated candidate in 37/37 states, including 17/17
case-001 states. This checks candidate recovery only; it does not prove that
the selected release survives PyBullet settle. The dedicated
`rescue-scan-ablation.yml` workflow compares the shipped baseline and rescue
over the five development regression configurations. Final-holdout cases are
not opened.
