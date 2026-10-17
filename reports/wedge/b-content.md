# Task B's content: priority never covered, and a deferral limit for the pool

Branch `claude/rl-packing-policy-ftogt3-bcontent`; flags
`priority_never_covered` and `pool_defer_max` (both off by default);
arms `arm_nc_b`, `arm_k3_b`, `arm_k6_b`, `arm_nck_b`
(`reports/bench/arms/README.md`); records `reports/bench/nc-*`, `k3-*`,
`k6-*`, `nck-*`, priced with `bench.platform_score` against
`ship-sample-b`, `shipr-core-b`, `shipr-hard2-b`.

## 1. What the shipped B form leaves on the table

The platform's 11 B episodes are all counted (over half placed, the
fraction about 0.62) and score placement 48 and soft 51 an episode
against Task C's 78 / 64 with the same ladder.  C must place what
arrives; B's pool order puts every soft and priority item behind every
hard one, and the episode ends on a hard box's decline with the typed
cargo still in the stream.  The shipped records say where the credit
goes (`contact_covered_pairs` are `[victim, other]`; the archetype is
the covering box's placement, the threshold half the stream plus one):

| record | priority placed / covered | of which count pass / grid rescue / other | over the threshold / under | soft placed / covered |
|---|---:|---|---|---:|
| ship-core-b (the stale base) | 230 / 42 | - | - | 479 / 2 |
| shipr-core-b | 231 / 39 | 33 / 3 / 3 (physics-resort 2, stack-rl 1: settled contacts the AABB rule did not read) | 34 / 5 | 477 / 10 |
| ship-sample-b | 17 / 3 | - (the 3 are settled contacts) | - | 40 / 2 |
| shipr-hard2-b | 497 / 71 | 53 / 22 / 7 | 28 / 54 | 1316 / 13 |

So on core-b 17 % of the placed priority boxes lose their credit, nearly
all of them to the count pass's covers in the low phase above the
threshold (`phase_switch_cover`), where a cover buys a count point an
episode that is counted with room to spare does not need.  On hard2-b
the covers are mostly under the threshold, where they do buy counts.

### 1.1 `priority_never_covered` (arm `nc`)

`count_cover_priority=false` alone narrows the count pass above the
threshold only: under it the covers of priority stay allowed whatever
the switch says (the v32 crossings rest on them), and the grid rescue
took every cover the count pass allowed without reading the switch at
all.  The new flag closes both paths: `_priority_cover_allowed` is the
one reading the count pass (`stack_candidates`, through the
`count_cover_priority` it is handed) and the grid rescue share -- never
with the flag, under the threshold proper yes, above it only while
`count_cover_priority` says so.  Soft cargo may still be covered under
the count pass's rules (soft on soft is not charged; a soft box's share
is one of fifteen, a priority box's one of three).  The arm is the
shipped B form plus `count_cover_priority=false,priority_never_covered=true`.
Phase stats: `prio_cover_refused_count` (the count pass's poses refused
at generation), `prio_cover_refused_grid` (the grid rescue's).

### 1.2 `pool_defer_max` (arms `k3`, `k6`)

Per item index the agent counts the calls the item sat in the pool
while another item was placed (`_passed_over`, updated in `policy`
after every placement).  A soft or priority item at k or more goes to
the front of the ladder's order (`_defer_order`, after `pool_order`;
several keep the pool order among themselves: priority before soft,
smallest first), the hard items after it, and every stage reads the
reordered list: the ladder's own pose for it or none, then the next
item, the usual rules applying (the cover rule, the shelf preference,
the headroom reserve).  Nothing is searched that the ladder would not
search for the item anyway, so the time is the ladder's.  The earlier
levers went first on the pose's *surface* (`soft_first_when_free`, the
restricted pass) and took the tops and shelves the priority cargo
needed; this one goes first on *time*, keeping the pool's advantage
for the first k passes.  Phase stats: `defer_calls`, `defer_items`,
`defer_fired` (with `_soft` / `_priority` and the archetype),
`defer_passed`.

Unit tests: `tests/test_b_content.py` (the count pass's generator
refuses a pose over a priority box under the rule and keeps the poses
over a soft box; `_priority_cover_allowed` under and over the threshold
with each switch; the deferral order with a soft item at k, under k, a
hard item at k, several deferred items; through `policy`: the hard box
goes first and the soft box is passed over, and the soft box passed
over k times goes first).  The full set (`tests.test_rule_alpha
tests.test_agent tests.test_bench tests.test_count_secure` plus these)
passes: 298 tests.

## 2. Local readings (sample-b seed 0, physics, budget 4.5)

| form | placed | soft placed | priority placed / covered | fires | policy mean / max | price against the shipped record |
|---|---:|---:|---|---|---|---|
| ship (CI record) | 26 | 2 | 1 / 0 | - | 0.77 / 4.70 | - |
| nc | 26 | 2 | 1 / 0 | 60 count-pass poses refused, the episode step for step the ship's | 0.44 / 2.92 | +0.00 |
| k3 | 22 | 6 | 1 / 0 | 7 deferred items, 7 fired (shelf-space-saving 4, pocket-soft 1, priority-edge 1, physics-resort 1) | 0.47 / 3.05 | +3.53 (soft +36.4, fill -10.3, cog +6.2) |

On seed 0 the four deferred soft boxes took the main shelf at steps 3-6
(the ship's hard boxes used it at steps 5-8 and 20), the episode placed
four items fewer and the price is still positive: four of eleven soft
boxes are 36 soft points at the weight 0.141, four hard boxes are 10
fill points at 0.287.  The suites decide whether that holds.

## 3. The suites (CI, the physics simulator, budget 4.5 s)

`python -m bench.platform_score <base> <new>`, the bench-run workflow,
3 / 6 / 6 shards; the bases `ship-sample-b`, `shipr-core-b`,
`shipr-hard2-b` (the fresh replicates of the shipped B arm,
soft-first-restricted.md section 3.4).

### 3.1 The first wave: never covered, the deferral at 3 and 6

| suite (base) | run | score | delta [95 % CI] | counted | up / down | fill | cog | stability | placement | soft | placed | policy max |
|---|---|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| sample-b (55.44, 11/12) | nc | 55.81 | +0.38 [-1.44, +2.23] | 11 (+0) | 2 / 1 | -1.2 | +0.8 | +0.0 | +9.7 | -5.9 | -1.00 | 4.3 s (base 5.8) |
| | k3 | 66.30 | **+10.86 [+5.24, +18.25]** | 12 (+1) | 11 / 1 | -6.8 | +8.7 | +7.8 | +18.8 | +46.7 | -0.83 | 5.7 s |
| | k6 | 65.65 | **+10.21 [+1.24, +22.07]** | 12 (+1) | 10 / 2 | -7.0 | +8.7 | +8.1 | +16.7 | +44.4 | -1.00 | 6.0 s |
| core-b (62.74, 48/48) | nc | 58.90 | **-3.85 [-8.70, -0.07]** | 44 (-4) | 23 / 13 | -1.8 | -5.2 | -8.2 | +8.0 | -11.4 | -2.35 | 7.0 s (base 7.4) |
| | k3 | 59.58 | -3.16 [-8.76, +1.58] | 43 (-5) | 30 / 18 | -7.4 | -4.0 | -10.1 | -1.5 | +15.5 | -1.67 | 7.4 s |
| | k6 | 65.18 | **+2.44 [+1.32, +3.71]** | 48 (+0) | 36 / 12 | -4.9 | +3.1 | -0.8 | +4.2 | +19.4 | -0.40 | 7.3 s |
| hard2-b (34.67, 47/96) | nc | 33.29 | -1.38 [-4.31, +1.48] | 45 (-2) | 22 / 38 | -1.1 | -1.0 | -2.7 | +1.7 | -3.6 | -0.75 | 7.5 s (base 7.3) |
| | k3 | 36.84 | +2.17 [-1.39, +6.13] | 49 (+2) | 51 / 32 | -1.9 | +2.1 | +2.1 | +4.0 | +8.9 | +0.47 | 7.4 s |
| | k6 | 36.22 | +1.55 [-1.77, +5.02] | 49 (+2) | 40 / 43 | -1.3 | +2.0 | +2.2 | +0.9 | +6.4 | +0.28 | 7.2 s |

### 3.2 The never-cover rule: where the count came from

Per run the covers refused at generation (`prio_cover_refused_count`
counts the count pass's poses dropped, `_grid` the grid rescue's), the
episodes the rule touched (any refusal), the soft and priority readings
per episode, and the price split by touched / untouched:

| run | refused: count pass / grid | touched / n (identical to the base) | priority placed, covered per ep (base) | soft placed, covered per ep (base) | touched delta [95 % CI] | untouched |
|---|---|---|---|---|---|---|
| nc-sample-b | 12 230 / 1 741 | 5 / 12 (9) | 1.42, 0.00 (1.42, 0.25) | 2.42, 0.00 (3.33, 0.17) | +0.90 [-3.46, +4.69], placement +23.3, soft -14.2 | +0.00, 7 of 7 identical |
| nc-core-b | 119 825 / 22 629 | 39 / 48 (12) | 4.75, 0.00 (4.81, 0.81) | 8.15, 0.06 (9.94, 0.21) | -4.73 [-10.42, -0.07], 4 crossings lost, placement +9.9, soft -14.0 | +0.00 |
| nc-hard2-b | 234 909 / 22 950 | 53 / 96 (34) | 4.96, 0.03 (5.18, 0.74) | 13.67, 0.25 (13.71, 0.14) | -3.64 [-8.56, +0.64], -3 counted, placement +2.1, soft -8.5 | +1.40 [-0.46, +4.69], +1 |

The rule does what it says: the priority boxes covered fall from 39 to
0 on core-b (the 3 left on hard2-b and the 4 on core-b's tally by
archetype are settled contacts under terrace or stack poses the AABB
cover rule did not read), and the placement component gains +8.0 on
core-b.  But the count pass's covers are what the low phase runs on:
without the poses over priority cargo the pass has 8-9 items fewer an
episode on the four core-b scenes that fell under the threshold
(b-c1-s0004 28 -> 20 of 41, b-c1-s0006 27 -> 19: the base's last four
placements on each are count-mode poses at 0.55-1.37 m, the rule's
episodes end on the ladder's decline at step 19-20 with no rescue pose
standing), the soft boxes that would have gone on top of them are
never placed (soft -11.4), and the lost crossings take cog and
stability with them.  So the priority credit the covers cost (one of
three priority boxes, 0.143 x 33 = 4.7 points) is less than the count,
the soft credit and the gated components a cover buys on the scenes
where the count pass is the only thing still placing.  The low-phase
form (`count_cover_priority=false` alone, now closing the grid rescue
too: arm `ncl`) is measured in the second wave, since 34 of core-b's
39 covered priority boxes were covered over the threshold.

### 3.3 The deferral: how often it fired and where the deferred cargo went

| run | calls with a deferred front | items that reached k | fired (soft / priority) | passed over again | fired by archetype |
|---|---:|---:|---|---:|---|
| k3-sample-b | 116 | 101 | 97 (78 / 19) | 16 | shelf-space-saving 51 %, pocket-soft 14 %, soft-edge 11 %, stack-rl 7 %, priority-edge 6 % |
| k6-sample-b | 117 | 92 | 89 (73 / 16) | 25 | shelf-space-saving 33 %, pocket-soft 27 %, soft-edge 15 %, stack-rl 13 %, fallback 4 % |
| k3-core-b | 906 | 725 | 700 (483 / 217) | 188 | pocket-soft 30 %, shelf-space-saving 24 %, stack-rl 13 %, soft-edge 10 %, fallback 7 %, priority-edge 6 % |
| k6-core-b | 888 | 686 | 655 (458 / 197) | 214 | pocket-soft 30 %, shelf-space-saving 24 %, stack-rl 13 %, soft-edge 11 %, fallback 8 %, priority-edge 7 % |
| k3-hard2-b | 1 819 | 1 544 | 1 411 (1 025 / 386) | 370 | pocket-soft 30 %, soft-edge 15 %, shelf-space-saving 14 %, stack-rl 12 %, max-footprint 6 %, fallback 5 % |
| k6-hard2-b | 1 326 | 1 096 | 981 (710 / 271) | 313 | pocket-soft 29 %, soft-edge 15 %, stack-rl 14 %, shelf-space-saving 12 %, max-footprint 7 %, physics-resort 6 % |

| run | placed per ep (base) | soft placed, covered per ep (base) | priority placed, covered per ep (base) | com ratio (base) | topples (base) | settle ends (base) | policy mean / mean of ep maxima / max (base) |
|---|---|---|---|---|---|---|---|
| k3-sample-b | 25.58 (26.42) | 8.00, 0.25 (3.33, 0.17) | 1.67, 0.25 (1.42, 0.25) | - | - | 0 (0) | 0.54 / 3.17 / 5.70 (0.98 / 4.96 / 5.81) |
| k6-sample-b | 25.42 (26.42) | 7.58, 0.17 (3.33, 0.17) | 1.50, 0.17 (1.42, 0.25) | 0.382 (0.401) | 2 (2) | 0 (0) | 0.72 / 3.71 / 6.02 |
| k3-core-b | 37.56 (39.23) | 13.42, 0.23 (9.94, 0.21) | 4.85, 0.69 (4.81, 0.81) | - | - | 1 (0) | 0.76 / 4.38 / 7.42 (0.95 / 5.10 / 7.42) |
| k6-core-b | 38.83 (39.23) | 13.19, 0.46 (9.94, 0.21) | 4.79, 0.58 (4.81, 0.81) | 0.375 (0.397) | 28 (18) | 3 (0) | 0.81 / 4.42 / 7.35 |
| k3-hard2-b | 46.76 (46.29) | 16.28, 0.26 (13.71, 0.14) | 5.67, 0.77 (5.18, 0.74) | 0.377 (0.388) | 79 (96) | 7 (7) | 0.86 / 4.23 / 7.41 (0.82 / 4.35 / 7.33) |
| k6-hard2-b | 46.57 (46.29) | 15.76, 0.31 (13.71, 0.14) | 5.61, 0.72 (5.18, 0.74) | - | - | 4 (7) | 0.83 / 4.35 / 7.21 |

On hard2-b the deferral touches 84-89 of 96 episodes and reads +1.55
(k6) / +2.17 (k3) with wide intervals: the crossings move both ways
(k6: 10 changed, 6 gained and 4 lost; the untouched 12 at +0.02), the
placed count is level, and the gain is soft +6.4 / +8.9 with placement
+0.9 / +4.0 (more priority boxes placed, 5.18 -> 5.61 a scene).

What the counts say.  (i) The limit is reached by nearly every typed
item of the pool (686 items on 48 core-b episodes, 14 an episode, where
the base places 10 soft and 4.8 priority boxes an episode): the pool
order defers them all, and k only sets when they come up.  (ii) The
deferred item has a ladder pose three calls in four (fired 655 of 888
on k6-core-b), mostly a typed one -- the pocket-soft and soft-edge
archetypes and the shelf, which the hard cargo was using when the soft
item came up at the end of the stream -- and the stack option for one
in eight; 7-8 % of the fires are the shadow's fallback, a pose the
shadow hard-vetoed and nothing replaced, which is where the settle ends
come from (b-c2-s0001 on k6-core-b, 55 -> 48, the last pose a
terrace-extension kept after a veto).  (iii) The soft boxes placed go
from 10 to 13 an episode on core-b (42 of 48 episodes up, 4 down) and
from 3.3 to 7.6-8.0 on sample-b, every episode up; the priority boxes
placed are level and fewer of them are covered (0.81 -> 0.58 a scene on
k6-core-b: a priority box placed at step 20 is not under the count
pass's late poses the way one placed at step 38 is).  (iv) The price
of the time is the hard cargo: 0.4 items fewer an episode at k6 and
1.7 at k3 on core-b (a soft box on the shelf at step 6 is a hard box
not on it at step 20: fill -4.9 / -7.4), and at k3 the earlier soft
cargo changed the layout enough to lose five crossings (b-c2-s0007 50
-> 22 of 82 ended on a settle failure at step 22: the shadow check was
skipped at 4.42 s of the 4.5 s budget on a stack-rl pose, and the
pose tipped 33 degrees).  At k6 all 48 count, and the centre of mass
is lower (0.397 -> 0.375: the soft cargo goes on the shelf and the
pockets, not on top of the load at the end).  (v) Time: the mean of the
episode maxima falls on every suite (the resort stages are reached
less often), the maximum step does not rise, and the mean rises
0.1-0.2 s a call on the hard suite.
