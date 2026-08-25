# Direction contract: search-internal NNs vs the policy loop (2026-08-25)

Recorded from design review. This freezes the taxonomy, the stop rule,
and the terminal-sampling contract so the work does not drift into
building search plumbing forever.

## Taxonomy — what the current NNs are and are not

```
              Search controller
                    │
       ┌────────────┴───────────┐
       ▼                        ▼
 Selector NN              Comparator NN
 (which branch gets       (after reading, which
  the physics budget)      branch to adopt)
       │                        │
       └───── Physics Search ───┘
```

The geometry selector and the checkpoint comparator are **search
components**. Neither is the agent policy `π_θ(a|s)` — a network that
proposes good actions from the state alone. The main prize is the outer
generation loop:

```
π_t → bounded Search(π_t) (selector/comparator inside)
    → improved action  → distill → π_{t+1}
    → π_{t+1} generates new states → repeat
```

`π_t → Search(π_t) → π_{t+1}` is the self-improving agent; everything
in this cycle so far strengthens `Search`, i.e. the teacher.

## Stop rule (frozen)

- The comparator gets **exactly one more gate**: retrain on the wave-3
  corpus (36 cells, aggregate run `32813542943`) and re-run the paired
  decision gate against the Pareto rule. v1 failed at wave-2 scale
  (9/25 vs 17/25 conversion).
- **No further search-internal NNs** (no NN③/NN④) regardless of that
  gate's outcome. If the comparator passes, it ships as a search
  component; if it fails, the Pareto rule stays and the comparator is
  shelved. Either way the next phase is **policy distillation**
  (roadmap items 7–9): train `π_θ(a|s)` on the search-improved actions,
  then close the generation loop.

## Terminal-sampling contract for the future collector

Selective terminal forks replace exhaustive collection, but a margin
gate alone is unsafe: a confidently wrong network is never audited, and
this project has already measured a calibration inversion in the
selector at wave-1 scale. `low margin ≠ high error probability` until
verified. The collector therefore samples terminal forks from:

1. **uncertain cases** (small comparator margin / tied frontier);
2. **a fixed random-audit fraction** of confident cases — the tripwire
   for confidently wrong regions;
3. **OOD / high-disagreement cases** (ensemble members disagree, or the
   state is far from the training support).

The claimed shrink (284 → 30–40 terminal forks per cycle) is a
**hypothesis** requiring its own measured gate before it is stated as
fact: measure what fraction of true decision errors falls inside the
sampled buckets, and the random-audit catch rate, on a cohort with full
terminal truth.

## What stays true underneath

The physics terminal rollout remains the oracle and the fixed held-out
yardstick — bounded evaluations cannot referee their own improvement
(measured three separate times on this branch). Policy learning
amortizes the oracle; it never replaces it.
