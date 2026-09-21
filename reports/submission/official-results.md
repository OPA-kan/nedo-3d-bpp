# Official evaluation results (as reported by the competition platform)

| build | fill | cog | stability | placement | soft | placed fraction | optimize s | policy s |
|---|---|---|---|---|---|---|---|---|
| trunk best (`trueenvelope`, from the trunk's HANDOFF) | 34.25 | 40.68 | 53.24 | 16.95 | 21.30 | 0.505 | | |
| v1 (33fce01: stack option, dry-run order, last resort) | 35.63 | 36.30 | 45.87 | 15.1 | 8.9 | 0.504 | 139.2 | 7.48 |
| v4 (7606e9f: any-container last resort, no-cover veto, priority first) | 36.29 | 41.38 | 50.12 | 19.4 | 10.4 | 0.515 | 138.6 | 7.21 |
| v5 (c47d35e: Task A row planner, hybrid with the dry-run) | 34.60 | 40.92 | 46.05 | 25.5 | 20.45 | 0.503 | 139.1 | 6.43 |
| v7 (78d478f: no standing boxes, three layouts, replay tolerance, conservative transport) | 34.52 | 32.32 | 37.60 | 16.0 | 16.35 | 0.488 | 140.4 | 6.46 |

v7's total was 29.47 against v5's 35.09, while the bench's 48-scene
physics suite had v7 ahead of v5 on every count.  The difference is the
budget: v7 gave each of its three layouts a third of the 140 s, and on
the evaluation machine (about five times slower than this sandbox) a
third was not enough to finish a plan, so every plan was cut before its
soft rows and its priority cargo -- which is exactly what the official
soft (-4) and placement (-9.5) scores show, and the ladder's
improvisation over a half plan is what the cog and stability drops
show.  v8 runs the layouts one after the other against the whole budget
and keeps a cut plan only when none finished.

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
