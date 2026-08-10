# Structured selector physical negative control

Status: measured; eager per-candidate materialization failed the negative
control and is not an admissible live-selector path.

Actions run: `31356809615` (45/45 episodes plus aggregate succeeded).

## Question

Can a selector consume the explicit proposal/evaluation/command pipeline in a
real deadline-bound episode without introducing a material policy change by
itself?

This is a measurement-system validation, not a new Ranker experiment. The
`structured_noop` arm computes named evaluation objects and then applies the
same settled-first ordering and scalar score as the shipped policy.

## Arms and sample

- `base`: shipped scalar hot path.
- `base_null`: byte-identical control used to measure runtime/physics noise.
- `structured_noop`: rich pipeline with unchanged selection semantics.

Five development configurations (`b000-k15/k20/k40`, `b001-k20/k30`) are run
three times per arm. Thus `n_case=5`, `n_runtime=3`, with no claim of multiple
independent item streams.

## Required outputs

The compact report must preserve, without a weighted total:

- placed, fill and any official component returned by the environment;
- final CoM height;
- shake maximum shift, peak kinetic energy, shifted count/fraction and topple
  count;
- priority-clean and soft-clean ratios;
- terminal inclusion/valid/safe result and failure channel;
- policy seconds, search attempts per decision and maximum attempts;
- count of selected structured-evaluation records, proving treatment
  activation.

## Reading rule

`base` and `base_null` jointly define the observed noise floor per case and
component. The treatment passes this instrumentation gate only if:

1. it emits structured records on non-fallback decisions;
2. its metric differences do not clear the control spread in a systematic
   adverse direction; and
3. its attempt coverage and policy time do not show an abstraction tax large
   enough to change the deadline-limited search regime.

Placed/fill agreement alone is not a pass. A proxy disagreement is reported as
an unresolved trade, never hidden by summation. If the negative control fails,
no advanced selector is evaluated on this path until its overhead is removed
or the comparison is moved to a deterministic fixed-work execution contract.

## Execution

GitHub Actions workflow:
`.github/workflows/structured-selector-negative-control.yml`.

The workflow saves raw rows as an artifact and commits only `summary.{md,json}`
and `noise-floor.{txt,json}` beneath
`reports/structured-selector/history/<run_id>/`.

## Result

Treatment activation was real: 295 of 303 non-fallback decisions retained a
named structured evaluation.  Fixed-work checks at 128 and 512 attempts were
bit-exact for action, ordered top three, score and attempts, so the two paths
implement the same ordering when work is held constant.

The deadline-bound physical negative control nevertheless failed.  The
clearest case was `b000-k15`: all six `base`/`base_null` runs returned 21
placements and fill 23.929, while `structured_noop` averaged 18.333 placements
and fill 20.849.  Its shake shifted count rose from 3.0 to 6.333, maximum shift
from 0.065 to 0.219, and shifted fraction from 0.143 to 0.361.  Priority
cleanliness and terminal validity moved in the opposite (better) direction,
so this is a proxy trade, not a scalar loss; the full vector still fails the
no-op requirement.

Across all cases, policy time did not show a uniform slowdown and the
treatment sometimes improved placed/fill.  Therefore the experiment identifies
deadline/cache/runtime perturbation by eager rich evaluation, but does not
isolate object allocation as its only cause.

Decision: keep `PLACEMENT_SELECTOR_MODE=scalar` as the live default.  Do not
attach a new Ranker to the eager per-candidate path.  The next negative control
must keep scalar streaming and enrich only the retained Top-K or final selected
candidate, or else use a deterministic fixed-work policy contract.
