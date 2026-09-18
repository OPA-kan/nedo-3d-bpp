# Official evaluation results (as reported by the competition platform)

| build | fill | cog | stability | placement | soft | placed fraction | optimize s | policy s |
|---|---|---|---|---|---|---|---|---|
| trunk best (`trueenvelope`, from the trunk's HANDOFF) | 34.25 | 40.68 | 53.24 | 16.95 | 21.30 | 0.505 | | |
| v1 (33fce01: stack option, dry-run order, last resort) | 35.63 | 36.30 | 45.87 | 15.1 | 8.9 | 0.504 | 139.2 | 7.48 |
| second result (v2 or v3; any-container last resort, strict budget) | 36.29 | 41.38 | 50.12 | 19.4 | 10.4 | 0.515 | 138.6 | 7.21 |

Both of our runs end with the status "Stopped in the middle. Did not
satisfy {is_valid, is_placed_safe, is_included}": that is the surrender
action (a placement far above the container) the wrapper answers with
instead of declining, and it is not scored any lower than a decline.
