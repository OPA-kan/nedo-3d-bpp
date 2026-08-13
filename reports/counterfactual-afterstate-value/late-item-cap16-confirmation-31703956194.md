# Late item cap 16 independent confirmation — run 31703956194

The frozen cap-16 candidate did not independently confirm across fresh
look-ahead-20 permutations. Source 000 produced +0.375 placed and +1.393 fill
(3 wins, 4 losses, 1 tie); source 001 produced +0.125 placed and -0.506 fill
(1 win, 1 loss, 6 ties). Fallback-ending counts were unchanged in both
sources. Pooled placed was +0.250 but wins/losses were 4/5, failing the frozen
acceptance rule. Do not adopt unconditional late cap 16.

The development effect was concentrated at look-ahead 15. The final scoped
candidate expands only when the visible pool has at most 16 items, preserving
cap 10 on wider pools. Confirm it on fresh k15 permutations of both sources.
