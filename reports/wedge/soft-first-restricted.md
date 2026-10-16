# The restricted soft-first pass on Task B

`config.soft_first_restricted` (off by default), arms `arm_sfr_b`,
`arm_sfr50_b`, `arm_sfrt_b` (`reports/bench/arms/README.md`), priced with
`bench.platform_score` against the shipped B form's records.

## 1. What

The platform prices a counted episode's soft component (weight 0.141) as
the share of the soft cargo placed and not covered by another attribute.
On B the pool order puts every soft item behind every hard one, and the
episode ends at the first call with no pose for any pool item -- in the
shipped form's records on a hard box's decline, with the soft cargo still
in the stream (sample-b: 40 of 128 soft boxes placed, 2 covered; core-b
479 of 874).  The soft credit has to be earned while the surface is there.

The earlier lever, `soft_first_when_free`, let a soft pool item go first
when the ladder's pose for it landed on a shelf, on soft cargo or on a top
too high for another hard box, and lost on B (findings, "The soft-first
pass on the v39 base": it took the shelves and the tops the priority
cargo needed, placement share 0.73 -> 0.58, three crossings lost).  What
the note there left of the idea is this pass: before the hard cargo is
tried, each soft item in the pool, smallest first, is offered the
ladder's pose (`layer1.choose_for_item`, so the cover rule and the shelf
preference apply as usual), and goes first only when

- the pose rests entirely on soft cargo (every box within the settle
  tolerance under its footprint soft), or
- it rests on hard tops none of the pool's hard or priority items could
  stand on (`surface.top_holds`);
- never on a shelf, never on the floor, never a normal soft box over a
  priority top.

`top_holds` mirrors the validator rather than the footprint: the official
rule is the centre of mass inside the convex hull of the contacts by
`com_margin` (0.03 m), overhang allowed, so a 0.65 x 0.45 box stands on a
lone 0.55 x 0.40 top and a footprint-in-patch test would have handed such
tops to soft cargo (the probe did, before the rule was read: the shipped
ladder put the pool's 0.65 x 0.45 box on exactly that top by
terrace-extension).  On the surface instrument's 2 cm grid
(`rule_alpha/surface.py`), a pool box stands at a window when its whole
footprint is free (its height plus the inclusion clearance, the band lift
and the anchor slack under the ceiling and the shelf plates, clear of
every box between the level and that height by the settled clearance,
past the chamfer, inside the walls), when it touches the top in question,
and when the level's support reaches past its centre by the margin on
both sides in x and in y.  The last condition is necessary for the hull
rule, not sufficient, and the transport sweep is not modelled, so the
test errs towards "a hard box fits": the safe side for a pass whose
failure mode is taking surface the hard count needed.  The pool's items
are tried flat (`soft_first_restricted_standing` adds their standing
poses; the ladder rarely stands a box on a top, and a standing footprint
fits almost any top).  The verdict costs 0.1-1 ms; the pass's cost is
the ladder decisions, bounded by `soft_first_restricted_share` (0.3) of
the budget with the strict accounting of the other stages.

`soft_first_restricted_tops` (arm `sfrt`): when the ladder's own pick is
refused, the pass asks for a pose on tops -- the ladder over item
surfaces only (`choose_for_item(surfaces=("item",))`, the typed
soft-on-soft column on for the ask) and then the stack option -- and
judges each the same way.  It exists because of the first local reading
below.  `phase_stats` (`metrics.phase` in the records) count the calls,
the decisions by source, every verdict and what fired on what (`sfr_*`).

Unit tests: `tests/test_soft_first_restricted.py` (a lone hard top the
pool's hard box stands on is refused; a top too high or hemmed in for
every pool hard box goes to the soft box; a shelf pose and a floor pose
refused; soft cargo under; a priority top under a normal soft box
refused; the standing poses when asked; the pass through `policy` on a
slab board; the tops ask after a refused pick; the ladder's surface
restriction).

## 2. Local readings (sample-b seeds 0 and 3, physics, budget 4.5)

The ladder's pick for a soft item on the sample's container, which has a
main shelf, is the shelf while the shelf has room and a floor edge after
it; the tops it does pick are ones the pool's hard boxes stand on.

| form | seed | placed | soft placed | pass calls / decisions | verdicts shelf / floor / top-usable / top / no pose | fired | pass seconds | policy mean / max |
|---|---:|---:|---:|---|---|---:|---:|---|
| ship | 0 | 26 | 2 | - | - | - | - | 0.77 / 4.70 |
| sfr | 0 | 26 | 2 | 27 / 138 | 39 / 36 / 11 / 0 / 52 | 0 | 11.1 | 0.93 / 3.75 |
| ship | 3 | 28 | 6 (2 covered) | - | - | - | - | 1.18 / 4.89 |
| sfr | 3 | 28 | 6 (2 covered) | 29 / 209 | 68 / 85 / 2 / 0 / 54 | 0 | 13.0 | 1.44 / 4.69 |
| sfrt | 3 | 32 | 10 (2 covered) | 33 / 437 (ladder 150, ladder-tops 144, stack 143) | 65 / 110 / 44 / 3 / 215 | 3 (all stack, on tops) | 30.7 | 2.05 / 4.83 |

So the pass as specified has nothing to judge on a layout with a shelf,
and the tops ask is what gives it a pose: on seed 3 the stack option's
pose for a soft box rested three times on a top no pool hard box could
use, the episode placed four more items, all soft, and the policy time's
mean rose 0.9 s a call (the max did not move; 21 of the asks were cut by
the deadline).

## 3. The suites

`python -m bench.platform_score <base> <new>` (physics, budget 4.5 s,
the bench-run workflow, 3 / 6 / 6 shards).  `sfr` is the pass as
specified at 30 % of the budget, `sfr50` at 50 %, `sfrt` with the tops
ask.

### 3.1 Against the shipped records

| suite (base) | run | score | delta [95 % CI] | counted | up / down | fill | cog | stability | placement | soft | placed | policy max |
|---|---|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| sample-b (55.44, 11/12) | sfr | 55.44 | +0.00 [+0.00, +0.00] | 11 (+0) | 0 / 0 | +0.0 | +0.0 | +0.0 | +0.0 | +0.0 | +0.00 | 4.9 s (base 5.8) |
| | sfr50 | 55.44 | +0.00 [+0.00, +0.00] | 11 (+0) | 0 / 0 | +0.0 | +0.0 | +0.0 | +0.0 | +0.0 | +0.00 | 4.6 s |
| | sfrt | 59.12 | +3.68 [-3.30, +12.42] | 12 (+1) | 8 / 4 | -0.0 | +5.3 | +7.8 | -16.0 | +22.6 | +1.00 | 5.3 s |
| core-b (61.58, 47/48) | sfr | 61.47 | -0.11 [-3.28, +3.10] | 47 (+0) | 10 / 17 | +0.4 | -0.6 | -0.6 | -0.7 | +1.1 | +0.29 | 7.3 s (base 7.4) |
| | sfr50 | 60.45 | -1.12 [-5.40, +2.55] | 46 (-1) | 11 / 15 | +0.4 | -2.3 | -2.4 | -1.5 | -0.1 | +0.08 | 7.4 s |
| | sfrt | 62.20 | +0.63 [-1.47, +3.84] | 48 (+1) | 19 / 29 | +0.7 | +0.9 | +2.0 | -2.9 | +1.6 | +0.62 | 7.0 s |
| hard2-b (32.70, 44/96) | sfr | 36.31 | +3.61 [+1.26, +6.56] | 50 (+6) | 37 / 18 | +0.9 | +4.2 | +5.7 | +3.9 | +4.7 | +0.70 | 7.3 s (base 7.5) |

### 3.2 How often it fired and where the soft went

Per run: the fires (all runs placed the fired soft box on a hard top
except the 36 + 4 `sfrt` fires on soft cargo), the source of the fired
pose, the ladder decisions the pass made and their verdicts, the pass's
seconds per call, the policy time's mean and maximum, and the soft and
priority readings per episode.

| run | episodes fired / n | fires | on soft / on top | ladder / ladder-tops / stack | decisions | shelf / floor / top usable / top / no pose / timeouts | pass s per call | policy mean / max (s) | soft placed, covered per ep (base) | priority placed, covered per ep (base) |
|---|---:|---:|---|---|---:|---|---:|---|---|---|
| sfr-sample-b | 0 / 12 | 0 | - | - | 1801 | 584 / 500 / 47 / 0 / 670 / 0 | 0.34 | 0.99 / 4.92 (0.98 / 5.81) | 3.33, 0.17 (same) | 1.42, 0.25 (same) |
| sfrt-sample-b | 12 / 12 | 39 | 4 / 35 | 0 / 2 / 37 | 4048 | 566 / 921 / 730 / 35 / 1781 / 40 | 0.59 | 0.96 / 5.33 | 5.25, 0.25 (3.33, 0.17) | 1.00, 0.17 (1.42, 0.25) |
| sfr-core-b | 20 / 48 | 29 | 0 / 29 | 29 / - / - | 12287 | 3027 / 3357 / 456 / 29 / 5418 / 2 | 0.31 | 1.13 / 7.35 (1.27 / 7.41) | 10.23, 0.15 (9.98, 0.04) | 4.71, 0.90 (4.79, 0.88) |
| sfr50-core-b | 20 / 48 | 29 | 0 / 29 | 29 / - / - | 12213 | 3027 / 3332 / 465 / 29 / 5360 / 0 | 0.36 | 1.24 / 7.41 | 10.06, 0.10 | 4.73, 0.85 |
| sfrt-core-b | 48 / 48 | 240 | 36 / 204 | 12 / 45 / 183 | 24131 | 2633 / 3967 / 4111 / 204 / 13141 / 893 | 0.86 | 1.54 / 7.04 | 10.27, 0.02 | 4.19, 0.48 |
| sfr-hard2-b | 14 / 96 | 24 | 0 / 24 | 24 / - / - | 17571 | 3576 / 5593 / 401 / 24 / 7977 / 91 | 0.24 | 0.90 / 7.34 (1.28 / 7.50) | 14.52, 0.23 (14.08, 0.27) | 5.25, 0.71 (5.14, 0.77) |

Three readings.  (i) The pass as specified fires on 1 in 400 of its
ladder decisions: the ladder's pick for a soft item is the shelf or the
floor on 86-90 % of the decisions that have a pose, and of the tops it
picks 19 in 20 hold one of the pool's hard boxes.  On B's 1.6 m
containers with 0.24-0.27 m hard boxes a top none of them stands on is
one within about 0.26 m of the ceiling or walled in by taller stacks;
the records do not say which kind each fire was.  (ii)
The tops ask multiplies the fires by eight on core-b, the stack option
giving three of every four fired poses, and the price is the priority
cargo: placed 4.79 -> 4.19 a scene (covered 0.88 -> 0.48, so the
priority boxes are not under the soft, they are not placed), the
placement component -2.9 on core-b and -16.0 on sample-b.  That is the
v39 soft-first pass's failure in a smaller form: the stack option's
"tops no pool hard box can stand on" are the tops the priority cargo in
the stream, and the hard boxes the stream brings after the pool, would
have stood on.  (iii) Time: the maximum step did not rise on any suite
(it fell by 0.1-0.9 s, the resort stages reached later); the mean rose
with the tops ask (core-b 1.27 -> 1.54 s a call), not with the pass as
specified (the ladder loop after it is shorter by what the pass tried).
The no-pose share is high (a third to a half of the decisions): a soft
item the ladder cannot place costs its decision on every call it sits
in the pool.

### 3.3 Fired against untouched episodes

The bases are the shipped records, run some commits ago; the pass
leaves an episode bit-identical only when the budget never binds
(sample-b), so each delta is split into the episodes the pass fired on
and the rest, whose difference is the replicate drift of the base.

| run | fired n | fired delta [95 % CI] | counted | up / down | untouched n | untouched delta [95 % CI] | counted | up / down / same |
|---|---:|---|---:|---|---:|---|---:|---|
| sfr-core-b | 20 | -2.44 [-8.90, +1.78] | -1 (b-c2-s0006 50 -> 41) | 8 / 12 | 28 | +1.55 [-0.64, +5.55] | +1 (b-c2-s0002, the known edge) | 2 / 5 / 21 |
| sfr50-core-b | 20 | -5.03 [-13.54, +1.37] | -2 (b-c2-s0006, b-c2p-s0002 51 -> 40) | 8 / 11 | 28 | +1.67 [-0.52, +5.66] | +1 (b-c2-s0002) | 3 / 4 / 21 |
| sfrt-core-b | 48 | +0.63 [-1.47, +3.84] | +1 (b-c2-s0002 41 -> 58) | 19 / 29 | 0 | - | | |
| sfrt-sample-b | 12 | +3.68 [-3.30, +12.42] | +1 (b-sample-s0010 21 -> 23) | 8 / 4 | 0 | - | | |
| sfr-hard2-b | 14 | +8.21 [+0.42, +19.70] | +2 (s0053 43 -> 50, s0077 19 -> 21) | 8 / 3 | 82 | +2.82 [+0.59, +5.54] | +4 | 29 / 15 / 38 |

On core-b the pass as specified loses where it fires (-2.4 a scene over
20 episodes, a crossing lost at b-c2-s0006, 50 -> 41 of 82) and the
suite's -0.11 is that loss against the base's drift; at half the budget
it loses more (two crossings).  On hard2-b it gains where it fires, +8.2
over 14 episodes against the untouched +2.8, so about +5 a fired scene
net of the drift, two crossings gained on the fired episodes and four on
the untouched ones.  The tops form fires everywhere, so it has no
untouched control; its core-b +0.63 is one edge crossing (b-c2-s0002,
which the untouched episodes of the other runs also cross) against 29
episodes down.

### 3.4 Against fresh replicates of the shipped arm

The drift above says the shipped records are stale, so the shipped arm
was run again on core-b and hard2-b in the same CI window
(`shipr-core-b`, `shipr-hard2-b`): against the shipped records they read
+1.17 [-0.22, +3.73] (one more counted, b-c2-s0002) and +1.97 [+0.27,
+4.28] (three more counted), which is the replicate noise of the stale
bases.  Against the fresh replicates 24 of 28 untouched core-b episodes
and 63 of 82 untouched hard2-b episodes are bit-identical, so the
untouched rows below are the control they should be.

| suite (fresh base) | run | score | delta [95 % CI] | counted | up / down | fill | cog | stability | placement | soft | placed | policy max |
|---|---|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| core-b (62.74, 48/48) | sfr | 61.47 | -1.28 [-3.89, +0.46] | 47 (-1) | 10 / 14 | +0.2 | -2.2 | -2.5 | -3.6 | +1.4 | +0.04 | 7.3 s (base 7.4) |
| | sfr50 | 60.45 | -2.29 [-6.07, +0.38] | 46 (-2) | 9 / 12 | +0.2 | -3.9 | -4.3 | -4.3 | +0.2 | -0.17 | 7.4 s |
| | sfrt | 62.20 | -0.54 [-1.63, +0.58] | 48 (+0) | 19 / 29 | +0.5 | -0.7 | +0.2 | -5.7 | +1.8 | +0.38 | 7.0 s |
| hard2-b (34.67, 47/96) | sfr | 36.31 | +1.63 [-0.07, +3.91] | 50 (+3) | 18 / 10 | +0.4 | +2.1 | +2.8 | +1.5 | +1.8 | +0.91 | 7.3 s (base 7.3) |
| | sfrt | 35.08 | +0.40 [-3.00, +3.69] | 48 (+1) | 33 / 30 | +0.9 | +0.9 | +0.9 | -2.2 | +0.5 | +1.29 | 7.2 s |

| run | fired n | fired delta [95 % CI] | counted | up / down | untouched n | untouched delta [95 % CI] | counted | up / down / same |
|---|---:|---|---:|---|---:|---|---:|---|
| sfr-core-b | 20 | -2.69 [-8.94, +1.40] | -1 (b-c2-s0006 50 -> 41) | 9 / 11 | 28 | -0.27 [-0.71, +0.08] | 0 | 1 / 3 / 24 |
| sfr50-core-b | 20 | -5.28 [-13.85, +1.04] | -2 | 9 / 10 | 28 | -0.15 [-0.45, +0.00] | 0 | 0 / 2 / 26 |
| sfrt-core-b | 48 | -0.54 [-1.63, +0.58] | 0 | 19 / 29 | 0 | - | | |
| sfr-hard2-b | 14 | +7.78 [-0.27, +19.60] | +2 (s0053 34 -> 50, s0077 19 -> 21) | 8 / 1 | 82 | +0.58 [-0.24, +2.04] | +1 (s0030 74 -> 80) | 10 / 9 / 63 |
| sfrt-hard2-b | 65 | +1.55 [-3.21, +6.43] | +2 (8 crossings changed, 5 up 3 down) | 33 / 28 | 31 | -2.00 [-5.74, +0.00] | -1 | 0 / 2 / 29 |

The tops form on hard2-b: 482 fires on 65 of 96 episodes (284 on soft
cargo, 198 on tops; 10 from the ladder's own pick, 209 from the tops
ask, 263 from the stack option), 34 788 decisions at 0.60 s a call, the
policy mean 0.82 -> 0.94 s and the maximum 7.33 -> 7.19 s; soft placed
13.71 -> 14.56 a scene, priority 5.18 -> 5.15 (covered 0.74 -> 0.59),
placement -2.2 all the same: the priority boxes are placed as often but
the count and the crossings move both ways (eight crossings changed on
the fired episodes, five gained and three lost, s0047 71 -> 58 and s0048
68 -> 62 among the lost).

## 4. Verdict

**Not shipped on B.**  Against fresh bases the pass as specified reads
core-b -1.28 [-3.89, +0.46] (one crossing lost; -2.69 over the 20
episodes it fired on, with the priority placement -8.1 there) and
hard2-b +1.63 [-0.07, +3.91] (three more counted; +7.78 [-0.27, +19.60]
over the 14 episodes it fired on, two crossings gained, the untouched
82 at +0.58 with 63 identical).  Half the budget makes core-b worse
(-2.29, two crossings).  The tops ask, which is what makes the pass fire
on the sample's kind of layout, reads sample-b +3.68 [-3.30, +12.42]
with soft +22.6 against placement -16.0, core-b -0.54 [-1.63, +0.58]
with placement -5.7, hard2-b +0.40 [-3.00, +3.69] with placement -2.2:
the stack option's soft poses on "tops no pool hard box stands on" are
the tops the priority cargo still in the stream would have stood on,
the v39 pass's failure in a smaller form.  The platform's B episodes are
core-b's kind, where every form loses; the one positive reading is the
specified form on hard2-b's dense manifests, where a soft box early on
a top under the ceiling is a count point the hard count would not have
taken, and that is worth a look on the next round as a count lever
(fired only under the count threshold, say) rather than a soft one.
Costs: the maximum step time did not rise on any run (it fell 0.1-0.9
s); the mean rose 0.1-0.3 s a call with the tops ask and not without
it.  Everything stays off by default.
