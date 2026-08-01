# Task A official-budget transfer analysis

Actions run: `30717998654`

Configuration: bundled Task A source 000, three repetitions per arm,
150-second internal optimization budget, 180-second external timeout.
`bounded128` uses 128 deterministic placement attempts per item and a
0.5-second pair-macro cap. Live placement/risk ranking is unchanged.

| arm | repeat | placed | fill | final CoM z | near miss 5-30 deg | max settle angle | offline evaluations | offline best placed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base | 0 | 20 | 27.541 | 0.746 | 0 | 2.542 | 3 | 21 |
| base | 1 | 20 | 30.176 | 0.756 | 0 | 0.142 | 3 | 21 |
| base | 2 | 20 | 30.176 | 0.756 | 0 | 0.142 | 3 | 21 |
| bounded128 | 0 | 25 | 34.949 | 0.735 | 0 | 0.178 | 54 | 23 |
| bounded128 | 1 | 25 | 34.949 | 0.735 | 0 | 0.178 | 49 | 23 |
| bounded128 | 2 | 25 | 34.949 | 0.735 | 0 | 0.178 | 51 | 23 |

The bounded arm chose the same order in every repetition (hash
`306eb9a997b8`; prefix `9,11,33,22,5,0,23,4,10,12,18,21`). The base order
hash was `8f3b7f514909`. The optimizer therefore produced a stable policy
change rather than relying on physical-run variance.

Verdict: positive Task-A-only adoption candidate. It increases the number of
complete-order rollouts from 3 to 49--54 and improves both placed and fill.
Keep the global default off until explicit adoption because this experiment
contains one real bundled Task A case, and the dry-run proxy is not absolutely
calibrated (23 predicted versus 25 physically placed). Both arms still end on
an included but invalid/unsafe action; this result does not fix fallback.
