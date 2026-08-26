# rule-alpha — Layer 1 rule-based packing prototype

rule-alpha is an **independent, rule-based prototype** that builds only the
*first* layer of a ULD and then stops. It exists so that a human can look at
the boards it produces and argue about the rules — not to improve a score.

It does not touch `agent/agent.py` (the production policy), it is not in the
league, and it introduces no new objective. It *reuses* the geometry,
transport and physics helpers that `agent/agent.py` already carries
(`rule_alpha/_reuse.py` loads that module by path, read-only), so that both
share one model of the official validator.

```bash
python3 -m pip install numpy matplotlib
python3 -m rule_alpha.runner --out reports/rule_alpha           # boards + pictures
python3 -m unittest discover -s tests -p 'test_rule_alpha*.py' -v

# the PyBullet replay needs the simulator extras *and* Python 3.12 — the
# simulator's validator.py uses PEP 701 nested f-strings, which 3.11 cannot parse
python3.12 -m venv .venv312 && .venv312/bin/pip install -r requirements-simulator.txt
.venv312/bin/python -m rule_alpha.runner --scenarios 01-normal-no-shelf --physics
```

Outputs land in `reports/rule_alpha/`:

| path | contents |
|---|---|
| `report.md` | one table of every scenario plus a section each |
| `summary.json` | the same data as JSON, plus the exact config used |
| `physics.md` | the PyBullet replay table (`--physics` only) |
| `steps/<scenario>.jsonl` | one JSON record per placement (see below) |
| `steps/<scenario>.physics.json` | the official validator's verdict per step (`--physics`) |
| `images/<scenario>/c<N>_step<K>.png` | the four views after K placements |
| `images/<scenario>/c<N>_physics.png` | settled poses from PyBullet (`--physics`) |

---

## 1. What the ULD actually looks like

Everything below follows from the container geometry, so it is worth being
precise about it. `write_open_cut_corner_cup_obj` chamfers **one corner of the
length × height cross section** and extrudes it along the depth. In the world
frame the simulator uses:

```
        +Z  height
         |
         |        BACK  +Y
         |      /
         |    /
         |  /
         +--------------- +X  length
        /
   OPENING  -Y
```

* **`cut_x` is horizontal, `cut_y` is vertical.** The chamfer is therefore a
  long 45°-ish bevel running along the **bottom −X edge for the whole depth** —
  not a corner you can see from above.
* The **small shelf** (always present when `cut_x > 0`) sits directly above that
  bevel at mid height, spanning `x ∈ [−L/2+t, −L/2+t+cut_x]` for the full depth.
* A **lid** closes the chamfered strip at the opening plane, so nothing can be
  carried in through it. The validator agrees: the transport entry `x` is
  clamped to `x ≥ −L/2 + t + cut_x + dx/2 + start_margin`.
* The **opening is −Y and the back wall is +Y**; the main shelf, when present,
  covers the **back half** of the container at mid height.

For the official `sample_config` ULD (L 2.0, W 1.45, H 1.61, t 0.04,
cut_x 0.44, cut_y 0.40) rule-alpha derives — and a unit test checks against the
simulator's own mesh code — that

* the floor is usable only for `x ≥ −0.5445` (the chamfer foot), i.e. the bevel
  eats **0.415 m of every floor row, 21 % of the floor**;
* the chamfer meets the left wall at `z = 0.4177`;
* the wedge above the bevel is **0.078 m² in cross section, 0.111 m³ in total**.

### The floor-lift subtlety

`PlacementValidator.check_inclusion` accepts a pose only when every corner
satisfies `dots <= inclusion_margin`, and `inclusion_margin` is **−0.005**. A
box resting exactly on the floor plane gives `dots = 0` and is **refused**.

So rule-alpha separates two poses:

* the **settled pose** — bottom exactly on its support. This is what gets
  recorded, drawn and measured.
* the **commanded pose** — the settled pose lifted by `floor_action_lift`
  (20 mm) for floor placements, or by the shelf lift the production helper
  already models. This is what `policy()` returns; the item falls that far and
  settles.

The lift stays under the validator's 0.05 m "direct rest" window, so a floor
placement still travels in at floor height rather than being flown in from
above.

> Note for whoever owns `agent/agent.py`: on this frozen `main`,
> `Geometry.valid()` cannot accept **any** floor placement, because
> `inside_container` demands 16 mm of clearance from the floor plane while
> `support_ratio` demands contact within 6 mm. rule-alpha works around it
> locally; it did not change the production module.

### Finding: `inclusion_margin = -0.005` zeroes the fill score of floor cargo

The same −5 mm margin is used by `Evaluator.calculate_fill_rate`, but there it
is applied to the **settled** pose. A box that has settled on the floor sits a
few micrometres *into* the floor plane (PyBullet contact penetration), so its
floor-plane term is `+6e-06`, which is `> -0.005`, and the evaluator marks it
`not inside (hit boundary plane)` and drops its volume.

Measured, not inferred — the same four accepted placements, the same run, only
the margin changed:

```
inclusion_margin=-0.0050  placed=4  evaluation={'fill_score': 0.00, ...}
inclusion_margin=+0.0050  placed=4  evaluation={'fill_score': 7.57, ...}
```

The scenario sweep demonstrates the same thing without any patching. Across
all twelve `--physics` runs, **every** attempted placement was accepted by the
validator, and exactly one scenario scored above zero — `06-soft-priority-heavy`,
the only one that got cargo onto a shelf (6 SP items on the priority shelf,
`fill_score` 7.60). Its 12 floor-resting items contributed nothing.

Every placement passed `check_inclusion`, the transport sweep and the settle
check in both runs; only the scoring changed. On this snapshot, with
`simulator/configs/sample_config.json` as shipped, **cargo resting on the
container floor contributes nothing to `fill_score`** — only cargo stacked at
least 5 mm above the floor plane counts. Whether the intended value is
`+0.005` (a penetration tolerance) rather than `-0.005` (a required clearance)
is a question for whoever owns the config; rule-alpha only reports it. To
reproduce:

```bash
.venv312/bin/python -m rule_alpha.runner --scenarios 01-normal-no-shelf --physics
# then flip validator.inclusion_margin in rule_alpha/physics.py:scenario_to_config
```

---

## 2. Item classification

Every visible item is classified before the board is consulted
(`rule_alpha/classify.py`).

| class | condition | Layer 1 home |
|---|---|---|
| `normal-hard` | `soft=False, priority=False` | foundation: back band, then centre |
| `soft` | `soft=True, priority=False` | shelf first; otherwise the left soft strip, clustered |
|  |  | *note:* the **small shelf** exists whenever `cut_x > 0`, so even a "no shelf" ULD offers one — soft cargo goes there first in every scenario |
| `priority` | `soft=False, priority=True` | priority ULD if one exists, else the right edge strip |
| `soft-priority` | both | priority ULD, priority shelf if possible, else clustered on the edge |

Two orthogonal **roles** may be attached to a placement:

* `elongated` — `rho = max(l,w,h) / median(l,w,h) >= tau`, `tau = 1.80`
  (logged in every run's config block).
* `wall-front` — a hard item standing against the chamfer foot.
* `slope-infill` — an item genuinely inside the chamfer wedge.

Roles matter for two things: they are **exempt from the flatness metric** (they
are *supposed* to be tall), and they unlock the height-seeking orientation
policy.

### Orientation policy

| surface / role | rule |
|---|---|
| floor, plain cargo | maximise `dx·dy`, break ties with the lower `dz` |
| shelf, soft cargo | **minimise** `dx·dy` (the shelf is scarce), capped at `R <= 2.2` |
| wall-front / elongated hard | maximise `dz`, then lowest `R` |
| elongated **soft** | lies flat like plain cargo — a soft bag is not a structural member |

`R = dz / min(dx, dy)` is the tip-over proxy. The spec's bands are recorded on
every step (`tipping_band`): `< 1.5` normal, `[1.5, 2)` wall preferred,
`[2, 3)` wall strongly preferred, `>= 3` corner/backing required. rule-alpha
turns that into one hard rule: **`R >= 2.0` is refused unless the placement has
a wall or a tall neighbour behind it.**

---

## 3. Candidate archetypes and the rule ladder

There is no single weighted score. Each valid candidate is tagged with every
archetype it qualifies for, each archetype ranks its own candidates by its own
comparator, and the item's class picks which archetype is asked first.

Archetypes: `max-footprint`, `back-corner`, `minimum-hole`,
`largest-residual-rectangle`, `shelf-space-saving`, `soft-edge`,
`priority-edge`, `sp-cluster`, `elongated-wall`, `slope-infill`, `wall-front`.

Ladders (first match wins):

```
normal hard      slope-infill → wall-front → max-footprint → back-corner
                              → minimum-hole → largest-residual-rectangle
elongated hard   slope-infill → wall-front → elongated-wall → back-corner → minimum-hole
soft             slope-infill → shelf-space-saving → soft-edge → minimum-hole → back-corner
priority (P ULD) slope-infill → max-footprint → back-corner → minimum-hole
priority (N ULD) slope-infill → priority-edge → minimum-hole → back-corner
soft + priority  slope-infill → shelf-space-saving → sp-cluster → priority-edge → …
```

Inside any archetype, a candidate that leaves the opening alone always beats
one that does not.

### Vetoes (each is counted per step in the JSONL)

| veto | fallback? | meaning |
|---|---|---|
| `low-footprint-pose` | **no** | a plain floor pose worth < 60 % of the item's best footprint is refused outright: that item belongs to Layer 2 |
| `corridor` | yes | while floor coverage < 0.62, nothing may enter the front-centre corridor |
| `reserved-zone` | **no** | plain hard cargo may not cover > 15 % of itself with a reserved soft / priority strip — for the whole of Layer 1, not just early on |
| `wall-front-strip` | yes | non-wall material may not squat on the slope strip while the wall is unfinished |
| `interior-hole` | yes | a candidate opening an interior hole > 0.06 m² loses to any candidate that does not |
| `free-standing-tipping-risk` | yes | `R >= 2.0` without a wall or backing |

"Fallback" means: if the veto would empty the candidate set, it is skipped for
that step — so the rule is a strong preference, not a wall. The two vetoes
marked **no** have no fallback: an item that only survives by breaking them is
simply not placed in Layer 1.

The 15 % guard is low on purpose: at 35 %, several items each clipping a corner
of a strip added up to a strip that was gone, which is exactly the leak the
reservation exists to prevent. The price of the reservation is visible in the
`zone occupancy` block of every run — and §4 explains why a strip that nobody
needs is not reserved in the first place.

---

## 4. Spatial layout of a normal container

```
                         BACK  +Y
   +----------+----------------------------+-----------+
   | wall     |     back foundation band   |           |
   | front    |     (large hard cargo)     |           |
   | strip    +----------------------------+           |
   | (slope)  | soft |   centre: generic   | priority  |
   |          | zone |   hard support      | / SP zone |
   |          |      +---------------+     |           |
   |          |      |   transport   |     |           |
   |          |      |   corridor    |     |           |
   +----------+------+---------------+-----+-----------+
                        OPENING  -Y
```

**Assumption, recorded here because the spec's diagram and this ULD disagree:**
the spec puts the soft edge on one side and the chamfer is on that same side.
rule-alpha resolves it by splitting the −X edge — the outermost
`wall_front_strip_fraction` (22 % of the usable length) is structural, and the
soft zone starts just inside it.

### Zone widths come from the manifest

A reserved strip that no cargo wants is wasted floor. The environment hands the
whole item list to `optimize()`, so rule-alpha sizes each strip from the
*declared* stream — reading a list it was given, not guessing at unseen items:

* a strip reaches full width once its class holds `zone_reference_share`
  (25 %) of the stream by footprint, shrinks proportionally below that, and
  disappears entirely when the class is absent;
* soft demand is reduced by the main shelf's area, because soft cargo goes
  there first;
* in a **priority** ULD there is no soft strip at all (soft-only is never
  routed there) and the right strip is sized by the soft+priority share, which
  is what SP clustering needs;
* in a **normal** ULD, when a priority ULD exists, priority cargo is routed
  away and the priority strip is zero.

The scales used are logged per run (`zone_scales` in the summary, and
`soft_zone_scale` / `priority_zone_scale` in every container description), and
the pictures draw the strips at the width that was actually enforced.

---

## 5. Slope handling — and what actually happens

rule-alpha computes the chamfer analytically and generates `slope-infill`
candidates gated on all of: eight corners inside the ULD planes, real
penetration into the wedge (≥ 60 mm and ≥ 50 % of the box width), entirely
below the small shelf, a legal support, the **full transport sweep**, and the
settle proxy. Geometric fit alone is never enough.

The finding this prototype produces is a negative one, and it is worth stating
plainly:

> **With its bottom on the floor, no box can ever enter the slope pocket.**
> The binding constraint is the bottom-−X corner, which must clear the chamfer
> at floor height; that is exactly the definition of the floor limit. The
> pocket is only reachable by a box whose bottom is *raised* — i.e. resting on
> a Layer 1 item — and by then it is a Layer 2 move.

`allow_slope_infill_on_items` (default on) therefore lets a slope-infill
candidate rest on a **hard** Layer 1 item inside the pocket, counted separately
in the role histogram. It is the one documented exception to "Layer 1 only".

A second finding: **nothing can rest on the bevel itself.** For the shipped
ULD the bevel is 42.3° (`tan = 0.909`) against a lateral friction of 0.8, so a
box placed on it slides. The wedge is wall-front territory, not storage.

### Slope wall front

The wall front is the hard wall built against the chamfer foot (spec §10).
rule-alpha prefers **height over base area** there, and only spends items on it
that are *not* prime foundation material:

* base area ≤ 13 % of the usable floor (bigger boxes stay flat in the
  foundation),
* a pose at least 0.25 m tall,
* stop when the wall spans 85 % of the depth **or** reaches half the container
  height.

`wall_height / container_height` is printed on every picture and logged on
every step.

---

## 6. Flatness and hole diagnostics

Both are **local heuristics and diagnostics only**. Nothing here is or becomes
a competition objective; `surface_total_variation` is not resurrected.

*Flatness* is measured on a 2 cm heightmap with the structural cells
(`wall-front`, `elongated`, `slope-infill`) **masked out** — the rule is
"unintentionally bumpy is bad", not "tall is bad". Reported: plateau count,
height spread, mean local height step, what fraction of cells the mask removed,
and two plateau ratios:

* `largest_plateau_ratio` — largest plateau ÷ **the whole usable floor**. The
  denominator is deliberately the whole floor: measuring against the
  non-masked area alone would let a board of nothing but spikes score 1.00.
  Free floor counts as a plateau at floor height, because for Layer 2 it is
  one.
* `largest_built_plateau_ratio` — largest plateau that is actually *built on*
  ÷ the built non-structural surface. This is the one that says whether the
  foundation Layer 2 inherits is a single flat table or a patchwork.

*Holes* are connected components of free floor, split into

* **interior holes** — enclosed, the ones to avoid, each reported with id,
  area, centroid, bounding box, an approximate largest inscribed rectangle,
  distance to the container edge, distance to the opening, and the height and
  **typed support** of the ring around it;
* **open free space** — still connected to the perimeter. The largest such
  region and its best inscribed rectangle are reported, because "one big
  contiguous region" is preferred to "the same area, scattered".

Typed support is stored per cell so a future Layer 2 can read it:
`hard`, `soft-only`, `priority-only`, `soft+priority-only`, `free-floor`.

### Transport corridor

Two things are reported, because they are not the same:

* `corridor_free_ratio` — how much of the spec's front-centre rectangle is
  still empty;
* `corridor_clear_lane_ratio` — the fraction of entry columns that still have
  an **uninterrupted straight run from the opening**. This is the one that
  matches what `check_transport_path` actually does (a Y sweep at the entry `x`,
  then an X sweep at the target `y`).

---

## 7. Scenarios

| # | name | what to look at |
|---|---|---|
| 1 | `01-normal-no-shelf` | the reference rectangular floor |
| 2 | `02-normal-with-shelf` | same cargo, shelf ULD: where soft goes once a shelf exists |
| 3 | `03-priority-plus-normal` | routing: soft never enters the priority ULD, hard is budgeted |
| 4 | `04-soft-heavy` | shelf saturates, the rest must cluster on the soft strip |
| 5 | `05-priority-heavy-no-priority-uld` | the priority edge zone is the only home |
| 6 | `06-soft-priority-heavy` | SP → priority shelf, then clustered |
| 7 | `07-elongated-heavy` | `rho` 2.5–6: the structural exception path and the tipping bands |
| 8 | `08-slope-exploitation` | small low boxes: is the wedge reachable at all? |
| 9 | `09-mixed-random` | realistic mix matching the official class ratios |
| 10 | `10-awkward-holes` | sizes that tile badly on purpose — the hole diagnostics |
| 11 | `11-lookahead-3` | does the pool ordering rule change the board? |
| 12 | `12-large-hard-only` | best case for the floor rule, the flatness reference |

Item sizes follow the official `sample_config` envelope (L 0.45–0.75,
W 0.30–0.56, H 0.20–0.40, mass 5–18) except where a scenario exists precisely
to leave it. Every stream is seeded.

---

## 8. How to read the pictures

Each PNG has four panels and a three-line caption of the headline diagnostics.

**top view** — the floor plan.
* Fill colour is the cargo class: tan `normal-hard`, blue `soft`, green
  `priority`, purple `soft+priority`.
* Outline is the role: thick red `wall-front`, orange dashed `elongated`,
  magenta dash-dot `slope-infill`, thin grey plain.
* Items **on a shelf** are drawn translucent with a dotted purple outline —
  they sit above the floor, not on it. A shelf item can appear over the grey
  pocket band, because the small shelf is directly above the bevel.
* The grey band on the left is the part of the footprint the chamfer removes;
  the red dash-dot line is the floor limit (the wall-front line).
* Dashed rectangles are the zones. The label in each box is
  `item index` over `height of its top above the floor`.

**top-view diagnostics** — the same footprint, recoloured:
* coloured patches = plateaus of the non-structural surface (one colour per
  plateau),
* solid red = structural cells masked out of the flatness metric,
* white = free floor still connected to the perimeter,
* black = **interior hole**, labelled `H<id>` with its area,
* grey = outside the usable floor (the pocket).

**opening view** — looking along +X: depth against height, opening on the left.
This is the picture for "does the board slope up towards the back" and "is
anything tall near the opening". The dotted red line is half the container
height.

**slope view** — looking along +Y: the pentagon cross section with the bevel,
the grey unreachable wedge, the magenta pocket outline, the small shelf and
everything projected onto it. This is the picture for the wall front.

---

## 9. Step log format

`reports/rule_alpha/steps/<scenario>.jsonl` — one JSON object per line:

* `record: "scenario"` — the config used and the derived geometry of every
  container.
* `record: "step"` — item index, `is_soft` / `is_prioritized`, class, role,
  `elongation_rho`, container, surface (`floor` / `shelf` / `item`),
  orientation index and `dx/dy/dz`, footprint, `tipping_ratio` and
  `tipping_band`, local position, the winning `archetype`, a human-readable
  `reason`, `candidate_count_by_archetype`, `veto_count_by_rule`,
  `archetype_ladder`, `transport_ok`, `settle_ok`, and a `board` digest with
  floor coverage, `wall_height_ratio`, largest plateau ratio, plateau count,
  interior hole count/area, largest interior hole and the remaining contiguous
  free floor.
* `record: "unplaced"` — items Layer 1 could not take.
* `record: "summary"` — the end-of-episode report, including the full
  per-container flatness / hole / wall / corridor blocks.

With `--physics`, `steps/<scenario>.physics.json` additionally carries the real
`is_included` / `is_valid` (transport) / `is_placed_safe` (settle) from the
official validator, plus the environment's own evaluation.

---

## 10. Known limitations and assumptions

1. **Layer 1 only.** There is no Layer 2, no staircase, no recursion. Items
   that need a second layer are logged as `unplaced`, not packed. Floor
   coverage in the 60–80 % range is therefore the expected result, not a
   failure.
2. **The analytic driver skips instead of terminating.** The official
   environment ends the episode on the first failed placement; the scenario
   runner keeps going so that the whole board is visible. Pass
   `--stop-on-unplaceable` for the official behaviour. This is why a
   `--physics` run places far fewer items than the analytic run of the same
   scenario: with `look_ahead = 1` the pool holds a single item, and the moment
   Layer 1 has no home for it rule-alpha declines and the episode is over. The
   analytic board is "what Layer 1 could build"; the physics board is "what
   Layer 1 alone gets through the official loop".
3. **The settle proxy is analytic.** Offline, "settled" means: support ratio
   ≥ 0.60 and the centre of mass over the contact patch. Only `--physics` runs
   the real 300-step settle. Soft-body compliance is not modelled offline at
   all.
4. **No lookahead beyond the pool.** `optimize()` reorders the stream with a
   fixed rule (wall material, then foundation largest-first, then structural
   oddments, then priority, SP, soft). Nothing anywhere assumes knowledge of
   items that are not visible.
5. **Zones are rectangles fixed at optimize time.** Their *widths* come from
   the declared manifest (§4), but once set they do not move as the board
   fills, and their depths and positions are plain fractions of the usable
   floor.
6. **The soft/priority reservation has no fallback.** Once a strip is sized, no
   plain hard cargo enters it for the rest of Layer 1, even when the strip's
   own class has stopped arriving. The cost shows up as empty strips and lower
   coverage; `zone occupancy` in the report measures it.
7. **Order matters and is fixed.** With the foundation-first order, a
   priority-heavy stream can fill the floor with plain hard cargo before the
   priority cargo is reached; the reserved strip is what stops that becoming
   total starvation. Whether the order should instead front-load constrained
   cargo is exactly the kind of question this prototype exists to raise —
   scenario 05 is the picture to argue over.
8. **`slope-infill` may rest on a Layer 1 item.** The one documented exception
   to the Layer 1 scope, for the reason in §5. It can be disabled with
   `allow_slope_infill_on_items = False`.
9. **A priority container still gets plain hard cargo** as foundation, capped
   at 45 % of its usable floor so it cannot be filled up before the priority
   cargo arrives. Soft-only cargo is never routed there.
10. **Multi-container routing is first-fit** down the routing order; there is no
   balancing between containers.
11. **Nothing here is tuned.** Every threshold in `rule_alpha/config.py` is a
    starting point, dumped into every run so a picture can always be traced
    back to the numbers that produced it.

---

## 11. Files

```
rule_alpha/
  config.py       every threshold, dumped into each run
  _reuse.py       read-only bridge to agent/agent.py's geometry helpers
  geometry.py     analytic cut-corner cross section, zones, slope pocket
  classify.py     item classification + orientation policy
  layer1.py       candidate generation, archetypes, vetoes, the rule ladder
  diagnostics.py  heightmap, plateaus, holes, typed support, corridor
  episode.py      analytic Layer 1 driver + JSONL logging
  physics.py      the same planner inside the real PyBullet environment
  agent.py        the official get_init_states / optimize / policy interface
  visualize.py    the four views and the diagnostic overlay
  scenarios.py    the twelve scenarios
  runner.py       CLI: boards, pictures, report
tests/test_rule_alpha.py
docs/rule_alpha/README.md   (this file)
```
