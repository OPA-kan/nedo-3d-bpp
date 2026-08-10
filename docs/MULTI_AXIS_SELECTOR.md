# Multi-axis selector shadow

## Question

The official score gives material weight to centre of gravity, stability,
priority-placement rules and soft-item handling.  Placed count and fill are
therefore necessary outcome measures, but they are not a sufficient selector
objective.  This experiment asks whether the retained immediate Top-K already
contains candidates that are physically and rule-wise preferable to the
current scalar winner.

## Contract

`MULTI_AXIS_SELECTOR_MODE=shadow` runs only with the retained structured
portfolio. Candidate generation, scalar scoring, heap updates, lookahead and
the simulator command are unchanged. The shadow evaluates the already retained
Top-K only after the final live action has been frozen and records a proposal;
it never replaces the live action. The post-selection placement is required:
the first run (`31359754451`) computed before lookahead, changed the remaining
wall-clock budget and failed its physical negative control despite never
directly replacing an action.

Each candidate keeps these axes separate:

- priority items newly covered by a non-priority item;
- soft items newly covered by a non-soft item;
- priority-container routing violation;
- release rotation and slide probabilities;
- predicted-contact support ratio and centre margin;
- predicted whole-load CoM z (telemetry only);
- immediate and risk-adjusted scalar score.

There is deliberately no locally invented weighted total. Candidate `a`
dominates candidate `b` only if it is no worse on every trusted rule/physical
axis and strictly better on at least one. The shadow proposal is the largest
current adjusted score on the nondominated front. Predicted CoM is excluded
from dominance until its direction against the official component is resolved.

The trace reports both rank 0 of the immediate retained Top-K and the final
closed-loop choice. The enforce proposal is relative to the final choice: it
changes that action only when at least one retained candidate dominates it,
then preserves the current adjusted score as the tie-break among dominators.

After the repaired shadow passed its full-vector negative control in Actions
`31360283401`, `enforce` was added as an explicit ablation mode. It never
trades one trusted axis against another and still leaves CoM out of the
decision until official calibration resolves its direction.

## Acceptance gate

The first run is diagnostic, not an adoption run. It must report:

- observed and multi-candidate steps;
- baseline-dominated frequency;
- proposed action and item change frequency;
- candidate count and Pareto-front size;
- the full episode outcome vector: placed/fill, CoM, shake stability,
  priority/soft cleanliness, terminal physical labels, policy time and search
  attempts.

`base`, `base_null`, `multi_axis_shadow`, and `multi_axis_enforce` run three
repeats on five Task B development cases. Any physical effect outside the
pooled control spread in shadow mode is an instrumentation regression. The
enforce arm is not a default switch: adoption requires the full-vector
comparison and cannot be justified by placed/fill alone.
