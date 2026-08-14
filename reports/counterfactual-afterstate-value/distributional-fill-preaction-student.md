# Distributional fill pre-action student

The frozen candidate is
`distributional-fill-preaction-student.json` (SHA-256
`26976649882a2529f5d63e3db9d800c9415782077fb95b9f8adcba87bd043d9e`). It
uses only the source observed-set tensor and the two candidate action tensors.
Post-settle afterstates, step indices, immediate score, and continuation labels
are absent from the inference features.

The model is a no-intercept pairwise ridge over action-geometry deltas and their
bilinear interactions with the standardized source-state summary. Its fixed
L2 value, `0.1`, won leave-one-physical-run-out selection on the four original
discovery runs. All fitting and model selection used runs `31722131035`,
`31720120600`, `31718231518`, and `31722145273` only.

## Development result

Seeds 46--48 were inspected while developing the student, so they are not a
confirmation set. On their 114 directional late H3 comparisons, the student
was correct on 88 (77.2%) and the frozen action-geometry model on 79 (69.3%).
The paired result was 26 wins, 71 ties, and 17 losses (two-sided exact sign
test `p=0.2220528201560228`). Per-run student/action results were 28/26, 33/32,
and 27/21, respectively. The complete machine-readable audit is in
`distributional-fill-preaction-student-development.json`.

This is a promising pre-action agent candidate, not a confirmed score gain.
The metric is counterfactual branch-direction accuracy; episode-level packing
score has not yet been measured.

## Prospective gate fixed before collection

Confirm on unopened original-stream H3/B3 seeds 49, 50, and 51. The candidate
passes only if it beats action geometry in every run, has more pooled paired
wins than losses, and the prospective-only two-sided exact sign test is at most
0.05. Any change to features, coefficients, L2, or decision threshold after
opening those runs creates a new candidate and requires new seeds.
