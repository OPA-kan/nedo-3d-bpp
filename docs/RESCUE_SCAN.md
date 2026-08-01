# Rescue scan contract

The rescue scan is an ablation for the observed
`unsafe_protocol_fallback` failure channel. It is disabled by default with
`RESCUE_SCAN_ENABLED=0`.

When enabled, the online policy reserves the final 0.2 seconds of its
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
- `RESCUE_SCAN_RESERVE_SECONDS` (default `0.2`)
- `RESCUE_SCAN_ATTEMPT_BUDGET` (default `512`)
- `RESCUE_SCAN_ATTEMPTS_PER_UNIT` (default `32`)

## Preliminary static replay

On the 37 checked-in replay snapshots at step 10 or later, a 0.1-second
reserve already returned a statically validated candidate in 37/37 states,
including 17/17 case-001 states. The 0.2-second default keeps a small timing
guard while returning 0.7 seconds to the primary search compared with the
rejected 0.9-second first ablation. This checks candidate recovery only; it
does not prove that
the selected release survives PyBullet settle. The dedicated
`rescue-scan-ablation.yml` workflow compares the shipped baseline and rescue
over the five development regression configurations. Final-holdout cases are
not opened.

The rejected 0.9-second ablation is preserved under
`reports/rescue-scan/ci-30698074510`: base/rescue totals were 83/75 placed and
100.32/86.98 fill. It improved b000-k20 by two placements and b001-k30 by one,
but lost nine placements on b001-k20. The reserve ladder then recovered a
candidate in all 37 snapshots with only 0.1 seconds, motivating the 0.2-second
second ablation rather than tuning the Ranker or risk terms.

The 0.2-second second ablation is preserved under
`reports/rescue-scan/ci-30698434932`: base/rescue totals were 80/74 placed and
98.00/88.02 fill. It recovered b001-k20 by two placements but lost two on
b000-k20 and six on b000-k40. This also rejects the current rescue policy.
The next diagnostic run records rescue-trigger, rescue-action, and remaining
protocol-fallback counts so reserve-induced trajectory changes can be
separated from the rescued action's physical outcome.
