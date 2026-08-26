# Packing League parallel-session reconciliation

Date: 2026-08-26 JST. This is a coordination snapshot for the concurrent
Claude and Codex sessions. It does not replace the immutable league ledger,
the season state machine, or the frozen evaluation records.

## Authority and operating rule

- Claude's implementation line on `work/terminal-rollout-oracle` is the
  authoritative development line for the two-timescale learner, diverse
  actors, exhibition, and spectator work described below.
- The repository-owned season chain remains authoritative for official season
  progress: collection -> distillation -> title match -> ledger/replay commit
  -> next wave.
- Codex is monitoring and reporting only. It must not independently edit the
  season matrices, registry, state, score weights, frozen evaluation data, or
  launch recovery runs while Claude is operating the line.
- A verdict produced inside a failed Actions run is evidence, but it is not a
  completed season transition until the ledger/replay commit reaches the
  branch and `reports/league/season/state.json` advances.

## Claude-side implementation now present

The frozen design is
`reports/self-play-packing/two-timescale-learning-and-diverse-actors.md`.
The corresponding implementation landed in commit `68515ae` and is present
on the shared branch.

### Short-timescale online learner

- `OnlineAdapterPolicy` keeps the promoted champion body theta frozen and
  learns only a zero-initialized per-episode delta phi on each ensemble
  member's final preference head.
- Updates are allowed only after a genuine paired terminal fork produces a
  strict multi-head dominance winner. Tied or censored forks teach nothing.
- The physical fork winner is executed. Pairwise logistic SGD updates phi
  under a trust-region bound, and phi is discarded at episode end.
- The online arm is SLA-exempt exhibition machinery: it cannot gate, veto,
  promote, or become champion. Its fork outcomes may later enter a new
  generation's preference corpus.

### Diverse experience actors

Three non-learning re-rankers are implemented over the same physically
screened candidate set:

| policy | racehorse | purpose |
|---|---|---|
| `rule-grid` | グリッドオー | lattice-like, regular boards |
| `rule-lowcog` | テイジュウシン | low center-of-mass boards |
| `rule-edge` | カベヅタイ | wall/corner-first boards |

They are experience-generation studs, not title candidates. Season 1 waves
5-14 remain frozen; these actors are reserved for a separately preregistered
season-2 or side-corpus diversity experiment.

### Exhibition 001

The committed record is `reports/league/exhibition-001-shun-hibari.md`.
Run `32913831956` compared the frozen champion プリフヒバリ with
シュンヒバリ, an online clone with identical base weights.

- Result: **1 win, 0 losses, 8 equals, 1 incomparable** for the online clone.
- Fourteen terminal forks were used; three produced strict outcomes and
  adapter updates, while eleven correctly produced no update.
- The decisive `dsm-173` turn-4 fork changed the pair probability from
  0.474 to 0.797 and selected the physically dominant alternate.
- Interpretation remains deliberately narrow: this demonstrates value from
  the combined uncertain-state fork authority and online calibration at equal
  weights. It does not isolate a long-horizon compounding benefit from phi,
  and it does not authorize production deployment or hyperparameter tuning on
  the frozen eval set.

CPU verification for the committed exhibition record succeeded in run
`32916646667`.

## Season 1 operational truth at this snapshot

Wave 7 is not yet finalized in repository state.

| stage | run | observed result |
|---|---:|---|
| collection | `32893228623` | success, 154 cells |
| distillation A | `32913941071` | success |
| distillation B | `32913958448` | success; duplicate recovery dispatch on identical source/seed |
| title attempt 1 | `32914990288` | failed after verdict in spectator-builder import path |
| title attempt 2 | `32915227049` | failed after verdict in the same path |
| title attempt 3 | `32916368296` | evaluation and finalization succeeded locally, but ledger push failed |

The import defect was fixed by `d277ad2`. The latest attempt then reached the
commit step and locally created `5620b95` (`Season wave 7: record title match
and advance`), but GitHub rejected the push because the Actions GitHub App was
not permitted to update
`.github/workflows/rollout-geometry-policy-learning.yml`. Consequently:

- the computed wave-7 verdict is **プリフスバル rejected** (0 wins, 2 losses,
  5 equals, 3 incomparables), but it is not yet an official committed season
  row;
- `reports/league/season/state.json` on the shared branch still says
  `stage=collecting`, `wave=7`, `champion=pi2-pref-w6`;
- the registry and committed champion remain unchanged;
- wave 8 has not been dispatched by the authoritative event chain.

No session should hand-apply the unpushed generated files or dispatch a
reseeded substitute. Recovery must preserve the already computed verdict and
fix only the workflow-authentication/push boundary (or use the repository's
declared recovery procedure).

## Spectator room

The user-facing Claude artifact is currently the easiest stable entry point:

<https://claude.ai/code/artifact/d9663d18-6c8b-4cea-b6af-bec1812e2ef4>

The repository spectator remains the durable source. It renders settled
container geometry, racehorse names, and transition-aligned soft/priority
effects. Static spectator artifacts can be published by Actions, but this is
stage/job polling rather than placement-level live video streaming.

## Coordination rule from here

1. Before any write or dispatch, fetch the exact shared branch ref and list
   recent workflow runs; the configured local fetch refspec does not track
   this work branch automatically.
2. Treat Claude's branch changes as upstream. Codex may add compact reports
   after reconciliation but must not independently change the active league
   mechanism.
3. Never infer season advancement from a run's internal verdict alone. Require
   a successful branch push and an advanced `season/state.json`.
4. Record duplicate or repeated frozen-eval executions in look accounting,
   even when deterministic outputs are identical.
5. Resume ordinary event-chain monitoring only after the wave-7 ledger push
   blocker is cleared. Do not dispatch wave 8 manually.
