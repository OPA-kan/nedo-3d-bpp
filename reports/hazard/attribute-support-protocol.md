# Rule-faithful attribute support: gates

## Disclosure first

**This protocol was written after the wave was launched, with two of
twenty-one pairs already visible.** That is a process failure and it is
recorded rather than hidden. To keep the thresholds from being chosen to
fit what I had seen, **every gate below is taken from
`reports/benchmarks/baseline.json`, which was frozen long before this
change existed** — the per-config
`minimum_resolvable_placed.paired_3v3_same_run` floors — or from the
adjudication discipline already written in `HANDOFF.md` item 6. No
number here is one I picked.

The two visible pairs are named so a reader can discount them:
`b000-k15-r0` and `b000-k20-r0`.

## The change

`support_surfaces()` admitted only PLAIN packed items, so the settled
anchor generator would never propose resting anything on a soft or
priority top. The published rule
(`simulator/README.md` 評価指標) penalises covering by a **different**
attribute and explicitly exempts same-attribute stacking, so that
over-approximation discards legal volume. `docs/ATTRIBUTE_PLACEMENT.md`
recorded the same shape — 公式が許す同属性積み重ね(体積になる)を捨てながら、
違反そのものは防げていない — and
`support-exhaustion-is-the-terminal-state` records a fatal board where
all 950 legal release candidates rest on protected tops while the
settled contract refuses every one.

`ATTRIBUTE_SUPPORT_RULE=1` admits a protected top exactly when the mover
carries every attribute that top is protected by. `attribute_rest_is_legal`
is pinned against the bundled `calculate_attribute_placement` on all
sixteen attribute pairs, including the case a loose reading gets wrong:
a priority item resting on a soft one IS a soft-axis violation.

The knob is default off; `behaviour_sha256` is unmoved.

## Data

7 development configs x {base, attr_support_rule} x 3 replicates, arms
run as concurrent pairs so wall-clock load is symmetric — the search is
time budgeted and this change alters how many candidates exist, so
asymmetric load would be the confound.

## Gates

**P — placed, primary.** Per config, the paired mean difference must
clear that config's own `paired_3v3_same_run` floor from
`baseline.json` (b000-k15 5.23, b000-k20 2.23, b000-k40 3.93,
b001-k20 4.22, and each remaining config's stored value) in the
POSITIVE direction on at least three configs, and must not breach any
config's floor in the negative direction. Configs whose floor is
unavailable are reported and excluded.

**A — attribute cost, disqualifying in one direction only.** The change
admits rests the rule permits, so `soft_clean_ratio` and
`priority_clean_ratio` are expected to fall somewhat as more items are
placed at all. What is NOT permitted is a rule violation the change
itself introduces: `soft_covered_by_other` and
`priority_covered_by_other` must not rise per *placed item* pooled. A
rise in the raw count with a flat or falling per-item rate is the
expected shape of placing more.

**S — stability, per HANDOFF item 6 and AGENT_OPERATIONS §5.** Pooled
`shake_max_shift` and `shake_peak_kinetic_energy` reported beside
placed. A worsening blocks adoption even if placed rises. Pooled paired
runs only; single-case shake differences are not read.

**C — channel shift, mechanism check.** The change is claimed to work by
opening candidates on boards that were exhausting. If it acts through
the claimed mechanism, physical endings (topple, slide) should fall and
surrender endings should rise as episodes run longer. If placed rises
without that shift, the mechanism is not what is written here and the
result needs a different explanation before adoption.

**Confirmation.** Fresh never-used permutations, new seed, no retuning,
same gates — the last-resort precedent. Development alone licenses
nothing.

## What no result here licenses

No default change without the confirmation wave. No adjustment of any
threshold above. And nothing about the official score: the
violation-count to 0–100 mapping is unpublished
(`docs/ATTRIBUTE_PLACEMENT.md`), so a local attribute improvement cannot
be quoted as a soft or placement score gain.
