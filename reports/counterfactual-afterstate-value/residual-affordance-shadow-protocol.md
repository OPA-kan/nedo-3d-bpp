# Residual-affordance live shadow protocol

Historical v1 protocol: both executed waves failed gate 2. Prospective runs use
`residual-affordance-shadow-negative-control-v2.md`; v2 does not retroactively
change either v1 verdict.

## Frozen object

The candidate is the exact no-intercept action-geometry ridge trained on raw
H3 run `32351615182`, discovered on `32368148298`, and confirmed without
refitting on `32372290412` and `32375696343`.  Its target is the Pareto
direction of branch-capped searched residual affordance, not official score.

The live scorer reconstructs the graph action tensor without
`immediate_score`: container index, official command xyz, orientation,
release flag, and the fourteen observed item fields.  Scales and weights are
embedded in `agent.py`; no runtime artifact or training code is loaded.

## Special-attribute contract

The unrestricted proposal measures the frozen learner exactly.  A second,
guarded proposal rejects a candidate if it increases any of these relative to
the played incumbent:

- direct-contact priority coverage;
- direct-contact soft coverage;
- stack-aware priority coverage;
- stack-aware soft coverage;
- priority routing violations.

This deliberately covers both current interpretations of the unpublished
official stack semantics.  It also encodes the per-axis rule: a mover may rest
on a protected item only when it carries every protected attribute of the
lower item.  In particular, priority-only cargo on soft cargo remains a soft
violation.

## Licensed behavior

Only `off` and `shadow` exist.  Shadow runs after the live decision is frozen,
records unrestricted and guarded proposals, and cannot change the executed
action.  There is intentionally no enforce path.

## Preregistered gates

1. Feature parity: unit evidence must reproduce the frozen pairwise logit from
   two independently reconstructed live feature vectors.
2. Physical negative control: base and shadow action-sequence hashes must
   match for every paired episode.  Any mismatch blocks the experiment.
3. Reach: at least 50 observed decisions and at least five guarded proposed
   action changes are required before a canary is worth running.
4. Attribute safety: guarded proposals must have zero recorded regressions by
   construction; report how often the guard blocks the unrestricted model.
5. No promotion from this wave: passing licenses a separately preregistered
   guarded canary only.  Official-score improvement must be measured with
   actual guarded actions before submission.
