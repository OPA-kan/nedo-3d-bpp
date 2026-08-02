# Typed option damage: irreversibility is per type, and soft is a converter

126 real placements over 3 skipped final_holdout datasets, successor states at the official `x_plus` pose.

## Cross-effect matrix

Rows: the type of item **placed**. Columns: the option type **measured**.

| placed \\ measured | priority | soft | rigid | n |
| --- | ---: | ---: | ---: | ---: |
| **priority** | (-1.000) | -0.500 | -1.542 | 24 |
| **soft** | +0.000 | (-1.174) | +0.261 | 23 |
| **rigid** | +0.000 | -0.076 | (+0.025) | 79 |

Parenthesised cells are the diagonal and are **confounded**: placing an
item of type X removes it from the remaining pool of X, so kappa_X falls
mechanically whenever it is multiplicity-capped. Only the off-diagonal
compares operators.

## Irreversibility is false in general and true for one type

**Placing a soft item raises the rigid option count**: mean +0.261 over 23
transitions, up in 10 of them. That is a repeated counterexample to
`s not in K => T_a(s) not in K` for the rigid type. Soft items settle into
gaps and leave flat top surfaces, which is option *creation*, not erosion.
Rigid placements do the same weakly (+0.025 on their own type, 35 increases
over 126 transitions, 27.8%).

**Priority options do not move under non-priority placements at all**:
0.000 mean, 0 increases and 0 decreases over 57 transitions (19 soft, 38
rigid). Only priority placements change kappa_priority, and then by the
mechanical -1.000 of removing the item from its own pool.

So the proposed split `K = K_irreversible ∩ K_recoverable` is supported,
with the assignment measured rather than assumed:

| type | verdict |
| --- | --- |
| `priority` | invariant under other placements; 0/57 moves in either direction |
| `rigid` | **recoverable** - created by soft placements (10/23) and by rigid ones (35/126) |
| `soft` | eroded by everything, 1 increase in 126 |

## The consequence for a priority hard veto is not the expected one

The concern was that a priority viability set might be *recoverable* and so
unsound to veto on. The measurement says something different and more
awkward: kappa_priority **does not respond to ordinary packing at all** in
this data. A veto keyed on it could be sound and still never fire, because
the quantity it watches is constant along the trajectories that matter.

That is a statement about this option-count instrument at this resolution,
not about corridor clearance, which is a continuous quantity and is
tracked separately.

## Soft is a converter, and the direction is now measured

Off-diagonal, a soft placement is the only operator that *adds* options:
+0.261 to rigid while leaving priority untouched. A priority placement is
the most destructive of all, costing -1.542 rigid options and -0.500 soft
options. Soft therefore does not dominate rigid and is not merely
incomparable with it - it trades its own type's option space for the rigid
type's.

## Scope

- 126 transitions from 42 development states; 108 survived settle, 18 did
  not. Failures are kept, because a placement that topples is still a
  placement that changed the container.
- kappa is an integer independent-option count at stride 16 with a cap of
  32 accepted anchors per class-orientation-kind. A move smaller than the
  granularity of that count is invisible to it.
- The first aggregation of this run bucketed by the raw `is_soft` flag,
  which put prioritised soft items in the soft row and imported the
  priority diagonal into it. Rows are keyed by `placed_type` now.
