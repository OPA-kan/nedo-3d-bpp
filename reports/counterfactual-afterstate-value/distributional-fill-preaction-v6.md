# Distributional fill pre-action student v6 — rejected in development

V6 tested the first new representation hypothesis after the powered v5
rejection closed the 116-feature local-geometry family: a physics-free
stamped height grid. Each candidate's oriented commanded box is dropped onto
the shared source-state 4x4 per-container height grid (rest top = highest
cell under the footprint plus oriented height), and the model learns from
the pairwise stamped-grid difference, four grid summaries, and the
action-geometry delta. Immediate score, step, post-settle state, and future
labels remain excluded, so the input is pre-action and label-blind.

## Development result

The corpus is every opened run: the 29 v5 training runs plus the twelve
completed seed-60 runs, 41 runs over 26 streams, 5,338 eligible rows and
1,751 exact pre-action signatures. The protocol is unchanged from v4/v5:
strict group-complement cross-fit over the same 288-policy kNN grid, with
selection requiring all-stream non-regression first.

No policy in the grid was non-regressing across all 26 streams. The
pooled-best policy (33 distance-weighted neighbors, override ratio 0.5)
scores 1191/1751 versus 1121/1751 for action geometry (203 wins, 133
losses, `p=1.6e-4`) but regresses five streams, worst on the structured
variants: `interleave` 48 versus 55 and `reverse-000` 61 versus 66. Its win
fraction of 0.604 is also below the closed family's 0.661, and freezing it
would demand 92 discordant pairs for a powered confirmation.

## Verdict

**Rejected in development; nothing is frozen and no confirmation stream was
spent.** The stamped-grid hypothesis fails the non-regression precondition
that every frozen candidate (v3, v4, v5) satisfied on its corpus, and its
pooled advantage concentrates on permutation streams while actively harming
the structured `interleave`/`reverse-000` orders. A pooled sign test alone
is exactly the kind of evidence this protocol exists to distrust.

Full numbers are in `distributional-fill-preaction-v6-development.json`.
The pre-action branch-direction question stays open with no live candidate.
The next attempt must either explain the structured-stream failures with a
representation that models arrival order, or change the label target; it
must not re-tune this grid.
