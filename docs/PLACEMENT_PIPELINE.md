# Placement pipeline contract

The live agent historically compressed candidate generation, immediate
ranking, physical-risk adjustment, settled/release selection and simulator
command construction into `PlacementCore.choose()`.  That made every richer
selector repeat search or reconstruct candidate facts from an opaque scalar.
It also made shadow instruments perturb the wall-clock policy through cache
and deadline effects.

The pipeline now has four explicit stages.  This refactor is behavior
preserving; it does not adopt a new ranker or a temporal-chunk policy.

## 1. Proposal

`PlacementProposal` is the output of candidate search.  It owns only facts:

- pool index and stable item index;
- item and container references;
- container index and orientation;
- the static `AABB` candidate; and
- provenance such as `placement_core`, `bounded_rollout`, or
  `cross_step_revalidation`.

It has no scalar value and makes no selection decision.

## 2. Evaluation

`Ranker.evaluate()` returns `RankEvaluation`, retaining the seven immediate
terms instead of discarding them into one number:

```text
12 V, 2 R, D, -0.12 |x|, -0.18 z m, B_route, B_zone
```

`release_risk_adjustment()` independently returns rotation and slide
probabilities and penalties.  `evaluate_placement_proposal()` combines these
objects into `CandidateEvaluation` and the compatibility scalar
`PlacementDecision.score`.

The scalar is unchanged. `Ranker.score()` retains the allocation-light scalar
implementation used by the live loop; `Ranker.evaluate()` is its named,
opt-in representation. Contract tests require the two totals to agree.

## 3. Selection

`PlacementCore` streams evaluated decisions into a selector with two methods:

```python
selector.observe(decision) -> bool
selector.select() -> PlacementDecision | list[PlacementDecision] | None
```

The opt-in `SettledFirstSelector` exactly preserves the shipped doctrine:
any settled incumbent beats every release incumbent, and the existing L3
container tie rules remain in force.  `TopKSettledFirstSelector` preserves the
same rule for bounded portfolios.

Future rollout, chunk, learned, lexicographic, or constrained selectors should
consume this evaluated stream.  They must not rerun candidate generation just
to recover score components.  A selector changes selection only; it does not
change static validity or simulator command construction.

The structured stream is opt-in.  Passing a custom selector, or setting
`structured_evaluation=True`, materializes proposals and named evaluations.
The shipped default selector stays on the allocation-light scalar path.  This
is a measured requirement: eagerly constructing rich objects for every valid
candidate reduced candidate throughput by roughly 16--17% in the first Task B
parity run.

For the physical integration negative control,
`PLACEMENT_SELECTOR_MODE=structured_noop` selects this rich path while keeping
the same scalar score and settled-first selector. It is not an adopted live
mode. See `docs/STRUCTURED_SELECTOR_EXPERIMENT.md` for the preregistered
full-proxy comparison.

`PLACEMENT_SELECTOR_MODE=structured_retained` leaves the scalar generator,
ranker and incumbent/heap updates on the shipped fast path. It materializes
named objects only for the final decision or final Top-K portfolio. This mode
exists because eager per-candidate materialization failed its deadline-bound
physical negative control despite fixed-work parity. See
`docs/RETAINED_SELECTOR_EXPERIMENT.md`.

## 4. Command and execution

`PlacementCommand` represents the command pose, not the settle result.  It
retains the stable item identity, current pool index, container, orientation,
mode (`settled` or `release`) and command position.  `action_for_execution()`
is the only conversion into the external simulator action dictionary.

This preserves the release contract:

```text
(p_cmd, o_cmd) != (p_settled, o_settled) in general.
```

`placement_evaluation_record()` exposes a JSON-safe schema for a selected
structured candidate.  When structured evaluation is enabled, policy traces
retain its immediate terms, risk adjustment, provenance, command mode and
stable item identity.  Default traces remain allocation-light.

## Compatibility and adoption boundary

- Existing callers may still construct a three-field `PlacementDecision`.
- Existing action dictionaries and scalar scores are unchanged.
- The default scalar path is the former inline selection logic; the equivalent
  selector object is used only by the structured path.
- The temporal chunk ensemble remains OFF and its negative result remains
  active evidence.
- This contract is infrastructure, not evidence that any richer selector is
  beneficial.  Each selector still requires its own shadow measurement and
  paired physical ablation.
- A selector ablation is incomplete if it reports only placed/fill. It must
  also retain the available proxies for official CoG, stability, placement,
  and soft-item components (`final_com_z`, the shake-response vector,
  `priority_clean_ratio`, and `soft_clean_ratio`), plus terminal validity,
  failure channel, policy time, and attempt coverage. Compare the vector by
  Pareto/dominance and per-component regressions; do not invent a weighted
  local total.
