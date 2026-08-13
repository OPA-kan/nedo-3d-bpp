# Late narrow-pool cap 16 confirmation — run 31706701682

Both source jobs and all 32 paired episodes completed successfully on fresh
seed-20260813 look-ahead-15 permutations.

- Source 000: placed +0.250 (3 wins / 3 losses / 2 ties), fill +3.004.
- Source 001: placed -0.250 (3 wins / 4 losses / 1 tie), fill -0.384.
- Pooled: placed 0.000, 6 wins / 7 losses / 3 ties.
- Fallback-ending counts were non-increasing (3 -> 3 and 4 -> 3).

The frozen acceptance rule failed on source-001 placed, pooled placed,
pooled wins versus losses, and pooled fill. Do not adopt
`late_narrow_pool_cap16`. Together with the failed unconditional cap-16
confirmation, this closes the late item-cap family: broadening the item search
does expose many safe alternatives and can produce large development gains,
but the trajectory benefit does not transfer across arrival orders.

The shipped default remains cap 10. The opt-in arms stay available only to
reproduce the negative experiments; none is a score-improving agent.
