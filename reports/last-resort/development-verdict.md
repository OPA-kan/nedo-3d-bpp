# Last-resort relaxation: development gates PASSED

Paired run `31947384483` completed all 42 episodes. Against the four
gates preregistered in `protocol.md` before any result was opened:

| gate | requirement | result | verdict |
|---|---|---|---|
| mechanism | pooled transport_invalid strictly lower | 10 -> 7 | PASS |
| direction | paired wins >= losses AND pooled placed strictly higher | 8W/6L, 387 vs 386 | PASS |
| no harm | no config below its resolvable floor | worst b000-k15 -2.67 vs floor 4.62 (2 sd) | PASS |
| gamble conservation | topple+slide rise <= transport_invalid fall | +3 vs -3 | PASS |

Per-config mean placed deltas (last_resort minus base): c000-k1 +2.33
(one replicate 16 -> 23), c001-k1 +1.00 uniformly across replicates —
**the certified 21-placed ceiling of c001-k1 was policy-conditional and
the rescue breaks it to 22 in all three replicates** — b001-k20 +0.67,
b001-k30 +0.67, b000-k40 -0.33, b000-k20 -1.33, b000-k15 -2.67 (all
b-regressions inside their measured noise floors; arms ran on separate
runner VMs, which those floors price in).

## Honest reading

The pooled margin (+1 placement of 386) is at the very edge of the
instrument, and the pass rests on the fatal-case gains. That is exactly
the configuration the confirmation stage exists for: per the protocol,
adoption requires an independent fresh arrival-order permutation wave
passing the same four gates. Until then the knob stays default 0.
