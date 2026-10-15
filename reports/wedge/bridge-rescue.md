# Bridge rescue: the grid rescue's contact filter and the low phase's rescue reserve

Two changes to the declining call's rescue path, each behind its own flag
(defaults unchanged), measured on Tasks B and C. Follows
`reports/wedge/bridge-spots.md` (the bridges exist and the rescue cannot
afford them) and `reports/wedge/task-b-time-budget.md` (the ladder and the
stack option spend the declining call). Scripts, arms and replay records are
in `reports/wedge/bridge-rescue/`; bench records in
`reports/bench/bresc-*`.

## Summary

1. **(A) the contact filter** (`grid_rescue_min_support=0.25`) is neutral:
   no crossing or time change on any suite (core C +0.33 items, core B
   +0.02 against the concurrent base). With the phase switch on, every
   low-phase call already takes the count path's 0.25, so the filter only
   matters in a few grid rescue calls a suite.
2. **(B) the low phase's rescue reserve** (`low_phase_rescue_seconds=1.5`)
   was redesigned after the stage timers. On C the low phase's ladder and
   stack option cost 0.2-0.5 s; the grid rescue was starved by the count
   pass's failed shadow checks (about 0.45 s each). So the flag also hands
   the reserve to the grid rescue out of the resort's window. In the
   replays it places c-c2p-s0001's declining call inside the budget (4.8 s;
   2.5 s at 2.0), where the base declines even at 8 s.
3. **On core C, B keeps all 48 crossings** with items flat (-0.08 alone,
   +0.38 with A). It is a time lever: slowest call 6.30 -> 5.33 / 5.26 s,
   placing calls over 5.3 s 13 -> 1 / 0, and at the 1.5x machine factor 11
   cut episodes -> 1 / 0. hard2 C (A+B): sample 33 -> 34, stretch 9 -> 9.
4. **On core B, B loses a crossing.** b-c2-s0002 goes 50 -> 41 in both B
   arms; with A, b-c2p-s0002 also goes 45 -> 40. The low phase covers most
   of a B episode, so cutting the ladder there changes the course. hard2-b
   is flat.
5. **Verdict.** Ship A + B on C only, through the gate added after the runs
   (`low_phase_rescue_single=True`; on B it reproduces the base exactly).
   Not on B. c-c1-s0003's bridge is still not reached inside 4.5 s: it is
   the 7th grid pose by contact-share order. Ordering the grid by the
   centre of mass's hull margin is the next step.

## 1. Design

**(A) `grid_rescue_min_support`** (default -1.0). `agent._grid_rescue` skipped
every grid pose off the floor whose contact share on the 5 cm skyline window
was under 0.5 (`count_mode_min_support`, 0.25 in the v50 arms, on the count
path). That 0.5 is the old support-ratio rule (`config.min_support_ratio`:
"not an official rule"); the validator's stability is the centre of mass
inside the convex hull of the contacts (`rule_alpha/stability.py`), and the
shadow judges the rest. With a value of 0 or more the filter is that value
off the count path and the smaller of it and `count_mode_min_support` on
it (`agent._grid_min_support`). The arm uses 0.25.

What it can reach: the count path is taken whenever `_under_count` is true,
and with `phase_switch` on that is **every low-phase call** as well as every
call under the count threshold. So on the v50 arms, where
`count_mode_min_support=0.25` already, (A) changes only the grid rescue calls
above the threshold *and* outside the low phase. c-c1-s0003's bridge (contact
0.36-0.48) was already admitted by the count path's 0.25: its problem was
time, not the filter.

**(B) `low_phase_rescue_seconds`** (default 0.0, the arm uses 1.5). In the low
phase (`_low_phase`, read once a call by the phase switch), with reserve R:

1. the ladder and the stack option take their usual shares (0.6 and 0.85)
   of the budget less R (4.5 s: ladder 1.8 s instead of 2.7, option 2.55 s
   instead of 3.825); the stack option's generation stops at its deadline
   (as `stack_deadline` does) and the option is skipped when the ladder has
   already passed it; the last resort ends at budget - R at the latest;
2. the physics resort (the count pass in the low phase) stops R before its
   deadline and the grid rescue takes the rest of the resort's window (with
   a pool: the larger of R and `grid_rescue_pool_seconds`, 1.5 on B, so no
   change there). The grid rescue's own window and cap are unchanged.

No end deadline moves: the stages start earlier inside the same call, and a
declining call ends where it did. Part 2 was added after the stage timers
(section 2) showed that on Task C the low phase's ladder and option are
cheap and the grid rescue is starved by the count pass's failed checks, not
by the ladder.

Unit tests (`tests/test_agent.py`, `BridgeRescueFlagTests`): the filter's
default figures and the flag's values; on a board of two 0.1 m columns with a
0.3 m slot, the default filter validates no bridge pose that the validator
accepts and the 0.25 filter admits 53; the stage deadlines handed out in one
declining call are unchanged with the flag off (in and out of the low phase)
and with the flag on outside the low phase; in the low phase the stack
option's deadline is 0.85 x (4.5 - 1.5), the last resort ends by 3.0 s, and
the resort's deadline is the grid rescue's less 1.5 s with the grid
rescue's end unchanged; with `low_phase_rescue_single` (added after the CI
runs, section 5) the reserve acts with a pool of one and not with a pool
of three.

## 2. Where the declining call's time goes on these boards

`stage_probe.py` (from `task-b-time-budget/`) over the v50 arm with
`stack_deadline=true`, seconds per call:

| scene, call | total | ladder | stack | last resort | resort (gen.) | shadow checks | grid |
|---|---|---|---|---|---|---|---|
| c-c1-s0003, the decline (21 placed) | 5.36 | 0.17 | 0.09 | 0.24 | 0.16 | 4.67 | - |
| c-c2p-s0001, the decline (47 placed) | 5.19 | 0.21 | 0.15 | 0.93 | 1.08 | 2.78 | 0.02 |
| c-c2p-s0001, low-phase count-mode placements | 2.5-3.3 | 0.4-0.5 | 0.15-0.3 | 0.6-1.1 | 0.35-0.9 | 0.2-1.1 | - |
| b-c1s-s0011, the decline (23 placed) | 5.29 | 2.54 | 0.94 | 0.50 | 1.01 | 0 | 0.29 |

On Task C the low phase's ladder (one item, one uninterruptible call of
0.2-0.5 s) and stack option (0.1-0.4 s) are not where the time goes; the
count pass's shadow checks are (about 0.45 s each). The B timer table's
"ladder 2 s, stack 1.2 s" is a pool of ten items run through both stages.

## 3. Replays at the declining call (`cf_flags.py`)

The episode runs under the v50 arm with `stack_deadline=true`; at the
declining call the same observation is asked again at 4.5 s under each
variant (the episode's timing state restored before each), and once at 8.0 s
for reference. Each check is traced (`show_trace.py`).

| scene (replay's decline) | base 4.5 s | A | B 1.5 | A+B 1.5 | A+B 2.0 | A+B 2.5 | base 8.0 s |
|---|---|---|---|---|---|---|---|
| c-c1-s0003 (21, margin 0) | declines (count 9 tries, grid 2) | the same | declines (count 7, grid 4) | the same | declines (count 6, grid 5) | declines (count 5, grid 5) | **grid-rescue-cover at 7.5 s, 7th grid try** |
| c-c2p-s0001 (48, +6) | declines (count 3) | the same | **grid-rescue at 4.79 s** | **at 3.96 s** | **at 2.45 s** | **at 2.37 s** | declines (count 6) |
| c-c2p-s0002 (54, +13) | declines, nothing to check | the same | the same | the same | the same | the same | the same |
| b-c1s-s0011 (25, +3, not low phase) | declines, nothing to check | the same | the same | the same | the same | the same | the same |

- **c-c2p-s0001**: the count pass's poses all fail; the grid rescue's first
  pose (0.55 m, contact 0.71, among 136) stands. The base call never reaches
  it, not even at 8.0 s (the count pass takes the whole window). With the
  reserve it is found inside the budget; at 1.5 s the call takes 4.8 s
  (7.2 s at the platform's 1.5x, under C's 8 s), at 2.0 s 2.5 s.
- **c-c1-s0003**: the grid rescue's ten poses are all covers at 0.86 m; it
  tries them by depth, then height, then contact share, so the 0.60 and 0.48
  poses (which fail) go before the 0.36 one (the bridge, which stands); the
  group rule skips a (bottom, share) group after three failures, so the
  bridge is the 7th try. The reserve raises the grid's tries from 2 to 4-5
  and still declines. Reaching it inside 4.5 s needs either about 3.5 s of
  reserve (the count pass would get one or two checks) or a grid order by
  the centre of mass's margin inside the contact hull instead of the
  contact share (not built; the unit test's board shows the hull, not the
  share, decides).
- **(A) changes nothing on these replays**: every declining C call here is
  in the low phase (count path, 0.25 already), and the B decline has no
  rescue pose to check at any filter.
- The 8.0 s reference is noisy: the same c-c1-s0003 call placed at 7.5 s
  alone on the machine and declined at 8.76 s with the C and B replays run in
  parallel. The c-c1-s0003 row is the run alone (`cf_c-c1-s0003.json`);
  the c-c2p rows ran beside the B replay (two processes on four cores).

## 4. CI

Ten bench runs on `claude/rl-packing-policy-ftogt3-bridge-rescue` (physics,
budget 4.5 s). The arms are the v50 arms (`arm_gate0_c.txt`,
`arm_gate0_b.txt`) **plus `stack_deadline=true`** (the shipped setting the
bench arms lacked), in the concurrent baselines too, so the four arms are
compared like for like: `base` (+ stack_deadline), `a` (+
`grid_rescue_min_support=0.25`), `b` (+ `low_phase_rescue_seconds=1.5`),
`ab` (both). Arm files: `reports/wedge/bridge-rescue/arm_*.txt`. Runs: core
38659420658 (base) / 38659425685 (a) / 38659430650 (b) / 38659436740 (ab);
core-b 38659423124 / 38659428275 / 38659433456 / 38659439160; hard2 (ab)
38663266250; hard2-b (ab) 38663268905. The recorded `gate0-*` baselines do
not carry the stack deadline, so on hard2 (no concurrent baseline) the time
columns mostly measure that setting.

**Core C** (`judge2.py`, `cmp_dirs.py`, `stats.py`, `cut15.py`):

| arm | crossings | placed vs gate0 / vs base | soft (uncov.) | fill | cog | priced vs base | rescue placements: resort / count / grid / grid-cover | ladder | time max / mean | placing calls > 5.3 s | 1.5x: episodes cut, crossings left |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gate0 (recorded) | 48 | 38.56 | 11.00 | 40.26 | 0.4012 | | 264 / 178 / 4 / 4 | 997 | 6.12 / 0.95 | 11 | 7, 47 |
| base | 48 | 37.98 (-0.58) | 10.88 | 39.82 | 0.4007 | | 264 / 173 / 0 / 5 | 1007 | 6.30 / 1.18 | 13 | 11, 45 |
| a | 48 | 38.31 (-0.25 / +0.33; 10 up, 4 down) | 10.92 | 40.13 | 0.4019 | -0.00 | 260 / 179 / 6 / 2 | 985 | 6.16 / 0.80 | 7 | 4, 46 |
| b | 48 | 37.90 (-0.67 / -0.08; 7 up, 12 down) | 11.04 | 39.62 | 0.3988 | +0.13 | 194 / 131 / 54 / 53 | 1002 | **5.33** / 1.15 | **1** | **1, 48** |
| ab | 48 | 38.35 (-0.21 / +0.38; 11 up, 8 down) | 11.00 | 40.09 | 0.4027 | -0.01 | 242 / 156 / 35 / 23 | 994 | **5.26** / 0.91 | **0** | **0, 48** |

**Core B:**

| arm | crossings | placed vs gate0 / vs base | soft (uncov.) | fill | cog | priced vs base | rescue: resort / count / grid / grid-cover | ladder | time max / mean | placing calls > 6.7 s | 1.5x: episodes cut, crossings left |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gate0 (recorded) | 48 | 39.56 | 10.19 | 41.07 | 0.4002 | | 101 / 122 / 15 / 27 | 1355 | 7.03 / 1.52 | 3 | 3, 48 |
| base | 48 | 39.35 (-0.21) | 10.02 | 41.01 | 0.4000 | | 102 / 124 / 12 / 16 | 1347 | 7.21 / 1.44 | 2 | 2, 48 |
| a | 48 | 39.38 (-0.19 / +0.02; 9 up, 11 down) | 10.00 | 41.02 | 0.3996 | -0.02 | 92 / 112 / 11 / 26 | 1365 | 7.32 / 1.38 | 2 | 1, 48 |
| b | **47** (b-c2-s0002 50 -> 41) | 39.50 (-0.06 / +0.15) | 10.10 | 41.13 | 0.4031 | -0.16 | 114 / 137 / 8 / 19 | 1363 | 7.42 / 1.45 | 5 | 4, 47 |
| ab | **46** (b-c2-s0002 50 -> 41, b-c2p-s0002 45 -> 40) | 39.79 (+0.23 / +0.44; 12 up, 7 down) | 10.21 | 41.40 | 0.4008 | +0.05 | 115 / 133 / 1 / 8 | 1364 | 7.35 / 1.25 | 3 | 2, 46 |

b-c2-s0002 ends at 41 in both the `b` and the `ab` run with the same last
steps, so it is the flag, not the clock: on Task B the low phase covers most
of an episode (38 of the base's 50 steps on that scene; the reserve acted on
29 of 41), and a ladder cut from 2.7 s to 1.8 s there changes the course,
not only the last call. On B the grid rescue's share was already 1.5 s
(`grid_rescue_pool_seconds`), so part 2 of the flag does nothing there and
the grid placements do not rise.

**hard2, A+B** (against the recorded runs, which lack the stack deadline):

| suite / stratum | crossings | placed |
|---|---|---|
| hard2 C sample | 33 -> 34 | 43.60 -> 43.23 |
| hard2 C stretch | 9 -> 9 | 49.44 -> 48.97 |
| hard2 C edge / fill-only | 1 -> 1 / 0 -> 0 | +1.62 / -5.75 (c-hard2-s0091 92 -> 49: its usual transport ending became a settle ending) |
| hard2-b sample, vs run 1 / run 2 | 35 -> 37 / 35 -> 37 | +0.04 / -0.25 |
| hard2-b stretch | 12 -> 11 / 12 -> 11 | +1.59 / +0.28 |
| hard2-b edge / fill-only | 1 -> 1 / 0 -> 0 | +5.75 +1.62 / -1.00 -0.50 |

| run | placed | soft uncov. | fill | cog | rescue: resort / count / grid / cover | ladder | time max | placing calls over the line | 1.5x: episodes cut, crossings left | settle endings |
|---|---|---|---|---|---|---|---|---|---|---|
| gate0-hard2 | 46.99 | 14.20 | 38.75 | 0.3905 | 499 / 258 / 114 / 68 | 2508 | 14.87 | 95 | 28, 39 | 4 |
| bresc-ab-hard2 | 46.30 | 14.49 | 38.54 | 0.3906 | 390 / 168 / 271 / 154 | 2454 | 5.95 | 8 | 7, 43 | 6 |
| gate0-hard2-b (r1 / r2) | 47.64 / 48.52 | 14.66 / 14.92 | 37.60 / 38.08 | 0.3897 / 0.3922 | 159 / 139 / 95 / 72 | 3232 | 23.97 / 14.17 | 55 / 63 | 7 / 10, 48 / 47 | 5 / 4 |
| bresc-ab-hard2-b | 48.58 | 14.95 | 38.20 | 0.3931 | 217 / 178 / 86 / 50 | 3278 | 7.41 | 11 | 9, 48 | 4 |

No call in any of the ten runs exceeds the platform limit on the bench (8 s
C, 10 s B); the slowest are 6.30 s (C, base) and 7.42 s (B, `b`).

## 5. Verdict

- **(A) `grid_rescue_min_support=0.25`: neutral, safe, little reach.** No
  crossing lost, no time change (C +0.33 items against the concurrent base,
  B +0.02, priced -0.00 / -0.02). With the phase switch on, the count path
  (0.25 already) covers every low-phase call, so (A) only acts in grid
  rescue calls above the threshold and outside the low phase: a few a
  suite. The C reading is within the run-to-run spread (the concurrent
  base itself is -0.58 against the recorded gate0). It can ship; it buys
  nothing measurable.
- **(B) `low_phase_rescue_seconds=1.5`: ship on C, not on B.** On core C it
  keeps all 48 crossings, items -0.08 alone and +0.38 with (A) against the
  concurrent base (both within noise), priced +0.13 / -0.01, and it is the
  time lever the bridge deep-dive asked for: the slowest call 6.30 -> 5.33 /
  5.26 s, placing calls over 5.3 s 13 -> 1 / 0, and at the 1.5x machine
  factor 11 cut episodes (45 crossings left) -> 1 / 0 (48). Grid rescue
  placements rise from 5 to 107 / 58 a suite as the count pass's failed
  checks stop eating its window. hard2 C (A+B): sample 33 -> 34, stretch
  9 -> 9, items -0.69 (against a record without the stack deadline;
  fill-only's -5.75 is one scene), placing calls over 5.3 s 95 -> 8. On
  core B it loses b-c2-s0002's crossing (50 -> 41, reproducible in both
  arms) and with (A) b-c2p-s0002's too (45 -> 40): the ship rule fails on
  B. hard2-b (A+B) is flat (sample 35 -> 37, stretch 12 -> 11, within the two
  baselines' own spread).
- **To ship (B) on C only** with the one set of B/C overrides, the flag has a
  gate, `low_phase_rescue_single=True` (the reserve only with a pool of
  one; unit-tested, added after the runs: on C it is the measured `b`
  form, on B it is the base exactly). Proposed overrides:
  `grid_rescue_min_support=0.25, low_phase_rescue_seconds=1.5,
  low_phase_rescue_single=True`. `submission/agent.py` was not touched.
- **The bridge itself is still not reached inside 4.5 s.** On c-c1-s0003 the
  grid's ten covers are tried in contact-share order and the bridge (0.36)
  is the 7th; ordering the grid rescue's poses by the centre of mass's
  margin inside the contact hull (what the validator and the settle read)
  instead of the contact share is the next cheap step, measurable with
  `cf_flags.py` on that scene. The bridge-spots price stands: about one item
  on a tenth of the sample-like declines, no platform crossing.
