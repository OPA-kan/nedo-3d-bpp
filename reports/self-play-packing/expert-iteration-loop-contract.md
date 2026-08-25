# Expert Iteration loop contract (frozen 2026-08-25)

Fixed after design review. Supersedes the scope of
`policy-loop-direction-contract.md` (whose taxonomy and stop rule stay
in force) and defines the one loop this project runs from here on.

## Purpose (why RL at all)

Humans supply the action domain and the physics. The placement
strategy itself is learned from environment outcomes, so performance
scales with data and compute — not with hand-tuning. Everything below
serves that sentence; anything that only polishes the hand-coded
ranker's last mile does not.

## The loop (one generation)

```
state s_t
   │
   ▼
Policy π_t                       (π_0 = the hand-coded ranker, demoted
   │                              to "initial policy", not the center)
   ├─ learned proposals
   ├─ coverage proposals          ← permanent floor: moves π_t doesn't know
   └─ rescue / legacy
   │
   ▼
bounded candidate set
   │
   ▼
10-second bounded physics search  (deadline executor; selector /
   │                               comparator / V are optional modules
   ▼                               that never block this mainline)
search-improved action â_t  →  actually placed  →  s_{t+1} → … → terminal
   │                                                              │
   │                                            terminal outcome vector
   │                                                              │
   └────────────── training data (generation-stamped) ────────────┘
                                   │
                                   ▼
                                π_{t+1}
```

The candidate distribution itself must shift across generations
(π_1 proposing what only coverage could reach in generation 0 is the
mechanism of growth). If the support stays closed over ranker Top-3,
the loop degenerates to "cleverly choosing among a fixed ranker's
candidates" and has failed regardless of any metric.

## The win rule (three tiers, identical for Q and for the gate)

Learning must optimize exactly what the judge measures.

```
Tier 0 (environment-given veto): a physically invalid placement loses.
Tier 1 (dominance): componentwise comparison of the official-aligned
        heads — placed_count(+), fill(+), soft_covered(−),
        priority_covered(−), priority_misrouted(−), CoG z(−),
        post-shake max shift(−), items toppled(−).
        Non-worse everywhere ∧ strictly better somewhere = win.
Tier 2: everything else is a draw (trade-offs are never adjudicated —
        that would invent official weights; they are logged as
        trade-off pairs, re-scorable the day weights are known).
```

Diagnostic-only telemetry (surface total variation, peak shake KE,
stack-aware counters) is reported but never decides a match. Paired
same-world episodes are deterministic, so comparisons use strict
epsilon — no noise tolerance is needed or allowed.

## Q (what the network carries)

`Q(s, a, b)` = per-head antisymmetric difference predictions
`ΔŶ_h(s,a,b) = N(s,a,b) − N(s,b,a)` for the official heads, plus
ensemble uncertainty. **The verdict is never a network output**: it is
derived by applying the win rule above to the predicted differences,
so the rule can change (official weights landing) without retraining.
Labels come from paired same-world comparisons (sibling branches in
collected cohorts; selective terminal forks in the live loop), all
generation-stamped as V^{π_t}/Q^{π_t} perishables — never accumulated
blindly across generations, never treated as V*.

## Terminal oracle: auditor, not teacher-factory

Every executed episode reaches its own terminal for free. Beyond that,
counterfactual terminal forks are sampled only from: contested /
low-margin decisions, new-proposal regions, **a fixed random-audit
fraction** (a confidently wrong network must stay detectable — the
selector's wave-1 calibration inversion is the standing precedent),
OOD / ensemble-disagreement states, and the benchmark hard states. Any
claimed shrink of fork counts is a hypothesis requiring its own
measured gate.

## Diversity defenses (mechanisms + gauges, per generation)

1. Proposal support: coverage floor permanent; F-head soft-resamples,
   never hard-prunes; rescue stays as a third stream.
2. Tie starvation: track the informative-pair rate; choose comparison
   pairs actively (expected-decisive, cross-stratum), not always
   top-2.
3. Distillation: target the distribution over non-dominated winners,
   not one-hot; sample (never argmax) during data generation, with a
   temperature floor.
4. State mixing: own episodes + benchmark hard states + lagged-policy
   episodes; perturb at contested decision points (arbitrary
   divergence is measured to be useless).
5. Streams: rotate training streams per generation; the eval streams
   below are frozen forever.

Gauges (conjunction, diagnostic not punitive): proposal stratum
entropy vs coverage baseline, novel-stratum discovery rate,
informative-pair rate, π output entropy, per-source decision-change
rate. A failing gauge adjusts the mixture and recollects; it does not
silently pass.

## The league (asymmetric: gate vs detector)

Implemented in `scripts/league.py` / `scripts/evaluate_league.py` /
`.github/workflows/league-match.yml`.

- **Main gate — π_{t+1} vs the current champion only**: on the frozen
  eval episodes (paired by scenario/stream/seed), paired Pareto wins
  must exceed losses, and the aggregate hard heads must not regress
  (rule-violation total not up, completion total not down).
- **League members — π_0 (absolute anchor, kept forever), the previous
  champion, and a few milestones — are a catastrophic-regression
  detector only**: aggregate thresholds (loss excess beyond a
  collapse fraction, aggregate violation/completion collapse), never
  per-episode vetoes. "Beat every member on every episode" is
  explicitly rejected: under a partial order it makes promotion
  impossible as the league grows — one special-stream trade-off
  against an old milestone must not block an otherwise dominant
  generation.
- Lagged members double as label-robustness probes (a branch verdict
  that holds under both π_t and π_{t−k} continuations is a property of
  the action, not of the continuation) and as state-mixing sources.
- No synthetic match reward, ever: the win is always derived from real
  outcome vectors (the dismantled ±50 pseudo-game is the standing
  counterexample).

### Frozen eval set (never used by any training wave)

10 episodes, seed 42, 40 steps:
dual-preloaded-dedicated × {permute-000-191, 000-193, 000-197},
dual-shelf-mixed × {permute-001-167, 001-173, 001-181},
dual-empty × {permute-000-197},
single-empty-shelf × {permute-001-179},
single-empty-noshelf × {permute-000-191},
single-preloaded × {permute-000-193}.

The registry lives at `reports/league/registry.json`; pushes of the
league workflow re-run the legacy anchor arm as a determinism audit
against it.

## Breakthrough criterion (unchanged, restated)

The first promotion of a distilled π_1 through this league — executed
held-out episodes, paired Pareto over official heads, no hard/completion
regression — is the first legitimate claim that the agent grew. No
intermediate metric (oracle reproduction, recall, AUC, conversion) may
substitute for it.
