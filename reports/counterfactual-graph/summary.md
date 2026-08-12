# Counterfactual graph H3/B2 pilot

Validated on commit `4bbbe84`, Task B development case `b000-k20`, step 3.

| metric | result |
|---|---:|
| horizon / branch factor | 3 / 2 |
| nodes by depth | 1 / 2 / 4 / 8 |
| total nodes / edges | 15 / 14 |
| physically safe edges | 14 / 14 |
| distinct stable items on edges | 5 |
| settle angle range | 0–0.019° |
| CoG z proxy range | 0.725–1.117 m |
| wall time | 77 s, replication 76 s |

Runs `31551011083` and `31551141292` produced byte-identical graph JSON
(`SHA256 8c7e204c547b5bac86528c13efc529aeb4bd030d59bd591f9d712cc17b69c6a9`).
Graph ID, all node IDs and all edge IDs match.

This validates the instrument, not a state-value model. It is one early root,
all sampled edges were safe, and there are no failure labels yet. The next
coverage step is at least three mid/late development/validation roots before
H5 or model training.
