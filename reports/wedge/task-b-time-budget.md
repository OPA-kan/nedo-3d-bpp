# Task B's time budget: where the seconds go, and 6.5 s measured

Deep-dive over the recorded B runs (v49 `bandnt-*`, v50 `gate0-*` and the
hard2-b replicate), local stage timers and counterfactual replays of the
near-miss declines, and one CI measurement of `policy_budget_seconds=6.5`
(`reports/bench/bt65-core-b`, `reports/bench/bt65-hard2-b`, against
`gate0-core-b` and `gate0-hard2-b` / `-r2`). 8.0 s was not dispatched because
6.5 s was not safe. Scripts and their outputs are in
`reports/wedge/task-b-time-budget/` (`profile.py` per-stage call times,
`stage_probe.py` / `stage_summary.py` timers inside one call, `cf_probe.py` /
`cf_summary.py` the counterfactual budgets at the declining call,
`platform_adj.py` the platform-time projection, `arm_bt65_b.txt` the arm).

**Recommendation: keep 4.5 s on B.** On the bench 6.5 s is flat on crossings
and slightly negative on items placed; under the 1.5x machine factor it would
cut 32 of 48 core-b and 52 of 96 hard2-b episodes short on the platform.

Two notes before the numbers:
- **The bench arm is not the shipped form.** `arm_gate0_b.txt` lacks the
  shipped `stack_deadline=True` (in the `submission/agent.py` OVERRIDES since
  v44). Two things in every B bench record come from that missing setting:
  every call over 10 s (all of them stack-option calls on b-hard2-s0070 and
  s0091), and most shadow skips (110-113 of the 118-130 placements without a
  shadow check on hard2-b).
- Nothing in the agent was changed; the measurement is one arm value.

## 1. Where the time goes on B

**Per stage, v50 at budget 4.5 s** (the policy call's duration):

| stage | core-b n / median / p90 / max | hard2-b n / median / p90 / max |
|---|---|---|
| ladder rungs | ~1390 / 0.3-0.4 / 0.7 / 4.3 | ~3600 / 0.3-0.4 / 0.8-1.0 / 6.9 |
| stack option | 214 / 2.99 / 3.76 / 4.51 | 504 / 2.85 / 6.40 / 24.0 (missing deadline) |
| physics resort | 101 / 4.90 / 5.61 / 6.02 | 159 / 4.64 / 5.62 / 6.01 |
| count pass | 122 / 4.87 / 5.43 / 6.05 | 139 / 4.04 / 5.23 / 5.86 |
| grid rescue | 42 / 5.0-5.4 / 6.3-6.5 / 7.03 | 167 / 4.6-4.8 / 6.2 / 7.47 |
| decline | 47 / 4.88 / 6.04 / 6.84 | 91 / 4.21 / 6.73 / 7.53 |

**Board size.** Calls are cheap until about 20 items are placed (p99 0.5 s).
From 40 items on core-b the median call is 4.4 s, because the low phase is
reached and most placements come from rescues. On hard2, boards of 50+ items
have a median of 2.7-3.8 s and a p90 of 5.4-8.4 s.

**Rescue placements always come after the budget is spent.** On core-b, 265
of 1900 placements (14 %) are rescue placements. Their calls take at least
3.8 s, with a median of 4.92 s, and 235 of them run over 4.5 s. The ladder
places only 32 times (core-b) and 112 times (hard2-b) after its own 2.7 s
deadline.

**Calls near the budget (3.6-5.0 s).** On core-b these are mostly the count
pass (73), the physics resort (54), the stack option (31), declines (29) and
the grid rescue (19).

**Stage timers inside one call** (7 scenes timed locally with `stage_probe.py`;
seconds, means):

| call | n | total | ladder | stack | last resort | resort | grid | shadow |
|---|---|---|---|---|---|---|---|---|
| ladder placement | 171 | 0.71 | 0.43 | 0.01 | 0 | 0.01 | 0 | 0.19 |
| stack placement | 35 | 3.28 | 1.89 | 0.87 | 0 | 0 | 0 | 0.49 |
| rescue placement | 32 | 4.99 | 2.03 | 1.18 | 0.20 | 0.56 | 0.06 | 0.94 |
| decline | 7 | 5.16 | 2.07 | 1.16 | 0.32 | 0.49 | 0.13 | 0.98 |

In a call that ends in a rescue or a decline, the ladder (about 2 s) and the
stack option (about 1.2 s) use most of the budget and find nothing. The resort
then gets about 0.5 s, plus about 1 s of shadow checks.

**The declines' last calls:**

| run | declines | under 4.2 s (stages ran out of poses) | between | at a rescue deadline (6.65 s or more) |
|---|---|---|---|---|
| gate0-core-b | 47 | 6 | 39 | 2 |
| gate0-hard2-b | 91 | 45 | 36 | 10 |
| gate0-hard2-b-r2 | 92 | 48 | 35 | 9 |
| bandnt-core-b (v49) | 47 | 5 | 40 | 2 |
| bandnt-hard2-b (v49) | 86 | 47 | 31 | 8 |

- None of the near-miss declines (margin -1 to -3) ends at a rescue deadline.
  They are s0007, s0009, s0040, s0067, s0077, s0026, s0039 and s0083, plus
  s0021, s0030, s0063 and s0078 in the second hard2 run.
- On core-b the rescues' failed checks summed over whole episodes are small:
  75 for the count pass and 5 for the grid rescue, across 47 declines.

## 2. How much of the declines is time-bound

Each near-miss episode was replayed locally with `cf_probe.py`. At its
declining call the same question was asked again with budgets of 4.5, 6.5,
8.0 and 30 s (no internal deadlines), with the validator room scan from
`last_call_probe.py`:

| scene (bench margin) | local margin | legal grid poses | 4.5 | 6.5 | 8.0 | 30 s |
|---|---|---|---|---|---|---|
| s0007 (sample, -1) | -1 | 0 | declines (2 checks) | declines (2) | declines (1) | **physics resort places, 14.2 s, 10 checks** |
| s0040 (sample, -1) | +1 | 20 | declines (0 checks) | declines | declines | **count pass places, 14.5 s, 1 check** |
| s0009 (-1) | -5 | 0 | declines | declines | declines | declines (68.8 s) |
| s0021 (-2, second run) | -4 | 0 | declines | declines | declines | declines |
| s0067 (-1) | -1 | 0 | declines | declines | declines | declines |
| s0077 (-1) | -1 | 0 | declines | declines | declines | declines |

- **Four of the six are dead ends.** No legal grid pose exists for any pool
  item, and no stage has anything to check even with unlimited time.
- **Two are time-bound, but only in the rescue stage.** s0007: the 10th check
  finds a pose that stands; at 4.5 s the window fits only 2. s0040: the
  resort never starts its candidate generation, because its time guard says
  it will not fit.
- **Neither places at 6.5 s or 8.0 s.** A larger budget goes to the ladder and
  the stack option. The resort's window ends at the budget plus about 1.5 s,
  so it moves later without getting longer; at 8.0 s, s0007 even got one
  check fewer.
- Overall about 10 % of bench declines end at a rescue deadline. About a third
  of the probed near misses are rescue-time-bound, and both would need well
  over 10 s on the platform.

## 3. Budget 6.5 s measured on CI

The arm is `arm_bt65_b.txt`: the v50 B form with the single
`policy_budget_seconds` value replaced (simulator budget 10.0). Runs: core-b
38580606656 (3 shards) and hard2-b 38580611642 (4 shards).

**core-b against gate0-core-b:**
- Crossings 48 -> 48, so the ship rule holds on the bench.
- Items placed 39.56 -> 39.21 per scene (-0.35; 11 up, 10 down). Soft -0.44.
- Priced reading -0.04. Largest losses: b-c2-s0004 -11, s0011 -7, s0003 -6.
- Policy time max 7.03 -> 9.15 s (slowest b-c1s-s0002 9.2, b-c2-s0003 8.8,
  b-c2-s0006 8.8).

**hard2-b by stratum:**

| stratum | crossings vs run 1 | crossings vs run 2 | placed vs run 1 | placed vs run 2 |
|---|---|---|---|---|
| sample | 35 -> 36 | 35 -> 36 | -0.67 | -0.96 |
| stretch | 12 -> 11 | 12 -> 11 | +0.16 | -1.16 |
| edge | 1 -> 1 | 1 -> 1 | +2.12 | -2.00 |
| fill-only | 0 -> 0 | 0 -> 0 | +0.38 | +0.88 |

- Overall placed -0.07 a scene and priced +0.02 against the first run.
- The two baseline runs differ from each other by +0.29 / +1.31 / +4.12 on
  the first three strata, so 6.5 s is within noise.
- Settle endings rise from 4-5 to 7, and topples from 113 to 125.

**Slowest calls against the platform's 10 s.** A bench call over 6.7 s is a
risk at 1.5x; over 8.3 s at 1.2x. "Episodes cut" counts episodes where a
placing call would time out on the platform, which answers with a random
action that fails and ends the episode.

| run | calls over 6.7 s | episodes cut at 1.5x (items lost per scene; crossings) | episodes cut at 1.2x (crossings) |
|---|---|---|---|
| gate0-core-b (4.5) | 5 | 3 (-0.40; 48 -> 48) | 0 (48) |
| **bt65-core-b (6.5)** | **147** | **32 (-3.96; 48 -> 41)** | 4 (48 -> 47) |
| gate0-hard2-b (4.5) | 65 | 6-9 (-1.1 to -2.0; 48 -> 47-48) | 2, both stack-option calls (48) |
| **bt65-hard2-b (6.5)** | **268** | **52 (-5.53; 48 -> 41)** | 15 (48 -> 46) |

- At 6.5 s, rescue placements come at a median of 6.74 s on core-b (4.92 s at
  4.5) and 6.06 s on hard2.
- The slowest calls that are not the stack option: core-b reaches 8.8 s
  (declines, grid rescue, a terrace placement); hard2-b reaches 10.0 s
  (b-hard2-s0005, a soft-edge placement), 9.4 s and 9.3 s.

## 4. Recommendation

**Keep 4.5 s on B.** At 6.5 s the bench gains no crossing on either suite and
loses 0.35 items a scene on core-b. On the platform it would lose 7 core-b
crossings at 1.5x, and 1 even at 1.2x. Two things explain why:
- B's rescue placements, 14 % of core-b's placements, only start after the
  budget is spent, so any budget increase pushes them toward or past 10 s.
- The time-bound declines need longer rescue windows, not a larger budget.

The old v18 figure of +0.15 items at 8 s comes from before the rescue stages
existed, and the structure has changed since.

Ideas that are not budget changes, none of them measured:
1. **Hand time from the ladder and the stack option to the rescue stages** in
   the low phase or under the count threshold. In rescue and decline calls
   those two stages spend about 3.2 s and find nothing. This targets the two
   time-bound near misses (s0007, s0040), but both needed about 14 s locally,
   so the possible gain is small.
2. **Add `stack_deadline=True` to the B/C bench arms** so the bench matches
   the shipped form. Today it inflates hard2's slow calls and shadow skips.
3. **Treat declining calls as free to overrun.** A timed-out call gets a
   random action that fails, which ends the episode the same way a decline
   does. The only real time risk is a placing call that runs too long.
