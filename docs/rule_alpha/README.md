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

### Release-and-drop: why there are two poses

The robot cannot set cargo down in contact; it has to release a little above
the resting surface and let it drop. `PlacementValidator.check_inclusion`
enforces that on the **commanded** pose: every corner must satisfy
`dots <= inclusion_margin`, and with `inclusion_margin = −0.005` a pose that
touches the floor plane (`dots = 0`) is refused.

So rule-alpha separates two poses:

* the **settled pose** — bottom exactly on its support. This is what gets
  recorded, drawn and measured.
* the **commanded pose** — the settled pose lifted by `floor_action_lift`
  (20 mm) for floor placements, or by the shelf lift the production helper
  already models. This is what `policy()` returns; the item falls that far and
  settles.

The lift stays under the validator's 0.05 m "direct rest" window, so a floor
placement still travels in at floor height rather than being flown in from
above. This is compliance with the placement spec, not a workaround.

> This is the same defect rule-alpha first reported in `agent/agent.py`, where
> `Geometry.valid()` applied both requirements to the *same* pose —
> `inside_container` wanting 16 mm of clearance from the floor plane while
> `support_ratio` wanted contact within 6 mm — so no floor placement was
> reachable at all (measured: 0 of 20 floor candidates valid). That is now
> fixed in the production module along the same two-pose lines; see
> `FLOOR_ACTION_LIFT` and the Geometry contract comment there.

### Finding: the settled-pose margin is a crush check, and its sign decides everything

`Evaluator.calculate_fill_rate` applies the same `inclusion_margin` to the
**settled** pose. Because the container floor is a wall of real thickness and
PyBullet resolves contact with a load-dependent penetration, a settled box
sits slightly *into* the floor plane — and the heavier the stack on top of it,
the deeper. That is what the margin is there to catch: cargo crushed into the
container body is not really inside it.

rule-alpha measures the curve rather than assuming it
(`.venv312/bin/python -m rule_alpha.penetration`, raw data in
`reports/rule_alpha/penetration.json`). One 0.60 × 0.45 × 0.25 m box on the
floor, then 18 kg boxes stacked on top of it:

| bottom box | load resting on it | penetration into the floor plane |
|---|---|---|
| hard | 0 kg | 0.012 mm |
| hard | 36 kg | 0.019 mm |
| hard | 72 kg | 0.058 mm |
| **soft** | 0 kg | **9.005 mm** |
| **soft** | 36 kg | **26.857 mm** |
| **soft** | 72 kg | **47.271 mm** |

Two things fall out of this.

**The crush check is a soft-cargo check.** A hard box never gets near a 5 mm
budget — 0.058 mm under 90 kg total, roughly 80× of headroom. A soft box is
already 9 mm in under its own weight, and 47 mm — a fifth of its own height —
with four boxes on it. So "stack too much and it sinks out" is real, and it is
a statement about soft cargo on the floor, not about mass in general.

**The sign is doing the opposite of that.** `inclusion_margin = -0.005`
requires 5 mm of *clearance* at evaluation time; a penetration tolerance would
be `+0.005`. The difference is not academic:

```
inclusion_margin=-0.0050  placed=4  evaluation={'fill_score': 0.00, ...}
inclusion_margin=+0.0050  placed=4  evaluation={'fill_score': 7.57, ...}
```

Same accepted placements, same run, only the margin flipped. And the scenario
sweep reproduces it without any patching: across all twelve `--physics` runs
every attempted placement was accepted by the validator, yet exactly one
scenario scored above zero — `06-soft-priority-heavy`, the only one that got
cargo onto a **shelf** (6 SP items, `fill_score` 7.60). Its 12 floor-resting
items contributed nothing, because a shelf is not one of the container planes
the evaluator tests, so cargo standing on one is far above the floor plane and
sails through.

Under `+0.005` the whole design coheres: hard cargo on the floor counts, soft
cargo crushed onto the floor does not, and soft cargo on a shelf does. Under
`-0.005` as shipped in `simulator/configs/sample_config.json`, **nothing that
rests on the container floor can ever score**, whatever it is made of. Which
value the real competition config carries is worth checking; rule-alpha only
reports what this snapshot does.

### What that means for the rules here

Soft cargo belongs on the shelf, and now there is a number for why: on the
floor it sinks 9 mm unloaded and 47 mm loaded. rule-alpha already sends soft
cargo to the shelf first (§2) and never treats a soft item as a support
surface. It does still fall back to the floor soft-strip when the shelf is
full, because the spec asks for that — but every scenario reports the floor
area carrying each support type (`support_type_area` → `soft-only`), so how
much soft cargo ended up on the floor is visible per board. Under either sign
convention that is the cargo most at risk.

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

### Tall perimeter: the fallback when the wall front says no

An item can be too tall to be wall-front material without being slender enough
to be classified elongated. Before this role existed such an item had no
structural option at all — the max-footprint rule simply laid it down, spending
floor area to store the air above it. The fallback order is

```
wall-front  →  tall-perimeter  →  max-footprint
```

`tall-perimeter` accepts a genuinely standing pose (taller than the item's
flattest), at least `tall_perimeter_min_height`, touching the left or right
edge or the back wall. The tipping veto and the transport check decide the
rest, and the pose is masked from flatness like any other structural piece.

It is capped by footprint (`tall_perimeter_max_footprint_fraction`) for the
same reason the wall front is: without the cap, `12-large-hard-only` stood
**all ten** of its large boxes on end and Layer 1 was left with no flat surface
whatsoever (`foundation_slab_fill_ratio` came back `null` — there was no
foundation to measure). The perimeter is for cargo that is awkward to lay down,
not for the big flat boxes the foundation is made of.

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

### The wedge as a staircase, not a wall

The wedge is not a small notch: the chamfer top is 0.378 m above the floor
while the usable height under the shelf is 0.765 m, so **nearly the lower half
of the cross section is cut away**. Writing that off as dead volume is
expensive.

The first design here tried to bridge it in one move — stand a single box tall
enough to reach the chamfer top, so cargo above could span the wedge. That is
the wrong shape. It demands one 0.378 m piece, the piece still has to be
delivered past the shelf, and it recovers nothing below its own top. Worse, the
ordinary wall-front cap is half the floor-to-shelf gap (0.383 m), so such a
bridge had a **4.8 mm** band to exist in.

The structure that actually fits grows instead (`rule_alpha/triangle.py`):

```
    wedge  ->  small-hard staircase  ->  soft cap

    shelf
    ────────────────────────────
              soft  soft            <- upper wedge: soft disposal zone
            ████████
              █████                 <- small cargo; each top is a new support
            ████████
          ██████████                <- first step: an ordinary low box on the floor
        ╱
       ╱   wedge
      ╱________________________
```

Each box sits on the flat top of the one below and reaches a little further
towards the wall. No single item has to be tall, so **the wall front can stay
low and keep the transport lane open** while the volume is recovered by small
cargo that is awkward to place anywhere else. The two jobs are separated:
wall-front protects transport, the staircase recovers the wedge.

**How far a step may reach** — two limits, whichever is tighter:

* the chamfer, `x_limit_at_height(bottom_z)`;
* stability. A step overhanging its support by `o` out of width `w` has support
  ratio `(w − o) / w`, so the official 0.6 floor gives `o ≤ 0.4w`. rule-alpha
  uses `wedge_overhang_fraction` = 0.25, deliberately under it, because the
  centre of mass and the settle step are not modelled exactly.

From the **second** step on it is stability that binds, not the chamfer — which
is why the staircase keeps climbing at a steady rate instead of stalling at the
chamfer top. Measured on the shipped ULD with 0.40 m boxes:

| step | bottom z | chamfer allows | support starts at | left face |
|---|---|---|---|---|
| 1 | 0.040 | −0.545 | −0.545 | −0.545 (no overhang possible) |
| 2 | 0.240 | −0.765 | −0.545 | **−0.645** |
| 3 | 0.440 | −0.960 | −0.645 | **−0.745** |
| 4 | 0.640 | −0.960 | −0.745 | **−0.845** |

The first step cannot overhang at all: at floor height the chamfer limit *is*
the floor limit. That is why an empty strip is probed with a nominal first step
when asking what the climb is still worth.

### States

```
   RAW ──first step──▶ STAIRCASE ──climb exhausted──▶ SOFT_READY ──▶ CLOSED
    │                      │                              │
    └──────────── score falls ─────────────────────────────┘
```

* **RAW** — nothing at the foot; the first step is an ordinary low floor box.
* **STAIRCASE** — steps are growing; the strip is held for cargo that can *be*
  a step (`wedge_step_max_footprint_fraction`, `wedge_step_max_height`).
* **SOFT_READY** — the next step would gain less than `wedge_min_step_gain`.
  What is left is short and awkward, which is what soft cargo absorbs well, so
  the top is offered down `CAP_LADDER` = soft → soft+priority → priority →
  plain.
* **CLOSED** — released to whatever fits.

Leaving the strip is **priced, not scheduled**, because committing it to
ordinary cargo is irreversible while withholding it costs only the volume held
right now:

```
R = w_step·p_step + w_cap·p_cap + w_area·A_remaining − w_fill·F − w_bottleneck·B
```

`p_step` is what could *be* a step and `p_cap` is what could *use* the top.
Below `wedge_min_step_share` the score is forced negative: cap customers are
worth nothing without something to build the stairs out of, and holding the
strip for soft cargo that has no way to get up there is exactly the waste the
score exists to prevent. `A_remaining` shrinks as the staircase eats the wedge,
and `F` and `B` rise as the board fills, so the reservation decays on its own
without a step counter.

`wedge_recovered_area_m2` reports how much of the wedge cross section the
staircase actually clawed back. It counts only the part of each step that is
left of the floor limit, below the chamfer top **and** above the chamfer line —
counting "everything left of the floor limit" would also count space above the
chamfer top, which was never wedge.

### The steps do not touch the slope, and mostly cannot

Look at any staircase picture and the steps are visibly *off* the chamfer: the
bottom-left edge hangs in space instead of meeting the slope.  Measured on
`08-slope-exploitation`:

| step | dz | dx | left face | chamfer at that height | **gap** | dx/dz |
|---|---|---|---|---|---|---|
| 4 | 0.230 | 0.517 | −0.658 | −0.821 | 0.163 | 2.25 |
| 8 | 0.176 | 0.496 | −0.782 | −0.960 | 0.178 | 2.82 |
| 10 | 0.285 | 0.473 | −0.647 | −0.821 | 0.174 | 1.66 |
| 15 | 0.165 | 0.431 | −0.636 | −0.960 | 0.324 | 2.61 |

This is geometry, not a tuning miss.  The chamfer recedes **1.100 m of x per
metre of z** — a 47.7° slope.  A step of height `dz` must move `1.1·dz` left to
stay on it, and the support ratio only allows `f·dx`.  So a step tracks the
slope exactly when

```
dx / dz  >=  1.1 / f
```

which is **4.4** at the shipped `wedge_overhang_fraction` = 0.25, and **2.75**
even at the official limit `f` = 0.4.  Ordinary baggage is roughly cubic, so
almost nothing qualifies.  Share of each stream with *any* pose that could
track, with the footprint cap lifted so the cap is not what is being measured:

| | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| f = 0.25 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **0.77** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| f = 0.40 | 0.23 | 0.23 | 0.17 | 0.15 | 0.27 | 0.15 | 0.95 | 0.20 | 0.06 | 0.23 | 0.06 | 0.60 |

Only `07-elongated-heavy`, which is made of long thin items on purpose, has
supply.  **"Pick cargo that can track the slope" has no stock to pick from.**

Nor is the pose choice being wasted.  Of the four steps above, three already
use the best step-legal pose available; the fourth looks like it settled for
`dx/dz` = 1.66 over an available 2.75, but that flatter pose is 0.285 deep in
`y` against a shallower support and loses the support ratio — it generates two
candidates reaching −0.563 against the chosen pose's twenty reaching −0.647.
The planner picks the pose that reaches furthest, which is the right rule.

**Pushing harder recovers area and loses cargo.**  Raising `f` does exactly
what the algebra says on the wedge, and the simulator accepts every placement
at every value tested — nothing tips, nothing penetrates:

| `f` | support ratio | recovered m² | of the wedge | worst gap | placed (08) | fill (08) |
|---|---|---|---|---|---|---|
| 0.25 | 0.75 | 0.0273 | 0.35 | 0.324 | 15 | 0.141 |
| 0.30 | 0.70 | 0.0336 | 0.43 | 0.302 | 15 | 0.141 |
| 0.35 | 0.65 | 0.0398 | 0.51 | 0.281 | 15 | 0.141 |
| 0.40 | 0.60 | 0.0461 | 0.59 | 0.259 | 15 | 0.141 |

Recovered area rises by two thirds and **not one extra item goes in** — on a
board with fifteen items still unplaced.  Across all twelve scenarios `f` = 0.35
is a net *loss*: **179 → 176 placed, mean fill 0.2303 → 0.2283**, giving up one
item on `06` and two on `07`.  The mechanism is visible in `07`: it places the
same two wedge steps at both settings and loses an elongated wall and a shelf
item instead.  The overhang is not free — it reaches further into a strip that
the wall front and the elongated walls are also using.

So `wedge_overhang_fraction` stays at 0.25.  It is the value that keeps a real
5-point margin under the official 0.6 support floor *and* the value that packs
best; `recovered_area_m2` is a diagnostic, not an objective, and this is what
optimising it directly costs.

The residual sliver is a property of the problem: an axis-aligned box resting
on a horizontal surface always leaves a triangle against a 47.7° wall, and
overhang can only claw back the fraction the support ratio pays for.  At
`f` = 0.25 with the cargo that actually arrives, roughly a third of the wedge
cross section is recoverable and the rest is not reachable by any box on any
flat support.  Treating that remainder as wall-front territory rather than
storage is the honest reading.

### What the measurement actually says: most streams have no step material

The staircase only exists if the stream contains cargo small enough to *be* a
step — footprint ≤ 0.203 m² and `dz` ≤ 0.35 m under the shipped config. Scoring
`p_step` (the share of the manifest that qualifies) and `p_cap` (the share that
could use the top) across all twelve scenarios at `optimize()` time:

| scenario | `p_step` | `p_cap` | state at step 0 |
|---|---|---|---|
| 01-normal-no-shelf | 0.23 | 0.23 | `raw-wedge` — reserves |
| 02-normal-with-shelf | 0.23 | 0.23 | `raw-wedge` — reserves |
| 03-priority-plus-normal | 0.15 | 0.25 | `raw-wedge` — reserves |
| 04-soft-heavy | 0.04 | 0.77 | closed — too little step material |
| 05-priority-heavy-no-priority-uld | 0.19 | 0.00 | `raw-wedge` — reserves |
| 06-soft-priority-heavy | 0.03 | 0.76 | closed — too little step material |
| 07-elongated-heavy | 0.41 | 0.05 | `raw-wedge` — reserves |
| 08-slope-exploitation | 0.90 | 0.00 | `raw-wedge` — reserves |
| 09-mixed-random | 0.09 | 0.41 | closed — too little step material |
| 10-awkward-holes | 0.12 | 0.12 | `raw-wedge` — reserves |
| 11-lookahead-3 | 0.09 | 0.41 | closed — too little step material |
| 12-large-hard-only | 0.00 | 0.00 | closed — too little step material |

Typical competition cargo is 0.45–0.75 m on a side, which is *not* small enough
to be a step, so on most streams the strip is not worth withholding. Note also
that every row that reserves at step 0 except 07 and 08 still ends `closed`:
`F` and `B` rise as the board fills, so the reservation is given back on its own
without anyone having to schedule a release.

Closing the strip is not the same as refusing to climb, though. `CLOSED` only
means the strip is no longer *held* for step material; a step that turns up
anyway is still placed. End state and recovered wedge cross section (out of the
0.0785 m² available):

| scenario | end state | recovered m² | share of wedge |
|---|---|---|---|
| 08-slope-exploitation | `staircase` | 0.0273 | 35 % |
| 02-normal-with-shelf | `closed` | 0.0144 | 18 % |
| 04-soft-heavy | `closed` | 0.0120 | 15 % |
| 01-normal-no-shelf | `closed` | 0.0100 | 13 % |
| 07-elongated-heavy | `soft-ready` | 0.0054 | 7 % |
| 10-awkward-holes | `closed` | 0.0012 | 2 % |
| 05-priority-heavy-no-priority-uld | `closed` | 0.0001 | 0 % |
| 03, 06, 09, 11, 12 | `closed` | 0.0000 | 0 % |

Only 08 — small low boxes on purpose — is still climbing when the stream runs
out. Everywhere else the staircase is an opportunistic 0–18 %, taken without
having reserved anything for it.

This is a finding, not a defect to tune away. The wedge staircase is a
*conditional* mechanism: worth having for small-cargo streams, worth nothing for
large-cargo ones, and cheap enough to leave switched on either way because the
option price releases the strip by itself. For the common case the honest lever
is the wall front, not the staircase.

### Slope wall front

The wall front is the hard wall built against the chamfer foot (spec §10).
rule-alpha prefers **height over base area** there, and only spends items on it
that are *not* prime foundation material:

* base area ≤ 13 % of the usable floor (bigger boxes stay flat in the
  foundation),
* a pose between 0.25 m and `wall_front_height_limit()` tall,
* stop when the wall spans 85 % of the depth **or** reaches half the container
  height.

**The height cap is the important one.** The wall front lives *under the small
shelf*, so a piece that fills most of that gap has nowhere to go: at the
commanded release height the transport sweep no longer clears the shelf
underside by the official 15 mm. The cap is the lower of

* half the floor-to-shelf gap — above that the piece is ordinary tall cargo and
  does more good on the perimeter than as structure, and
* what can actually be carried in: `gap − (floor_action_lift +
  settled_clearance)`.

For the shipped ULD that is **0.383 m**. Before the cap, `10-awkward-holes`
built a wall of four 0.71–0.74 m pieces that the real validator refused to
transport, and spent four large items doing it. With the cap those pieces are
reclassified and go to the perimeter, and the board gains an item and 8 points
of floor coverage.

There is a cost, and `08-slope-exploitation` pays it: its cargo is small and
not elongated, so capped pieces lie flat as foundation instead of standing as
walls, which fits fewer items (12 → 9) and 5 points less floor coverage. That
is the trade the rule is making on purpose — standing medium cargo up to make
a wall buys floor area at the price of a structure that cannot be delivered.

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

### 3D fill

Floor coverage is a 2D number and says nothing about how much of the ULD is
actually full, so every container also reports its volume:

| field | meaning |
|---|---|
| `placed_volume_m3` | Σ oriented box volume in this container, floor and shelf alike. Structural cargo (wall-front, elongated, slope-infill) **is** counted — the flatness metric masks it because it is meant to be tall, but occupied volume is occupied volume. |
| `usable_container_volume_m3` | the simulator's own `container.volume`: inner box, minus the chamfer wedge, minus the small shelf, minus the main shelf when present. This is exactly what `Evaluator.calculate_fill_rate` divides by, so it is read from the observation when there is one and recomputed with the same formula (`simulator_container_volume`) otherwise. |
| `volume_fill_ratio` | the two above, divided. One layer cannot fill a 1.6 m ULD, so 0.10–0.25 is the expected range, not a failure. |
| `structural_volume_m3` | how much of the placed volume went into wall-front, elongated and slope structure. Counted in `volume_fill_ratio` like everything else; broken out because it is spent on structure rather than on foundation. |
| `foundation_slab_fill_ratio` | how densely and evenly the *normal* Layer 1 foundation was built: normal floor cargo volume ÷ (usable floor area × the height normal floor cargo reached). Shelf cargo, wall-front, elongated and slope structure are excluded from **both** sides. |
| `official_evaluator_fill_score` | only from a `--physics` run, and only per scenario: the official evaluator scores a whole episode across all containers, so there is no per-container value. `null` rows carry the reason. |

The four numbers have four separate jobs, and no number does two of them:

* `floor_coverage` — how much of the floor is covered, in XY.
* `volume_fill_ratio` — how much of the ULD is used, everything included.
* `structural_volume_m3` — how much was spent on wall / elongated structure.
* `foundation_slab_fill_ratio` — how densely the normal foundation was built.

The mask on the last one matters. Structural pieces are excluded from the
flatness metric because they are *meant* to be tall; letting one of them set
the slab's envelope height would contradict that — a single 1 m wall-front
piece would divide the foundation by a 1 m slab it never fills, and report a
tidy floor as full of air. A regression test pins this: adding a 1 m
wall-front spike to a flat board leaves `foundation_slab_fill_ratio` and
`foundation_slab_height_m` unchanged, while `volume_fill_ratio` rises and
`structural_volume_m3` accounts for it.

The gap between the ratios is where the reading is. `12-large-hard-only`
covers 80 % of the floor with a 0.32 m slab that is 64 % solid — a proper flat
layer that has barely started on the ULD (`volume_fill_ratio` 0.10).
`07-elongated-heavy` reaches `volume_fill_ratio` 0.22 off only 60 % floor
coverage, by standing long cargo up: that is the structural exception paying
for itself in volume, which is a result to weigh rather than a fault.

### Back-to-front adherence

Layer 1 is supposed to fill from the back wall towards the opening, and when it
does not, the gaps show up between columns. Every container reports it rather
than leaving it to impression:

* `back_to_front_adherence` — the share of placements that did **not** land
  entirely behind the frontier (the most forward point reached so far).
* `back_to_front_violations`, `max_backtrack_m` — how many went back, and how
  far the worst one did.
* `frontier_depth_used` — how much of the depth the frontier covered.

Frontiers are tracked **per surface**: the floor and each shelf fill
independently, so a bag going onto a shelf is not counted as landing behind the
floor frontier.

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

Six panels, and every figure is written as **both PNG and SVG** — the
clearances that decide whether a placement is legal are millimetres wide, and a
raster at this size loses them, so zoom into the `.svg`.

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

**placement order** — the same footprint, numbered by placement step and
shaded from dark (first) to light (last), with an arrow chain through the
centroids. This is the picture for "was it filled from the back forward?": a
jump from the back to the opening and back again reads as a zig-zag instead of
having to be reconstructed from the step log.

**fill progression** — placement step across, depth down. Each bar is the
item's depth span; the red ticks are the frontier after that step. A board that
respects back-first draws a staircase falling to the right; a bar that climbs
back up after the frontier has moved on is cargo placed behind something
already packed.

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
  penetration.py  measures settled penetration into the floor plane vs load
  agent.py        the official get_init_states / optimize / policy interface
  visualize.py    the four views and the diagnostic overlay
  scenarios.py    the twelve scenarios
  runner.py       CLI: boards, pictures, report
tests/test_rule_alpha.py
docs/rule_alpha/README.md   (this file)
```
