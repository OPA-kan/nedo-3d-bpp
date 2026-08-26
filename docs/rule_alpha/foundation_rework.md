# Layer 1 foundation rework — back-first, frontier/follower, reachability

What was asked for, what was built, what the numbers say, and — the part worth
reading — **which of the six mechanisms turned out to do nothing, and why**.

Frozen for this round, unchanged: the wedge staircase at
`wedge_overhang_fraction = 0.25`, the shelf as first home for soft / priority /
SP, tall-perimeter, priority-container semantics, and the soft/priority
support-type constraints.

## The six principles, and what happened to each

| # | principle | built as | verdict |
|---|---|---|---|
| 1 | back-first as a *principle*, not a tie-break | `not-back-first` veto against the deepest **good** placement | **inert** — the shortlist is already back-sorted before the veto sees it |
| 2 | large flat hard is the frontier setter | manifest-quantile split; frontier ladder is foundation-first, standing demoted | **the main effect**, good and bad |
| 3 | small hard must not set the macro frontier | follower ladder + `breaks-frontier-bay` guard from the outstanding large footprints | works on the adversarial stream, inert elsewhere |
| 4 | Layer 1 leaves a terrace *seed* | falls out of 1, 2 and 5 | **unmeasurable** — see below |
| 5 | reachability priced above coverage | `reach_at`, `stranded_added`, `sealed_added` | the metric is right; **the veto never charges anybody** |
| 6 | backward compaction of pointless slack | bisection on +Y, then ±X for wall roles | **almost no slack exists** |

## Results — 13 scenarios, container 0

Baseline is `bd416a0`; the adversarial scenario `13` is new and was run against
both by copying it into a worktree of the old code.

| metric | before | after | |
|---|---|---|---|
| placed (total / mean) | 192 / 14.77 | 185 / 14.23 | **−3.6 %** |
| volume fill | 0.221 | 0.216 | **−2.3 %** |
| normal-hard back share | 0.679 | **0.717** | +5.6 % |
| normal-hard centre share | 0.236 | **0.319** | **+35 %** |
| stranded floor (m²) | 0.271 | **0.197** | **−27 %** |
| back-half reachability @ floor | 0.058 | 0.038 | −34 % |
| back-half reachability @ 0.40 m | 0.361 | **0.401** | +11 % |
| largest buildable hard pad (m²) | 0.277 | **0.299** | +8 % |
| back-to-front violations | 5.00 | **4.08** | **−18 %** |
| back-to-front adherence | 0.634 | **0.694** | +9 % |

Every structural target improved.  Throughput did not: seven items and about a
fiftieth of the fill were traded for them.

## Attribution: it is almost all one change

Isolated on seven scenarios (measured before the sealing fix below, which was
inert at the time and so does not affect the attribution):

| config | placed | fill | back | centre | stranded | pad | violations |
|---|---|---|---|---|---|---|---|
| baseline `bd416a0` | 114 | 0.228 | 0.715 | 0.297 | 0.280 | 0.278 | 5.43 |
| new code, everything switched off | 113 | 0.224 | 0.741 | 0.303 | 0.270 | 0.286 | 5.00 |
| + the gates only | 109 | 0.223 | 0.713 | 0.294 | 0.243 | **0.362** | 4.57 |
| + standing demotion only | 104 | 0.210 | 0.721 | **0.415** | 0.229 | 0.309 | **4.14** |
| everything on | 107 | 0.217 | 0.724 | 0.405 | **0.209** | 0.309 | 4.29 |

Row two is the parity check: with every new mechanism disabled the new code
reproduces the baseline, so the differences below it are real and attributable.

**Demoting standing is the lever.**  Not spending a big flat hard box as a tall
perimeter member is what moves centre share (0.303 → 0.415) and what costs the
throughput (113 → 104).  It is one flag: `frontier_prefers_lying`.  Turning it
off recovers two items and gives the *best* buildable pad of any configuration
(0.362), at the cost of the centre share the zoning asked for.  That is a real
choice and it is left switchable rather than decided silently.

## Why five of the six mechanisms are inert

**The candidate set is pruned before any principle can act.**  `choose_for_item`
shortlists by `(-y_back, -wall_contact)` per orientation and truncates.  By the
time the vetoes and the ladder run, the survivors are *already* the deepest
candidates, so:

* the back-first veto has nothing left to reject — it drops 15 candidates over a
  whole episode, none of which would have won;
* the reachability veto never fires either.  Sweeping
  `stranded_veto_area` over 0.12 / 0.20 / 0.30 **and disabling it entirely**
  gives byte-identical boards.  The front-stranding candidates it exists to
  refuse never reach the shortlist.

That is the finding that matters for the next round: **`back_first_slack` and
`stranded_veto_area` are not the knobs; the shortlist is.**  Any further work on
principle 1 or 5 has to widen or re-rank the shortlist first, or the rules will
keep being written downstream of the decision they are meant to make.

**The corridor veto was doing the work all along.**  Replacing
`corridor_release_fill` with the reachability price cost 8 % of throughput and
7 points of back share on its own, because the price never charges anybody.  It
is restored and now runs *alongside* the price, with a comment saying exactly
that.  Setting it to `0.0` runs on the price alone, and is worse.

**There is no backward slack to remove.**  Scanning every floor placement at the
moment it was made, in 5 mm steps: `09` and `12` have **zero** items with any
legal +Y travel, `01` has one with 0.030 m.  Over the whole suite compaction
removes 0.275 m, all of it on `10-awkward-holes`.  The existing x/y anchor set —
the back wall, and every packed box's edges — already produces tight placements.
The code is kept because it is cheap and the situation could change, but
principle 6 is answered: there was nothing there.

## One real bug the tests caught

`sealed_added` was first written as "what does this box seal, asked at its own
top".  That is **always zero**, and has to be: a box travelling at 0.40 m clears
a wall whose top is 0.40 m.  The metric was vacuous, which is a second reason
the reachability veto never fired.

It now asks at `reach_probe_heights = (0.0, 0.20, 0.40)` — the heights a later
item might actually arrive at — and takes the worst, skipping probes at or above
the candidate's own top where it cannot be in the way.  What a wall costs is
delivery to the *lower* ground behind it, not delivery at its own height.

## The terrace is not measurable yet

`slab_height_by_y_third` measures the depth profile of the foundation with the
structural members masked out, the same masking `foundation_slab_fill_ratio`
uses — because averaging the wall front into the depth thirds reports a "front
wall" that is really the chamfer wall seen end-on.

Masked, most boards have **one or two** non-structural hard floor items in
total, so two of the three depth thirds are empty and no shape can be read.
Layer 1 does not place enough general foundation cargo for `H_back ≳ H_mid ≳
H_front` to be a measurable property of its output.  Principle 4 is therefore
neither confirmed nor refuted here; it becomes measurable only once something
puts a second layer of ordinary cargo down.

## The adversarial stream works

`13-small-first-then-large`: twelve small hard boxes (0.073–0.123 m² footprint)
then eight large ones (0.378–0.443 m²).  Nothing in the stream is unusual on its
own; the order is the attack.

| | placed | centre share | pads | largest pad | buildable |
|---|---|---|---|---|---|
| before | 13/20 | 0.134 | 3 | 0.4256 | 0.664 |
| after | 13/20 | **0.505** | **6** | **0.4408** | **0.779** |

Same throughput, but the small cargo no longer carves up the floor: the largest
bay survives, the buildable fraction rises by a sixth, and the foundation is in
the centre instead of round the edges.  Note the honest caveat — `optimize()`
already reorders the manifest largest-first, so the follower guard is a second
line of defence rather than the only one, and it is the online path (where the
order is fixed) that needs it most.
