# Official evaluation results (as reported by the competition platform)

| build | fill | cog | stability | placement | soft | placed fraction | optimize s | policy s |
|---|---|---|---|---|---|---|---|---|
| trunk best (`trueenvelope`, from the trunk's HANDOFF) | 34.25 | 40.68 | 53.24 | 16.95 | 21.30 | 0.505 | | |
| v1 (33fce01: stack option, dry-run order, last resort) | 35.63 | 36.30 | 45.87 | 15.1 | 8.9 | 0.504 | 139.2 | 7.48 |
| v4 (7606e9f: any-container last resort, no-cover veto, priority first) | 36.29 | 41.38 | 50.12 | 19.4 | 10.4 | 0.515 | 138.6 | 7.21 |
| v5 (c47d35e: Task A row planner, hybrid with the dry-run) | 34.60 | 40.92 | 46.05 | 25.5 | 20.45 | 0.503 | 139.1 | 6.43 |

v5 against v4: soft +10.0 and placement +6.1 (the two components the
planner was built for; the bench's counts of soft and priority cargo
placed moved the same way), fill -1.7, stability -4.1, cog -0.5.  The
platform's total for v5 was 35.09.  Optimization used the whole budget
(139 s): on that machine the ladder's dry-run never finishes, so the
planner's plan is the one in use on every Task A scene.

Both of our runs end with the status "Stopped in the middle. Did not
satisfy {is_valid, is_placed_safe, is_included}": that is the surrender
action (a placement far above the container) the wrapper answers with
instead of declining, and it is not scored any lower than a decline.
