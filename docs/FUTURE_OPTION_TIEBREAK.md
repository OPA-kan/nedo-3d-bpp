# Future-option tie-break

## Status

Experimental and default-off. Enable with:

```text
FUTURE_OPTION_TIEBREAK=1
```

This experiment does not change `Ranker.score`, the live release-risk terms,
or the settled-before-release contract.

## Selection contract

The Task B decision is split into four stages:

1. Run the existing candidate generator and live score, but retain at most one
   immediate representative per visible item. This prevents a single item
   from occupying the whole global top-K.
2. Keep representatives whose `Q_live` is within `FUTURE_OPTION_Q_BAND`
   (default `0.15`) of the best immediate representative.
3. For each member of that cohort, virtually apply the same settled proxy used
   by the current lookahead and revalidate a fixed number of already-generated
   probes from the current visible pool, excluding the placed item.
4. Select lexicographically by:

```text
feasible_items
feasible_item_orientations
distinct_support_regions
valid_probe_candidates
Q_live
```

The first three fields prevent raw anchor multiplicity from masquerading as
future flexibility. `valid_probe_candidates` is explicitly a count inside a
fixed sample; it is not the complete next-state candidate population.

## Budget and observability

The default future validation budget is 32 candidates per hypothetical state.
The future loop has no PyBullet call and no wall-clock cutoff. The preceding
live generator remains the existing deadline-driven search; consequently the
probe population at the edge of that deadline can still vary between runs.
If an evaluation reaches the policy reserve, the implementation returns the
best immediate `Q_live` representative instead of comparing a partial cohort.

`candidate_diagnostics.future_option_tiebreak` records the shortlist, cohort,
Q gaps, all four value components, per-hypothetical runtime, total future
runtime, selection change, and deadline abort status.

### Quotient and capacity shadow descriptors

The same fixed probe pass also records experimental descriptors that do **not**
participate in `rank_key()`:

- feasible item classes, with identity removed but dimensions, mass, handling
  class, contact physics, and eligible containers retained;
- feasible pose classes, which additionally retain oriented dimensions;
- coarse corridor classes and action classes;
- unique item-class volume sum and maximum feasible item volume;
- a deterministic greedy static-conflict independent-set count and volume.

The corridor partition is a coarse route-zone signature, not an exact group
orbit. The greedy independent set uses predicted settled AABBs and existing
lateral-clearance rules. It is a simultaneous static capacity proxy, not a
claim of sequential PyBullet executability. Identical physical item classes
collapse for the quotient counts, while distinct item identities retain their
actual multiplicity in the conflict-capacity calculation.

## Saved-snapshot measurement

Run:

```powershell
python3 scripts/evaluate_future_option.py `
  --snapshot <step-state.json> `
  --repeats 3 `
  --output-dir reports/future-option/<name>
```

On the saved `b000-k20` step-9 observation, the current baseline selected item
5 in all three fresh runs. The feature admitted the previously starved item 17
on all runs and changed the choice to item 17 or 21 in all three runs. Total
policy time was 5.81--5.91 seconds; the fixed-work future stage itself was
0.80--0.89 seconds. This is geometry-only evidence. It neither reproduces the
historical item-28 action nor establishes a better PyBullet trajectory.

## Adoption gate

`.github/workflows/future-option-ablation.yml` compares `base` against
`future-option` on five development configurations:

- `b000-k15`
- `b000-k20`
- `b000-k40`
- `b001-k20`
- `b001-k30`

The workflow stores compact paired placed/fill summaries in
`reports/future-option/history/<run_id>/`. Do not enable the feature by default
unless that episode-level guard gives an explained non-regression result.

Run `30684302181` completed all ten episodes successfully. Its single-run
screening result was mixed:

| case | placed delta | fill delta |
|---|---:|---:|
| b000-k15 | 0 | -8.523 |
| b000-k20 | +11 | +3.731 |
| b000-k40 | 0 | -2.650 |
| b001-k20 | +3 | +3.901 |
| b001-k30 | -1 | -9.824 |

Across the five cases, mean placed increased `16.4 -> 19.0`, while mean fill
fell `21.479 -> 18.806`. The feature is therefore not adopted. The result
supports the item-option signal but exposes its missing volume/utility axis:
preserving many feasible item identities can prefer futures containing more
small items. Repeat runs are required before changing the value tuple; do not
hide this trade-off by immediately fitting an additive beta.

A second five-config run (`30692389788`) reproduced the aggregate direction:
mean placed increased `14.2 -> 16.4`, while mean fill fell
`18.042 -> 16.734`. Per-case effects were much less stable (`0/-8.523`,
`+1/-1.209`, `+10/+10.722`, `+3/+3.901`, `-3/-11.426` for placed/fill),
confirming substantial episode/runner variance. The repeated placed-up,
fill-down aggregate split strengthens the missing-volume diagnosis but is not
an adoption result.

## Quotient/capacity shadow measurement

The saved step-9 observation was replayed again after adding the shadow-only
descriptors. With the default 32-probe budget, every evaluated cohort member
had the same descriptor values: 3 item classes, 7 pose classes, 2 corridor
classes, 7 action classes, `0.2665 m^3` unique-class volume, `0.1134 m^3`
maximum item volume, and greedy capacity `(1, 0.1134 m^3)`. The descriptors
therefore supplied no discrimination at the live budget.

At a diagnostic budget of 64, the future stage took 1.086 seconds and exposed
more spatial structure. Item 17 and item 21 both had 2 item classes, 9 pose
classes, 6 corridor classes, and greedy capacity `(2, 0.1934 m^3)`; only their
action-class/raw valid counts differed (`19/40` versus `18/37`). This is useful
negative evidence: the present score-biased probe population is too
concentrated for the volume/conflict descriptors to resolve this snapshot.
The fields remain telemetry-only.

## Route-survival shadow measurement

The next experiment used a separate corridor-stratified probe population and
partitioned probes lost after each hypothetical placement into structural
`space_lost` and corridor-only `route_lost`. This leaves the existing live
probe population and `rank_key()` unchanged.

Across five saved states, 27 hypothetical immediate placements, and 350 probes
accepted in their current states, 169 probes survived, 181 became structurally
invalid, and **zero** became invalid only because of the transport corridor.
A focused actual-geometry test does produce `route_lost` when a blocker is
placed only in a target probe's transport sweep, so the zero is an observed
negative result rather than an unreachable counter.

This small, bounded, geometry-only screen does not prove that corridor survival
is globally irrelevant. It does mean the field must remain shadow-only. The
next discriminating experiment should target exact pre-action states followed
by `transport_invalid`, rather than further refining saturated capacity
descriptors. See `docs/ROUTE_SURVIVAL.md` and
`reports/future-option/route-survival-summary.{md,json}`.
