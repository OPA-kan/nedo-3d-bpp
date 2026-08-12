# `submission22` behavioural reconstruction

The original `submission22.zip` is not stored in Git, but its live-policy
configuration is reconstructible without inventing a parameter value.

The official result was returned at 2026-08-02 07:34 JST
(2026-08-01 22:34 UTC). Commit `13381bd` had already changed the Task A
offline default to `OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM=128` at 21:48 UTC.
At that commit the live search still used:

- the historical box anchor envelope; and
- `ANCHOR_FIRST_PASS_ATTEMPTS=64`.

Depth 256 did not become the default until `2cef4b9` on 2026-08-02 13:56
UTC. The true container envelope did not exist until `1191992` on
2026-08-03. The intervening live-interleave experiment was opt-in and does
not alter the default environment. The saved Task A replay at depth 64 also
uses 6.514 seconds of policy time and about 149 seconds of optimization time,
matching the official 6.533 / 149.452 second timing independently.

Therefore the current-tree reconstruction is the composition:

```text
ANCHOR_TRUE_ENVELOPE=0
ANCHOR_FIRST_PASS_ATTEMPTS=64
OFFLINE_DRY_RUN_ATTEMPTS_PER_ITEM=128  # inherited shipped default
```

`scripts/run_risk_ablation.py --arm submission22` pins the two live-policy
knobs explicitly. The bounded offline value remains the tested shipped
default, rather than being redundantly overridden by an experimental arm.
This is a behavioural reconstruction, not a claim that the lost ZIP archive
or its byte-identical `agent.py` has been recovered.
