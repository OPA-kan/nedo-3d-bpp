# State-model experiment

## Question

`scripts/audit_learnability.py` tested an eight-scalar contact vector with a
linear model and a lookup table, found no signal beyond the incumbent
`Ranker.score`, and observed that the learning curve saturated near sixteen
boards. That null was then used to argue against training anything larger,
which overreaches: it is a statement about those eight scalars, not about the
data.

The retained snapshots carry the whole board — every placed item with its
pose, dimensions, mass and attributes, the pending pool, and the container
geometry — and none of it reaches `phi_modelling`. The eight scalars describe
*predicted contact*; they never say where in the container the item is going.

So: does a model that sees the board rank candidates better than the incumbent?

## Contract

Identical protocol to the audit, so the numbers sit beside its arms:

- **Leave-one-case-out.** Rows inside one board share a parent state, so a
  random row split would report memorisation as skill. The run asserts that
  no board straddles a fold, and the inner validation split used for early
  stopping is also by case for the same reason.
- **Ranking is scored inside a board.** Pooled AUC can be produced entirely
  by between-board differences in difficulty — the step/fullness confound
  this project has already been burned by. Within a board, `packed_items`,
  the container and the pool are all constant, so the only inputs that vary
  are the candidate's own and its relative geometry. The headline metric is
  therefore structurally immune to that confound.
- **The incumbent is in the table.** Beating a constant establishes nothing;
  `Ranker.score` is what the live agent already uses.

Three arms, chosen so a win can be attributed rather than just observed:

| arm | adds | isolates |
|---|---|---|
| `phi_mlp` | non-linearity on the same eight scalars | model capacity |
| `candidate_mlp` | the candidate's own geometry and its container | the feature set |
| `set_attention` | attention over placed items and the pending pool | the board |

## The selection confound, and how it is checked

Safe rows and unsafe rows are not drawn the same way. The safe rows in
`step-NNN-candidates.jsonl` are exactly the subset the observed-state swap
optimizer chose to spread out in afterstate space, while
`step-NNN-negative-risk.jsonl` keeps *every* unsafe candidate the overdraw
produced. A model could therefore learn "this looks like a selected row"
rather than "this is safe".

`--positive-source control` keeps only `step-NNN-random-control.jsonl` safe
rows, which are a stratified random draw carrying no such selection. If the
arm ordering and the AUCs survive that, the sampler is not what the model was
reading.

Both arms must be run against a **frozen copy** of the corpus. CI lands new
boards continuously, and two arms trained minutes apart otherwise see
different data — which happened twice before it was noticed.

## Reading the numbers

Current results: `reports/state-model/summary.md` (all positives) and
`reports/state-model/control-only.md` (selection removed).

- **Quote AUC, not top-1.** Top-1 safe rate depends on the safe fraction per
  board, which is a sampling design here, so it moves between the two arms
  for reasons that have nothing to do with model quality.
- **Read the ordering of the arms, not the third decimal.** Eight cases, two
  seeds.

## What this cannot claim

- It is not a live-policy result. The incumbent is consumed inside a
  deadline-bounded search; this project has already rejected a selector that
  looked better statically and lost on trajectories (multi-axis Pareto
  enforce v1, `docs/MULTI_AXIS_SELECTOR.md`). A physical negative control on
  real trajectories is the next gate, not another dataset run.
- Latency is unmeasured and is a real constraint: the policy has an eight
  second budget per step.
- The prevalence of safe candidates is a sampling design, so no calibration
  claim is made and none is reported.
- It says nothing about board value. There is still no long-horizon label
  whose noise is smaller than its effect
  (`sigma-branch-is-the-size-of-the-effects`).

## Dependency

Torch lives in `requirements-learning.txt` and is imported inside `run()`,
not at module import. The shipped agent stays CPU-first on numpy, CI does not
install torch, and nothing here executes inside the policy.
